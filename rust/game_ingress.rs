use crate::{auth, login_wire, runtime::DeadlineStream};
use gpw_offline_core::{
    protocol::v15_static::{
        TransportMode, decode_rpc_header, parse_transport_header, transform_payload,
    },
    session::{Service, Session},
};
use std::{
    io::{self, Read, Write},
    net::{Ipv4Addr, SocketAddr, TcpListener},
    sync::{
        atomic::{AtomicBool, Ordering},
        mpsc::Receiver,
    },
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

// Windows' IPv4 owner table has one DWORD count followed by rows of six DWORDs.
// Match both directions of the client's four-tuple while the accepted socket is open.
#[link(name = "iphlpapi")]
unsafe extern "system" {
    fn GetExtendedTcpTable(
        table: *mut u32,
        size: *mut u32,
        sort: i32,
        family: u32,
        class: u32,
        reserved: u32,
    ) -> u32;
}

fn client_pid(client: SocketAddr, server: SocketAddr) -> Option<u32> {
    let (SocketAddr::V4(client), SocketAddr::V4(server)) = (client, server) else {
        return None;
    };
    let mut size = 0;
    let mut words: Vec<u32> = Vec::new();
    for _ in 0..4 {
        let ptr = if words.is_empty() {
            std::ptr::null_mut()
        } else {
            words.as_mut_ptr()
        };
        // AF_INET, TCP_TABLE_OWNER_PID_ALL. The buffer is DWORD-aligned.
        match unsafe { GetExtendedTcpTable(ptr, &mut size, 0, 2, 5, 0) } {
            122 if size <= 16 * 1024 * 1024 => words.resize((size as usize).div_ceil(4), 0),
            0 => {
                let (&count, rows) = words.split_first()?;
                return rows
                    .chunks_exact(6)
                    .take(count as usize)
                    .find(|row| {
                        row[1].to_ne_bytes() == client.ip().octets()
                            && u16::from_be(row[2] as u16) == client.port()
                            && row[3].to_ne_bytes() == server.ip().octets()
                            && u16::from_be(row[4] as u16) == server.port()
                            && row[5] != 0
                    })
                    .map(|row| row[5]);
            }
            _ => return None,
        }
    }
    None
}

pub fn listen(port: u16) -> io::Result<TcpListener> {
    let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, port))?;
    listener.set_nonblocking(true)?;
    Ok(listener)
}

pub struct Endpoints {
    pub login: TcpListener,
    pub client: TcpListener,
    parameter: Option<[u8; 30]>,
    pub owned_auth: Option<auth::Runtime>,
}

impl Endpoints {
    pub fn configure(&mut self, config: Option<crate::AccountConfig<'_>>) -> Result<(), String> {
        if let Some(config) = config {
            let addr = self.client.local_addr().map_err(|e| e.to_string())?;
            self.owned_auth = Some(auth::Runtime::load(config.file, addr, config.characters)?);
        }
        Ok(())
    }

    pub fn bind(port: u16) -> io::Result<Self> {
        Self::bind_pair(port, 0)
    }

    pub fn bind_pair(port: u16, client_port: u16) -> io::Result<Self> {
        Ok(Self {
            parameter: transport_parameter()?,
            login: listen(port)?,
            client: listen(client_port)?,
            owned_auth: None,
        })
    }
}

// Only explicitly supplied ordinary transport configuration is accepted.
// There is no lookup of platform, launcher or player data.
fn transport_parameter() -> io::Result<Option<[u8; 30]>> {
    let Some(raw) = std::env::var_os("GPW_FRAME_PARAMETER_HEX") else {
        return Ok(None);
    };
    let invalid = || io::Error::new(io::ErrorKind::InvalidInput, "invalid_gpw_frame_parameter");
    let value = raw.to_str().ok_or_else(invalid)?;
    if value.len() != 60 || !value.bytes().all(|c| c.is_ascii_hexdigit()) {
        return Err(invalid());
    }
    let mut bytes = [0; 30];
    for (idx, b) in bytes.iter_mut().enumerate() {
        *b = u8::from_str_radix(&value[idx * 2..idx * 2 + 2], 16).map_err(|_| invalid())?;
    }
    Ok(Some(bytes))
}

