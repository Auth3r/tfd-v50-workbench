use std::{
    ffi::{CStr, c_char, c_int, c_void},
    fs::{self, OpenOptions},
    io::Read,
    os::windows::fs::OpenOptionsExt,
    path::Path,
    ptr,
};

#[link(name = "crypt32")]
unsafe extern "system" {
    fn CryptHashCertificate2(
        name: *const u16,
        flags: u32,
        reserved: *mut c_void,
        bytes: *const u8,
        len: u32,
        hash: *mut u8,
        size: *mut u32,
    ) -> i32;
}

#[link(name = "winsqlite3")]
unsafe extern "C" {
    fn sqlite3_open(name: *const c_char, db: *mut *mut c_void) -> c_int;
    fn sqlite3_close(db: *mut c_void) -> c_int;
    fn sqlite3_deserialize(
        db: *mut c_void,
        schema: *const c_char,
        bytes: *mut u8,
        size: i64,
        capacity: i64,
        flags: u32,
    ) -> c_int;
    fn sqlite3_prepare_v2(
        db: *mut c_void,
        sql: *const c_char,
        len: c_int,
        stmt: *mut *mut c_void,
        tail: *mut *const c_char,
    ) -> c_int;
    fn sqlite3_step(stmt: *mut c_void) -> c_int;
    fn sqlite3_finalize(stmt: *mut c_void) -> c_int;
    fn sqlite3_column_int64(stmt: *mut c_void, col: c_int) -> i64;
    fn sqlite3_column_type(stmt: *mut c_void, col: c_int) -> c_int;
    fn sqlite3_column_text(stmt: *mut c_void, col: c_int) -> *const c_char;
}

struct Database(*mut c_void);
impl Drop for Database {
    fn drop(&mut self) {
        unsafe {
            sqlite3_close(self.0);
        }
    }
}
struct Statement(*mut c_void);
impl Drop for Statement {
    fn drop(&mut self) {
        unsafe {
            sqlite3_finalize(self.0);
        }
    }
}
impl Database {
    fn prepare(&self, sql: &CStr) -> Result<Statement, &'static str> {
        let mut stmt = Statement(ptr::null_mut());
        if unsafe { sqlite3_prepare_v2(self.0, sql.as_ptr(), -1, &mut stmt.0, ptr::null_mut()) }
            != 0
        {
            return Err("snapshot_invalid_schema");
        }
        Ok(stmt)
    }
}

const ROOT: &str = env!("CARGO_MANIFEST_DIR");
const A: &str = "2a5c9d70b1eab0c9a5a38e45573d9b1f838f173a6a61117c7765df9fb629f5c0";
const B: &str = "6cd5fa37795d55fba24f10ab7801b58547b622ddd58f5478baabd6a1a6962f84";
const SIZE: usize = 1662976;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Selected {
    pub character_id: i64,
    pub template_id: i64,
    pub level: i64,
}

fn approved_image(approved_snapshot: &str) -> Result<Vec<u8>, &'static str> {
    let (relative, digest) = match approved_snapshot {
        "A" => ("target/gpw-local-data-ab-20261118/A.sqlite3", A),
        "B" => ("target/gpw-local-data-ab-20261118/B.sqlite3", B),
        "GPW" => (
            "target/gpw-v15-minimal-handoff-20261118/gpw-level2.sqlite3",
            B,
        ),
        _ => return Err("snapshot_not_approved"),
    };
    sealed_bytes(&Path::new(ROOT).join(relative), digest)
}

pub fn read_selected_level(approved_snapshot: &str) -> Result<Selected, &'static str> {
    decode(&mut approved_image(approved_snapshot)?)
}

fn sealed_bytes(path: &Path, digest: &str) -> Result<Vec<u8>, &'static str> {
    for ancestor in path.ancestors() {
        use std::os::windows::fs::MetadataExt;
        if fs::symlink_metadata(ancestor)
            .map_err(|_| "snapshot_unavailable")?
            .file_attributes()
            & 0x400
            != 0
        {
            return Err("snapshot_reparse_point");
        }
    }
    let file = OpenOptions::new()
        .read(true)
        .share_mode(1)
        .open(&path)
        .map_err(|_| "snapshot_not_quiescent")?;
    for suffix in ["-wal", "-shm", "-journal"] {
        let mut side = path.as_os_str().to_owned();
        side.push(suffix);
        match fs::symlink_metadata(side) {
            Err(err) if err.kind() == std::io::ErrorKind::NotFound => (),
            _ => return Err("snapshot_has_sidecar"),
        }
    }
    let mut bytes = Vec::with_capacity(SIZE);
    file.take((SIZE + 1) as u64)
        .read_to_end(&mut bytes)
        .map_err(|_| "snapshot_read_failed")?;
    if bytes.len() != SIZE {
        return Err("snapshot_identity_mismatch");
    }
    let mut hash = [0u8; 32];
    let mut size = 32u32;
    let algorithm: Vec<u16> = "SHA256\0".encode_utf16().collect();
    if unsafe {
        CryptHashCertificate2(
            algorithm.as_ptr(),
            0,
            ptr::null_mut(),
            bytes.as_ptr(),
            bytes.len() as u32,
            hash.as_mut_ptr(),
            &mut size,
        )
    } == 0
        || size != 32
    {
        return Err("sha256_failed");
    }
    if hash
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>()
        != digest
    {
        return Err("snapshot_identity_mismatch");
    }
    Ok(bytes)
}

