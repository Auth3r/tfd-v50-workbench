//! Drive the release/debug binary with a separate .NET client and ephemeral signing keys.
#[test]
fn local_identity_and_session_lifecycle_across_real_tcp_and_process_restart() {
    let mut client = std::process::Command::new("pwsh.exe");
    client
        .args(["-NoLogo", "-NoProfile", "-NonInteractive", "-File"])
        .arg(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/tests/auth_runtime.ps1"
        ))
        .arg("-Binary")
        .arg(env!("CARGO_BIN_EXE_gpw-offline-core"));
    if let Some(root) = std::env::var_os("GPW_TEST_CHARACTER_ROOT") {
        client.arg("-CharacterRoot").arg(root);
        if let Some(reference) = std::env::var_os("GPW_TEST_REFERENCE_ROOT") {
            client.arg("-ReferenceRoot").arg(reference);
        }
    }
    let result = client
        .output()
        .expect("project PowerShell 7 runtime required for the independent client");
    println!("{}", String::from_utf8_lossy(&result.stdout));
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
}
