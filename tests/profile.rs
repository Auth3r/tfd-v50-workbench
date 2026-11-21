use gpw_offline_core::{read_frame, write_frame};
use std::{
    io::{BufRead, BufReader},
    net::TcpStream,
    process::{Command, Stdio},
    time::Duration,
};

#[test]
fn sealed_profiles_are_served_by_real_short_lived_processes() {
    for (snapshot, level) in [("A", 1), ("B", 2), ("GPW", 2)] {
        let mut child = Command::new(env!("CARGO_BIN_EXE_gpw-offline-core"))
            .args(["serve-profile", snapshot, "0", "1"])
            .stdout(Stdio::piped())
            .spawn()
            .unwrap();
        let mut ready = String::new();
        BufReader::new(child.stdout.take().unwrap())
            .read_line(&mut ready)
            .unwrap();
        let port = ready
            .trim_end()
            .strip_prefix("ready\t")
            .unwrap()
            .parse::<u16>()
            .unwrap();
        let address = (std::net::Ipv4Addr::LOCALHOST, port);
        for (request, expected) in [
            (
                "GPW.rust/1\tselected.level\tprobe-17",
                format!("selected\tprobe-17\t23\t101000023\t{level}"),
            ),
            (
                "GPW.rust/1\tselected.level\t",
                "error\tinvalid_request_id".into(),
            ),
            (
                "GPW.rust/1\tcreate\ttest\t2\t2",
                "error\tunsupported_profile_request".into(),
            ),
        ] {
            let mut socket = TcpStream::connect(address).unwrap();
            socket
                .set_read_timeout(Some(Duration::from_secs(2)))
                .unwrap();
            write_frame(&mut socket, request).unwrap();
            let reply = read_frame(&mut socket).unwrap().unwrap();
            assert_eq!(reply, expected);
            println!(
                "pid={} port={port} snapshot={snapshot} reply={reply}",
                child.id()
            );
        }
        assert!(child.wait().unwrap().success());
        assert!(TcpStream::connect(address).is_err());
        println!("pid={} exited=0 listenerClosed=true", child.id());
    }
}

#[test]
fn arbitrary_paths_rejected_before_listen() {
    let out = Command::new(env!("CARGO_BIN_EXE_gpw-offline-core"))
        .args(["serve-profile", "../A.sqlite3", "0", "1"])
        .output()
        .unwrap();
    assert_eq!(out.status.code(), Some(2));
    assert!(out.stdout.is_empty());
    assert!(String::from_utf8_lossy(&out.stderr).contains("snapshot_not_approved"));
}
