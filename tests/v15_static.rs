//! STATIC_RULE_DERIVED vectors, not captures and not a game compatibility test.
//! See evidence/v15-rpc-20261117/REVERSE.md for native addresses/operations.
use gpw_offline_core::protocol::v15_static::{
    DecodeError, IntegerOutOfRange, RpcHeader, Width, decode_rpc_header, decode_signed,
    decode_unsigned, encode_signed, encode_unsigned,
};

#[test]
fn unsigned_vectors_follow_seven_bit_groups_and_width_limits() {
    // Independent numeric vectors: 127 + 1*128 = 255, 1*128^2 = 16384.
    let vectors: &[(u64, Width, &[u8])] = &[
        (0, Width::W8, &[0]),
        (127, Width::W8, &[0x7f]),
        (128, Width::W8, &[0x80, 1]),
        (255, Width::W8, &[0xff, 1]),
        (16384, Width::W16, &[0x80, 0x80, 1]),
        (65535, Width::W16, &[0xff, 0xff, 3]),
        (u32::MAX as u64, Width::W32, &[0xff, 0xff, 0xff, 0xff, 0x0f]),
        (
            u64::MAX,
            Width::W64,
            &[0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 1],
        ),
    ];
    for &(value, width, bytes) in vectors {
        assert_eq!(encode_unsigned(value, width).unwrap(), bytes);
        assert_eq!(decode_unsigned(bytes, width), Ok((value, bytes.len())));
    }
}

#[test]
fn signed_vectors_cover_negative_values_and_extremes() {
    // Static sign fold: 0 -> 0, -1 -> 1, 1 -> 2, -65 -> 129.
    let vectors: &[(i64, Width, &[u8])] = &[
        (0, Width::W8, &[0]),
        (-1, Width::W8, &[1]),
        (1, Width::W8, &[2]),
        (-64, Width::W8, &[0x7f]),
        (64, Width::W8, &[0x80, 1]),
        (-65, Width::W8, &[0x81, 1]),
        (-128, Width::W8, &[0xff, 1]),
        (127, Width::W8, &[0xfe, 1]),
        (-32768, Width::W16, &[0xff, 0xff, 3]),
        (32767, Width::W16, &[0xfe, 0xff, 3]),
        (i32::MIN as i64, Width::W32, &[0xff, 0xff, 0xff, 0xff, 0x0f]),
        (
            i64::MIN,
            Width::W64,
            &[0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 1],
        ),
        (
            i64::MAX,
            Width::W64,
            &[0xfe, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 1],
        ),
    ];
    for &(value, width, bytes) in vectors {
        assert_eq!(encode_signed(value, width).unwrap(), bytes);
        assert_eq!(decode_signed(bytes, width), Ok((value, bytes.len())));
    }
}

#[test]
fn redundant_zero_groups_are_accepted_only_within_static_width_budget() {
    // V15's reader has no shortest-form check. Old SYNTHETIC codec rejects these.
    assert_eq!(decode_unsigned(&[0x80, 0], Width::W8), Ok((0, 2)));
    assert_eq!(decode_signed(&[0x81, 0], Width::W8), Ok((-1, 2)));
    assert_eq!(
        decode_unsigned(&[0x80, 0x80, 0], Width::W8),
        Err(DecodeError::UnterminatedInteger)
    );
    // A standalone decoder stops at its terminator, preserving the following field.
    assert_eq!(decode_unsigned(&[1, 0xff], Width::W8), Ok((1, 1)));
    assert_eq!(encode_unsigned(0, Width::W8).unwrap(), [0]);
}

#[test]
fn truncated_overflow_and_unterminated_inputs_are_distinct_failures() {
    for (width, overflow, max_bytes) in [
        (Width::W8, vec![0x80, 2], 2),
        (Width::W16, vec![0x80, 0x80, 4], 3),
        (Width::W32, vec![0x80, 0x80, 0x80, 0x80, 0x10], 5),
        (
            Width::W64,
            vec![0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 0x80, 2],
            10,
        ),
    ] {
        assert_eq!(
            decode_unsigned(&overflow, width),
            Err(DecodeError::IntegerOverflow)
        );
        for cut in 0..max_bytes {
            assert_eq!(
                decode_unsigned(&vec![0x80; cut], width),
                Err(DecodeError::Truncated)
            );
        }
        assert_eq!(
            decode_unsigned(&vec![0x80; max_bytes], width),
            Err(DecodeError::UnterminatedInteger)
        );
        assert_eq!(
            decode_signed(&vec![0xff; max_bytes], width),
            Err(DecodeError::UnterminatedInteger)
        );
    }
}

#[test]
fn writers_reject_out_of_range_before_returning_bytes() {
    for (width, unsigned_limit, signed_half) in [
        (Width::W8, 256, 128),
        (Width::W16, 65536, 32768),
        (Width::W32, 4294967296, 2147483648),
    ] {
        assert_eq!(
            encode_unsigned(unsigned_limit, width),
            Err(IntegerOutOfRange)
        );
        assert_eq!(encode_signed(signed_half, width), Err(IntegerOutOfRange));
        assert_eq!(
            encode_signed(-signed_half - 1, width),
            Err(IntegerOutOfRange)
        );
    }
}

