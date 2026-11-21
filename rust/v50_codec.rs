//! Inspect one bounded V50 frame slice offline. A caller must supply any
//! independently established body decoder explicitly.
use crate::protocol::{MAX_PAYLOAD, PLAIN};

const HEADER_LEN: usize = 10;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum FrameField {
    Length,
    LengthMirror,
    Marker,
    Payload,
    Body(&'static str),
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum WarningKind {
    TruncatedField,
    InvalidLength(i32),
    LengthMirrorMismatch { declared: i32, mirror: i32 },
    UnknownMarker(u16),
    PayloadLengthMismatch { declared: usize, actual: usize },
    MissingBodyDecoder,
    BodyDecodeFailed,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Warning {
    pub frame_offset: u64,
    pub field: FrameField,
    pub field_offset: usize,
    pub kind: WarningKind,
}

#[derive(Debug, Eq, PartialEq)]
pub enum DecodeState<T> {
    Decoded(T),
    RawOnly,
    Unknown { marker: u16 },
}

pub struct Inspection<'a, T> {
    pub state: DecodeState<T>,
    pub warnings: Vec<Warning>,
    raw: &'a [u8],
}

impl<T> Inspection<'_, T> {
    /// Exact bytes for offline replay, including the original header.
    pub fn replay_bytes(&self) -> &[u8] {
        self.raw
    }
}

#[derive(Debug)]
pub struct BodyDecodeError {
    pub field: &'static str,
    pub payload_offset: usize,
}

/// Observe the captured envelope with the body left opaque.
pub fn inspect_frame(raw: &[u8], frame_offset: u64) -> Inspection<'_, ()> {
    inspect_with_decoder(raw, frame_offset, |_| {
        Err((
            FrameField::Payload,
            HEADER_LEN,
            WarningKind::MissingBodyDecoder,
        ))
    })
}

/// Decode a body using a caller-supplied profile. A decoder is never selected
/// from the mode marker alone, and never sees truncated or unknown frames.
pub fn decode_frame<T>(
    raw: &[u8],
    frame_offset: u64,
    decoder: impl FnOnce(&[u8]) -> Result<T, BodyDecodeError>,
) -> Inspection<'_, T> {
    inspect_with_decoder(raw, frame_offset, |body| {
        decoder(body).map_err(|failure| {
            (
                FrameField::Body(failure.field),
                HEADER_LEN.saturating_add(failure.payload_offset),
                WarningKind::BodyDecodeFailed,
            )
        })
    })
}

fn inspect_with_decoder<T>(
    raw: &[u8],
    frame_offset: u64,
    decoder: impl FnOnce(&[u8]) -> Result<T, (FrameField, usize, WarningKind)>,
) -> Inspection<'_, T> {
    use FrameField::*;
    use WarningKind::*;

    let mut warnings = Vec::new();
    let mut warn = |field, field_offset, kind| {
        warnings.push(Warning {
            frame_offset,
            field,
            field_offset,
            kind,
        })
    };

    let state = match raw {
        _ if raw.len() < 4 => {
            warn(Length, 0, TruncatedField);
            DecodeState::RawOnly
        }
        _ if raw.len() < 8 => {
            warn(LengthMirror, 4, TruncatedField);
            DecodeState::RawOnly
        }
        _ if raw.len() < HEADER_LEN => {
            warn(Marker, 8, TruncatedField);
            DecodeState::RawOnly
        }
        _ => {
            let declared = i32::from_le_bytes(raw[..4].try_into().unwrap());
            let mirror = i32::from_le_bytes(raw[4..8].try_into().unwrap());
            let marker = u16::from_le_bytes(raw[8..10].try_into().unwrap());
            let body = &raw[HEADER_LEN..];
            let valid_length = declared > 0 && declared as usize <= MAX_PAYLOAD;
            if !valid_length {
                warn(Length, 0, InvalidLength(declared));
            } else if declared as usize != body.len() {
                warn(
                    Payload,
                    HEADER_LEN,
                    PayloadLengthMismatch {
                        declared: declared as usize,
                        actual: body.len(),
                    },
                );
            }
            if i64::from(mirror) != -i64::from(declared) {
                warn(LengthMirror, 4, LengthMirrorMismatch { declared, mirror });
            }
            if marker != PLAIN {
                warn(Marker, 8, UnknownMarker(marker));
                DecodeState::Unknown { marker }
            } else if !valid_length || declared as usize != body.len() {
                DecodeState::RawOnly
            } else {
                match decoder(body) {
                    Ok(body) => DecodeState::Decoded(body),
                    Err((field, field_offset, kind)) => {
                        warn(field, field_offset, kind);
                        DecodeState::RawOnly
                    }
                }
            }
        }
    };

    Inspection {
        state,
        warnings,
        raw,
    }
}
