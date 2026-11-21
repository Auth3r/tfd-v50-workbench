use std::{
    io::{BufRead, BufReader, Read, Write},
    net::{Shutdown, TcpStream},
    process::{Child, Command, Stdio},
    time::Duration,
};

const MASK: &[u8; 30] = b"GPW0123456789abcdefghijklmnopq";

fn service(mask: bool) -> (Child, String, String) {
    let mut cmd = Command::new(env!("CARGO_BIN_EXE_gpw-offline-core"));
    cmd.args(["serve-game", "0", "4"])
        .env_remove("GPW_FRAME_PARAMETER_HEX");
    if mask {
        cmd.env(
            "GPW_FRAME_PARAMETER_HEX",
            MASK.iter().map(|b| format!("{b:02x}")).collect::<String>(),
        );
    }
    let mut child = cmd
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let mut ready = String::new();
    BufReader::new(child.stdout.take().unwrap())
        .read_line(&mut ready)
        .unwrap();
    let mut parts = ready.split_whitespace();
    let login = parts
        .next()
        .unwrap()
        .strip_prefix("login_endpoint=")
        .unwrap();
    let client = parts
        .find_map(|v| v.strip_prefix("client_endpoint="))
        .unwrap();
    (child, login.into(), client.into())
}

fn frame(payload: &[u8], xor: bool) -> Vec<u8> {
    let n = payload.len() as i32;
    let mut out = n.to_le_bytes().to_vec();
    out.extend((-n).to_le_bytes());
    out.extend(if xor { [0xff, 0x7f] } else { [0, 0x80] });
    out.extend(
        payload
            .iter()
            .enumerate()
            .map(|(i, b)| if xor { b ^ MASK[i % 30] } else { *b }),
    );
    out
}

fn connect(endpoint: &str) -> TcpStream {
    let s = TcpStream::connect(endpoint).unwrap();
    s.set_read_timeout(Some(Duration::from_secs(3))).unwrap();
    s
}

fn exchange(endpoint: &str, bytes: &[u8]) -> Vec<u8> {
    let mut s = connect(endpoint);
    s.write_all(bytes).unwrap();
    s.shutdown(Shutdown::Write).unwrap();
    let mut reply = vec![];
    s.read_to_end(&mut reply).unwrap();
    reply
}

fn logs(child: Child) -> String {
    let out = child.wait_with_output().unwrap();
    assert!(out.status.success());
    String::from_utf8(out.stderr).unwrap()
}

fn hello(xor: bool) -> Vec<u8> {
    let mut payload = vec![2, 0xe2, 0xd4, 3, 38];
    payload.extend(b"GPW_fixture_marker\0");
    payload.push(14);
    frame(&payload, xor)
}

// Auth-free, independently laid out ordinary LOGIN_REQUEST, including a region,
// a non-ASCII PARTICIPATE name and a multi-byte revision. No account fixture.
fn request(id: u8) -> Vec<u8> {
    let mut p = vec![id * 2, 2];
    p.extend([0, 7, 0, 0, 0, 0, 1, 0, 0, 2, 0, 0, 3]); // through LoginPlatform
    p.extend([2, 4, b'X', 0]); // one REGION
    p.extend(1.5f32.to_le_bytes());
    p.extend([0, 1, 0, 1, 2]); // CROSS_PLAY
    p.extend([3, 0x2d, 0x4e, 0, 0, 0, 0]); // negative count -2; 中 + terminator
    p.extend([1, 0x80, 1, 0, 0, 0, 0, 0]);
    p
}