fn decode(bytes: &mut [u8]) -> Result<Selected, &'static str> {
    with_database(bytes, selection)
}

fn with_database<T>(
    bytes: &mut [u8],
    read: impl FnOnce(&Database) -> Result<T, &'static str>,
) -> Result<T, &'static str> {
    let mut db = Database(ptr::null_mut());
    if unsafe { sqlite3_open(c":memory:".as_ptr(), &mut db.0) } != 0 {
        return Err("sqlite_open_failed");
    }
    if unsafe {
        sqlite3_deserialize(
            db.0,
            c"main".as_ptr(),
            bytes.as_mut_ptr(),
            bytes.len() as i64,
            bytes.len() as i64,
            4,
        )
    } != 0
    {
        return Err("snapshot_corrupt");
    }
    let check = db
        .prepare(c"PRAGMA integrity_check(1)")
        .map_err(|_| "snapshot_corrupt")?;
    if unsafe { sqlite3_step(check.0) } != 100 {
        return Err("snapshot_corrupt");
    }
    let value = unsafe { sqlite3_column_text(check.0, 0) };
    if value.is_null()
        || unsafe { CStr::from_ptr(value) } != c"ok"
        || unsafe { sqlite3_step(check.0) } != 101
    {
        return Err("snapshot_corrupt");
    }
    read(&db)
}

fn selection(db: &Database) -> Result<Selected, &'static str> {
    let row = db.prepare(c"SELECT s.account_uid,s.character_uid,c.account_uid,c.uid,c.template_id,c.level,c.max_level FROM account_character_selection s LEFT JOIN characters c ON s.account_uid=c.account_uid AND s.character_uid=c.uid LIMIT 2")?;
    match unsafe { sqlite3_step(row.0) } {
        101 => return Err("no_selection"),
        100 => (),
        _ => return Err("snapshot_corrupt"),
    }
    let types = (0..7)
        .map(|col| unsafe { sqlite3_column_type(row.0, col) })
        .collect::<Vec<_>>();
    let integer = |col| unsafe { sqlite3_column_int64(row.0, col) };
    let selected = Selected {
        character_id: integer(3),
        template_id: integer(4),
        level: integer(5),
    };
    let cap = integer(6);
    match unsafe { sqlite3_step(row.0) } {
        100 => return Err("ambiguous_selection"),
        101 => (),
        _ => return Err("snapshot_corrupt"),
    }
    if types[3] == 5 {
        return Err("dangling_selection");
    }
    if types.iter().any(|ty| *ty != 1) {
        return Err("selection_type_mismatch");
    }
    if !(1..=cap).contains(&selected.level) {
        return Err("invalid_selected_level");
    }
    Ok(selected)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Character {
    pub uid: i64,
    pub template: i64,
    pub level: i64,
    pub exp: i64,
    pub max_level: i64,
    pub resets: i64,
    pub revision: i64,
}

