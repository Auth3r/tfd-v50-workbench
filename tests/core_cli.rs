use std::{
    fs,
    path::PathBuf,
    process::{Command, Output, Stdio},
    time::{Duration, Instant},
};

fn run(args: &[&str]) -> Output {
    let mut child = Command::new(env!("CARGO_BIN_EXE_gpw-offline-core"))
        .args(args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let deadline = Instant::now() + Duration::from_secs(5);
    while child.try_wait().unwrap().is_none() {
        if Instant::now() >= deadline {
            let _ = child.kill();
            let _ = child.wait();
            panic!("core CLI did not exit; no-argument startup must print help, not open a window");
        }
        std::thread::sleep(Duration::from_millis(10));
    }
    child.wait_with_output().unwrap()
}

struct Input(PathBuf);
impl Input {
    fn new(name: &str, bytes: &[u8]) -> Self {
        let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("target/test-data");
        fs::create_dir_all(&dir).unwrap();
        let file = dir.join(format!("cli-{name}-{}", std::process::id()));
        fs::write(&file, bytes).unwrap();
        Self(file)
    }
    fn path(&self) -> &str {
        self.0.to_str().unwrap()
    }
}
impl Drop for Input {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.0);
    }
}

#[test]
fn headless_default_and_help_exit_without_opening_game_or_window() {
    for args in [vec![], vec!["--help"]] {
        let out = run(&args);
        assert!(out.status.success());
        let text = String::from_utf8(out.stdout).unwrap();
        assert!(text.contains("GPW Offline by 狗屁王_official"));
        assert!(text.contains("world_runtime_implemented=false"));
        assert!(!text.contains("training arena"));
    }
    for (arg, extension) in [("--self-test", "json"), ("--screenshot", "png")] {
        assert_eq!(run(&[arg]).status.code(), Some(2));
        let f = Input::new(extension, b"sentinel");
        let report = Input(f.0.with_extension(extension));
        fs::write(&report.0, b"sentinel").unwrap();
        assert_eq!(run(&[arg, report.path()]).status.code(), Some(2));
        assert_eq!(fs::read(&report.0).unwrap(), b"sentinel");
    }
}

#[test]
fn actual_cli_inspects_opaque_bytes_and_refuses_truncated_frames() {
    let f = Input::new("frame", b"\x03\0\0\0\xfd\xff\xff\xff\xff\x7fabc");
    let out = run(&["inspect-frames", f.path()]);
    assert!(out.status.success());
    let text = String::from_utf8(out.stdout).unwrap();
    assert!(text.contains("frames=1 payload_bytes=3 integerEncoding=UNKNOWN"));
    assert!(!text.contains("abc"));
    fs::write(&f.0, b"\x03\0\0\0\xfd\xff\xff\xff\xff\x7fab").unwrap();
    let out = run(&["inspect-frames", f.path()]);
    assert_eq!(out.status.code(), Some(2));
    assert!(out.stdout.is_empty());
    assert!(String::from_utf8(out.stderr).unwrap().contains("Truncated"));
}

#[test]
fn actual_metadata_process_accepts_cause_link_and_rejects_own_notification_id() {
    let good = b"GPW.metadata/1\n0\tClientService\trequest\t12\t1110\t-\n1\tClientService\tresponse\t12\t1110\t-\n2\tClientService\tnotification\t-1\t1120\t12\n3\tClientService\trequest\t13\t1400\t-\n4\tClientService\tresponse\t13\t1400\t-\n";
    let f = Input::new("chain", good);
    let out = run(&["inspect-chain", f.path()]);
    assert!(out.status.success());
    let text = String::from_utf8(out.stdout).unwrap();
    assert!(text.contains("events=5 gameConnected=false world_runtime_implemented=false"));
    assert!(text.contains("completed=2 timed_out=0 cancelled=0"));
    let bad = String::from_utf8(good.to_vec())
        .unwrap()
        .replace("1120\t12", "1120\t-1");
    fs::write(&f.0, bad).unwrap();
    let out = run(&["inspect-chain", f.path()]);
    assert_eq!(out.status.code(), Some(2));
    assert!(out.stdout.is_empty());
    assert!(
        String::from_utf8(out.stderr)
            .unwrap()
            .contains("UnknownRequest")
    );
    // EOF cancels incomplete work; correlation never implies world success.
    fs::write(
        &f.0,
        b"GPW.metadata/1\n0\tClientService\trequest\t12\t1110\t-\n",
    )
    .unwrap();
    let out = run(&["inspect-chain", f.path()]);
    assert!(out.status.success());
    assert!(
        String::from_utf8(out.stdout)
            .unwrap()
            .contains("completed=0 timed_out=0 cancelled=1")
    );
}

#[test]
fn unapproved_metadata_fields_and_oversized_lines_are_rejected() {
    for (name, content) in [
        ("raw", "request\t12\t1110\tAUTH_PAYLOAD".to_string()),
        ("long", format!("GPW.metadata/1\n{}\n", "x".repeat(257))),
        (
            "extra",
            "GPW.metadata/1\n0\tClientService\trequest\t12\t1110\t-\tTOKEN\n".to_string(),
        ),
    ] {
        let f = Input::new(name, content.as_bytes());
        let out = run(&["inspect-chain", f.path()]);
        assert_eq!(out.status.code(), Some(2));
        assert!(out.stdout.is_empty());
        assert!(!String::from_utf8(out.stderr).unwrap().contains("TOKEN"));
    }
}
