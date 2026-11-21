//! GPW-owned equipment transactions. This protocol is NOT V15 or GPW.local/1.
use crate::snapshot::{Character, Roster};
use std::{
    collections::BTreeMap,
    fs::{File, OpenOptions},
    io::{self, Read, Seek, SeekFrom, Write},
    path::Path,
};

pub type Result<T> = std::result::Result<T, String>;
const MAX_FRAME: usize = 65536;
const MAX_LOG: u64 = 32 * 1024 * 1024;
fn io_error(e: io::Error) -> String {
    format!("storage_or_transport:{:?}", e.kind())
}

pub fn read_frame(reader: &mut impl Read) -> Result<Option<String>> {
    let mut header = [0; 8];
    match reader.read(&mut header[..1]).map_err(io_error)? {
        0 => return Ok(None),
        _ => reader.read_exact(&mut header[1..]).map_err(io_error)?,
    }
    if &header[..4] != b"GPWR" {
        return Err("foreign_protocol".into());
    }
    let len = u32::from_le_bytes(header[4..].try_into().unwrap()) as usize;
    if !(1..=MAX_FRAME).contains(&len) {
        return Err("frame_size_invalid".into());
    }
    let mut body = vec![0; len];
    reader.read_exact(&mut body).map_err(io_error)?;
    let text = String::from_utf8(body).map_err(|_| "invalid_utf8")?;
    if text.contains(['\r', '\n', '\0']) {
        return Err("invalid_text".into());
    }
    Ok(Some(text))
}
pub fn write_frame(writer: &mut impl Write, text: &str) -> Result<()> {
    if text.is_empty() || text.len() > MAX_FRAME {
        return Err("frame_size_invalid".into());
    }
    writer.write_all(b"GPWR").map_err(io_error)?;
    writer
        .write_all(&(text.len() as u32).to_le_bytes())
        .map_err(io_error)?;
    writer.write_all(text.as_bytes()).map_err(io_error)
}
fn identifier(s: &str) -> Result<String> {
    if s.is_empty()
        || s.len() > 64
        || !s
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
    {
        return Err("invalid_identifier".into());
    }
    Ok(s.into())
}
fn number(s: &str) -> Result<u64> {
    s.parse().map_err(|_| "invalid_number".into())
}
fn character_owner(owner: &str) -> Result<String> {
    let (build, identity) = owner.split_once(':').ok_or("invalid_selection_owner")?;
    if build.parse::<u32>().ok().filter(|n| *n > 0).is_none() {
        return Err("invalid_selection_owner".into());
    }
    let (account, key) = identity.split_once(':').ok_or("invalid_selection_owner")?;
    identifier(account)?;
    if key.len() != 128 || !key.bytes().all(|b| b.is_ascii_hexdigit()) {
        return Err("invalid_selection_owner".into());
    }
    Ok(owner.to_owned())
}