#[test]
fn unwrapped_header_uses_signed32_then_signed16_with_opaque_remainder() {
    // Artificial header: 12 -> 24; 1110 -> 2220 = 44 + 17*128.
    // The sentinel is arbitrary, never represented as a historical request body.
    let bytes = [0x18, 0xac, 0x11, 0xde, 0xad, 0xbe, 0xef];
    let rpc = decode_rpc_header(&bytes).unwrap();
    assert_eq!(
        rpc.header,
        RpcHeader {
            request_id: 12,
            procedure_id: 1110
        }
    );
    assert_eq!(rpc.body_offset, 3);
    assert_eq!(rpc.body, &bytes[3..]);
    assert!(!format!("{rpc:?}").contains("222, 173"));
    assert_eq!(decode_rpc_header(&bytes[..3]).unwrap().body, []);
    for cut in 0..3 {
        assert_eq!(
            decode_rpc_header(&bytes[..cut]),
            Err(DecodeError::Truncated)
        );
    }
}

#[test]
fn header_keeps_negative_id_and_nested_service_bytes_without_classifying_events() {
    let notification_header = decode_rpc_header(&[1, 0xc0, 0x11]).unwrap();
    assert_eq!(
        notification_header.header,
        RpcHeader {
            request_id: -1,
            procedure_id: 1120
        }
    );
    // Artificial ClientService 20000 header: 40000 = 64 + 56*128 + 2*16384.
    // Its remainder stays opaque; no second same-level GameService request is made.
    let outer = decode_rpc_header(&[0x1c, 0xc0, 0xb8, 2, 0xea, 1]).unwrap();
    assert_eq!(
        outer.header,
        RpcHeader {
            request_id: 14,
            procedure_id: 20000
        }
    );
    assert_eq!(outer.body, &[0xea, 1]);
}

#[test]
fn dictionary_wrapper_and_invalid_headers_never_expose_a_guessed_body() {
    // 30003 -> 60006 = 102 + 84*128 + 3*16384, actual dictionary prefix omitted.
    for suffix in [&[][..], &[0, 2][..]] {
        let mut bytes = vec![0, 0xe6, 0xd4, 3];
        bytes.extend_from_slice(suffix);
        assert_eq!(
            decode_rpc_header(&bytes),
            Err(DecodeError::DictionaryWrapperUnsupported)
        );
    }
    assert_eq!(
        decode_rpc_header(&[0xff, 0xff, 0xff, 0xff, 0x10, 0]),
        Err(DecodeError::IntegerOverflow)
    );
    assert_eq!(
        decode_rpc_header(&[0, 0x80, 0x80, 4]),
        Err(DecodeError::IntegerOverflow)
    );
    assert_eq!(
        decode_rpc_header(&[0, 0x80, 0x80, 0x80, 0]),
        Err(DecodeError::UnterminatedInteger)
    );
}

#[test]
fn ordinary_header_accepts_nonminimal_fields_without_shifting_the_body() {
    // STATIC_RULE_DERIVED, not a capture: -1 uses two groups and 1120 uses three.
    let bytes = [0x81, 0x00, 0xc0, 0x91, 0x00, 0xe6, 0xd4, 0x03];
    let rpc = decode_rpc_header(&bytes).unwrap();
    assert_eq!(
        rpc.header,
        RpcHeader {
            request_id: -1,
            procedure_id: 1120
        }
    );
    assert_eq!(rpc.body_offset, 5);
    // A 30003-shaped sequence inside the opaque body is not a header marker.
    assert_eq!(rpc.body, &[0xe6, 0xd4, 0x03]);
}

#[test]
fn fragmented_plain_frames_preserve_rpc_marker_layer_and_field_boundaries() {
    use gpw_offline_core::protocol::FrameReader;

    // Fixed numeric vectors, never reconstructed from historical body lengths.
    for (procedure, encoded) in [
        (1003, &[0xd6, 0x0f][..]),
        (1004, &[0xd8, 0x0f][..]),
        (1110, &[0xac, 0x11][..]),
        (1120, &[0xc0, 0x11][..]),
        (1400, &[0xf0, 0x15][..]),
        (30001, &[0xe2, 0xd4, 0x03][..]),
        (30003, &[0xe6, 0xd4, 0x03][..]),
    ] {
        let mut payload = vec![0x01]; // signed32 request_id = -1
        payload.extend_from_slice(encoded);
        // Deliberately arbitrary body; no business meaning or inner 20000 format.
        payload.extend_from_slice(&[0xe6, 0xd4, 0x03]);
        let size = payload.len() as i32;
        let mut wire = Vec::new();
        wire.extend_from_slice(&size.to_le_bytes());
        wire.extend_from_slice(&(-size).to_le_bytes());
        wire.extend_from_slice(&[0xff, 0x7f]); // transport mode, not procedure ID
        wire.extend_from_slice(&payload);

        for split in 0..=wire.len() {
            let mut reader = FrameReader::default();
            let mut frames = reader.feed(&wire[..split]).unwrap();
            frames.extend(reader.feed(&wire[split..]).unwrap());
            reader.finish().unwrap();
            assert_eq!(frames.len(), 1);
            assert_eq!(frames[0].payload, payload);
            let decoded = decode_rpc_header(&frames[0].payload);
            if procedure == 30003 {
                assert_eq!(decoded, Err(DecodeError::DictionaryWrapperUnsupported));
            } else {
                let rpc = decoded.unwrap();
                assert_eq!(
                    rpc.header,
                    RpcHeader {
                        request_id: -1,
                        procedure_id: procedure
                    }
                );
                assert_eq!(rpc.body_offset, 1 + encoded.len());
                assert_eq!(rpc.body, &[0xe6, 0xd4, 0x03]);
            }
        }
    }
}
