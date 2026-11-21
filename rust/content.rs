use gpw_offline_core::snapshot::Roster;
use std::{
    ffi::c_void, fs::OpenOptions, io::Read, os::windows::fs::OpenOptionsExt, path::Path, ptr,
};

pub const TARGET: &str = "26263743";
pub const REFERENCE: &str = "26431286";
const ROOT_EXE: &str = "TheFirstDescendant.exe";
const SHIPPING: &str = r"M1\Binaries\Win64\M1-Win64-Shipping.exe";

#[link(name = "bcrypt")]
unsafe extern "system" {
    fn BCryptCreateHash(
        alg: *mut c_void,
        hash: *mut *mut c_void,
        object: *mut u8,
        object_len: u32,
        secret: *mut u8,
        secret_len: u32,
        flags: u32,
    ) -> i32;
    fn BCryptHashData(hash: *mut c_void, bytes: *const u8, len: u32, flags: u32) -> i32;
    fn BCryptFinishHash(hash: *mut c_void, bytes: *mut u8, len: u32, flags: u32) -> i32;
    fn BCryptDestroyHash(hash: *mut c_void) -> i32;
}
struct Hash(*mut c_void);
impl Drop for Hash {
    fn drop(&mut self) {
        unsafe {
            BCryptDestroyHash(self.0);
        }
    }
}

fn digest(mut input: impl Read) -> Result<String, &'static str> {
    let mut handle = ptr::null_mut();
    // Windows BCRYPT_SHA256_ALG_HANDLE pseudo-handle. CNG owns the hash buffer.
    if unsafe {
        BCryptCreateHash(
            0x41 as *mut c_void,
            &mut handle,
            ptr::null_mut(),
            0,
            ptr::null_mut(),
            0,
            0,
        )
    } < 0
    {
        return Err("sha256_failed");
    }
    let hash = Hash(handle);
    let mut buf = vec![0u8; 256 * 1024];
    loop {
        let n = input
            .read(&mut buf)
            .map_err(|_| "fingerprint_read_failed")?;
        if n == 0 {
            break;
        }
        if unsafe { BCryptHashData(hash.0, buf.as_ptr(), n as u32, 0) } < 0 {
            return Err("sha256_failed");
        }
    }
    let mut bytes = [0u8; 32];
    if unsafe { BCryptFinishHash(hash.0, bytes.as_mut_ptr(), 32, 0) } < 0 {
        return Err("sha256_failed");
    }
    Ok(bytes.iter().map(|b| format!("{b:02x}")).collect())
}

pub fn identify(root: &Path) -> Result<&'static str, &'static str> {
    let open = |name| {
        OpenOptions::new()
            .read(true)
            .share_mode(1)
            .open(root.join(name))
            .map_err(|_| "game_image_unavailable")
    };
    let entry = open(ROOT_EXE)?;
    let shipping = open(SHIPPING)?;
    match_build(&digest(&entry)?, &digest(&shipping)?)
}

fn match_build(entry: &str, shipping: &str) -> Result<&'static str, &'static str> {
    match (entry, shipping) {
        (
            "88793f25b554b7a72b93aaa239d796b82ee192f7f7bf31d58355c913648734d1",
            "c01476888da891bf38f464aca7081a7da6bde6a33e50485cd75c9fa93794e867",
        ) => Ok(TARGET),
        (
            "c481d516480290867e186372edbb945937a57b3997a926bcae6d1c61f2b596d0",
            "2a821b3634165e972b1d20d741e8e293e7081daaacc341201e080203996c5e07",
        ) => Ok(REFERENCE),
        _ => Err("unrecognized_game_images"),
    }
}

pub fn check_player_templates(roster: &Roster) -> Result<(), &'static str> {
    // Fingerprint of ordered decimal template IDs plus LF from the historical catalog's
    // content-tables.jsonl / M1PlayerData / reflected_fields partition (see evidence).
    let mut ids: Vec<_> = roster.characters.iter().map(|c| c.template).collect();
    ids.sort_unstable();
    let canonical: String = ids.iter().map(|id| format!("{id}\n")).collect();
    if digest(canonical.as_bytes())?
        != "2e9ba91acbc611c2d09bb66263313192f5dbb34e54642de0eb728c429967f87d"
    {
        return Err("player_template_set_mismatch");
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn mixed_install_and_incomplete_roster_cannot_use_target_mapping() {
        assert_eq!(
            match_build(
                "c481d516480290867e186372edbb945937a57b3997a926bcae6d1c61f2b596d0",
                "c01476888da891bf38f464aca7081a7da6bde6a33e50485cd75c9fa93794e867"
            ),
            Err("unrecognized_game_images")
        );
        let mut roster = match gpw_offline_core::snapshot::read_gpw_roster() {
            Ok(roster) => roster,
            // The roster comes from a local snapshot that is never committed; a clean clone must
            // read this as "skipped", not as "the template rules are broken".
            Err(reason) => {
                eprintln!("skip: read_gpw_roster -> {reason} (local snapshot absent, not in repo)");
                return;
            }
        };
        check_player_templates(&roster).unwrap();
        roster.characters.pop();
        assert_eq!(
            check_player_templates(&roster),
            Err("player_template_set_mismatch")
        );
    }
}