fn parse_roster(selected: &str, records: &str) -> Result<Roster> {
    let selected = selected
        .parse::<i64>()
        .map_err(|_| "invalid_roster_selection")?;
    let mut characters = Vec::new();
    for record in records.split(',') {
        let mut fields = record.split(':');
        let mut integer = || {
            fields
                .next()
                .and_then(|v| v.parse::<i64>().ok())
                .ok_or("invalid_character_row")
        };
        let character = Character {
            uid: integer()?,
            template: integer()?,
            level: integer()?,
            exp: integer()?,
            max_level: integer()?,
            resets: integer()?,
            revision: integer()?,
        };
        if fields.next().is_some()
            || !character.valid()
            || characters
                .last()
                .is_some_and(|prior: &Character| prior.uid >= character.uid)
        {
            return Err("invalid_character_row".into());
        }
        characters.push(character);
    }
    if !characters.iter().any(|c| c.uid == selected) {
        return Err("invalid_roster_selection".into());
    }
    Ok(Roster {
        selected,
        characters,
    })
}
#[derive(Clone, Debug, PartialEq)]
pub enum Command {
    Create {
        profile: String,
        inventory: u64,
        warehouse: u64,
    },
    Provision {
        profile: String,
        revision: u64,
        item: String,
        equipped: bool,
    },
    Move {
        profile: String,
        revision: u64,
        operation: String,
        items: Vec<String>,
        warehouse: bool,
    },
    Read(String),
    ImportRoster {
        owner: String,
        roster: Roster,
    },
    SelectCharacter {
        owner: String,
        revision: u64,
        character: i64,
    },
}
impl Command {
    pub fn parse(text: &str) -> Result<Self> {
        let f: Vec<_> = text.split('\t').collect();
        match f.as_slice() {
            // Internal durable records. The TCP developer API only accepts GPW.rust/1.
            ["GPW.roster/1", owner, selected, records] => Ok(Self::ImportRoster {
                owner: character_owner(owner)?,
                roster: parse_roster(selected, records)?,
            }),
            ["GPW.selection/1", owner, rev, uid] => {
                let character = uid.parse::<i64>().map_err(|_| "invalid_character_uid")?;
                if character <= 0 {
                    return Err("invalid_character_uid".into());
                }
                Ok(Self::SelectCharacter {
                    owner: character_owner(owner)?,
                    revision: number(rev)?,
                    character,
                })
            }
            ["GPW.rust/1", "create", p, i, w] => {
                let (inventory, warehouse) = (number(i)?, number(w)?);
                if !(1..=128).contains(&inventory) || !(1..=128).contains(&warehouse) {
                    return Err("invalid_capacity".into());
                }
                Ok(Self::Create {
                    profile: identifier(p)?,
                    inventory,
                    warehouse,
                })
            }
            ["GPW.rust/1", "provision", p, rev, item, equipped] => Ok(Self::Provision {
                profile: identifier(p)?,
                revision: number(rev)?,
                item: identifier(item)?,
                equipped: match *equipped {
                    "0" => false,
                    "1" => true,
                    _ => return Err("invalid_equipped".into()),
                },
            }),
            ["GPW.rust/1", "move", p, rev, op, destination, batch] => {
                let mut items = batch
                    .split(',')
                    .map(identifier)
                    .collect::<Result<Vec<_>>>()?;
                items.sort();
                if items.len() > 256 || items.windows(2).any(|w| w[0] == w[1]) {
                    return Err("invalid_batch".into());
                }
                Ok(Self::Move {
                    profile: identifier(p)?,
                    revision: number(rev)?,
                    operation: identifier(op)?,
                    items,
                    warehouse: match *destination {
                        "warehouse" => true,
                        "inventory" => false,
                        _ => return Err("invalid_destination".into()),
                    },
                })
            }
            ["GPW.rust/1", "read", p] => Ok(Self::Read(identifier(p)?)),
            ["GPW.rust/1", "world.reserve"] => Err("world_runtime_unimplemented".into()),
            _ => Err("unsupported_request".into()),
        }
    }
}
#[derive(Clone, Default)]
struct Profile {
    revision: u64,
    inventory: u64,
    warehouse: u64,
    // item -> (in warehouse, equipped)
    items: BTreeMap<String, (bool, bool)>,
    receipts: BTreeMap<String, (Command, String)>,
}
#[derive(Clone, Default)]
struct State {
    profiles: BTreeMap<String, Profile>,
    selections: BTreeMap<String, (u64, i64)>,
    rosters: BTreeMap<String, std::sync::Arc<Roster>>,
}
impl State {
    fn apply(&mut self, command: &Command) -> Result<(String, bool)> {
        if let Command::ImportRoster { owner, roster } = command {
            if self.rosters.contains_key(owner) {
                return Err("roster_already_imported".into());
            }
            if let Some((_, uid)) = self.selections.get(owner) {
                if !roster.characters.iter().any(|c| c.uid == *uid) {
                    return Err("saved_character_missing".into());
                }
            }
            self.rosters
                .insert(owner.clone(), std::sync::Arc::new(roster.clone()));
            return Ok(("roster_imported".into(), true));
        }
        if let Command::SelectCharacter {
            owner,
            revision,
            character,
        } = command
        {
            if self
                .rosters
                .get(owner)
                .is_some_and(|r| !r.characters.iter().any(|c| c.uid == *character))
            {
                return Err("character_not_owned".into());
            }
            let current = self.selections.get(owner).copied();
            let next = revision.checked_add(1).ok_or("revision_exhausted")?;
            if current == Some((next, *character)) {
                return Ok((format!("selection\t{next}\t{character}"), false));
            }
            if current.map_or(0, |(rev, _)| rev) != *revision {
                return Err("revision_conflict".into());
            }
            if current == Some((*revision, *character)) {
                return Ok((format!("selection\t{revision}\t{character}"), false));
            }
            self.selections.insert(owner.clone(), (next, *character));
            return Ok((format!("selection\t{next}\t{character}"), true));
        }
        if let Command::Create {
            profile,
            inventory,
            warehouse,
        } = command
        {
            if self.profiles.contains_key(profile) {
                return Err("profile_exists".into());
            }
            if self.profiles.len() >= 1000 {
                return Err("profile_limit".into());
            }
            self.profiles.insert(
                profile.clone(),
                Profile {
                    inventory: *inventory,
                    warehouse: *warehouse,
                    ..Default::default()
                },
            );
            return Ok(("ok\t0".into(), true));
        }
        let uid = match command {
            Command::Provision { profile, .. }
            | Command::Move { profile, .. }
            | Command::Read(profile) => profile,
            _ => unreachable!(),
        };
        if let Command::Provision { item, .. } = command
            && self.profiles.values().any(|p| p.items.contains_key(item))
        {
            return Err("duplicate_item_uid".into());
        }
        let p = self.profiles.get_mut(uid).ok_or("profile_not_found")?;
        if let Command::Read(_) = command {
            let items = p
                .items
                .iter()
                .map(|(id, (w, e))| {
                    format!(
                        "{id}:{}:{}",
                        if *w { "warehouse" } else { "inventory" },
                        u8::from(*e)
                    )
                })
                .collect::<Vec<_>>()
                .join(",");
            let response = format!("ok\t{}\t{}", p.revision, items);
            if response.len() > MAX_FRAME {
                return Err("response_too_large".into());
            }
            return Ok((response, false));
        }
        if let Command::Move { operation, .. } = command {
            if let Some((prior, response)) = p.receipts.get(operation) {
                return if prior == command {
                    Ok((response.clone(), false))
                } else {
                    Err("operation_uid_conflict".into())
                };
            }
            if p.receipts.len() >= 10000 {
                return Err("receipt_limit".into());
            }
        }
        let revision = match command {
            Command::Provision { revision, .. } | Command::Move { revision, .. } => *revision,
            _ => unreachable!(),
        };
        if p.revision != revision {
            return Err("revision_conflict".into());
        }
        let next = revision.checked_add(1).ok_or("revision_exhausted")?;
        match command {
            Command::Provision { item, equipped, .. } => {
                if p.items.values().filter(|(w, _)| !w).count() as u64 >= p.inventory {
                    return Err("destination_full".into());
                }
                p.items.insert(item.clone(), (false, *equipped));
            }
            Command::Move {
                items, warehouse, ..
            } => {
                for item in items {
                    let (location, equipped) = p.items.get(item).ok_or("item_not_owned")?;
                    if *equipped {
                        return Err("equipped_item".into());
                    }
                    if location == warehouse {
                        return Err("item_already_at_destination".into());
                    }
                }
                let capacity = if *warehouse { p.warehouse } else { p.inventory };
                if p.items.values().filter(|(w, _)| w == warehouse).count() as u64
                    + items.len() as u64
                    > capacity
                {
                    return Err("destination_full".into());
                }
                for item in items {
                    p.items.get_mut(item).unwrap().0 = *warehouse;
                }
            }
            _ => unreachable!(),
        }
        p.revision = next;
        let response = format!("ok\t{next}");
        if let Command::Move { operation, .. } = command {
            p.receipts
                .insert(operation.clone(), (command.clone(), response.clone()));
        }
        Ok((response, true))
    }
}
// FNV-1a detects accidental corruption; it is not authentication or a signature.
fn checksum(bytes: &[u8]) -> u64 {
    bytes.iter().fold(0xcbf29ce484222325, |hash, b| {
        (hash ^ u64::from(*b)).wrapping_mul(0x100000001b3)
    })
}
pub struct Store {
    file: File,
    state: State,
    poisoned: bool,
}
impl Store {
    pub fn open(path: &Path) -> Result<Self> {
        Self::open_journal(path, true)
    }
    pub fn open_existing(path: &Path) -> Result<Self> {
        Self::open_journal(path, false)
    }
    fn open_journal(path: &Path, create: bool) -> Result<Self> {
        let mut file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(create)
            .truncate(false)
            .open(path)
            .map_err(|e| {
                if !create && e.kind() == io::ErrorKind::NotFound {
                    "journal_missing".to_string()
                } else {
                    io_error(e)
                }
            })?;
        file.try_lock().map_err(|_| "workspace_locked")?;
        if file.metadata().map_err(io_error)?.len() > MAX_LOG {
            return Err("journal_limit".into());
        }
        let mut state = State::default();
        while let Some(text) = read_frame(&mut file)? {
            let mut check = [0; 8];
            file.read_exact(&mut check)
                .map_err(|_| "truncated_journal")?;
            if u64::from_le_bytes(check) != checksum(text.as_bytes()) {
                return Err("corrupt_journal".into());
            }
            let (_, changed) = state.apply(&Command::parse(&text)?)?;
            if !changed {
                return Err("invalid_journal_record".into());
            }
        }
        Ok(Self {
            file,
            state,
            poisoned: false,
        })
    }
    pub fn execute(&mut self, text: &str, allow_provisioning: bool) -> Result<String> {
        if !text.starts_with("GPW.rust/1\t") {
            return Err("unsupported_request".into());
        }
        self.commit(text, allow_provisioning)
    }

