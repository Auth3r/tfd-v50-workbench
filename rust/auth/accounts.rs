use super::{
    Result,
    crypto::{PublicKey, hex, random, unhex},
};
use std::{
    collections::BTreeMap,
    fs::{self, File, OpenOptions},
    io::{ErrorKind, Read, Write},
    path::Path,
};

#[derive(Default)]
pub struct Accounts(BTreeMap<String, [u8; 64]>);

impl Accounts {
    fn parse(file: File) -> Result<Self> {
        const LIMIT: u64 = 64 * 1024;
        if !file
            .metadata()
            .map_err(|_| "accounts_unreadable")?
            .is_file()
        {
            return Err("accounts_not_file");
        }
        let mut contents = String::new();
        file.take(LIMIT + 1)
            .read_to_string(&mut contents)
            .map_err(|_| "accounts_invalid")?;
        let mut lines = contents.lines();
        if contents.len() as u64 > LIMIT || lines.next() != Some("GPW.accounts/1") {
            return Err("accounts_invalid");
        }
        let mut accounts = Self::default();
        for line in lines {
            let (name, key) = line.split_once('\t').ok_or("accounts_invalid")?;
            accounts.add(name, key)?;
        }
        if accounts.0.is_empty() {
            return Err("accounts_empty");
        }
        Ok(accounts)
    }

    fn add(&mut self, name: &str, public_key: &str) -> Result<()> {
        if name.is_empty()
            || name.len() > 32
            || !name
                .bytes()
                .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-' || b == b'_')
        {
            return Err("invalid_account_name");
        }
        let key = unhex(public_key).ok_or("invalid_account_key")?;
        PublicKey::import(&key)?;
        if self.0.len() >= 256 || self.0.contains_key(name) || self.0.values().any(|k| k == &key) {
            return Err("duplicate_or_excess_accounts");
        }
        self.0.insert(name.to_owned(), key);
        Ok(())
    }

    pub fn load(path: &Path) -> Result<Self> {
        Self::parse(File::open(path).map_err(|_| "accounts_unreadable")?)
    }

    pub fn key(&self, account: &str) -> Option<&[u8; 64]> {
        self.0.get(account)
    }
}

/// Operator-local provisioning. Serialize writers across replacement of the registry itself.
pub fn register(path: &Path, name: &str, public_key: &str) -> Result<()> {
    let mut lock_path = path.as_os_str().to_owned();
    lock_path.push(".lock");
    let lock = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(lock_path)
        .map_err(|_| "accounts_lock_unavailable")?;
    lock.try_lock().map_err(|_| "accounts_busy")?;
    let mut accounts = match File::open(path) {
        Ok(file) => Accounts::parse(file)?,
        Err(e) if e.kind() == ErrorKind::NotFound => Accounts::default(),
        Err(_) => return Err("accounts_unreadable"),
    };
    if accounts
        .key(name)
        .is_some_and(|key| unhex(public_key).as_ref() == Some(key))
    {
        return Ok(());
    }
    accounts.add(name, public_key)?;
    let temp = path.with_file_name(format!(".gpw-accounts-{}.tmp", hex(&random()?)));
    let mut out = File::create_new(&temp).map_err(|_| "accounts_create_failed")?;
    let result = (|| -> std::io::Result<()> {
        writeln!(out, "GPW.accounts/1")?;
        for (name, key) in accounts.0 {
            writeln!(out, "{name}\t{}", hex(&key))?;
        }
        out.sync_all()?;
        drop(out);
        fs::rename(&temp, path)
    })();
    if result.is_err() {
        let _ = fs::remove_file(temp);
        return Err("accounts_commit_failed");
    }
    Ok(())
}
