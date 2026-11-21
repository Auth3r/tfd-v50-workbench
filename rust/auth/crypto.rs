//! Only GPW public signing keys and GPW-generated random values enter this module.
use std::{
    ffi::c_void,
    fmt::Write,
    ptr::{null, null_mut},
};

type Handle = *mut c_void;
// Windows 10+ CNG algorithm pseudo-handles from bcrypt.h.
const SHA256: Handle = 0x41 as Handle;
const ECDSA_P256: Handle = 0x2e1 as Handle;

#[link(name = "bcrypt")]
unsafe extern "system" {
    fn BCryptGenRandom(alg: Handle, out: *mut u8, size: u32, flags: u32) -> i32;
    fn BCryptHash(
        alg: Handle,
        secret: *const u8,
        secret_len: u32,
        input: *const u8,
        len: u32,
        out: *mut u8,
        out_len: u32,
    ) -> i32;
    fn BCryptImportKeyPair(
        alg: Handle,
        import: Handle,
        kind: *const u16,
        out: *mut Handle,
        bytes: *const u8,
        size: u32,
        flags: u32,
    ) -> i32;
    fn BCryptDestroyKey(key: Handle) -> i32;
    fn BCryptVerifySignature(
        key: Handle,
        padding: *const c_void,
        digest: *const u8,
        digest_len: u32,
        signature: *const u8,
        sig_len: u32,
        flags: u32,
    ) -> i32;
}

pub fn random() -> Result<[u8; 32], &'static str> {
    let mut bytes = [0; 32];
    if unsafe { BCryptGenRandom(null_mut(), bytes.as_mut_ptr(), 32, 2) } < 0 {
        return Err("random_unavailable");
    }
    Ok(bytes)
}

pub fn hex(bytes: &[u8]) -> String {
    let mut out = String::with_capacity(2 * bytes.len());
    for b in bytes {
        write!(out, "{b:02x}").expect("writing to a string");
    }
    out
}

pub fn unhex<const N: usize>(s: &str) -> Option<[u8; N]> {
    if s.len() != N * 2 || !s.is_ascii() {
        return None;
    }
    let mut bytes = [0; N];
    for (i, byte) in bytes.iter_mut().enumerate() {
        let pair = &s[2 * i..2 * i + 2];
        if !pair.bytes().all(|b| b.is_ascii_hexdigit()) {
            return None;
        }
        *byte = u8::from_str_radix(pair, 16).ok()?;
    }
    Some(bytes)
}

pub struct PublicKey(Handle);

impl Drop for PublicKey {
    fn drop(&mut self) {
        unsafe {
            BCryptDestroyKey(self.0);
        }
    }
}

impl PublicKey {
    pub fn import(xy: &[u8; 64]) -> Result<Self, &'static str> {
        let mut blob = [0_u8; 72];
        blob[..4].copy_from_slice(b"ECS1");
        blob[4..8].copy_from_slice(&32_u32.to_le_bytes());
        blob[8..].copy_from_slice(xy);
        let kind: Vec<_> = "ECCPUBLICBLOB\0".encode_utf16().collect();
        let mut key = null_mut();
        if unsafe {
            BCryptImportKeyPair(
                ECDSA_P256,
                null_mut(),
                kind.as_ptr(),
                &mut key,
                blob.as_ptr(),
                blob.len() as u32,
                0,
            )
        } < 0
        {
            return Err("invalid_account_key");
        }
        Ok(Self(key))
    }

    pub fn verify(&self, message: &[u8], signature: &[u8; 64]) -> Result<(), &'static str> {
        let mut digest = [0; 32];
        if unsafe {
            BCryptHash(
                SHA256,
                null(),
                0,
                message.as_ptr(),
                message.len() as u32,
                digest.as_mut_ptr(),
                32,
            )
        } < 0
        {
            return Err("hash_unavailable");
        }
        if unsafe {
            BCryptVerifySignature(
                self.0,
                null(),
                digest.as_ptr(),
                32,
                signature.as_ptr(),
                64,
                0,
            )
        } < 0
        {
            return Err("authentication_failed");
        }
        Ok(())
    }
}
