//! Owned loopback service runtime. No third-party executable or game adapter.
use gpw_offline_core::{Store, read_frame, write_frame};
use std::{
    io::{self, Read, Write},
    net::{Ipv4Addr, TcpListener, TcpStream},
    path::Path,
    sync::atomic::{AtomicBool, Ordering},
    time::{Duration, Instant},
};

pub(crate) struct DeadlineStream<'a> {
    pub(crate) socket: &'a mut TcpStream,
    pub(crate) deadline: Instant,
    pub(crate) stopping: Option<&'a AtomicBool>,
}
impl DeadlineStream<'_> {
    pub(crate) fn remaining(&self) -> io::Result<Duration> {
        if self
            .stopping
            .is_some_and(|stop| stop.load(Ordering::Acquire))
        {
            return Err(io::Error::new(
                io::ErrorKind::ConnectionAborted,
                "service_stopping",
            ));
        }
        let remaining = self.deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Err(io::Error::new(io::ErrorKind::TimedOut, "frame_deadline"));
        }
        Ok(remaining)
    }

    fn transfer(
        &mut self,
        timeout: fn(&TcpStream, Option<Duration>) -> io::Result<()>,
        mut operation: impl FnMut(&mut TcpStream) -> io::Result<usize>,
    ) -> io::Result<usize> {
        if self.stopping.is_none() {
            timeout(self.socket, Some(self.remaining()?))?;
            return operation(self.socket);
        }
        // Managed sockets are nonblocking. A peer cannot extend the manager's lifetime by
        // holding a partial frame or by generating traffic before each idle deadline.
        loop {
            let remaining = self.remaining()?;
            match operation(self.socket) {
                Err(e) if e.kind() == io::ErrorKind::WouldBlock => {
                    std::thread::sleep(remaining.min(Duration::from_millis(10)))
                }
                result => return result,
            }
        }
    }
}
impl Read for DeadlineStream<'_> {
    fn read(&mut self, buffer: &mut [u8]) -> io::Result<usize> {
        self.transfer(TcpStream::set_read_timeout, |socket| socket.read(buffer))
    }
}
impl Write for DeadlineStream<'_> {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        self.transfer(TcpStream::set_write_timeout, |socket| socket.write(bytes))
    }
    fn flush(&mut self) -> io::Result<()> {
        self.remaining()?;
        self.socket.flush()
    }
}

pub fn serve(journal: &Path, port: u16, seconds: u64, provision: bool) -> Result<(), String> {
    let mut store = Store::open(journal)?;
    serve_requests(port, seconds, false, None, |request| {
        store.execute(request, provision)
    })
}

pub fn serve_profile(snapshot: &str, port: u16, seconds: u64, managed: bool) -> Result<(), String> {
    let profile = gpw_offline_core::snapshot::read_selected_level(snapshot)?;
    let stop = managed.then(|| {
        let (tx, rx) = std::sync::mpsc::channel();
        std::thread::spawn(move || {
            let _ = io::stdin().read(&mut [0]);
            let _ = tx.send(());
        });
        rx
    });
    serve_requests(port, seconds, true, stop, |request| {
        let Some(id) = request.strip_prefix("GPW.rust/1\tselected.level\t") else {
            return Err("unsupported_profile_request".into());
        };
        if id.is_empty()
            || id.len() > 64
            || !id
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-')
        {
            return Err("invalid_request_id".into());
        }
        Ok(format!(
            "selected\t{id}\t{}\t{}\t{}",
            profile.character_id, profile.template_id, profile.level
        ))
    })
}

fn serve_requests(
    port: u16,
    seconds: u64,
    trace_peer: bool,
    stop: Option<std::sync::mpsc::Receiver<()>>,
    mut dispatch: impl FnMut(&str) -> Result<String, String>,
) -> Result<(), String> {
    let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, port)).map_err(|e| e.to_string())?;
    listener.set_nonblocking(true).map_err(|e| e.to_string())?;
    println!(
        "ready\t{}",
        listener.local_addr().map_err(|e| e.to_string())?.port()
    );
    io::stdout().flush().map_err(|e| e.to_string())?;
    let deadline = Instant::now() + Duration::from_secs(seconds);
    while Instant::now() < deadline {
        if stop
            .as_ref()
            .is_some_and(|rx| rx.try_recv() != Err(std::sync::mpsc::TryRecvError::Empty))
        {
            break;
        }
        match listener.accept() {
            Ok((mut socket, peer)) => {
                if trace_peer {
                    eprintln!("profile_accept\t{peer}");
                }
                // Windows accepted sockets inherit the listener's nonblocking
                // mode; use blocking I/O with an absolute, non-renewing deadline.
                socket.set_nonblocking(false).map_err(|e| e.to_string())?;
                let mut stream = DeadlineStream {
                    socket: &mut socket,
                    stopping: None,
                    deadline: deadline.min(Instant::now() + Duration::from_secs(2)),
                };
                let response = match read_frame(&mut stream) {
                    Ok(Some(request)) => {
                        // A complete frame received after timeout still cannot
                        // enter a transaction. Disk sync itself is not preempted.
                        if Instant::now() >= stream.deadline {
                            continue;
                        }
                        dispatch(&request).unwrap_or_else(|e| format!("error\t{e}"))
                    }
                    Ok(None) => continue,
                    Err(e) => format!("error\t{e}"),
                };
                let _ = write_frame(&mut stream, &response);
            }
            Err(e) if e.kind() == io::ErrorKind::WouldBlock => {
                std::thread::sleep(Duration::from_millis(5));
            }
            Err(e) => return Err(e.to_string()),
        }
    }
    Ok(())
}
