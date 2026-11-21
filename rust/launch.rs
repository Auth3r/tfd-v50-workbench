use std::{
    io::{BufRead, BufReader},
    path::Path,
    process::{Child, Command, Stdio},
    thread,
    time::Duration,
};

struct Service(Child);
impl Drop for Service {
    fn drop(&mut self) {
        drop(self.0.stdin.take());
        if let Ok(status) = self.0.wait() {
            println!("profile_stopped\t{}\t{status}", self.0.id());
        }
    }
}

fn start_profile_service() -> Result<Service, String> {
    let mut service = Service(
        Command::new(std::env::current_exe().map_err(|e| e.to_string())?)
            .args(["serve-profile-managed", "GPW", "0", "3600"])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .spawn()
            .map_err(|e| e.to_string())?,
    );
    let mut ready = String::new();
    BufReader::new(service.0.stdout.take().ok_or("profile_stdout_missing")?)
        .read_line(&mut ready)
        .map_err(|e| e.to_string())?;
    let port = ready
        .trim_end()
        .strip_prefix("ready\t")
        .and_then(|value| value.parse::<u16>().ok())
        .filter(|port| *port != 0)
        .ok_or("profile_not_ready")?;
    println!(
        "manager={} profile={} listen=127.0.0.1:{port}",
        std::process::id(),
        service.0.id()
    );
    Ok(service)
}

