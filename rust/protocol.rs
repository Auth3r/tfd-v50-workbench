//! Original Rust port of GPW frame_reader.py (Round 2/3).
//! Contract/evidence and limits: ../PROTOCOL.md. Frame ingress keeps payload opaque.
//! Opt-in V15 static integer/header decoding is in `v15_static` below.

pub const MAX_PAYLOAD: usize = 8 * 1024 * 1024;
// Historical name in the owned opaque ingress contract; this is NOT V15 PLAIN.
// Use v15_static::TransportMode for the explicitly selected V15 profile.
pub const PLAIN: u16 = 0x7fff;
pub const INTEGER_ENCODING: &str = "UNKNOWN";

#[derive(Debug, PartialEq, Eq)]
pub enum FrameError {
    InvalidLength,
    UnsupportedMode,
    Truncated,
    Rejected,
    Finished,
}

/// Independently implemented from the selected V15 native instruction paths.
/// STATIC_CONFIRMED only: no captured RPC bytes or game interoperability test.
/// Evidence: evidence/v15-rpc-20261117/REVERSE.md. This profile is never inferred
/// from a frame's mode. The login endpoint uses the outer header and ordinary PLAIN reader.
pub mod v15_static {
    pub const ORIGINAL_EXE_SHA256: &str =
        "482bcd4f2cfd80a363423353e6e650230aa5e44bdd34f46bae63f87381460b71";
    pub const EVIDENCE_STATUS: &str = "STATIC_CONFIRMED";

    /// Sample-specific markers, independent of the owned opaque FrameReader.
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum TransportMode {
        Plain,
        Xor,
        Unknown(u16),
    }

    impl TransportMode {
        pub const fn from_marker(marker: u16) -> Self {
            match marker {
                0x8000 => Self::Plain,
                0x7fff => Self::Xor,
                other => Self::Unknown(other),
            }
        }
    }

    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum TransformError {
        RangeOverflow,
        InvalidOffset {
            offset: usize,
            input_len: usize,
        },
        Truncated {
            offset: usize,
            required: usize,
            available: usize,
        },
        InvalidLength {
            declared: i32,
            inverse: i32,
        },
        PayloadTooLarge {
            length: usize,
            limit: usize,
        },
        UnsupportedMode {
            marker: u16,
        },
        EmptyXorParameter,
        AllocationFailed,
    }

    /// RVA 0x9debf0 / 0x9ea660: byte XOR with a repeating parameter, reset at
    /// the start of each payload. Only caller-owned, ordinary protocol data is
    /// supported. No sample parameter, credential lookup or negotiation is built in.
    /// PLAIN copies the payload; neither branch mutates caller input or state.
    pub fn transform_payload(
        input: &[u8],
        mode: TransportMode,
        xor_parameter: &[u8],
    ) -> Result<Vec<u8>, TransformError> {
        if let TransportMode::Unknown(marker) = mode {
            return Err(TransformError::UnsupportedMode { marker });
        }
        if input.len() > super::MAX_PAYLOAD {
            return Err(TransformError::PayloadTooLarge {
                length: input.len(),
                limit: super::MAX_PAYLOAD,
            });
        }
        if mode == TransportMode::Xor && xor_parameter.is_empty() {
            return Err(TransformError::EmptyXorParameter);
        }
        let mut output = Vec::new();
        output
            .try_reserve_exact(input.len())
            .map_err(|_| TransformError::AllocationFailed)?;
        match mode {
            TransportMode::Plain => output.extend_from_slice(input),
            TransportMode::Xor => {
                for (i, byte) in input.iter().enumerate() {
                    output.push(byte ^ xor_parameter[i % xor_parameter.len()]);
                }
            }
            TransportMode::Unknown(_) => unreachable!(), // Rejected before allocation.
        }
        Ok(output)
    }

    /// One complete frame from a caller-supplied reassembled byte stream.
    /// payload is Q, ready for decode_rpc_header at index 0 (never strip again).
    /// Debug deliberately reports lengths and boundaries without payload bytes.
    #[derive(PartialEq, Eq)]
    pub struct TransformedFrame {
        pub mode: TransportMode,
        pub frame_offset: usize,
        pub payload_offset: usize,
        pub wire_bytes: usize,
        pub payload: Vec<u8>,
    }

