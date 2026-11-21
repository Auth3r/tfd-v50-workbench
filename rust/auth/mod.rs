//! Local GPW identities. The game wire decoder cannot construct an authenticated account.
mod accounts;
mod crypto;
pub use accounts::register;

use crate::character::{Characters, ProfileConfig, ProfileSource};
use crate::runtime::DeadlineStream;
use crypto::{PublicKey, hex, random, unhex};
use gpw_offline_core::{read_frame, session::Service, write_frame};
use std::{
    collections::BTreeMap,
    io::{self, Read},
    net::SocketAddr,
    path::Path,
    sync::{Mutex, MutexGuard},
    time::{Duration, Instant},
};

type Result<T> = std::result::Result<T, &'static str>;
const VERSION: &str = "GPW.auth/1";
const CHALLENGE_TTL: Duration = Duration::from_secs(30);
const HANDOFF_TTL: Duration = Duration::from_secs(30);
const ACTIVE_TTL: Duration = Duration::from_secs(15 * 60);
const IDLE: Duration = Duration::from_secs(30);

pub fn init_character_profile(
    registry: &Path,
    owner: &str,
    root: &Path,
) -> std::result::Result<(), String> {
    let accounts = accounts::Accounts::load(registry)?;
    let key = accounts.key(owner).ok_or("character_owner_unregistered")?;
    Characters::open(
        ProfileConfig {
            owner,
            game_root: root,
            source: ProfileSource::New,
        },
        &hex(key),
        registry,
    )?;
    Ok(())
}

pub struct Runtime {
    accounts: accounts::Accounts,
    sessions: Mutex<Sessions>,
    client: SocketAddr,
    characters: Option<Characters>,
}

impl Runtime {
    pub fn load(
        path: &Path,
        client: SocketAddr,
        profile: Option<ProfileConfig<'_>>,
    ) -> std::result::Result<Self, String> {
        let accounts = accounts::Accounts::load(path)?;
        let characters = if let Some(config) = profile {
            let key = accounts
                .key(config.owner)
                .ok_or("character_owner_unregistered")?;
            Some(Characters::open(config, &hex(key), path)?)
        } else {
            None
        };
        Ok(Self {
            accounts,
            characters,
            sessions: Mutex::default(),
            client,
        })
    }

    fn sessions(&self) -> Result<MutexGuard<'_, Sessions>> {
        let mut sessions = self
            .sessions
            .lock()
            .map_err(|_| "session_service_unavailable")?;
        let now = Instant::now();
        sessions.0.retain(|_, session| now < session.expires);
        Ok(sessions)
    }
}

enum Phase {
    Pending([u8; 32]),
    Active(u64), // server-assigned connection ID
}
struct Session {
    phase: Phase,
    expires: Instant,
}

#[derive(Default)]
struct Sessions(BTreeMap<String, Session>);

impl Sessions {
    fn issue(&mut self, account: &str, now: Instant) -> Result<String> {
        let handle = random()?;
        self.0.insert(
            account.to_owned(),
            Session {
                phase: Phase::Pending(handle),
                expires: now + HANDOFF_TTL,
            },
        );
        Ok(format!("gpwh1-{}", hex(&handle)))
    }

    fn attach(&mut self, account: &str, ticket: &str, connection: u64, now: Instant) -> Result<()> {
        let bytes = ticket
            .strip_prefix("gpwh1-")
            .and_then(unhex::<32>)
            .ok_or("session_invalid")?;
        let session = self.0.get_mut(account).ok_or("session_invalid")?;
        let Phase::Pending(expected) = &session.phase else {
            return Err("session_invalid");
        };
        let diff = expected
            .iter()
            .zip(bytes)
            .fold(0u8, |diff, (a, b)| diff | (a ^ b));
        if diff != 0 || now >= session.expires {
            return Err("session_invalid");
        }
        session.phase = Phase::Active(connection);
        session.expires = now + ACTIVE_TTL;
        Ok(())
    }

    fn active(&self, account: &str, connection: u64, now: Instant) -> bool {
        self.0.get(account).is_some_and(|s| {
            now < s.expires && matches!(s.phase, Phase::Active(owner) if owner == connection)
        })
    }

    fn disconnect(&mut self, account: &str, connection: u64) {
        if self
            .0
            .get(account)
            .is_some_and(|s| matches!(s.phase, Phase::Active(owner) if owner == connection))
        {
            self.0.remove(account);
        }
    }
}

struct Challenge {
    account: String,
    nonce: String,
    expires: Instant,
}

struct Peer<'a> {
    runtime: &'a Runtime,
    service: Service,
    connection: u64,
    last_id: u64,
    challenge: Option<Challenge>,
    attached: Option<String>,
}

impl Drop for Peer<'_> {
    fn drop(&mut self) {
        if let Some(account) = self.attached.as_ref() {
            if let Ok(mut sessions) = self.runtime.sessions() {
                sessions.disconnect(account, self.connection);
            }
        }
    }
}