    pub fn saved_roster(&self, owner: &str) -> Option<std::sync::Arc<Roster>> {
        self.state.rosters.get(owner).cloned()
    }

    pub fn import_roster(&mut self, owner: &str, roster: &Roster) -> Result<()> {
        let rows: Vec<_> = roster
            .characters
            .iter()
            .map(|c| {
                format!(
                    "{}:{}:{}:{}:{}:{}:{}",
                    c.uid, c.template, c.level, c.exp, c.max_level, c.resets, c.revision
                )
            })
            .collect();
        self.commit(
            &format!(
                "GPW.roster/1\t{owner}\t{}\t{}",
                roster.selected,
                rows.join(",")
            ),
            false,
        )?;
        Ok(())
    }

    pub fn character_selection(&self, owner: &str) -> Result<Option<(u64, i64)>> {
        if self.poisoned {
            return Err("storage_requires_restart".into());
        }
        Ok(self.state.selections.get(owner).copied())
    }

    pub fn select_character(
        &mut self,
        owner: &str,
        revision: u64,
        character: i64,
    ) -> Result<String> {
        let text = format!("GPW.selection/1\t{owner}\t{revision}\t{character}");
        self.commit(&text, false)
    }

    fn commit(&mut self, text: &str, allow_provisioning: bool) -> Result<String> {
        if self.poisoned {
            return Err("storage_requires_restart".into());
        }
        if text.len() > MAX_FRAME {
            return Err("frame_size_invalid".into());
        }
        let command = Command::parse(text)?;
        if matches!(command, Command::Provision { .. }) && !allow_provisioning {
            return Err("provisioning_disabled".into());
        }
        let mut candidate = self.state.clone();
        let (response, changed) = candidate.apply(&command)?;
        if !changed {
            return Ok(response);
        }
        let start = self.file.seek(SeekFrom::End(0)).map_err(io_error)?;
        if start + text.len() as u64 + 16 > MAX_LOG {
            return Err("journal_limit".into());
        }
        let commit = (|| {
            write_frame(&mut self.file, text)?;
            self.file
                .write_all(&checksum(text.as_bytes()).to_le_bytes())
                .map_err(io_error)?;
            self.file.sync_all().map_err(io_error)
        })();
        if let Err(error) = commit {
            if self
                .file
                .set_len(start)
                .and_then(|_| self.file.sync_all())
                .is_err()
            {
                self.poisoned = true;
            }
            return Err(error);
        }
        self.state = candidate;
        Ok(response)
    }
}