fn read_frame(
    input: &mut DeadlineStream<'_>,
    parameter: &[u8],
    prefix: Option<[u8; 4]>,
) -> Result<(TransportMode, Vec<u8>), String> {
    let mut outer = [0_u8; 10];
    let start = if let Some(prefix) = prefix {
        outer[..4].copy_from_slice(&prefix);
        4
    } else {
        0
    };
    input
        .read_exact(&mut outer[start..])
        .map_err(|e| format!("transport_header_{:?}", e.kind()))?;
    let (mode, length) = parse_transport_header(&outer).map_err(|e| format!("transport_{e:?}"))?;
    if mode == TransportMode::Xor && parameter.is_empty() {
        return Err("xor_transport_context_unavailable".into());
    }
    let mut bytes = Vec::new();
    input
        .take(length as u64)
        .read_to_end(&mut bytes)
        .map_err(|e| format!("frame_body_{:?}", e.kind()))?;
    if bytes.len() != length {
        return Err("frame_body_truncated".into());
    }
    if Instant::now() >= input.deadline {
        return Err("frame_body_TimedOut".into());
    }
    if mode == TransportMode::Xor {
        bytes =
            transform_payload(&bytes, mode, parameter).map_err(|e| format!("transport_{e:?}"))?;
    }
    Ok((mode, bytes))
}