    impl std::fmt::Debug for TransformedFrame {
        fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
            f.debug_struct("TransformedFrame")
                .field("mode", &self.mode)
                .field("frame_offset", &self.frame_offset)
                .field("payload_offset", &self.payload_offset)
                .field("wire_bytes", &self.wire_bytes)
                .field("payload_bytes", &self.payload.len())
                .finish()
        }
    }

    /// Validate only the fixed transport prefix. No payload transform or service selection.
    pub fn parse_transport_header(
        header: &[u8; 10],
    ) -> Result<(TransportMode, usize), TransformError> {
        let declared = i32::from_le_bytes(header[..4].try_into().unwrap());
        let inverse = i32::from_le_bytes(header[4..8].try_into().unwrap());
        // Widen before negation, including i32::MIN on invalid inputs.
        if declared <= 0 || i64::from(inverse) != -i64::from(declared) {
            return Err(TransformError::InvalidLength { declared, inverse });
        }
        let length = declared as usize;
        if length > super::MAX_PAYLOAD {
            return Err(TransformError::PayloadTooLarge {
                length,
                limit: super::MAX_PAYLOAD,
            });
        }
        let marker = u16::from_le_bytes(header[8..10].try_into().unwrap());
        let mode = TransportMode::from_marker(marker);
        if let TransportMode::Unknown(marker) = mode {
            return Err(TransformError::UnsupportedMode { marker });
        }
        Ok((mode, length))
    }

    /// RVA 0x9e0530 success boundary: <iiH>, then exactly size payload bytes.
    /// This stateless opt-in API does not connect a session, resynchronize a
    /// stream, or infer a V15 profile from mode. Trailing frames remain unread.
    pub fn transform_frame(
        stream: &[u8],
        frame_offset: usize,
        xor_parameter: &[u8],
    ) -> Result<TransformedFrame, TransformError> {
        let payload_offset = frame_offset
            .checked_add(10)
            .ok_or(TransformError::RangeOverflow)?;
        let remaining = stream
            .get(frame_offset..)
            .ok_or(TransformError::InvalidOffset {
                offset: frame_offset,
                input_len: stream.len(),
            })?;
        let header = remaining.get(..10).ok_or(TransformError::Truncated {
            offset: frame_offset,
            required: 10,
            available: remaining.len(),
        })?;
        let (mode, length) = parse_transport_header(header.try_into().unwrap())?;
        let end = payload_offset
            .checked_add(length)
            .ok_or(TransformError::RangeOverflow)?;
        let input = stream
            .get(payload_offset..end)
            .ok_or(TransformError::Truncated {
                offset: payload_offset,
                required: length,
                available: remaining.len() - 10,
            })?;
        let payload = transform_payload(input, mode, xor_parameter)?;
        Ok(TransformedFrame {
            mode,
            frame_offset,
            payload_offset,
            wire_bytes: end - frame_offset,
            payload,
        })
    }

    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum Width {
        W8,
        W16,
        W32,
        W64,
    }

    impl Width {
        fn bits(self) -> u32 {
            match self {
                Self::W8 => 8,
                Self::W16 => 16,
                Self::W32 => 32,
                Self::W64 => 64,
            }
        }
    }

    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub enum DecodeError {
        Truncated,
        IntegerOverflow,
        UnterminatedInteger,
        /// 30003 introduces a dictionary prefix; it cannot be treated as a body.
        DictionaryWrapperUnsupported,
    }

    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct IntegerOutOfRange;

    /// RVA 0x9e8310: at most ceil(bits/7) octets, low group first.
    /// A terminating redundant zero group is accepted within that limit, just
    /// as in this static reader. This is not the old synthetic canonical codec.
    pub fn decode_unsigned(input: &[u8], width: Width) -> Result<(u64, usize), DecodeError> {
        let bits = width.bits();
        // u128 retains excessive high bits in the last octet before validation.
        let mut value = 0u128;
        for i in 0..bits.div_ceil(7) as usize {
            let byte = *input.get(i).ok_or(DecodeError::Truncated)?;
            value |= u128::from(byte & 0x7f) << (7 * i);
            if byte & 0x80 == 0 {
                if value >= 1u128 << bits {
                    return Err(DecodeError::IntegerOverflow);
                }
                return Ok((value as u64, i + 1));
            }
        }
        Err(DecodeError::UnterminatedInteger)
    }

    /// RVA 0x9e8e60: unsigned(bits), then (n >> 1) XOR -(n AND 1).
    pub fn decode_signed(input: &[u8], width: Width) -> Result<(i64, usize), DecodeError> {
        let (value, consumed) = decode_unsigned(input, width)?;
        Ok((((value >> 1) as i64) ^ -((value & 1) as i64), consumed))
    }

    /// RVA 0x9e5880: range-checked unsigned writer; always emits shortest form.
    pub fn encode_unsigned(mut value: u64, width: Width) -> Result<Vec<u8>, IntegerOutOfRange> {
        if u128::from(value) >= 1u128 << width.bits() {
            return Err(IntegerOutOfRange);
        }
        let mut bytes = Vec::with_capacity(width.bits().div_ceil(7) as usize);
        while value >= 0x80 {
            bytes.push((value as u8 & 0x7f) | 0x80);
            value >>= 7;
        }
        bytes.push(value as u8);
        Ok(bytes)
    }

    /// RVA 0x9e4010: signed range check, then sign fold into unsigned(bits).
    pub fn encode_signed(value: i64, width: Width) -> Result<Vec<u8>, IntegerOutOfRange> {
        let half = 1i128 << (width.bits() - 1);
        if i128::from(value) < -half || i128::from(value) >= half {
            return Err(IntegerOutOfRange);
        }
        let folded = ((value as u64) << 1) ^ ((value >> 63) as u64);
        encode_unsigned(folded, width)
    }

    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct RpcHeader {
        pub request_id: i32,
        pub procedure_id: i16,
    }

    #[derive(PartialEq, Eq)]
    pub struct RpcEnvelope<'a> {
        pub header: RpcHeader,
        pub body_offset: usize,
        /// Business fields and nested service messages remain uninterpreted.
        pub body: &'a [u8],
    }

    impl std::fmt::Debug for RpcEnvelope<'_> {
        fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
            f.debug_struct("RpcEnvelope")
                .field("header", &self.header)
                .field("body_offset", &self.body_offset)
                .field("body_bytes", &self.body.len())
                .finish()
        }
    }

    /// RVA 0x9e2fe0: signed32 request_id, then signed16 procedure_id.
    /// The unwrapped body is the remaining slice, including an empty slice.
    /// No response/notification or service identity is inferred from this header.
    pub fn decode_rpc_header(payload: &[u8]) -> Result<RpcEnvelope<'_>, DecodeError> {
        let (request_id, request_bytes) = decode_signed(payload, Width::W32)?;
        let (procedure_id, procedure_bytes) = decode_signed(&payload[request_bytes..], Width::W16)?;
        if procedure_id == 30003 {
            return Err(DecodeError::DictionaryWrapperUnsupported);
        }
        let body_offset = request_bytes + procedure_bytes;
        Ok(RpcEnvelope {
            header: RpcHeader {
                request_id: request_id as i32,
                procedure_id: procedure_id as i16,
            },
            body_offset,
            body: &payload[body_offset..],
        })
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FrameWarning {
    LengthMirrorMismatch { declared: i32, mirror: i32 },
}

