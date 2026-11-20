//! Offline outer transport payload codec for the V50 wire (M01c).
//!
//! `payload[i] = body[i] ^ KEY[i % 30]`. The key is a fixed, printable-ASCII
//! constant: there is no randomness, no compression and no per-session state,
//! so the same body always produces the same payload bytes.
//!
//! This module only moves between the body layer and the payload layer. It
//! does not frame (10-byte header), authenticate, or interpret a body.

pub const KEY: [u8; 30] = [
    0x21, 0x40, 0x23, 0x54, 0x66, 0x64, 0x4b, 0x65, 0x79, 0x4b, 0x6a, 0x68, 0x4b, 0x6a, 0x79,
    0x53, 0x69, 0x68, 0x4c, 0x68, 0x77, 0x4a, 0x73, 0x6a, 0x4a, 0x6a, 0x68, 0x24, 0x25, 0x5e,
];

pub const KEY_LEN: usize = 30;

/// Body layer -> on-wire payload.
pub fn wrap(body: &[u8]) -> Vec<u8> {
    body.iter()
        .enumerate()
        .map(|(i, byte)| byte ^ KEY[i % KEY_LEN])
        .collect()
}

/// On-wire payload -> body layer. Symmetric to [`wrap`].
pub fn unwrap(payload: &[u8]) -> Vec<u8> {
    wrap(payload)
}
