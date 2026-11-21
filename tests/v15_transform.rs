//! STATIC_RULE_DERIVED / NEGATIVE_SYNTHETIC unless explicitly marked below.
//! No captured RPC bytes and no sample XOR parameter are included.
use gpw_offline_core::protocol::{MAX_PAYLOAD, v15_static::*};

fn frame(payload: &[u8], marker: u16) -> Vec<u8> {
    let n = i32::try_from(payload.len()).unwrap();
    [
        n.to_le_bytes().as_slice(),
        (-n).to_le_bytes().as_slice(),
        marker.to_le_bytes().as_slice(),
        payload,
    ]
    .concat()
}

#[test]
fn synthetic_repeating_xor_vector_preserves_every_byte_and_resets() {
    // Hand-calculated; length 3 exposes modulo vs power-of-two masking.
    let input = [0x00, 0x01, 0x7f, 0x80, 0xff, 0x55, 0xaa];
    let parameter = [0x10, 0x80, 0x03];
    let expected = [0x10, 0x81, 0x7c, 0x90, 0x7f, 0x56, 0xba];
    let before = input;
    let out = transform_payload(&input, TransportMode::Xor, &parameter).unwrap();
    assert_eq!(out, expected);
    assert_eq!(input, before);
    assert_eq!(out.len(), input.len());
    assert_eq!(
        transform_payload(&out, TransportMode::Xor, &parameter).unwrap(),
        input
    );
    assert_eq!(
        transform_payload(&input, TransportMode::Xor, &parameter).unwrap(),
        expected
    );
    assert_eq!(
        transform_payload(&input, TransportMode::Plain, &[]).unwrap(),
        input
    );
    assert_eq!(
        transform_payload(&input, TransportMode::Xor, &[0xff]).unwrap(),
        [0xff, 0xfe, 0x80, 0x7f, 0x00, 0xaa, 0x55]
    );
    assert_eq!(
        transform_payload(&[], TransportMode::Xor, &parameter).unwrap(),
        []
    );
}

#[test]
fn unknown_modes_and_missing_parameter_never_become_plain() {
    assert_eq!(TransportMode::from_marker(0x7fff), TransportMode::Xor);
    assert_eq!(TransportMode::from_marker(0x8000), TransportMode::Plain);
    for marker in [0, 1, 0x7ffe, 0x8001, 0xffff] {
        assert_eq!(
            TransportMode::from_marker(marker),
            TransportMode::Unknown(marker)
        );
        assert_eq!(
            transform_frame(&frame(&[2, 0], marker), 0, &[]),
            Err(TransformError::UnsupportedMode { marker })
        );
        assert_eq!(
            transform_payload(&[2, 0], TransportMode::Unknown(marker), &[1]),
            Err(TransformError::UnsupportedMode { marker })
        );
    }
    assert_eq!(
        transform_payload(&[2, 0], TransportMode::Xor, &[]),
        Err(TransformError::EmptyXorParameter)
    );
    assert_eq!(
        transform_payload(&[], TransportMode::Xor, &[]),
        Err(TransformError::EmptyXorParameter)
    );
    assert_eq!(
        transform_frame(&frame(&[2, 0], 0x7fff), 0, &[]),
        Err(TransformError::EmptyXorParameter)
    );
}

#[test]
fn synthetic_frames_transform_once_then_enter_rpc_at_zero() {
    // request=1 -> 02, procedure=1400 -> f0 15, body=aa bb.
    // Same artificial three-byte parameter as the independent vector above.
    let plain = [0x02, 0xf0, 0x15, 0xaa, 0xbb];
    let xor = [0x12, 0x70, 0x16, 0xba, 0x3b];
    let parameter = [0x10, 0x80, 0x03];
    let first = frame(&xor, 0x7fff);
    let second = frame(&plain, 0x8000);
    let stream = [
        vec![0xde, 0xad, 0xbe],
        first.clone(),
        second.clone(),
        first.clone(),
    ]
    .concat();
    let before = stream.clone();
    let mut offset = 3;
    for (mode, supplied) in [
        (TransportMode::Xor, parameter.as_slice()),
        (TransportMode::Plain, &[][..]),
        (TransportMode::Xor, parameter.as_slice()),
    ] {
        let f = transform_frame(&stream, offset, supplied).unwrap();
        assert_eq!(f.mode, mode);
        assert_eq!(
            (f.frame_offset, f.payload_offset, f.wire_bytes),
            (offset, offset + 10, 15)
        );
        assert_eq!(f.payload, plain);
        let rpc = decode_rpc_header(&f.payload).unwrap();
        assert_eq!(
            rpc.header,
            RpcHeader {
                request_id: 1,
                procedure_id: 1400
            }
        );
        assert_eq!(rpc.body_offset, 3);
        assert_eq!(rpc.body, [0xaa, 0xbb]);
        offset += f.wire_bytes;
    }
    assert_eq!(offset, stream.len());
    assert_eq!(stream, before);
    // The untransformed representation does not have the asserted RPC identity.
    assert_ne!(
        decode_rpc_header(&xor).unwrap().header,
        RpcHeader {
            request_id: 1,
            procedure_id: 1400
        }
    );
}