#[derive(PartialEq, Eq)]
pub struct Frame {
    pub stream_offset: u64,
    pub frame_index: u64,
    pub warning: Option<FrameWarning>,
    pub payload: Vec<u8>,
}

impl std::fmt::Debug for Frame {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Frame")
            .field("stream_offset", &self.stream_offset)
            .field("frame_index", &self.frame_index)
            .field("warning", &self.warning)
            .field("payload_bytes", &self.payload.len())
            .finish()
    }
}

#[derive(Default)]
pub struct FrameReader {
    pending: Vec<u8>,
    offset: u64,
    index: u64,
    failed: bool,
    closed: bool,
    warn_on_length_mirror: bool,
}

impl FrameReader {
    /// Inspect V50 frames with a structured warning on a mirror mismatch.
    pub fn v50() -> Self {
        Self {
            warn_on_length_mirror: true,
            ..Self::default()
        }
    }

    /// Retains at most one frame, even when the caller supplies many frames.
    /// An error poisons the stream; bytes cannot be resynchronized by guessing.
    pub fn feed(&mut self, mut bytes: &[u8]) -> Result<Vec<Frame>, FrameError> {
        if self.failed {
            return Err(FrameError::Rejected);
        }
        if self.closed {
            return Err(FrameError::Finished);
        }
        let mut frames = Vec::new();
        while !bytes.is_empty() {
            let needed = if self.pending.len() < 10 {
                10 - self.pending.len()
            } else {
                self.frame_size()? - self.pending.len()
            };
            let take = needed.min(bytes.len());
            self.pending.extend_from_slice(&bytes[..take]);
            bytes = &bytes[take..];
            if self.pending.len() >= 10 {
                let size = match self.frame_size() {
                    Ok(size) => size,
                    Err(error) => {
                        self.failed = true;
                        self.pending.clear();
                        return Err(error);
                    }
                };
                if self.pending.len() == size {
                    let declared = (size - 10) as i32;
                    let mirror = i32::from_le_bytes(self.pending[4..8].try_into().unwrap());
                    let warning = (mirror != -declared)
                        .then_some(FrameWarning::LengthMirrorMismatch { declared, mirror });
                    let payload = self.pending.split_off(10);
                    self.pending.clear();
                    frames.push(Frame {
                        stream_offset: self.offset,
                        frame_index: self.index,
                        warning,
                        payload,
                    });
                    self.offset += size as u64;
                    self.index += 1;
                }
            }
        }
        Ok(frames)
    }

    fn frame_size(&self) -> Result<usize, FrameError> {
        let size = i32::from_le_bytes(self.pending[..4].try_into().unwrap());
        let inverse = i32::from_le_bytes(self.pending[4..8].try_into().unwrap());
        if size <= 0
            || size as usize > MAX_PAYLOAD
            || (!self.warn_on_length_mirror && inverse != -size)
        {
            return Err(FrameError::InvalidLength);
        }
        if u16::from_le_bytes(self.pending[8..10].try_into().unwrap()) != PLAIN {
            return Err(FrameError::UnsupportedMode);
        }
        Ok(10 + size as usize)
    }

    pub fn finish(&mut self) -> Result<(), FrameError> {
        if self.failed {
            return Err(FrameError::Rejected);
        }
        if self.closed {
            return Err(FrameError::Finished);
        }
        if !self.pending.is_empty() {
            self.failed = true;
            self.pending.clear();
            return Err(FrameError::Truncated);
        }
        self.closed = true;
        Ok(())
    }
}
