use crate::content;
use gpw_offline_core::{
    Store,
    snapshot::{Character, Roster, read_gpw_roster},
};
use std::{
    path::Path,
    sync::{Arc, Mutex},
};

pub struct ProfileConfig<'a> {
    pub owner: &'a str,
    pub game_root: &'a Path,
    pub source: ProfileSource,
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum ProfileSource {
    Saved,
    ApprovedSnapshot,
    New,
}

// GPW assigns instance IDs locally. Only the template and level cap are build facts.
fn new_profile() -> Roster {
    Roster {
        selected: 1,
        characters: vec![Character {
            uid: 1,
            template: 101000023,
            level: 2,
            exp: 0,
            max_level: 40,
            resets: 0,
            revision: 0,
        }],
    }
}

pub struct Characters {
    owner: String,
    binding: String,
    roster: Arc<Roster>,
    store: Mutex<Store>,
}

impl Characters {
    pub fn open(
        config: ProfileConfig<'_>,
        public_key: &str,
        registry: &Path,
    ) -> Result<Self, String> {
        let owner = config.owner;
        if content::identify(config.game_root)? != content::TARGET {
            return Err("character_content_unavailable_for_build".into());
        }
        let mut journal = registry.as_os_str().to_owned();
        journal.push(".characters.gpw");
        let journal = Path::new(&journal);
        let mut store = if config.source != ProfileSource::Saved {
            Store::open(journal)?
        } else {
            Store::open_existing(journal).map_err(|e| {
                if e == "journal_missing" {
                    "owned_roster_missing".to_string()
                } else {
                    e
                }
            })?
        };
        let binding = format!("{}:{owner}:{public_key}", content::TARGET);
        let roster = match store.saved_roster(&binding) {
            Some(saved) => {
                if saved.as_ref() != &new_profile() {
                    if config.source == ProfileSource::New {
                        return Err("character_profile_exists".into());
                    }
                    content::check_player_templates(&saved)?;
                }
                saved
            }
            None => {
                let initial = match config.source {
                    ProfileSource::Saved => return Err("owned_roster_missing".into()),
                    ProfileSource::New => {
                        if store.character_selection(&binding)?.is_some() {
                            return Err("existing_selection_requires_import".into());
                        }
                        new_profile()
                    }
                    ProfileSource::ApprovedSnapshot => {
                        let roster = read_gpw_roster()?;
                        content::check_player_templates(&roster)?;
                        roster
                    }
                };
                store.import_roster(&binding, &initial)?;
                store.saved_roster(&binding).ok_or("roster_import_failed")?
            }
        };
        Ok(Self {
            owner: owner.to_owned(),
            binding,
            roster,
            store: Mutex::new(store),
        })
    }

    fn character(&self, uid: i64) -> Result<&Character, &'static str> {
        self.roster
            .characters
            .iter()
            .find(|c| c.uid == uid)
            .ok_or("character_not_owned")
    }

    pub fn request(&self, account: &str, fields: &[&str]) -> Result<String, &'static str> {
        if account != self.owner {
            return Err("character_profile_unassigned");
        }
        let mut store = self
            .store
            .lock()
            .map_err(|_| "character_storage_unavailable")?;
        let (revision, selected) = store
            .character_selection(&self.binding)
            .map_err(|_| "character_storage_unavailable")?
            .unwrap_or((0, self.roster.selected));
        match fields {
            ["characters"] => {
                let list = self
                    .roster
                    .characters
                    .iter()
                    .map(|c| format!("{}:{}:{}", c.uid, c.template, c.level))
                    .collect::<Vec<_>>()
                    .join(",");
                Ok(format!("characters\t{revision}\t{selected}\t{list}"))
            }
            ["character", rest @ ..] => {
                let uid = match rest {
                    [] => selected,
                    [uid] => uid.parse::<i64>().map_err(|_| "invalid_character_uid")?,
                    _ => return Err("unsupported_operation"),
                };
                let c = self.character(uid)?;
                Ok(format!(
                    "character\t{revision}\t{}\t{}\t{}\t{}\t{}\t{}\t{}",
                    c.uid, c.template, c.level, c.exp, c.max_level, c.resets, c.revision
                ))
            }
            ["select-character", expected, uid] => {
                let expected = expected.parse::<u64>().map_err(|_| "invalid_revision")?;
                let uid = uid.parse::<i64>().map_err(|_| "invalid_character_uid")?;
                self.character(uid)?;
                if selected == uid && revision == expected {
                    return Ok(format!("selection\t{revision}\t{uid}"));
                }
                store
                    .select_character(&self.binding, expected, uid)
                    .map_err(|e| match e.as_str() {
                        "revision_conflict" => "revision_conflict",
                        "revision_exhausted" => "revision_exhausted",
                        _ => "character_storage_unavailable",
                    })
            }
            _ => Err("unsupported_operation"),
        }
    }
}
