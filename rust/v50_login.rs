//! Offline LoginService.1 body codec. This does not authenticate a peer, issue
//! game sessions, or transform a body into an outer transport payload (M01c).
use crate::protocol::v15_static::{Width, decode_signed, encode_signed};

pub type Result<T> = std::result::Result<T, &'static str>;

#[derive(Clone, Eq, PartialEq)]
pub struct LoginResponseInfo {
    pub login_result_type: i32,
    pub game_server_addr: String,
    pub port: u16,
    pub game_server_index: i32,
    pub game_server_version: String,
    pub session_token: String,
    pub account_uid: i64,
    pub account_name: String,
    pub forced_cross_play_off: bool,
    pub queue_number: i64,
}

impl std::fmt::Debug for LoginResponseInfo {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("LoginResponseInfo")
            .field("login_result_type", &self.login_result_type)
            .field("game_server_addr", &self.game_server_addr)
            .field("port", &self.port)
            .field("game_server_index", &self.game_server_index)
            .field("game_server_version", &self.game_server_version)
            .field("session_token_bytes", &self.session_token.len())
            .field("account_uid", &self.account_uid)
            .field("account_name", &self.account_name)
            .field("forced_cross_play_off", &self.forced_cross_play_off)
            .field("queue_number", &self.queue_number)
            .finish()
    }
}

struct Reader<'a>(&'a [u8]);

impl<'a> Reader<'a> {
    fn take(&mut self, count: usize) -> Result<&'a [u8]> {
        let (value, rest) = self.0.split_at_checked(count).ok_or("body_truncated")?;
        self.0 = rest;
        Ok(value)
    }

    fn integer(&mut self, width: Width) -> Result<i64> {
        let (value, count) = decode_signed(self.0, width).map_err(|_| "body_invalid_integer")?;
        self.0 = &self.0[count..];
        Ok(value)
    }

    fn text(&mut self) -> Result<String> {
        let count = self.integer(Width::W32)? as i32;
        if count == 0 {
            return Ok(String::new());
        }
        if count > 0 {
            let value = self.take(count as usize)?;
            let text = value.strip_suffix(&[0]).ok_or("body_string_terminator")?;
            if !text.is_ascii() {
                return Err("body_string_encoding");
            }
            return String::from_utf8(text.to_vec()).map_err(|_| "body_string_encoding");
        }
        let bytes = (count.unsigned_abs() as usize)
            .checked_mul(2)
            .ok_or("body_string_size")?;
        let value = self.take(bytes)?;
        let text = value
            .strip_suffix(&[0, 0])
            .ok_or("body_string_terminator")?;
        String::from_utf16(
            &text
                .chunks_exact(2)
                .map(|u| u16::from_le_bytes([u[0], u[1]]))
                .collect::<Vec<_>>(),
        )
        .map_err(|_| "body_string_encoding")
    }

    fn boolean(&mut self) -> Result<bool> {
        match self.take(1)?[0] {
            0 => Ok(false),
            1 => Ok(true),
            _ => Err("body_invalid_bool"),
        }
    }

    fn finish(self) -> Result<()> {
        if self.0.is_empty() {
            Ok(())
        } else {
            Err("body_trailing_bytes")
        }
    }
}

fn integer(out: &mut Vec<u8>, value: i64, width: Width) -> Result<()> {
    out.extend(encode_signed(value, width).map_err(|_| "body_integer_range")?);
    Ok(())
}

fn text(out: &mut Vec<u8>, value: &str) -> Result<()> {
    if value.is_empty() {
        return integer(out, 0, Width::W32);
    }
    if value.is_ascii() {
        let count = value
            .len()
            .checked_add(1)
            .and_then(|n| i32::try_from(n).ok())
            .ok_or("body_string_size")?;
        integer(out, count.into(), Width::W32)?;
        out.extend(value.as_bytes());
        out.push(0);
    } else {
        let units: Vec<_> = value.encode_utf16().collect();
        let count = units
            .len()
            .checked_add(1)
            .and_then(|n| i32::try_from(n).ok())
            .ok_or("body_string_size")?;
        integer(out, -i64::from(count), Width::W32)?;
        for unit in units {
            out.extend(unit.to_le_bytes());
        }
        out.extend([0, 0]);
    }
    Ok(())
}

/// Fields follow the non-synthetic M1LoginResponseInfo descriptor order.
/// The handoff's 70-byte `req_hex` has this response-body layout, not the
/// M1LoginRequestInfo layout. No identity is authenticated by decoding it.
pub fn decode_login_body(body: &[u8]) -> Result<LoginResponseInfo> {
    let mut r = Reader(body);
    let value = LoginResponseInfo {
        login_result_type: r.integer(Width::W32)? as i32,
        game_server_addr: r.text()?,
        port: u16::try_from(r.integer(Width::W32)?).map_err(|_| "body_port_range")?,
        game_server_index: r.integer(Width::W32)? as i32,
        game_server_version: r.text()?,
        session_token: r.text()?,
        account_uid: r.integer(Width::W64)?,
        account_name: r.text()?,
        forced_cross_play_off: r.boolean()?,
        queue_number: r.integer(Width::W64)?,
    };
    r.finish()?;
    Ok(value)
}

pub fn encode_login_body(value: &LoginResponseInfo) -> Result<Vec<u8>> {
    let mut out = Vec::new();
    integer(&mut out, value.login_result_type.into(), Width::W32)?;
    text(&mut out, &value.game_server_addr)?;
    integer(&mut out, value.port.into(), Width::W32)?;
    integer(&mut out, value.game_server_index.into(), Width::W32)?;
    text(&mut out, &value.game_server_version)?;
    text(&mut out, &value.session_token)?;
    integer(&mut out, value.account_uid, Width::W64)?;
    text(&mut out, &value.account_name)?;
    out.push(u8::from(value.forced_cross_play_off));
    integer(&mut out, value.queue_number, Width::W64)?;
    Ok(out)
}

/// RPC envelope only; outer transport encoding remains outside this module.
pub fn encode_login_reply(request_id: i32, value: &LoginResponseInfo) -> Result<Vec<u8>> {
    if request_id < 0 {
        return Err("reply_id_range");
    }
    let mut out = Vec::new();
    integer(&mut out, request_id.into(), Width::W32)?;
    integer(&mut out, 1, Width::W16)?;
    out.extend(encode_login_body(value)?);
    Ok(out)
}

pub fn decode_login_reply(bytes: &[u8]) -> Result<(i32, LoginResponseInfo)> {
    let mut r = Reader(bytes);
    let id = r.integer(Width::W32)? as i32;
    if id < 0 {
        return Err("reply_id_range");
    }
    if r.integer(Width::W16)? != 1 {
        return Err("reply_procedure");
    }
    Ok((id, decode_login_body(r.0)?))
}

/// The caller supplies AccountLinkInfo explicitly; no unknown link value is
/// inferred. This carries the received ticket, not a newly authenticated one.
pub fn encode_client_login_body(
    value: &LoginResponseInfo,
    account_link_info: &str,
) -> Result<Vec<u8>> {
    if value.session_token.is_empty() {
        return Err("empty_session_token");
    }
    let mut out = Vec::new();
    text(&mut out, &value.session_token)?;
    text(&mut out, account_link_info)?;
    Ok(out)
}

pub fn decode_client_login_body(bytes: &[u8]) -> Result<(String, String)> {
    let mut r = Reader(bytes);
    let token = r.text()?;
    let link = r.text()?;
    r.finish()?;
    Ok((token, link))
}