impl Peer<'_> {
    fn dispatch(&mut self, fields: &[&str], deadline: Instant) -> Result<String> {
        let now = Instant::now();
        if now >= deadline {
            return Err("request_expired");
        }
        match (self.service, fields) {
            (Service::Login, ["challenge", account]) => {
                self.challenge = None;
                if self.runtime.accounts.key(account).is_none() {
                    return Err("authentication_failed");
                }
                let nonce = hex(&random()?);
                let response = format!("challenge\t{nonce}");
                self.challenge = Some(Challenge {
                    account: account.to_string(),
                    nonce,
                    expires: now + CHALLENGE_TTL,
                });
                Ok(response)
            }
            (Service::Login, ["1", proof]) => {
                let challenge = self.challenge.take().ok_or("challenge_required")?;
                let signature = unhex(proof).ok_or("authentication_failed")?;
                let account = &challenge.account;
                let key = PublicKey::import(
                    self.runtime
                        .accounts
                        .key(account)
                        .ok_or("authentication_failed")?,
                )?;
                let message = format!("{VERSION}\nLoginService.1\n{account}\n{}", challenge.nonce);
                key.verify(message.as_bytes(), &signature)?;
                let mut sessions = self.runtime.sessions()?;
                let now = Instant::now();
                if now >= challenge.expires.min(deadline) {
                    return Err("challenge_expired");
                }
                let handoff = sessions.issue(account, now)?;
                Ok(format!(
                    "login\t{account}\t{}\t{handoff}",
                    self.runtime.client
                ))
            }
            (Service::Client, ["1003", account, handoff]) => {
                let mut sessions = self.runtime.sessions()?;
                let now = Instant::now();
                if now >= deadline {
                    return Err("request_expired");
                }
                if self
                    .attached
                    .as_deref()
                    .is_some_and(|name| sessions.active(name, self.connection, now))
                {
                    return Err("already_initialized");
                }
                sessions.attach(account, handoff, self.connection, now)?;
                self.attached = Some(account.to_string());
                Ok(format!("initialized\t{account}"))
            }
            (Service::Client, ["identity" | "logout"])
            | (Service::Client, ["character" | "characters" | "select-character", ..]) => {
                let account = self.attached.as_deref().ok_or("session_invalid")?;
                let mut sessions = self.runtime.sessions()?;
                let now = Instant::now();
                if now >= deadline {
                    return Err("request_expired");
                }
                if !sessions.active(account, self.connection, now) {
                    self.attached = None;
                    return Err("session_invalid");
                }
                match fields {
                    ["identity"] => Ok(format!("identity\t{account}")),
                    ["logout"] => {
                        sessions.disconnect(account, self.connection);
                        self.attached = None;
                        Ok("closed".into())
                    }
                    _ => {
                        let profiles = self
                            .runtime
                            .characters
                            .as_ref()
                            .ok_or("character_profile_unassigned")?;
                        profiles.request(account, fields)
                    }
                }
            }
            _ => Err("unsupported_operation"),
        }
    }

    fn reply(&mut self, request: &str, deadline: Instant) -> String {
        let fields: Vec<_> = request.splitn(6, '\t').collect();
        let [VERSION, id, op @ ..] = fields.as_slice() else {
            return format!("{VERSION}\t0\terror\tinvalid_request");
        };
        let Ok(id) = id.parse::<u64>() else {
            return format!("{VERSION}\t0\terror\tinvalid_request");
        };
        let result = if id <= self.last_id {
            Err("request_id_reused")
        } else {
            self.last_id = id;
            self.dispatch(op, deadline)
        };
        let body = result.unwrap_or_else(|e| format!("error\t{e}"));
        format!("{VERSION}\t{id}\t{body}")
    }
}

/// The caller has consumed the GPWR magic. Reuse the existing framed-text codec.
pub fn serve_peer(
    runtime: &Runtime,
    connection: u64,
    service: Service,
    stream: &mut DeadlineStream<'_>,
    until: Option<Instant>,
) -> io::Result<()> {
    let mut peer = Peer {
        runtime,
        service,
        connection,
        last_id: 0,
        challenge: None,
        attached: None,
    };
    let mut request = read_frame(&mut b"GPWR".as_slice().chain(&mut *stream));
    while let Some(text) = request.map_err(io::Error::other)? {
        stream.remaining()?;
        let response = peer.reply(&text, stream.deadline);
        write_frame(stream, &response).map_err(io::Error::other)?;
        let next = Instant::now() + IDLE;
        stream.deadline = until.map_or(next, |end| end.min(next));
        request = read_frame(stream);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn handoff_and_attached_sessions_expire_at_their_deadlines() {
        let now = Instant::now();
        let mut s = Sessions::default();
        let first = s.issue("alice", now).unwrap();
        assert_eq!(
            s.attach("alice", &first, 42, now + HANDOFF_TTL),
            Err("session_invalid")
        );
        let second = s.issue("alice", now).unwrap();
        s.attach("alice", &second, 42, now).unwrap();
        assert!(s.active("alice", 42, now + ACTIVE_TTL - Duration::from_millis(1)));
        assert!(!s.active("alice", 42, now + ACTIVE_TTL));
        assert!(s.attach("alice", &second, 43, now + ACTIVE_TTL).is_err());
    }
}
