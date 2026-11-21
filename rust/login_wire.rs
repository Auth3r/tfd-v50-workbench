//! Build-specific ordinary bodies. Field validation borrows only the frame;
//! no account, ticket, session token or signature value leaves this module.
use gpw_offline_core::protocol::v15_static::{
    TransportMode, Width, decode_signed, encode_signed, transform_payload,
};

type Result<T> = std::result::Result<T, &'static str>;

struct Reader<'a>(&'a [u8]);

impl<'a> Reader<'a> {
    fn take(&mut self, n: usize) -> Result<&'a [u8]> {
        let (bytes, rest) = self.0.split_at_checked(n).ok_or("body_truncated")?;
        self.0 = rest;
        Ok(bytes)
    }

    fn signed(&mut self, width: Width) -> Result<i64> {
        let (n, used) = decode_signed(self.0, width).map_err(|_| "body_invalid_integer")?;
        self.0 = &self.0[used..];
        Ok(n)
    }

    fn i32(&mut self) -> Result<i32> {
        Ok(self.signed(Width::W32)? as i32)
    }

    // Return only whether the decoded text is nonempty. The count includes
    // the terminator in bytes (ASCII) or 16-bit code units (UTF-16LE).
    fn text_present(&mut self) -> Result<bool> {
        let count = self.i32()?;
        if count == 0 {
            return Ok(false);
        }
        if count > 0 {
            let bytes = self.take(count as usize)?;
            let text = bytes.strip_suffix(&[0]).ok_or("body_string_terminator")?;
            if !text.is_ascii() {
                return Err("body_string_encoding");
            }
            return Ok(!text.is_empty());
        }
        let n = (count.unsigned_abs() as usize)
            .checked_mul(2)
            .ok_or("body_string_size")?;
        let bytes = self.take(n)?;
        let text = bytes
            .strip_suffix(&[0, 0])
            .ok_or("body_string_terminator")?;
        let units = text
            .chunks_exact(2)
            .map(|u| u16::from_le_bytes([u[0], u[1]]));
        if char::decode_utf16(units).any(|c| c.is_err()) {
            return Err("body_string_encoding");
        }
        Ok(!text.is_empty())
    }

    fn boolean(&mut self) -> Result<()> {
        match self.take(1)?[0] {
            0 | 1 => Ok(()),
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

pub fn handshake(body: &[u8]) -> Result<()> {
    let mut r = Reader(body);
    let present = r.text_present()?;
    r.i32()?; // Value
    r.finish()?;
    if !present {
        return Err("empty_handshake_signature");
    }
    Ok(())
}

// LOGIN_REQUEST uses an ordinary reader with no object dictionary. i64
// goes through Reader.object_id's signed(64) branch in this case.
pub fn login_request(body: &[u8]) -> Result<()> {
    let mut r = Reader(body);
    r.text_present()?; // name
    r.take(1)?; // ExternalLinkerType
    for _ in 0..4 {
        r.text_present()?;
    } // ExternalLinkerData, CountryName, SignCountry, DeviceName
    r.i32()?; // OsType
    r.text_present()?; // OsName
    r.text_present()?; // OsLanguage
    r.take(1)?; // Locale
    r.text_present()?; // LoginPlatformId
    r.signed(Width::W64)?; // LoginPlatformUid, discarded
    r.take(1)?; // LoginPlatform
    let count = r.i32()?;
    if !(0..=4096).contains(&count) {
        return Err("body_region_count");
    }
    for _ in 0..count {
        r.text_present()?;
        let latency = f32::from_le_bytes(r.take(4)?.try_into().unwrap());
        if !latency.is_finite() {
            return Err("body_region_latency");
        }
    }
    for _ in 0..3 {
        r.boolean()?;
    } // CROSS_PLAY
    r.i32()?;
    r.i32()?;
    r.text_present()?; // PARTICIPATE
    r.i32()?;
    r.text_present()?;
    r.boolean()?; // Boosting
    r.i32()?; // Revision
    r.boolean()?; // IsCreator
    for _ in 0..3 {
        r.text_present()?;
    } // CHECKSUM
    r.i32()?; // XBoxAdditionalInfo
    r.finish()
}

pub fn client_login(body: &[u8]) -> Result<()> {
    let mut r = Reader(body);
    r.text_present()?; // Token: validate the wire structure without retaining the value.
    r.text_present()?; // AccountLinkInfo
    r.finish()
}

// The only response currently producible: Store.Missing in ClientService.1003.
// Use the received ID unchanged. There is no path here for login success.
pub fn missing_client_session(id: i32, mode: TransportMode, parameter: &[u8]) -> Result<Vec<u8>> {
    let mut payload = encode_signed(id.into(), Width::W32).map_err(|_| "reply_id")?;
    payload.extend(encode_signed(1003, Width::W16).map_err(|_| "reply_procedure")?);
    payload.extend(encode_signed(8, Width::W32).map_err(|_| "reply_result")?);
    let (marker, bytes) = match mode {
        TransportMode::Plain => (0x8000_u16, payload),
        TransportMode::Xor => (
            0x7fff,
            transform_payload(&payload, mode, parameter).map_err(|_| "reply_transport")?,
        ),
        TransportMode::Unknown(_) => return Err("reply_transport"),
    };
    let length = bytes.len() as i32;
    let mut frame = length.to_le_bytes().to_vec();
    frame.extend((-length).to_le_bytes());
    frame.extend(marker.to_le_bytes());
    frame.extend(bytes);
    Ok(frame)
}
