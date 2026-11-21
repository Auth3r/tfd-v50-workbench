use gpw_offline_core::{Store, read_frame, write_frame};
use std::{
    fs,
    io::{BufRead, BufReader, Write},
    net::TcpStream,
    path::PathBuf,
    process::{Child, Command, Stdio},
    time::{Duration, Instant},
};

struct Workspace(PathBuf);
impl Workspace {
    fn new(name: &str) -> Self {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("target/test-data")
            .join(format!(
                "{name}-{}-{}",
                std::process::id(),
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_nanos()
            ));
        fs::create_dir_all(&root).unwrap();
        Self(root)
    }
    fn journal(&self) -> PathBuf {
        self.0.join("equipment.gpwr")
    }
}
impl Drop for Workspace {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
struct Server {
    child: Child,
    port: u16,
}
impl Server {
    fn start(w: &Workspace, provision: bool) -> Self {
        Self::start_for(w, provision, "30")
    }
    fn start_for(w: &Workspace, provision: bool, seconds: &str) -> Self {
        let mut command = Command::new(env!("CARGO_BIN_EXE_gpw-offline-core"));
        command.arg("serve").arg(w.journal()).args(["0", seconds]);
        if provision {
            command.arg("--allow-provisioning");
        }
        let mut child = command
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        let mut ready = String::new();
        BufReader::new(child.stdout.take().unwrap())
            .read_line(&mut ready)
            .unwrap();
        let port = ready
            .trim()
            .strip_prefix("ready\t")
            .expect("server must start")
            .parse()
            .unwrap();
        Self { child, port }
    }
    fn request(&self, text: &str) -> String {
        request(self.port, text)
    }
}

#[test]
fn slow_partial_frame_cannot_extend_runtime_or_commit_after_deadline() {
    let w = Workspace::new("deadline");
    let mut server = Server::start_for(&w, false, "1");
    let mut socket = TcpStream::connect(("127.0.0.1", server.port)).unwrap();
    socket
        .set_write_timeout(Some(Duration::from_millis(200)))
        .unwrap();
    let mut wire = Vec::new();
    write_frame(
        &mut wire,
        &format!("GPW.rust/1\tcreate\t{}\t2\t2", "a".repeat(64)),
    )
    .unwrap();
    let mut bytes = wire.into_iter();
    let start = Instant::now();
    let status = loop {
        if let Some(status) = server.child.try_wait().unwrap() {
            break status;
        }
        assert!(
            start.elapsed() < Duration::from_secs(3),
            "slow client extended the runtime deadline"
        );
        if let Some(byte) = bytes.next() {
            let _ = socket.write_all(&[byte]);
        }
        std::thread::sleep(Duration::from_millis(50));
    };
    assert!(status.success());
    drop(socket);
    drop(server);
    assert!(
        fs::read(w.journal()).unwrap().is_empty(),
        "partial request must never commit"
    );
}
impl Drop for Server {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}
fn request(port: u16, text: &str) -> String {
    let mut socket = TcpStream::connect(("127.0.0.1", port)).unwrap();
    socket
        .set_read_timeout(Some(Duration::from_secs(5)))
        .unwrap();
    write_frame(&mut socket, &format!("GPW.rust/1\t{text}")).unwrap();
    read_frame(&mut socket).unwrap().unwrap()
}

#[test]
fn actual_process_transfer_retry_restart_and_return() {
    let w = Workspace::new("restart");
    {
        let server = Server::start(&w, true);
        assert_eq!(server.request("create\talice\t2\t2"), "ok\t0");
        assert_eq!(server.request("provision\talice\t0\tgun\t0"), "ok\t1");
        assert_eq!(
            server.request("move\talice\t1\top1\twarehouse\tgun"),
            "ok\t2"
        );
        assert_eq!(server.request("read\talice"), "ok\t2\tgun:warehouse:0");
    }
    let before = fs::read(w.journal()).unwrap();
    let server = Server::start(&w, true);
    assert_eq!(
        server.request("move\talice\t1\top1\twarehouse\tgun"),
        "ok\t2"
    );
    // Windows enforces the live server's exclusive journal lock for reads too.
    drop(server);
    assert_eq!(fs::read(w.journal()).unwrap(), before);
    let server = Server::start(&w, true);
    assert_eq!(
        server.request("move\talice\t2\top2\tinventory\tgun"),
        "ok\t3"
    );
    assert_eq!(server.request("read\talice"), "ok\t3\tgun:inventory:0");
    assert_eq!(
        server.request("move\talice\t1\top1\tinventory\tgun"),
        "error\toperation_uid_conflict"
    );
}
#[test]
fn rejected_batches_leave_disk_and_equipment_unchanged() {
    let w = Workspace::new("reject");
    let server = Server::start(&w, true);
    assert_eq!(server.request("create\ta\t3\t1"), "ok\t0");
    assert_eq!(server.request("create\tb\t2\t2"), "ok\t0");
    for (rev, item, equipped) in [(0, "one", 0), (1, "two", 0), (2, "worn", 1)] {
        assert_eq!(
            server.request(&format!("provision\ta\t{rev}\t{item}\t{equipped}")),
            format!("ok\t{}", rev + 1)
        );
    }
    drop(server);
    let before = fs::read(w.journal()).unwrap();
    let server = Server::start(&w, true);
    for (cmd, error) in [
        ("move\ta\t3\tx\twarehouse\tone,two", "destination_full"),
        ("move\ta\t3\tx\twarehouse\tone,missing", "item_not_owned"),
        ("move\ta\t3\tx\twarehouse\tworn", "equipped_item"),
        ("move\tb\t0\tx\twarehouse\tone", "item_not_owned"),
        ("move\ta\t0\tx\twarehouse\tone", "revision_conflict"),
        ("move\ta\t3\tx\twarehouse\tone,one", "invalid_batch"),
        ("provision\tb\t0\tone\t0", "duplicate_item_uid"),
        ("world.reserve", "world_runtime_unimplemented"),
    ] {
        assert_eq!(server.request(cmd), format!("error\t{error}"));
    }
    assert_eq!(
        server.request("read\ta"),
        "ok\t3\tone:inventory:0,two:inventory:0,worn:inventory:1"
    );
    drop(server);
    assert_eq!(fs::read(w.journal()).unwrap(), before);
}
#[test]
fn competing_writers_cannot_lose_updates() {
    let w = Workspace::new("concurrency");
    let server = Server::start(&w, true);
    assert_eq!(server.request("create\ta\t2\t2"), "ok\t0");
    assert_eq!(server.request("provision\ta\t0\tone\t0"), "ok\t1");
    assert_eq!(server.request("provision\ta\t1\ttwo\t0"), "ok\t2");
    let threads: Vec<_> = ["one", "two"]
        .into_iter()
        .map(|id| {
            let port = server.port;
            std::thread::spawn(move || request(port, &format!("move\ta\t2\t{id}\twarehouse\t{id}")))
        })
        .collect();
    let mut replies: Vec<_> = threads.into_iter().map(|t| t.join().unwrap()).collect();
    replies.sort();
    assert_eq!(replies, ["error\trevision_conflict", "ok\t3"]);
    let state = server.request("read\ta");
    assert_eq!(state.matches(":warehouse:0").count(), 1);
    assert_eq!(state.matches(":inventory:0").count(), 1);
}
#[test]
fn exclusive_store_and_corruption_fail_closed() {
    let w = Workspace::new("corrupt");
    let mut store = Store::open(&w.journal()).unwrap();
    store.execute("GPW.rust/1\tcreate\ta\t2\t2", false).unwrap();
    assert!(Store::open(&w.journal()).is_err());
    drop(store);
    let intact = fs::read(w.journal()).unwrap();
    let mut corrupt = intact.clone();
    corrupt[10] ^= 1;
    fs::write(w.journal(), &corrupt).unwrap();
    assert!(Store::open(&w.journal()).is_err());
    assert_eq!(fs::read(w.journal()).unwrap(), corrupt);
    fs::write(w.journal(), &intact[..intact.len() - 1]).unwrap();
    assert!(Store::open(&w.journal()).is_err());
}
#[test]
fn provisioning_is_explicit_and_bad_frames_do_not_kill_service() {
    let w = Workspace::new("framing");
    let server = Server::start(&w, false);
    assert_eq!(server.request("create\ta\t2\t2"), "ok\t0");
    assert_eq!(
        server.request("provision\ta\t0\tone\t0"),
        "error\tprovisioning_disabled"
    );
    for header in [*b"NOPE\x01\0\0\0", *b"GPWR\xff\xff\xff\xff"] {
        let mut socket = TcpStream::connect(("127.0.0.1", server.port)).unwrap();
        socket
            .set_read_timeout(Some(Duration::from_secs(5)))
            .unwrap();
        socket.write_all(&header).unwrap();
        assert!(
            read_frame(&mut socket)
                .unwrap()
                .unwrap()
                .starts_with("error\t")
        );
    }
    let mut bytes = Vec::new();
    write_frame(&mut bytes, "GPW.rust/1\tread\ta").unwrap();
    let mut socket = TcpStream::connect(("127.0.0.1", server.port)).unwrap();
    socket
        .set_read_timeout(Some(Duration::from_secs(5)))
        .unwrap();
    for chunk in bytes.chunks(2) {
        socket.write_all(chunk).unwrap();
        std::thread::sleep(Duration::from_millis(10));
    }
    assert_eq!(read_frame(&mut socket).unwrap().unwrap(), "ok\t0\t");
    let mut invalid = &b"GPWR\x02\0\0\0\xff\xff"[..];
    assert!(read_frame(&mut invalid).is_err());
    let mut truncated = &b"GPWR\x02\0\0\0x"[..];
    assert!(read_frame(&mut truncated).is_err());
}