#[test]
fn login_handshake_and_structural_validation_reach_the_provider_boundary() {
    let (child, login, client) = service(false);
    for id in [2, 4, 6] {
        let mut s = connect(&login);
        let hello = hello(false);
        s.write_all(&hello[..7]).unwrap();
        s.write_all(&hello[7..]).unwrap();
        s.write_all(&frame(&request(id), false)).unwrap();
        s.shutdown(Shutdown::Write).unwrap();
        let mut reply = vec![];
        s.read_to_end(&mut reply).unwrap();
        assert!(reply.is_empty());
    }
    // Matching the historical byte count is insufficient evidence of a valid request.
    let mut junk = vec![4, 2];
    junk.resize(734, 0);
    assert!(exchange(&login, &[hello(false), frame(&junk, false)].concat()).is_empty());
    let mut invalid = request(2);
    let region_count = 15;
    invalid[region_count] = 1; // signed -1
    assert!(exchange(&login, &[hello(false), frame(&invalid, false)].concat()).is_empty());
    let mut invalid = request(2);
    invalid[region_count + 4..region_count + 8].copy_from_slice(&f32::NAN.to_le_bytes());
    assert!(exchange(&login, &[hello(false), frame(&invalid, false)].concat()).is_empty());
    let mut invalid = request(2);
    invalid[region_count + 8] = 2; // PCEnabled
    assert!(exchange(&login, &[hello(false), frame(&invalid, false)].concat()).is_empty());
    let h = hello(false);
    assert!(exchange(&login, &[h.clone(), h.clone()].concat()).is_empty());
    assert!(exchange(&login, &frame(&request(2), false)).is_empty());
    assert!(exchange(&login, &[h.clone(), frame(&[4, 2, 0xff], false)].concat()).is_empty());
    assert!(exchange(&login, &frame(&[2, 0xe2, 0xd4, 3, 0, 0], false)).is_empty());
    assert!(
        exchange(
            &login,
            &frame(&[2, 0xe2, 0xd4, 3, 4, b'X', 0, 0, 99], false)
        )
        .is_empty()
    );
    assert!(exchange(&login, &[h.clone(), frame(&request(1), false)].concat()).is_empty());
    assert!(exchange(&client, &frame(&[2, 2], false)).is_empty());
    assert!(exchange(&login, &h[..h.len() - 1]).is_empty());
    let mut slow = connect(&login);
    slow.write_all(&h[..h.len() - 1]).unwrap();
    // An incomplete login frame must not block a different service connection.
    assert_eq!(
        exchange(&client, &frame(&[8, 0xd6, 0x0f, 0, 0], false)),
        frame(&[8, 0xd6, 0x0f, 0x10], false)
    );
    assert_eq!(slow.read(&mut [0]).unwrap(), 0);
    // Header alone tests lack of configuration without sending a private body.
    assert!(exchange(&login, &hello(true)[..10]).is_empty());
    let log = logs(child);
    for id in [2, 4, 6] {
        assert!(
            log.contains(&format!("service=Login id={id} procedure=1")),
            "{log}"
        );
    }
    for reason in [
        "duplicate_handshake",
        "request_before_transport_handshake",
        "body_invalid_integer",
        "body_region_count",
        "body_region_latency",
        "body_invalid_bool",
        "empty_handshake_signature",
        "body_trailing_bytes",
        "request_IdAlreadyUsed",
        "unhandled_service_procedure",
        "frame_body_truncated",
        "xor_transport_context_unavailable",
    ] {
        assert!(log.contains(&format!("reason={reason}")), "{log}");
    }
    assert!(
        log.contains("reason=frame_body_TimedOut") || log.contains("reason=frame_body_WouldBlock"),
        "{log}"
    );
    assert_eq!(
        log.matches("reason=login_authentication_provider_unavailable")
            .count(),
        3
    );
    assert!(!log.contains("GPW_fixture"));
}

#[test]
fn client_service_replies_missing_on_ordinary_and_configured_xor_frames() {
    let (child, login, client) = service(true);
    for xor in [true, false] {
        // 1003 may precede explicit 30001 on ClientService. Split writes and
        // read the response while the connection is still open.
        let mut s = connect(&client);
        let query = frame(&[8, 0xd6, 0x0f, 0, 0], xor);
        s.write_all(&query[..11]).unwrap();
        s.write_all(&query[11..]).unwrap();
        let mut reply = [0u8; 14];
        s.read_exact(&mut reply).unwrap();
        // Literal ordinary header and body for request 4, proc 1003, result 8.
        let mut expected = [
            4, 0, 0, 0, 0xfc, 0xff, 0xff, 0xff, 0, 0x80, 8, 0xd6, 0x0f, 0x10,
        ];
        if xor {
            expected[8..10].copy_from_slice(&[0xff, 0x7f]);
            for i in 0..4 {
                expected[10 + i] ^= MASK[i];
            }
        }
        assert_eq!(reply, expected);
        s.write_all(&[hello(xor), query.clone()].concat()).unwrap();
        let mut tail = vec![];
        s.read_to_end(&mut tail).unwrap();
        assert!(tail.is_empty());
        assert!(exchange(&login, &query).is_empty());
        assert!(exchange(&client, &frame(&[2, 0xd6, 0x0f, 4, b'A', 1, 0], xor)).is_empty());
        assert!(exchange(&login, &[hello(xor), frame(&request(6), xor)].concat()).is_empty());
    }
    let log = logs(child);
    assert_eq!(log.matches("client_session_missing ").count(), 2, "{log}");
    assert_eq!(log.matches("reason=request_IdAlreadyUsed").count(), 2);
    assert_eq!(log.matches("reason=body_string_terminator").count(), 2);
    assert_eq!(
        log.matches("reason=login_authentication_provider_unavailable")
            .count(),
        2
    );
    assert!(log.contains("service=Client id=1 mode=Xor response_bytes=0"));
    assert!(!log.contains("GPW_fixture"));
}