fn handle_connection(
    connection: u64,
    service: Service,
    mut socket: std::net::TcpStream,
    peer: SocketAddr,
    until: Option<Instant>,
    endpoints: &Endpoints,
    stopping: &AtomicBool,
) -> io::Result<()> {
    let server = socket.local_addr()?;
    let owner = client_pid(peer, server).map_or("unknown".into(), |pid| pid.to_string());
    let time = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis();
    eprintln!(
        "transport_accept id={connection} unix_ms={time} peer={peer} peer_pid={owner} local={server} server_pid={} service={service:?}",
        std::process::id()
    );
    socket.set_nonblocking(true)?;
    let started = Instant::now();
    let limit = started + Duration::from_secs(2);
    let mut input = DeadlineStream {
        socket: &mut socket,
        stopping: Some(stopping),
        deadline: until.map_or(limit, |t| t.min(limit)),
    };
    let mut prefix = None;
    if let Some(runtime) = &endpoints.owned_auth {
        let mut magic = [0u8; 4];
        input.read_exact(&mut magic)?;
        if &magic == b"GPWR" {
            eprintln!("gpw_auth_accept conn={connection} service={service:?}");
            return auth::serve_peer(runtime, connection, service, &mut input, until);
        }
        prefix = Some(magic);
    }
    let parameter = endpoints.parameter.as_slice().as_flattened();
    eprintln!(
        "game_accept id={connection} unix_ms={time} peer={peer} peer_pid={owner} local={server} server_pid={} service={service:?}",
        std::process::id()
    );
    let mut session = Session::new(0, 30_000, 10_000, 1024)
        .map_err(|e| io::Error::other(format!("session_policy_{e:?}")))?;
    let mut explicit_handshake = None;
    let mut sent = 0;
    let result = (|| -> Result<(), String> {
        loop {
            let (mode, bytes) = read_frame(&mut input, parameter, prefix.take())?;
            let rpc = decode_rpc_header(&bytes).map_err(|e| format!("rpc_header_{e:?}"))?;
            let id = rpc.header.request_id;
            let procedure = rpc.header.procedure_id;
            if id < 0 {
                return Err("non_request_envelope".into());
            }
            if procedure == 30001 && explicit_handshake.is_some() {
                return Err("duplicate_handshake".into());
            }
            if explicit_handshake == Some(id) || session.state(service, id).is_some() {
                return Err("request_IdAlreadyUsed".into());
            }
            if procedure == 30001 {
                login_wire::handshake(rpc.body)?;
                if Instant::now() >= input.deadline {
                    return Err("handshake_TimedOut".into());
                }
                explicit_handshake = Some(id);
                eprintln!(
                    "handshake_accepted conn={connection} service={service:?} id={id} mode={mode:?} response_bytes=0"
                );
                continue;
            }
            let tick = || started.elapsed().as_millis() as u64;
            match (service, procedure) {
                (Service::Login, 1) => {
                    if explicit_handshake.is_none() {
                        return Err("request_before_transport_handshake".into());
                    }
                    session
                        .begin(tick(), service, id, 1)
                        .map_err(|e| format!("request_{e:?}"))?;
                    login_wire::login_request(rpc.body)?;
                    if Instant::now() >= input.deadline {
                        return Err("login_request_TimedOut".into());
                    }
                    eprintln!(
                        "login_request_validated conn={connection} service=Login id={id} procedure=1"
                    );
                    return Err("login_authentication_provider_unavailable".into());
                }
                (Service::Client, 1003) => {
                    session
                        .begin(tick(), service, id, 1003)
                        .map_err(|e| format!("request_{e:?}"))?;
                    login_wire::client_login(rpc.body)?;
                    // GPW has issued zero game sessions. This result applies only
                    // to this local service. No presented token is used or retained.
                    let reply = login_wire::missing_client_session(id, mode, parameter)?;
                    let mut pending = &reply[..];
                    while !pending.is_empty() {
                        let n = input
                            .write(pending)
                            .map_err(|e| format!("reply_{:?}", e.kind()))?;
                        if n == 0 {
                            return Err("reply_WriteZero".into());
                        }
                        sent += n;
                        pending = &pending[n..];
                    }
                    session
                        .response(tick(), service, id, 1003)
                        .map_err(|e| format!("response_{e:?}"))?;
                    eprintln!(
                        "client_session_missing conn={connection} service=Client id={id} procedure=1003 result=8 response_bytes={}",
                        reply.len()
                    );
                }
                _ => return Err("unhandled_service_procedure".into()),
            }
        }
    })();
    session.disconnect();
    if let Err(reason) = result {
        eprintln!(
            "connection_closed conn={connection} reason={reason} cancelled={} response_bytes={sent}",
            session.counts().cancelled
        );
    }
    Ok(())
}

struct StopWorkers<'a>(&'a AtomicBool);
impl Drop for StopWorkers<'_> {
    fn drop(&mut self) {
        self.0.store(true, Ordering::Release);
    }
}

