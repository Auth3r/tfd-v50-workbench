//! M01b acceptance harness. Real captured bytes are opaque payloads here.
//! Calls the existing Rust FrameReader, without reimplementing its parser.
use gpw_offline_core::protocol::{Frame, FrameError, FrameReader, FrameWarning};

struct Stream {
    id: String,
    bytes: Vec<u8>,
    expected: Vec<(u64, usize)>,
}

fn samples() -> Vec<Stream> {
    let path = std::env::var("M01B_INPUT_TSV").expect("M01B_INPUT_TSV set by reproduce.ps1");
    let contents = std::fs::read_to_string(path).expect("read prepared sample TSV");
    let streams: Vec<_> = contents.lines().map(|line| {
        let fields: Vec<_> = line.split('\t').collect();
        assert_eq!(fields.len(), 5, "sample TSV field count");
        let hex = fields[3];
        assert_eq!(hex.len() % 2, 0);
        let bytes: Vec<u8> = (0..hex.len()).step_by(2)
            .map(|i| u8::from_str_radix(&hex[i..i + 2], 16).expect("hex byte"))
            .collect();
        assert_eq!(bytes.len(), fields[1].parse::<usize>().unwrap());
        let expected: Vec<_> = fields[4].split(';').map(|entry| {
            let values: Vec<_> = entry.split(',').collect();
            assert_eq!(values.len(), 3);
            let off = values[0].parse::<u64>().unwrap();
            let plen = values[1].parse::<usize>().unwrap();
            let total = values[2].parse::<usize>().unwrap();
            assert_eq!(total, 10 + plen, "annotation consistency");
            (off, total)
        }).collect();
        assert_eq!(expected.len(), fields[2].parse::<usize>().unwrap());
        Stream { id: fields[0].into(), bytes, expected }
    }).collect();
    assert_eq!(streams.len(), 9);
    assert_eq!(streams.iter().map(|s| s.expected.len()).sum::<usize>(), 44);
    streams
}

fn boundaries(frames: &[Frame]) -> Vec<(u64, usize)> {
    for (index, frame) in frames.iter().enumerate() {
        assert_eq!(frame.frame_index, index as u64);
        assert_eq!(frame.warning, None, "real sample must pass mirror check");
    }
    frames.iter().map(|f| (f.stream_offset, 10 + f.payload.len())).collect()
}

fn decode_chunks(stream: &Stream, chunk: usize) -> Vec<(u64, usize)> {
    let mut reader = FrameReader::v50();
    let mut frames = Vec::new();
    for bytes in stream.bytes.chunks(chunk) {
        frames.extend(reader.feed(bytes).expect("sample frame feed"));
    }
    reader.finish().expect("complete sample stream");
    boundaries(&frames)
}

#[test]
fn whole_streams_match_all_44_annotated_boundaries() {
    for stream in samples() {
        let actual = decode_chunks(&stream, stream.bytes.len());
        println!("stream={} bytes={} frames={} expected={:?} actual={:?}",
            stream.id, stream.bytes.len(), actual.len(), stream.expected, actual);
        assert_eq!(actual, stream.expected, "{}", stream.id);
    }
    println!("WHOLE_STREAMS=9/9 FRAMES=44/44 MIRROR_WARNINGS=0");
}

#[test]
fn bytewise_and_header_boundary_fragments_preserve_boundaries() {
    let chunks = [1, 7, 9, 10, 11, 17, 509];
    let mut split_cases = 0;
    for stream in samples() {
        for chunk in chunks {
            assert_eq!(decode_chunks(&stream, chunk), stream.expected,
                "{} chunk={chunk}", stream.id);
        }
        let mut cuts = Vec::new();
        for &(off, total) in &stream.expected {
            let off = off as usize;
            cuts.extend([off + 1, off + 3, off + 7, off + 9, off + 10, off + total - 1]);
        }
        cuts.sort_unstable();
        cuts.dedup();
        for cut in cuts.into_iter().filter(|cut| *cut < stream.bytes.len()) {
            let mut reader = FrameReader::v50();
            let mut frames = reader.feed(&stream.bytes[..cut]).unwrap();
            frames.extend(reader.feed(&stream.bytes[cut..]).unwrap());
            reader.finish().unwrap();
            assert_eq!(boundaries(&frames), stream.expected, "{} split={cut}", stream.id);
            split_cases += 1;
        }
        println!("stream={} chunk_sizes={:?} fragmented_boundaries=match", stream.id, chunks);
    }
    println!("FRAGMENTED_STREAMS=9/9 FIXED_CHUNK_CASES=63 HEADER_AND_TAIL_SPLITS={split_cases}");
}

#[test]
fn mirror_mutation_produces_the_existing_structured_warning() {
    let stream = samples().remove(0);
    let total = stream.expected[0].1;
    let mut bytes = stream.bytes[..total].to_vec();
    bytes[4..8].copy_from_slice(&0_i32.to_le_bytes());
    let mut reader = FrameReader::v50();
    let frames = reader.feed(&bytes).unwrap();
    reader.finish().unwrap();
    let declared = (total - 10) as i32;
    assert_eq!(frames.len(), 1);
    assert_eq!(frames[0].warning,
        Some(FrameWarning::LengthMirrorMismatch { declared, mirror: 0 }));
    println!("MIRROR_MUTATION=diagnosed {:?}; original v50 warning policy preserved", frames[0].warning);
}

#[test]
fn marker_mutation_is_rejected_and_poisons_the_reader() {
    let stream = samples().remove(0);
    let total = stream.expected[0].1;
    let mut bytes = stream.bytes[..total].to_vec();
    bytes[8..10].copy_from_slice(&0_u16.to_le_bytes());
    let mut reader = FrameReader::v50();
    assert_eq!(reader.feed(&bytes), Err(FrameError::UnsupportedMode));
    assert_eq!(reader.feed(&stream.bytes[..total]), Err(FrameError::Rejected));
    println!("MARKER_MUTATION=UnsupportedMode SUBSEQUENT_FEED=Rejected");
}

#[test]
fn truncated_captured_streams_are_not_accepted_as_complete() {
    for stream in samples() {
        let mut reader = FrameReader::v50();
        reader.feed(&stream.bytes[..stream.bytes.len() - 1]).unwrap();
        assert_eq!(reader.finish(), Err(FrameError::Truncated), "{}", stream.id);
    }
    println!("TRUNCATED_STREAMS_REFUSED=9/9");
}
