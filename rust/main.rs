use std::path::Path;

fn run() -> Result<(), String> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if args.is_empty() || args == ["--help"] {
        println!(
            "serve-game PORT SECONDS [--gpw-accounts FILE [--characters ACCOUNT GAME_ROOT]] (GPW login, session and account-owned characters)"
        );
        println!(
            "launch-game [--startup-diagnostics] [--gpw-accounts FILE [--characters ACCOUNT GAME_ROOT]] (use Start-GpwOffline.ps1)"
        );
        println!("register-account FILE ACCOUNT PUBLIC_XY_HEX (GPW P-256 public verification key)");
        println!("identify-build GAME_ROOT (read-only executable fingerprints)");
        println!(
            "init-character-profile FILE ACCOUNT GAME_ROOT (create GPW's own Ultimate Freyna Lv2 profile)"
        );
        println!(
            "--saved-characters ACCOUNT GAME_ROOT loads the GPW character journal only; --characters allows one-time import of the approved snapshot"
        );
        println!(
            "GPW Offline by 狗屁王_official\nUnofficial local service; no game compatibility claim.\nserve JOURNAL PORT SECONDS [--allow-provisioning]\ninspect-frames FILE\ninspect-chain FILE\nBinds 127.0.0.1 only. GPW.rust/1 is a local developer API, not GPW.local/1 or V15.\nV15 integerEncoding=UNKNOWN; world_runtime_implemented=false."
        );
        println!(
            "selected-level A|B|GPW\nserve-profile A|B|GPW PORT SECONDS (GPW-only, not a game endpoint)"
        );
        println!(
            "registered-route (inspect installed Windows launch route; never starts Steam or the game)"
        );
        return Ok(());
    }
    if let [cmd, file, account, value] = args.as_slice() {
        if cmd == "init-character-profile" {
            auth::init_character_profile(Path::new(file), account, Path::new(value))?;
            println!("character_profile_ready\t{account}");
            return Ok(());
        }
        if cmd == "register-account" {
            auth::register(Path::new(file), account, value)?;
            println!("account_registered\t{account}");
            return Ok(());
        }
    }
    if let [cmd, port, seconds, options @ ..] = args.as_slice() {
        if cmd == "serve-game" {
            let port = port.parse::<u16>().map_err(|_| "invalid_port")?;
            let seconds = seconds.parse::<u64>().map_err(|_| "invalid_seconds")?;
            if !(1..=3600).contains(&seconds) {
                return Err("invalid_seconds".into());
            }
            let mut listener = game_ingress::Endpoints::bind(port).map_err(|e| e.to_string())?;
            let client = listener.client.local_addr().map_err(|e| e.to_string())?;
            listener.configure(account_config(options)?)?;
            println!(
                "login_endpoint={} server_pid={} client_endpoint={}",
                listener.login.local_addr().map_err(|e| e.to_string())?,
                std::process::id(),
                client
            );
            let (_lifetime, shutdown) = std::sync::mpsc::channel();
            let until = std::time::Instant::now() + std::time::Duration::from_secs(seconds);
            game_ingress::serve(listener, shutdown, Some(until)).map_err(|e| e.to_string())?;
            return Ok(());
        }
    }
    if args[0] == "launch-game" {
        let diagnostic = args.get(1).is_some_and(|v| v == "--startup-diagnostics");
        let options = &args[1 + usize::from(diagnostic)..];
        return launch::game(diagnostic, account_config(options)?);
    }
    if args == ["registered-route"] {
        let windows = std::env::var_os("SystemRoot").ok_or("windows_directory_missing")?;
        let host = Path::new(&windows).join(r"System32\WindowsPowerShell\v1.0\powershell.exe");
        let status = std::process::Command::new(host)
            .args([
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                include_str!("registered-route.ps1"),
            ])
            .status()
            .map_err(|error| error.to_string())?;
        return if status.success() {
            Ok(())
        } else {
            Err("registered_route_unresolved".into())
        };
    }
    if let [command, file] = args.as_slice() {
        match command.as_str() {
            "identify-build" => {
                let build = content::identify(Path::new(file))?;
                println!(
                    "build={build} character_mapping={}",
                    if build == content::TARGET {
                        "known"
                    } else {
                        "unmapped"
                    }
                );
                return Ok(());
            }
            "selected-level" => {
                let profile = gpw_offline_core::snapshot::read_selected_level(file)?;
                println!(
                    "character_id={} template_id={} level={}",
                    profile.character_id, profile.template_id, profile.level
                );
                return Ok(());
            }
            "inspect-frames" => return inspection::frames(Path::new(file)),
            "inspect-chain" => return inspection::chain(Path::new(file)),
            _ => {}
        }
    }
    if !(args.len() == 4 || args.len() == 5 && args[4] == "--allow-provisioning")
        || !(args[0] == "serve"
            || matches!(args[0].as_str(), "serve-profile" | "serve-profile-managed")
                && args.len() == 4)
    {
        return Err("invalid_arguments".into());
    }
    let port: u16 = args[2].parse().map_err(|_| "invalid_port")?;
    let seconds: u64 = args[3].parse().map_err(|_| "invalid_seconds")?;
    if !(1..=3600).contains(&seconds) {
        return Err("invalid_seconds".into());
    }
    if args[0].starts_with("serve-profile") {
        runtime::serve_profile(&args[1], port, seconds, args[0] == "serve-profile-managed")
    } else {
        runtime::serve(Path::new(&args[1]), port, seconds, args.len() == 5)
    }
}
struct AccountConfig<'a> {
    file: &'a Path,
    characters: Option<character::ProfileConfig<'a>>,
}
fn account_config(options: &[String]) -> Result<Option<AccountConfig<'_>>, String> {
    match options {
        [] => Ok(None),
        [flag, file] if flag == "--gpw-accounts" => Ok(Some(AccountConfig {
            file: Path::new(file),
            characters: None,
        })),
        [flag, file, mode, owner, root]
            if flag == "--gpw-accounts"
                && matches!(mode.as_str(), "--characters" | "--saved-characters") =>
        {
            Ok(Some(AccountConfig {
                file: Path::new(file),
                characters: Some(character::ProfileConfig {
                    owner,
                    game_root: Path::new(root),
                    source: if mode == "--characters" {
                        character::ProfileSource::ApprovedSnapshot
                    } else {
                        character::ProfileSource::Saved
                    },
                }),
            }))
        }
        _ => Err("invalid_arguments".into()),
    }
}
fn main() {
    if let Err(e) = run() {
        eprintln!("error\t{e}");
        std::process::exit(2);
    }
}
mod auth;
mod character;
mod content;
mod game_ingress;
mod inspection;
mod launch;
mod login_wire;
mod runtime;
