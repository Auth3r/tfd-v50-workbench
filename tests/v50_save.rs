use gpw_offline_core::v50_save::SaveSnapshot;

// Independent records, including preserved whitespace/Unicode and two accounts.
const ROWS: &str = "TFD-SAVE/1\nA\t1\t41\t54\nA\t2\t42\t55\nC\t7\t1\t42\t9007199254740993\t40\t40\t2\t7b20227a223a22e4b8ad22207d\t9\t56\nC\t8\t2\t43\t0\t1\t40\t0\t7b7d\t1\t57\nS\t1\t7\nS\t2\t8\n";

#[test]
fn preserves_all_columns_wide_integers_and_original_json_text() {
    let snapshot = SaveSnapshot::from_exchange(ROWS).unwrap();
    assert_eq!(snapshot.characters.len(), 2);
    let c = &snapshot.characters[0];
    assert_eq!((c.uid, c.account_uid, c.template_id), (7, 1, 42));
    assert_eq!(c.exp, 9_007_199_254_740_993);
    assert_eq!(
        (c.level, c.max_level, c.reset_count, c.revision),
        (40, 40, 2, 9)
    );
    assert_eq!(c.state_json, "{ \"z\":\"中\" }");
    assert_eq!(c.updated_at, "V");
    assert_eq!(snapshot.to_exchange().unwrap(), ROWS);
}

#[test]
fn refuses_cross_account_selection_duplicate_identity_and_missing_columns() {
    assert_eq!(
        SaveSnapshot::from_exchange(&ROWS.replace("S\t1\t7", "S\t1\t8")),
        Err("selection_owner_mismatch")
    );
    assert_eq!(
        SaveSnapshot::from_exchange(&ROWS.replace("C\t8\t2", "C\t7\t2")),
        Err("invalid_or_duplicate_character")
    );
    assert!(SaveSnapshot::from_exchange(&ROWS.replace("\t9007199254740993", "")).is_err());
    assert!(SaveSnapshot::from_exchange(&ROWS.replace("9007199254740993", "-1")).is_err());
    assert!(SaveSnapshot::from_exchange(&ROWS.replace("7b7d", "zz")).is_err());
}
