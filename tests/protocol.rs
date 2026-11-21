use gpw_offline_core::protocol::{FrameError, FrameReader, FrameWarning};

// Independently written byte fixtures: little-endian 3/-3/0x7fff + abc,
// then 1/-1/0x7fff + x. Synthetic; not captured from the game.
const BYTES: &[u8] = b"\x03\0\0\0\xfd\xff\xff\xff\xff\x7fabc\x01\0\0\0\xff\xff\xff\xff\xff\x7fx";

#[test]
fn every_tcp_split_and_coalesced_frame_preserves_boundaries() {
    for cut in 0..=BYTES.len() {
        let mut reader = FrameReader::default();
        let mut frames = reader.feed(&BYTES[..cut]).unwrap();
        frames.extend(reader.feed(&BYTES[cut..]).unwrap());
        reader.finish().unwrap();
        assert_eq!(frames.len(), 2);
        assert_eq!(frames[0].payload, b"abc");
        assert_eq!(frames[1].payload, b"x");
        assert_eq!((frames[0].stream_offset, frames[0].frame_index), (0, 0));
        assert_eq!((frames[1].stream_offset, frames[1].frame_index), (13, 1));
    }
}

#[test]
fn bytewise_ingress_and_clean_eof_do_not_lose_frames() {
    let mut reader = FrameReader::default();
    let frames: Vec<_> = BYTES
        .chunks(1)
        .flat_map(|b| reader.feed(b).unwrap())
        .collect();
    assert_eq!(frames.len(), 2);
    assert!(!format!("{:?}", frames[0]).contains("97, 98, 99"));
    reader.finish().unwrap();
    assert_eq!(reader.feed(b"x"), Err(FrameError::Finished));
    assert_eq!(reader.finish(), Err(FrameError::Finished));
}

#[test]
fn malformed_lengths_and_unverified_modes_poison_stream() {
    for (header, expected) in [
        (
            &b"\x03\0\0\0\xfc\xff\xff\xff\xff\x7f"[..],
            FrameError::InvalidLength,
        ),
        (&b"\0\0\0\0\0\0\0\0\xff\x7f"[..], FrameError::InvalidLength),
        (
            &b"\0\0\0\x80\0\0\0\x80\xff\x7f"[..],
            FrameError::InvalidLength,
        ),
        (
            &b"\x01\0\x80\0\xff\xff\x7f\xff\xff\x7f"[..],
            FrameError::InvalidLength,
        ),
        (
            &b"\x03\0\0\0\xfd\xff\xff\xff\0\x80"[..],
            FrameError::UnsupportedMode,
        ),
    ] {
        let mut reader = FrameReader::default();
        assert_eq!(reader.feed(header), Err(expected));
        assert_eq!(reader.feed(BYTES), Err(FrameError::Rejected));
        assert_eq!(reader.finish(), Err(FrameError::Rejected));
    }
}

#[test]
fn truncated_headers_and_payloads_cannot_be_accepted() {
    for cut in (1..13).chain(14..BYTES.len()) {
        let mut reader = FrameReader::default();
        reader.feed(&BYTES[..cut]).unwrap();
        assert_eq!(reader.finish(), Err(FrameError::Truncated));
        assert_eq!(reader.feed(&BYTES[cut..]), Err(FrameError::Rejected));
    }
}

include!("fixtures/v50_first_frame.rs");

#[test]
fn captured_v50_first_frame_has_mirrored_payload_length() {
    let declared = i32::from_le_bytes(V50_FIRST_FRAME[..4].try_into().unwrap());
    let inverse = i32::from_le_bytes(V50_FIRST_FRAME[4..8].try_into().unwrap());
    assert_eq!(declared, 25);
    assert_eq!(declared as usize, V50_FIRST_FRAME[10..].len());
    assert_eq!(inverse, -declared);
    assert_eq!(
        u16::from_le_bytes(V50_FIRST_FRAME[8..10].try_into().unwrap()),
        0x7fff
    );

    for cut in 0..=V50_FIRST_FRAME.len() {
        let mut reader = FrameReader::v50();
        let mut frames = reader.feed(&V50_FIRST_FRAME[..cut]).unwrap();
        frames.extend(reader.feed(&V50_FIRST_FRAME[cut..]).unwrap());
        reader.finish().unwrap();
        assert_eq!(frames.len(), 1);
        assert_eq!(frames[0].payload.as_slice(), &V50_FIRST_FRAME[10..]);
        assert_eq!(frames[0].warning, None);
    }
}

#[test]
fn v50_mirror_mismatch_warns_without_losing_the_next_frame() {
    let mut bad_inverse = V50_FIRST_FRAME;
    bad_inverse[4] = 0xe8; // -24 while the declared length is 25.
    let mut reader = FrameReader::v50();
    assert!(reader.feed(&bad_inverse[..10]).unwrap().is_empty());
    let mut rest = bad_inverse[10..].to_vec();
    rest.extend_from_slice(&V50_FIRST_FRAME);
    let frames = reader.feed(&rest).unwrap();
    assert_eq!(frames.len(), 2);
    assert_eq!(
        frames[0].warning,
        Some(FrameWarning::LengthMirrorMismatch {
            declared: 25,
            mirror: -24,
        })
    );
    assert_eq!(frames[0].payload, V50_FIRST_FRAME[10..]);
    assert_eq!(frames[1].stream_offset, 35);
    assert_eq!(frames[1].warning, None);
    reader.finish().unwrap();
}

#[test]
fn v50_still_rejects_invalid_sizes_unknown_marker_and_truncation() {
    for size in [0_i32, -1, i32::MIN, 8 * 1024 * 1024 + 1] {
        let mut invalid = V50_FIRST_FRAME;
        invalid[..4].copy_from_slice(&size.to_le_bytes());
        let mut reader = FrameReader::v50();
        assert_eq!(reader.feed(&invalid), Err(FrameError::InvalidLength));
        assert_eq!(reader.finish(), Err(FrameError::Rejected));
    }
    let mut invalid = V50_FIRST_FRAME;
    invalid[8] = 0;
    assert_eq!(
        FrameReader::v50().feed(&invalid),
        Err(FrameError::UnsupportedMode)
    );
    let mut reader = FrameReader::v50();
    assert!(reader.feed(&V50_FIRST_FRAME[..34]).unwrap().is_empty());
    assert_eq!(reader.finish(), Err(FrameError::Truncated));
}
