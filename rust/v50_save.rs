//! Lossless offline mapping of the three identity/roster SQLite tables.
//! The TSV exchange is an internal tool format, never a game wire format.
use std::collections::BTreeSet;

pub type Result<T> = std::result::Result<T, &'static str>;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Account {
    pub uid: i64,
    pub name: String,
    pub created_at: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Character {
    pub uid: i64,
    pub account_uid: i64,
    pub template_id: i32,
    pub exp: i64,
    pub level: i32,
    pub max_level: i32,
    pub reset_count: i32,
    /// Preserve the original JSON text exactly; its semantics are not inferred.
    pub state_json: String,
    pub revision: i64,
    pub updated_at: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Selection {
    pub account_uid: i64,
    pub character_uid: i64,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SaveSnapshot {
    pub accounts: Vec<Account>,
    pub characters: Vec<Character>,
    pub selections: Vec<Selection>,
}

fn unhex(value: &str) -> Result<String> {
    if !value.is_ascii() || value.len() % 2 != 0 {
        return Err("invalid_text_hex");
    }
    let bytes: Vec<_> = (0..value.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&value[i..i + 2], 16).map_err(|_| "invalid_text_hex"))
        .collect::<Result<_>>()?;
    String::from_utf8(bytes).map_err(|_| "invalid_utf8")
}

fn hex(value: &str) -> String {
    value
        .as_bytes()
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

fn number<T: std::str::FromStr>(value: &str) -> Result<T> {
    value.parse().map_err(|_| "invalid_integer")
}

impl SaveSnapshot {
    pub fn from_exchange(input: &str) -> Result<Self> {
        let mut lines = input.lines();
        if lines.next() != Some("TFD-SAVE/1") {
            return Err("exchange_version");
        }
        let mut value = Self {
            accounts: vec![],
            characters: vec![],
            selections: vec![],
        };
        for line in lines {
            let fields: Vec<_> = line.split('\t').collect();
            match fields.as_slice() {
                ["A", uid, name, created] => value.accounts.push(Account {
                    uid: number(uid)?,
                    name: unhex(name)?,
                    created_at: unhex(created)?,
                }),
                [
                    "C",
                    uid,
                    owner,
                    template,
                    exp,
                    level,
                    max,
                    reset,
                    state,
                    rev,
                    updated,
                ] => {
                    value.characters.push(Character {
                        uid: number(uid)?,
                        account_uid: number(owner)?,
                        template_id: number(template)?,
                        exp: number(exp)?,
                        level: number(level)?,
                        max_level: number(max)?,
                        reset_count: number(reset)?,
                        state_json: unhex(state)?,
                        revision: number(rev)?,
                        updated_at: unhex(updated)?,
                    });
                }
                ["S", owner, character] => value.selections.push(Selection {
                    account_uid: number(owner)?,
                    character_uid: number(character)?,
                }),
                _ => return Err("exchange_columns"),
            }
        }
        value.validate()?;
        Ok(value)
    }

    pub fn validate(&self) -> Result<()> {
        let mut accounts = BTreeSet::new();
        for a in &self.accounts {
            if a.uid <= 0 || a.name.is_empty() || !accounts.insert(a.uid) {
                return Err("invalid_or_duplicate_account");
            }
        }
        let mut characters = BTreeSet::new();
        let mut owned = BTreeSet::new();
        for c in &self.characters {
            if c.uid <= 0 || !characters.insert(c.uid) {
                return Err("invalid_or_duplicate_character");
            }
            if !accounts.contains(&c.account_uid) {
                return Err("character_account_missing");
            }
            if c.template_id < 0
                || c.exp < 0
                || c.level < 0
                || c.max_level < 0
                || c.reset_count < 0
                || c.revision < 0
            {
                return Err("character_range");
            }
            owned.insert((c.account_uid, c.uid));
        }
        let mut selected = BTreeSet::new();
        for s in &self.selections {
            if !selected.insert(s.account_uid) {
                return Err("duplicate_selection");
            }
            if !owned.contains(&(s.account_uid, s.character_uid)) {
                return Err("selection_owner_mismatch");
            }
        }
        Ok(())
    }

    pub fn to_exchange(&self) -> Result<String> {
        self.validate()?;
        let mut rows = vec!["TFD-SAVE/1".to_owned()];
        for a in &self.accounts {
            rows.push(format!(
                "A\t{}\t{}\t{}",
                a.uid,
                hex(&a.name),
                hex(&a.created_at)
            ));
        }
        for c in &self.characters {
            rows.push(format!(
                "C\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}",
                c.uid,
                c.account_uid,
                c.template_id,
                c.exp,
                c.level,
                c.max_level,
                c.reset_count,
                hex(&c.state_json),
                c.revision,
                hex(&c.updated_at)
            ));
        }
        for s in &self.selections {
            rows.push(format!("S\t{}\t{}", s.account_uid, s.character_uid));
        }
        Ok(rows.join("\n") + "\n")
    }
}