pub fn game(
    startup_diagnostics: bool,
    config: Option<crate::AccountConfig<'_>>,
) -> Result<(), String> {
    let dir = Path::new(r"E:\第二后裔\The First Descendant");
    let root = dir.join("TheFirstDescendant.exe");
    let shipping = dir.join(r"M1\Binaries\Win64\M1-Win64-Shipping.exe");
    if crate::content::identify(dir)? != crate::content::TARGET {
        return Err("game_build_mismatch".into());
    }
    let windows = std::env::var_os("SystemRoot").ok_or("windows_directory_missing")?;
    let check = Command::new(Path::new(&windows).join(r"System32\WindowsPowerShell\v1.0\powershell.exe"))
        .env("GPW_ROOT_IMAGE", &root)
        .env("GPW_SHIP_IMAGE", &shipping)
        .args(["-NoProfile","-NonInteractive","-Command",r#"
$ErrorActionPreference='Stop'
$env:PSModulePath=Join-Path $PSHOME 'Modules'
if(Get-Process -Name steam,steamwebhelper,TFD-Offline,TheFirstDescendant,M1-Win64-Shipping -ErrorAction SilentlyContinue){throw 'conflicting_runtime_active'}
$id=[guid]::Parse($env:GPW_FIREWALL_RUN)
if(Get-NetFirewallProfile -PolicyStore ActiveStore | Where-Object { $_.Enabled -ne 'True' -or $_.AllowLocalFirewallRules -eq 'False' }){throw 'firewall_profile_unavailable'}
$images=@($env:GPW_ROOT_IMAGE,$env:GPW_SHIP_IMAGE)
for($i=0;$i -lt 2;$i++){
    $r=Get-NetFirewallRule -PolicyStore ActiveStore -Name "GPW-$id-$i" -ErrorAction Stop
    if($r.Enabled -ne 'True' -or $r.Direction -ne 'Outbound' -or $r.Action -ne 'Block' -or $r.Profile -ne 'Any' -or ($r | Get-NetFirewallApplicationFilter).Program -ne $images[$i]){throw 'offline_rule_mismatch'}
    $p=[int]$env:GPW_GAME_PORT
    if($p -lt 1 -or $p -gt 65534 -or $r.Description -notmatch ('^GPW ports='+$p+','+($p+1)+' filters=(\d+,){9}\d+$')){throw 'port_isolation_missing'}
    $ranges=@(($r | Get-NetFirewallAddressFilter).RemoteAddress)
    if($ranges -notcontains '0.0.0.0-126.255.255.255' -or ($ranges -notcontains '128.0.0.0-255.255.255.255' -and $ranges -notcontains '128.0.0.0/1') -or $ranges -notcontains '::2-ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff'){throw "offline_address_mismatch: $ranges"}
}
exit 0
"#]).status().map_err(|error| error.to_string())?;
    if !check.success() {
        return Err("launch_preflight_failed".into());
    }
    let port = std::env::var("GPW_GAME_PORT")
        .ok()
        .and_then(|v| v.parse::<u16>().ok())
        .filter(|p| *p != 0)
        .ok_or("missing_isolated_game_port")?;
    let client_port = port.checked_add(1).ok_or("invalid_isolated_port_pair")?;
    let mut listener =
        crate::game_ingress::Endpoints::bind_pair(port, client_port).map_err(|e| e.to_string())?;
    let standalone_profile = config.is_none();
    let source = if standalone_profile || config.as_ref().is_some_and(|c| c.characters.is_some()) {
        "GPW"
    } else {
        "unassigned"
    };
    listener.configure(config)?;
    let mut service = if standalone_profile {
        Some(start_profile_service()?)
    } else {
        println!(
            "manager={} client_endpoint={}",
            std::process::id(),
            listener.client.local_addr().map_err(|e| e.to_string())?
        );
        None
    };
    let addr = listener.login.local_addr().map_err(|e| e.to_string())?;
    let (stop, shutdown) = std::sync::mpsc::channel();
    let observer = thread::spawn(move || crate::game_ingress::serve(listener, shutdown, None));
    println!(
        "game_endpoint={} server_pid={} profile_source={source}",
        addr,
        std::process::id()
    );
    let run = (|| -> Result<(), String> {
        let mut command = Command::new(&root);
        command.args(["-LoginIP=127.0.0.1", &format!("-LoginPort={}", addr.port())]);
        if startup_diagnostics {
            command.args(["-windowed", "-ResX=1280", "-ResY=720", "-stdout"]);
        }
        let mut game = command
            .current_dir(dir)
            .spawn()
            .map_err(|error| error.to_string())?;
        println!("root_started\t{}\t{}", game.id(), root.display());
        loop {
            if let Some(status) = game.try_wait().map_err(|error| error.to_string())? {
                println!("root_exited\t{}\t{status}", game.id());
                let tail = Command::new(Path::new(&windows).join(r"System32\WindowsPowerShell\v1.0\powershell.exe"))
                    .env("GPW_SHIP_IMAGE", &shipping)
                    .env("GPW_PARENT_PID", game.id().to_string())
                    .args(["-NoProfile","-NonInteractive","-Command",r#"
$ErrorActionPreference='Stop'
$env:PSModulePath=Join-Path $PSHOME 'Modules'
Get-CimInstance Win32_Process -Filter ("ParentProcessId="+$env:GPW_PARENT_PID+" AND Name='M1-Win64-Shipping.exe'") |
    Where-Object ExecutablePath -eq $env:GPW_SHIP_IMAGE | ForEach-Object {
        $p=Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue
        if($p -and $p.Path -eq $env:GPW_SHIP_IMAGE){$p.WaitForExit()}
    }
"#]).status().map_err(|e| e.to_string())?;
                if !tail.success() {
                    return Err("shipping_exit_observation_failed".into());
                }
                return if status.success() {
                    Ok(())
                } else {
                    Err("game_root_exited_unsuccessfully".into())
                };
            }
            if let Some(profile) = service.as_mut()
                && let Some(status) = profile.0.try_wait().map_err(|error| error.to_string())?
            {
                return Err(format!("profile_ended_before_root: {status}"));
            }
            if observer.is_finished() {
                return Err("game_listener_ended".into());
            }
            thread::sleep(Duration::from_millis(100));
        }
    })();
    drop(stop);
    let accepted = observer
        .join()
        .map_err(|_| "game_listener_panicked")?
        .map_err(|e| e.to_string())?;
    run?;
    if accepted == 0 {
        Err("game_endpoint_received_no_connections".into())
    } else {
        Err("game_business_session_unverified".into())
    }
}