pub fn serve(endpoints: Endpoints, stop: Receiver<()>, until: Option<Instant>) -> io::Result<u64> {
    let endpoints = &endpoints;
    let stopping = &AtomicBool::new(false);
    let mut accepted = 0;
    std::thread::scope(|scope| -> io::Result<()> {
        let _stop_before_join = StopWorkers(stopping);
        let mut workers: Vec<std::thread::ScopedJoinHandle<'_, ()>> = Vec::new();
        while until.is_none_or(|t| Instant::now() < t) {
            if stop.try_recv() != Err(std::sync::mpsc::TryRecvError::Empty) {
                break;
            }
            workers.retain(|worker| !worker.is_finished());
            for (listener, service) in [
                (&endpoints.login, Service::Login),
                (&endpoints.client, Service::Client),
            ] {
                if workers.len() >= 16 {
                    break;
                }
                match listener.accept() {
                    Ok((socket, peer)) => {
                        accepted += 1;
                        let connection = accepted;
                        let worker = scope.spawn(move || {
                            if let Err(e) = handle_connection(
                                connection, service, socket, peer, until, endpoints, stopping,
                            ) {
                                eprintln!(
                                    "connection_failed conn={connection} reason={:?}",
                                    e.kind()
                                );
                            }
                        });
                        workers.push(worker);
                    }
                    Err(e) if e.kind() == io::ErrorKind::WouldBlock => {}
                    Err(e) => return Err(e),
                }
            }
            if stop.recv_timeout(Duration::from_millis(5))
                != Err(std::sync::mpsc::RecvTimeoutError::Timeout)
            {
                break;
            }
        }
        Ok(())
    })?;
    eprintln!("game_listener_stopped accepted={accepted}");
    Ok(accepted)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{process::Command, thread, time::Instant};

    #[test]
    fn manager_stop_closes_live_gpw_connection_before_joining() {
        let mut endpoints = Endpoints::bind(0).unwrap();
        let address = endpoints.client.local_addr().unwrap();
        let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("target/test-data");
        std::fs::create_dir_all(&dir).unwrap();
        let registry = dir.join(format!("shutdown-{}.txt", std::process::id()));
        // Public generator point on P-256. No private signing key is needed for this read.
        std::fs::write(
            &registry,
            concat!(
                "GPW.accounts/1\nfixture\t",
                "6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296",
                "4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5\n"
            ),
        )
        .unwrap();
        endpoints
            .configure(Some(crate::AccountConfig {
                file: &registry,
                characters: None,
            }))
            .unwrap();
        std::fs::remove_file(registry).unwrap();
        let (stop, rx) = std::sync::mpsc::channel();
        let (done, finished) = std::sync::mpsc::channel();
        let service =
            thread::spawn(move || done.send(serve(endpoints, rx, None).unwrap()).unwrap());
        let mut client = std::net::TcpStream::connect(address).unwrap();
        client
            .set_read_timeout(Some(Duration::from_secs(3)))
            .unwrap();
        gpw_offline_core::write_frame(&mut client, "GPW.auth/1\t1\tidentity").unwrap();
        assert_eq!(
            gpw_offline_core::read_frame(&mut client)
                .unwrap()
                .as_deref(),
            Some("GPW.auth/1\t1\terror\tsession_invalid")
        );
        stop.send(()).unwrap();
        let outcome = finished.recv_timeout(Duration::from_secs(2));
        drop(client);
        service.join().unwrap();
        assert_eq!(
            outcome,
            Ok(1),
            "service shutdown waited for the client to close"
        );
    }

    #[test]
    fn windows_reports_the_connecting_child_for_the_accepted_tuple() {
        let listener = listen(0).unwrap();
        let endpoint = listener.local_addr().unwrap();
        let script = r#"$ErrorActionPreference='Stop'
$c=[Net.Sockets.TcpClient]::new()
try {
    $c.Connect('127.0.0.1',[int]$env:GPW_TEST_PORT)
    $c.ReceiveTimeout=5000
    if($c.GetStream().ReadByte() -ne -1){exit 3}
} finally {$c.Dispose()}"#;
        let mut peer = Command::new("powershell.exe")
            .args(["-NoProfile", "-NonInteractive", "-Command", script])
            .env("GPW_TEST_PORT", endpoint.port().to_string())
            .spawn()
            .unwrap();
        let until = Instant::now() + Duration::from_secs(8);
        let (socket, remote) = loop {
            match listener.accept() {
                Ok(connection) => break connection,
                Err(e) if e.kind() == io::ErrorKind::WouldBlock && Instant::now() < until => {
                    thread::sleep(Duration::from_millis(5));
                }
                Err(e) => {
                    let _ = peer.kill();
                    let _ = peer.wait();
                    panic!("{e}");
                }
            }
        };
        let observed = client_pid(remote, endpoint);
        let child_pid = peer.id();
        drop(socket);
        assert!(peer.wait().unwrap().success());
        assert_eq!(observed, Some(child_pid));
        assert_ne!(child_pid, std::process::id());
    }
}
