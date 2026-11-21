use std::{
    fs,
    io::{BufRead, BufReader, Write},
    net::{Shutdown, TcpStream},
    path::PathBuf,
    process::{Command, Stdio},
};

#[test]
fn short_client_prefix_keeps_transport_attribution_without_a_business_request() {
    let dir =
        PathBuf::from(std::env::var_os("CARGO_TARGET_DIR").unwrap_or_else(|| "target".into()))
            .join("test-data");
    fs::create_dir_all(&dir).unwrap();
    let registry = dir.join(format!("ingress-{}.txt", std::process::id()));
    // Public test fixture used only to enable the multiplexed account endpoint.
    fs::write(
        &registry,
        concat!(
            "GPW.accounts/1\nfixture\t",
            "6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296",
            "4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5\n"
        ),
    )
    .unwrap();
    let mut server = Command::new(env!("CARGO_BIN_EXE_gpw-offline-core"))
        .args(["serve-game", "0", "3", "--gpw-accounts"])
        .arg(&registry)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let mut ready = String::new();
    BufReader::new(server.stdout.take().unwrap())
        .read_line(&mut ready)
        .unwrap();
    let addr = ready
        .split_whitespace()
        .find_map(|s| s.strip_prefix("client_endpoint="))
        .unwrap();
    let mut peer = TcpStream::connect(addr).unwrap();
    peer.write_all(b"G").unwrap();
    peer.shutdown(Shutdown::Write).unwrap();
    let output = server.wait_with_output().unwrap();
    fs::remove_file(registry).unwrap();
    let log = String::from_utf8(output.stderr).unwrap();
    let accept = log
        .lines()
        .find(|line| line.starts_with("transport_accept id=1 "))
        .expect(&log);
    for field in [
        format!("local={addr}"),
        format!("peer_pid={}", std::process::id()),
        "service=Client".into(),
    ] {
        assert!(accept.split_whitespace().any(|s| s == field), "{log}");
    }
    assert!(
        output.status.success() && log.contains("connection_failed conn=1"),
        "{log}"
    );
    assert!(
        !log.contains("gpw_auth_accept") && !log.contains("handshake_accepted"),
        "{log}"
    );
}
