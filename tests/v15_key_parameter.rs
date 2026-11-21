//! Owned artificial 30-byte parameter; STATIC_RULE_DERIVED, never captured V15 K.
use gpw_offline_core::protocol::v15_static::{TransportMode, transform_frame, transform_payload};

#[test]
fn owned_thirty_byte_parameter_wraps_at_30_and_plain_ignores_all_parameters() {
    // Independent pencil-and-paper vector: ff XOR 00..1d = ff..e2.
    let parameter = [
        0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24,
        25, 26, 27, 28, 29,
    ];
    let expected = [
        0xff, 0xfe, 0xfd, 0xfc, 0xfb, 0xfa, 0xf9, 0xf8, 0xf7, 0xf6, 0xf5, 0xf4, 0xf3, 0xf2, 0xf1,
        0xf0, 0xef, 0xee, 0xed, 0xec, 0xeb, 0xea, 0xe9, 0xe8, 0xe7, 0xe6, 0xe5, 0xe4, 0xe3, 0xe2,
        0xff, 0xfe, 0xfd, 0xfc, 0xfb, 0xfa, 0xf9, 0xf8, 0xf7, 0xf6, 0xf5, 0xf4, 0xf3, 0xf2, 0xf1,
        0xf0, 0xef, 0xee, 0xed, 0xec, 0xeb, 0xea, 0xe9, 0xe8, 0xe7, 0xe6, 0xe5, 0xe4, 0xe3, 0xe2,
        0xff, 0xfe, 0xfd, 0xfc, 0xfb,
    ];
    let input = [0xff; 65];
    assert_eq!(
        transform_payload(&input, TransportMode::Xor, &parameter).unwrap(),
        expected
    );
    let make_frame = |n: i32, marker: u16| {
        [
            n.to_le_bytes().as_slice(),
            (-n).to_le_bytes().as_slice(),
            marker.to_le_bytes().as_slice(),
            &input[..n as usize],
        ]
        .concat()
    };
    let first = make_frame(65, 0x7fff);
    let second = make_frame(7, 0x7fff);
    let stream = [first.as_slice(), second.as_slice()].concat();
    let before = stream.clone();
    let one = transform_frame(&stream, 0, &parameter).unwrap();
    let two = transform_frame(&stream, one.wire_bytes, &parameter).unwrap();
    assert_eq!(one.payload, expected);
    assert_eq!(two.payload, [0xff, 0xfe, 0xfd, 0xfc, 0xfb, 0xfa, 0xf9]);
    let plain = make_frame(65, 0x8000);
    for supplied in [&[][..], parameter.as_slice(), &[0xff; 30][..]] {
        assert_eq!(transform_frame(&plain, 0, supplied).unwrap().payload, input);
    }
    assert_eq!(stream, before);
    assert_eq!(input, [0xff; 65]);
}