impl Character {
    pub fn valid(&self) -> bool {
        self.uid > 0
            && self.template > 0
            && (1..=self.max_level).contains(&self.level)
            && self.exp >= 0
            && self.resets >= 0
            && self.revision >= 0
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Roster {
    pub selected: i64,
    pub characters: Vec<Character>,
}

/// Materialize only the approved GPW snapshot and the selected snapshot account's rows.
pub fn read_gpw_roster() -> Result<Roster, &'static str> {
    with_database(&mut approved_image("GPW")?, |db| {
        let selected = selection(db)?;
        let rows = db.prepare(c"SELECT c.uid,c.template_id,c.level,c.exp,c.max_level,c.reset_count,c.revision FROM characters c JOIN account_character_selection s ON s.account_uid=c.account_uid ORDER BY c.uid")?;
        let mut characters = Vec::new();
        loop {
            match unsafe { sqlite3_step(rows.0) } {
                101 => break,
                100 => (),
                _ => return Err("snapshot_corrupt"),
            }
            if (0..7).any(|col| unsafe { sqlite3_column_type(rows.0, col) } != 1) {
                return Err("character_type_mismatch");
            }
            let integer = |col| unsafe { sqlite3_column_int64(rows.0, col) };
            let c = Character {
                uid: integer(0),
                template: integer(1),
                level: integer(2),
                exp: integer(3),
                max_level: integer(4),
                resets: integer(5),
                revision: integer(6),
            };
            if !c.valid()
                || characters
                    .last()
                    .is_some_and(|prev: &Character| prev.uid == c.uid)
            {
                return Err("invalid_character_row");
            }
            characters.push(c);
        }
        if !characters.iter().any(|c| c.uid == selected.character_id) {
            return Err("dangling_selection");
        }
        Ok(Roster {
            selected: selected.character_id,
            characters,
        })
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::ffi::CString;

    fn read_sealed(path: &Path, digest: &str) -> Result<Selected, &'static str> {
        decode(&mut sealed_bytes(path, digest)?)
    }

    #[link(name = "winsqlite3")]
    unsafe extern "C" {
        fn sqlite3_exec(
            db: *mut c_void,
            sql: *const c_char,
            callback: *const c_void,
            arg: *mut c_void,
            err: *mut *mut c_char,
        ) -> c_int;
        fn sqlite3_serialize(
            db: *mut c_void,
            schema: *const c_char,
            size: *mut i64,
            flags: u32,
        ) -> *mut u8;
        fn sqlite3_free(allocation: *mut c_void);
    }
    fn fixture(change: &str) -> Result<Selected, &'static str> {
        let mut db = Database(ptr::null_mut());
        assert_eq!(unsafe { sqlite3_open(c":memory:".as_ptr(), &mut db.0) }, 0);
        let sql = CString::new(format!("CREATE TABLE account_character_selection(account_uid INTEGER,character_uid INTEGER); CREATE TABLE characters(account_uid INTEGER,uid INTEGER,template_id INTEGER,level INTEGER,max_level INTEGER); INSERT INTO characters VALUES(10,5,30,8,40),(11,5,31,9,40); INSERT INTO account_character_selection VALUES(11,5); {change}")).unwrap();
        assert_eq!(
            unsafe {
                sqlite3_exec(
                    db.0,
                    sql.as_ptr(),
                    ptr::null(),
                    ptr::null_mut(),
                    ptr::null_mut(),
                )
            },
            0
        );
        let mut size = 0;
        let data = unsafe { sqlite3_serialize(db.0, c"main".as_ptr(), &mut size, 0) };
        assert!(!data.is_null() && size > 0);
        let mut image = unsafe { std::slice::from_raw_parts(data, size as usize).to_vec() };
        unsafe {
            sqlite3_free(data.cast());
        }
        decode(&mut image)
    }
    #[test]
    fn account_and_character_must_both_match() {
        assert_eq!(
            fixture(""),
            Ok(Selected {
                character_id: 5,
                template_id: 31,
                level: 9
            })
        );
    }

    #[test]
    fn wrong_identity_and_unsealed_files_are_refused() {
        let root = Path::new(ROOT).join("target/test-data").join(format!(
            "profile-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir_all(&root).unwrap();
        let file = root.join("candidate.sqlite3");
        fs::copy(
            Path::new(ROOT).join("target/gpw-local-data-ab-20261118/A.sqlite3"),
            &file,
        )
        .unwrap();
        assert_eq!(read_sealed(&file, B), Err("snapshot_identity_mismatch"));
        let side = root.join("candidate.sqlite3-wal");
        fs::write(&side, []).unwrap();
        assert_eq!(read_sealed(&file, A), Err("snapshot_has_sidecar"));
        fs::remove_file(side).unwrap();
        let held = OpenOptions::new().write(true).open(&file).unwrap();
        assert_eq!(read_sealed(&file, A), Err("snapshot_not_quiescent"));
        drop(held);
        assert_eq!(read_sealed(&file, A).unwrap().level, 1);
        fs::remove_file(file).unwrap();
        fs::remove_dir(root).unwrap();
    }
    #[test]
    fn invalid_selection_is_never_defaulted() {
        for (change, error) in [
            ("DELETE FROM account_character_selection", "no_selection"),
            (
                "INSERT INTO account_character_selection VALUES(10,5)",
                "ambiguous_selection",
            ),
            (
                "UPDATE account_character_selection SET character_uid=42",
                "dangling_selection",
            ),
            (
                "UPDATE characters SET level='two'",
                "selection_type_mismatch",
            ),
            ("UPDATE characters SET level=41", "invalid_selected_level"),
            (
                "ALTER TABLE characters RENAME COLUMN level TO missing",
                "snapshot_invalid_schema",
            ),
            ("DROP TABLE characters", "snapshot_invalid_schema"),
        ] {
            assert_eq!(fixture(change), Err(error), "{change}");
        }
        assert_eq!(decode(&mut [0x33; 4096]), Err("snapshot_corrupt"));
    }
}