#[test]
fn every_truncation_is_rejected_without_contaminating_retry() {
    for marker in [0x7fff, 0x8000] {
        let full = frame(&[2, 0xf0, 0x15, 0xaa, 0xbb], marker);
        for cut in 0..full.len() {
            let partial = full[..cut].to_vec();
            let before = partial.clone();
            assert!(
                matches!(
                    transform_frame(&partial, 0, &[1, 2, 3]),
                    Err(TransformError::Truncated { .. })
                ),
                "marker={marker:x}, cut={cut}"
            );
            assert_eq!(partial, before);
            assert!(transform_frame(&full, 0, &[1, 2, 3]).is_ok());
        }
    }
}

#[test]
fn invalid_lengths_offsets_and_overflow_are_explicit_errors() {
    for (declared, inverse) in [(0i32, 0i32), (-1, 1), (i32::MIN, i32::MIN), (2, -3)] {
        let bytes = [
            declared.to_le_bytes().as_slice(),
            inverse.to_le_bytes().as_slice(),
            &[0, 0x80],
        ]
        .concat();
        assert_eq!(
            transform_frame(&bytes, 0, &[]),
            Err(TransformError::InvalidLength { declared, inverse })
        );
    }
    for n in [(MAX_PAYLOAD + 1) as i32, i32::MAX] {
        let bytes = [
            n.to_le_bytes().as_slice(),
            (-n).to_le_bytes().as_slice(),
            &[0, 0x80],
        ]
        .concat();
        assert_eq!(
            transform_frame(&bytes, 0, &[]),
            Err(TransformError::PayloadTooLarge {
                length: n as usize,
                limit: MAX_PAYLOAD
            })
        );
    }
    assert_eq!(
        transform_frame(&[], usize::MAX, &[]),
        Err(TransformError::RangeOverflow)
    );
    assert_eq!(
        transform_frame(&[1, 2], 3, &[]),
        Err(TransformError::InvalidOffset {
            offset: 3,
            input_len: 2
        })
    );
    assert_eq!(
        transform_frame(&[1, 2], 2, &[]),
        Err(TransformError::Truncated {
            offset: 2,
            required: 10,
            available: 0
        })
    );
    // A ten-byte input is a header, not a complete payload.
    let bytes = frame(&[2, 0], 0x8000);
    assert_eq!(
        transform_frame(&bytes[..10], 0, &[]),
        Err(TransformError::Truncated {
            offset: 10,
            required: 2,
            available: 0
        })
    );
}

#[test]
fn payload_limit_is_inclusive_and_oversize_does_not_modify_input() {
    let mut input = vec![0x5a; MAX_PAYLOAD];
    let out = transform_payload(&input, TransportMode::Xor, &[0xff]).unwrap();
    assert_eq!(out.len(), MAX_PAYLOAD);
    assert!(out.iter().all(|&v| v == 0xa5));
    assert!(input.iter().all(|&v| v == 0x5a));
    input.push(0x5a);
    for mode in [TransportMode::Plain, TransportMode::Xor] {
        assert_eq!(
            transform_payload(&input, mode, &[1]),
            Err(TransformError::PayloadTooLarge {
                length: MAX_PAYLOAD + 1,
                limit: MAX_PAYLOAD
            })
        );
    }
    assert_eq!(input.len(), MAX_PAYLOAD + 1);
}

#[test]
fn transform_does_not_weaken_rpc_integer_or_wrapper_errors() {
    let oversized_integer = [0xff, 0xff, 0xff, 0xff, 0x7f, 0x00];
    let f = transform_frame(&frame(&oversized_integer, 0x8000), 0, &[]).unwrap();
    assert_eq!(
        decode_rpc_header(&f.payload),
        Err(DecodeError::IntegerOverflow)
    );
    // request 1, procedure 30003 -> e6 d4 03: remains unsupported after transform.
    let f = transform_frame(&frame(&[2, 0xe6, 0xd4, 3], 0x8000), 0, &[]).unwrap();
    assert_eq!(
        decode_rpc_header(&f.payload),
        Err(DecodeError::DictionaryWrapperUnsupported)
    );
}

#[test]
fn historical_outer_header_only_cannot_claim_rpc_bytes() {
    // HISTORICAL_OUTER_HEADER_ONLY; source: outer-slice-source.json in
    // evidence/v15-live-rpc-20261118-012857. No payload bytes were retained.
    let header = [0xb9, 0, 0, 0, 0x47, 0xff, 0xff, 0xff, 0xff, 0x7f];
    assert_eq!(
        transform_frame(&header, 0, &[]),
        Err(TransformError::Truncated {
            offset: 10,
            required: 185,
            available: 0
        })
    );
}
