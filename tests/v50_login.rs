use gpw_offline_core::v50_login::*;

include!("fixtures/v50_login_sample.rs");
#[allow(dead_code)]
#[path = "../rust/login_wire.rs"]
mod existing_login_validator;

fn unhex(value: &str) -> Vec<u8> {
    (0..value.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&value[i..i + 2], 16).unwrap())
        .collect()
}

#[test]
fn real_70_byte_body_matches_all_72_reply_bytes_and_carries_ticket_forward() {
    let input = unhex(INPUT_HEX);
    let expected = unhex(RESPONSE_HEX);
    assert_eq!(input.len(), 70);
    assert_eq!(expected.len(), 72);
    let info = decode_login_body(&input).unwrap();
    // Independent field oracle: reflected M1LoginResponseInfo order + supplied bytes.
    assert_eq!(info.login_result_type, 1);
    assert_eq!(info.game_server_addr, "127.0.0.1");
    assert_eq!(info.port, 1800);
    assert_eq!(info.game_server_index, 1);
    assert_eq!(info.game_server_version, "");
    assert_eq!(
        info.session_token,
        "mX3CPiP2Hc9GH2OLyb32a57yJ3gi9ZgzGAtCxPvLGr8"
    );
    assert_eq!(info.account_uid, 1);
    assert_eq!(info.account_name, "demo");
    assert!(info.forced_cross_play_off);
    assert_eq!(info.queue_number, 0);
    assert_eq!(encode_login_body(&info).unwrap(), input);
    let (id, response) = decode_login_reply(&expected).unwrap();
    assert_eq!(id, 2);
    assert_eq!(response, info);
    assert_eq!(encode_login_reply(id, &info).unwrap(), expected);
    let next = encode_client_login_body(&info, "").unwrap();
    let (ticket, link) = decode_client_login_body(&next).unwrap();
    assert_eq!(ticket, info.session_token);
    assert_eq!(link, "");
    existing_login_validator::client_login(&next).unwrap();
    assert!(existing_login_validator::login_request(&input).is_err());
    println!(
        "real input=70 B -> 10 response fields -> exact RPC reply=72 B; request_id=2, procedure=1, AccountUid=1"
    );
    println!(
        "received ticket {} B -> ClientService.1003 body -> existing client_login validator: accepted; no session authentication claimed",
        ticket.len()
    );
}

#[test]
fn incomplete_or_malformed_real_login_bodies_are_rejected() {
    let input = unhex(INPUT_HEX);
    for end in 0..input.len() {
        assert!(decode_login_body(&input[..end]).is_err(), "cut={end}");
    }
    let mut tail = input.clone();
    tail.push(0);
    assert_eq!(decode_login_body(&tail), Err("body_trailing_bytes"));
    let mut bad_bool = input.clone();
    bad_bool[68] = 2;
    assert_eq!(decode_login_body(&bad_bool), Err("body_invalid_bool"));
    let mut bad_terminator = input;
    bad_terminator[11] = 1;
    assert_eq!(
        decode_login_body(&bad_terminator),
        Err("body_string_terminator")
    );
    let mut wrong_proc = unhex(RESPONSE_HEX);
    wrong_proc[1] = 4;
    assert_eq!(decode_login_reply(&wrong_proc), Err("reply_procedure"));
    println!(
        "70 truncations, trailing bytes, invalid boolean, missing terminator and wrong procedure: rejected"
    );
}

#[test]
fn next_process_carries_unicode_link_and_rejects_truncated_ticket() {
    let info = decode_login_body(&unhex(INPUT_HEX)).unwrap();
    let next = encode_client_login_body(&info, "中").unwrap();
    assert!(next.ends_with(&[3, 0x2d, 0x4e, 0, 0]));
    existing_login_validator::client_login(&next).unwrap();
    let (ticket, link) = decode_client_login_body(&next).unwrap();
    assert_eq!(ticket, info.session_token);
    assert_eq!(link, "中");
    for end in 0..next.len() {
        assert!(decode_client_login_body(&next[..end]).is_err());
    }
    let mut no_ticket = info;
    no_ticket.session_token.clear();
    assert_eq!(
        encode_client_login_body(&no_ticket, ""),
        Err("empty_session_token")
    );
    println!(
        "explicit UTF-16 AccountLinkInfo survives ticket handoff; incomplete bodies and missing ticket rejected"
    );
}
