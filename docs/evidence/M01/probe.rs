// Diagnostic only: pass the supplied request bytes unchanged to the existing
// frame implementation. Labels are input metadata, never decoded procedure IDs.
use gpw_offline_core::{protocol::FrameReader, v50_codec::inspect_frame};

fn main() {
    let input = std::fs::read_to_string(std::env::args().nth(1).expect("TSV path"))
        .expect("read TSV");
    let mut complete = 0;
    let mut rows = 0;
    println!("expected_proc is JSON metadata, not a decoded result");
    for line in input.lines() {
        let fields: Vec<_> = line.split('\t').collect();
        assert_eq!(fields.len(), 4);
        let hex = fields[2];
        assert_eq!(hex.len() % 2, 0);
        let bytes: Vec<_> = (0..hex.len()).step_by(2)
            .map(|i| u8::from_str_radix(&hex[i..i + 2], 16).expect("hex"))
            .collect();
        assert_eq!(bytes.len(), fields[1].parse::<usize>().expect("length"));
        let mut reader = FrameReader::v50();
        let result = reader.feed(&bytes);
        let finish = reader.finish();
        let frame_count = result.as_ref().map(|frames| frames.len()).unwrap_or(0);
        let feed = match &result {
            Ok(_) => "Ok".to_owned(),
            Err(error) => format!("Err({error:?})"),
        };
        let inspection = inspect_frame(&bytes, 0);
        println!("row={} expected_proc={} request_bytes={} response_truncated={} frames={} feed={} finish={:?} inspect={:?} warnings={:?}",
            rows + 1, fields[0], bytes.len(), fields[3], frame_count,
            feed, finish, inspection.state, inspection.warnings);
        if result.is_ok() && finish.is_ok() && frame_count == 1 { complete += 1; }
        rows += 1;
    }
    println!("complete_request_frames={complete}/{rows}");
    println!("No headers were synthesized; no procedure IDs were filled from metadata.");
    if complete != rows || rows != 8 {
        eprintln!("M01 BLOCKED: supplied requests cannot satisfy complete-frame/procedure acceptance as written");
        std::process::exit(1);
    }
}
