use gpw_offline_core::v50_codec::*;

include!("fixtures/v50_first_frame.rs");

#[test]
fn golden_is_raw_only_and_replays_identically() {
    let outcome = inspect_frame(&V50_FIRST_FRAME, 35);
    assert_eq!(outcome.state, DecodeState::RawOnly);
    assert_eq!(
        outcome.warnings,
        [Warning {
            frame_offset: 35,
            field: FrameField::Payload,
            field_offset: 10,
            kind: WarningKind::MissingBodyDecoder
        }]
    );
    assert_eq!(outcome.replay_bytes(), V50_FIRST_FRAME);
    let replay = inspect_frame(outcome.replay_bytes(), 35);
    assert_eq!(replay.state, outcome.state);
    assert_eq!(replay.warnings, outcome.warnings);
}

#[test]
fn decoded_requires_explicit_decoder_and_preserves_mirror_warning() {
    let sample = [1, 0, 0, 0, 0, 0, 0, 0, 0xff, 0x7f, 42];
    let output = decode_frame(&sample, 70, |body| match body {
        [value] => Ok(*value),
        _ => Err(BodyDecodeError {
            field: "example_field",
            payload_offset: 2,
        }),
    });
    assert_eq!(output.state, DecodeState::Decoded(42));
    assert_eq!(
        output.warnings,
        [Warning {
            frame_offset: 70,
            field: FrameField::LengthMirror,
            field_offset: 4,
            kind: WarningKind::LengthMirrorMismatch {
                declared: 1,
                mirror: 0
            }
        }]
    );
}

#[test]
fn unknown_marker_retains_raw_and_never_calls_decoder() {
    let mut sample = V50_FIRST_FRAME;
    sample[8..10].copy_from_slice(&0x1234_u16.to_le_bytes());
    let output = decode_frame::<()>(&sample, 12, |_| panic!("must stay opaque"));
    assert_eq!(output.state, DecodeState::Unknown { marker: 0x1234 });
    assert_eq!(output.replay_bytes(), sample);
    assert_eq!(
        output.warnings,
        [Warning {
            frame_offset: 12,
            field: FrameField::Marker,
            field_offset: 8,
            kind: WarningKind::UnknownMarker(0x1234)
        }]
    );
}

#[test]
fn decode_and_boundary_failures_report_field_and_keep_bytes() {
    let output = decode_frame::<()>(&V50_FIRST_FRAME, 4, |_| {
        Err(BodyDecodeError {
            field: "example_field",
            payload_offset: 2,
        })
    });
    assert_eq!(output.state, DecodeState::RawOnly);
    assert_eq!(output.replay_bytes(), V50_FIRST_FRAME);
    assert_eq!(output.warnings[0].kind, WarningKind::BodyDecodeFailed);
    assert_eq!(output.warnings[0].field, FrameField::Body("example_field"));
    assert_eq!(output.warnings[0].field_offset, 12);
    assert_eq!(output.warnings[0].frame_offset, 4);

    for (end, field, field_offset, kind) in [
        (3, FrameField::Length, 0, WarningKind::TruncatedField),
        (7, FrameField::LengthMirror, 4, WarningKind::TruncatedField),
        (9, FrameField::Marker, 8, WarningKind::TruncatedField),
        (
            34,
            FrameField::Payload,
            10,
            WarningKind::PayloadLengthMismatch {
                declared: 25,
                actual: 24,
            },
        ),
    ] {
        let raw = &V50_FIRST_FRAME[..end];
        let output = decode_frame::<()>(raw, 500, |_| panic!("must stay opaque"));
        assert_eq!(output.state, DecodeState::RawOnly);
        assert_eq!(output.replay_bytes(), raw);
        assert_eq!(
            output.warnings,
            [Warning {
                frame_offset: 500,
                field,
                field_offset,
                kind
            }]
        );
    }
}
