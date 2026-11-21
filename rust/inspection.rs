//! Explicit file-only developer diagnostics. Never print opaque payload bytes.
use gpw_offline_core::{
    protocol::FrameReader,
    session::{Service, Session},
};
use std::{
    fs::File,
    io::{BufRead, BufReader, Read},
    path::Path,
};

pub fn frames(path: &Path) -> Result<(), String> {
    let mut file = File::open(path).map_err(|e| e.to_string())?;
    let mut reader = FrameReader::default();
    let mut buffer = [0; 8192];
    let mut count = 0;
    let mut payload_bytes = 0u64;
    loop {
        let n = file.read(&mut buffer).map_err(|e| e.to_string())?;
        if n == 0 {
            break;
        }
        for frame in reader
            .feed(&buffer[..n])
            .map_err(|e| format!("frame:{e:?}"))?
        {
            count += 1;
            payload_bytes += frame.payload.len() as u64;
        }
    }
    reader.finish().map_err(|e| format!("frame:{e:?}"))?;
    println!(
        "scope=OPAQUE_FRAME_INSPECTION frames={count} payload_bytes={payload_bytes} integerEncoding=UNKNOWN gameConnected=false world_runtime_implemented=false"
    );
    Ok(())
}

pub fn chain(path: &Path) -> Result<(), String> {
    let mut input = BufReader::new(File::open(path).map_err(|e| e.to_string())?);
    let mut line = String::new();
    read_line(&mut input, &mut line)?;
    if line.trim_end() != "GPW.metadata/1" {
        return Err("metadata_profile_required".into());
    }
    let mut session = Session::new(0, 30_000, 10_000, 1024).unwrap();
    let mut count = 0;
    while read_line(&mut input, &mut line)? != 0 {
        count += 1;
        let f: Vec<_> = line.trim_end_matches(['\r', '\n']).split('\t').collect();
        if f.len() != 6 {
            return Err(format!("metadata_shape:row={count}"));
        }
        let now: u64 = f[0].parse().map_err(|_| "metadata_time")?;
        let service = match f[1] {
            "LoginService" => Service::Login,
            "ClientService" => Service::Client,
            "GameService" => Service::Game,
            _ => return Err("metadata_service".into()),
        };
        let id: i32 = f[3].parse().map_err(|_| "metadata_id")?;
        let procedure: u16 = f[4].parse().map_err(|_| "metadata_procedure")?;
        let result = match (f[2], f[5]) {
            ("request", "-") => session.begin(now, service, id, procedure),
            ("response", "-") => session.response(now, service, id, procedure),
            ("notification", cause) => session.notification(
                now,
                service,
                procedure,
                cause.parse().map_err(|_| "metadata_cause")?,
            ),
            _ => return Err("metadata_event".into()),
        };
        result.map_err(|e| format!("session:row={count}:{e:?}"))?;
    }
    session.disconnect();
    let counts = session.counts();
    println!(
        "scope=GPW_METADATA_ONLY events={count} gameConnected=false world_runtime_implemented=false bodyState=UNKNOWN completed={} timed_out={} cancelled={}",
        counts.completed, counts.timed_out, counts.cancelled
    );
    Ok(())
}

fn read_line(reader: &mut impl BufRead, line: &mut String) -> Result<usize, String> {
    line.clear();
    let n = reader
        .take(257)
        .read_line(line)
        .map_err(|e| e.to_string())?;
    if n > 256 {
        return Err("metadata_line_limit".into());
    }
    Ok(n)
}
