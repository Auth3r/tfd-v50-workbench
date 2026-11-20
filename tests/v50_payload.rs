use gpw_offline_core::v50_payload::*;

include!("fixtures/v50_payload_sample.rs");

fn unhex(value: &str) -> Vec<u8> {
    (0..value.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&value[i..i + 2], 16).unwrap())
        .collect()
}

fn pairs() -> Vec<(&'static str, &'static str, usize)> {
    vec![
        (BODY_0_HEX, PAYLOAD_0_HEX, 4),
        (BODY_1_HEX, PAYLOAD_1_HEX, 5),
        (BODY_2_HEX, PAYLOAD_2_HEX, 223),
        (BODY_3_HEX, PAYLOAD_3_HEX, 322),
        (BODY_4_HEX, PAYLOAD_4_HEX, 3869),
        (BODY_5_HEX, PAYLOAD_5_HEX, 322),
    ]
}

#[test]
fn real_captured_pairs_reproduce_on_wire_bytes_exactly() {
    let mut checked = 0usize;
    for (body_hex, payload_hex, expected_len) in pairs() {
        let body = unhex(body_hex);
        let payload = unhex(payload_hex);
        assert_eq!(body.len(), expected_len, "fixture body length drifted");
        assert_eq!(payload.len(), expected_len, "fixture payload length drifted");
        assert_eq!(wrap(&body), payload, "wrap(body) != captured payload");
        assert_eq!(unwrap(&payload), body, "unwrap(payload) != captured body");
        checked += 1;
    }
    assert_eq!(checked, 6);
    println!("6 real pairs: wrap(body) == captured payload bytes, both directions");
}

#[test]
fn two_independent_captures_agree_on_the_322_byte_frame() {
    // seq=12 and seq=19 come from two separate captures of the same reply.
    assert_eq!(BODY_3_HEX, BODY_5_HEX);
    assert_eq!(PAYLOAD_3_HEX, PAYLOAD_5_HEX);
    assert_eq!(wrap(&unhex(BODY_3_HEX)), unhex(PAYLOAD_5_HEX));
    println!("two captures: identical body and payload for the 322-byte reply");
}

#[test]
fn key_is_thirty_printable_ascii_bytes_and_cycles() {
    assert_eq!(KEY_LEN, 30);
    assert!(KEY.iter().all(|b| (0x21..=0x7e).contains(b)));
    // Cycle: byte 30 reuses KEY[0], byte 31 reuses KEY[1].
    let body: Vec<u8> = vec![0u8; 61];
    let payload = wrap(&body);
    for i in 0..61 {
        assert_eq!(payload[i], KEY[i % 30]);
    }
    println!("key: 30 printable bytes, period confirmed at offset 30 and 60");
}

#[test]
fn length_is_preserved_and_empty_body_stays_empty() {
    for len in [0usize, 1, 29, 30, 31, 255, 4096] {
        let body = vec![0x5au8; len];
        assert_eq!(wrap(&body).len(), len);
        assert_eq!(unwrap(&wrap(&body)), body);
    }
    assert!(wrap(&[]).is_empty());
}

#[test]
fn single_byte_corruption_in_body_changes_exactly_one_payload_byte() {
    let body = unhex(BODY_3_HEX);
    let payload = unhex(PAYLOAD_3_HEX);
    let mut mutated = body.clone();
    mutated[232] ^= 0x01;
    let got = wrap(&mutated);
    let diffs: Vec<usize> = (0..payload.len()).filter(|&i| got[i] != payload[i]).collect();
    assert_eq!(diffs, vec![232]);
    println!("negative control: 1 body byte flipped -> exactly 1 payload byte differs at 232");
}
