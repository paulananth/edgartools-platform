use source_contract::json_sequence::{scan, Limits, RecordEncoding};
use source_contract::Rejected;

fn limits() -> Limits { Limits { max_bytes: 1 << 20, max_record: 4096, max_records: 100, max_depth: 64, min_integer: i64::MIN, record_encoding: RecordEncoding::Native } }

#[test]
fn emits_exact_typed_objects_in_order_and_verifies_eof() {
    let body = br#"{"records":[{"n":9223372036854775807,"flag":true,"text":"9223372036854775808","empty":[],"nested":{"null":null}},{"n":-9223372036854775808,"float":1.25}]}"#;
    let mut rows = Vec::new();
    let stats = scan(&body[..], "records", limits(), |row, ordinal| { rows.push((ordinal, row)); Ok(()) }).unwrap();
    assert_eq!(stats.records, 2);
    assert_eq!(stats.bytes, body.len());
    assert_eq!(rows[0].0, 0);
    assert_eq!(rows[1].0, 1);
    assert_eq!(rows[0].1["n"].as_i64(), Some(i64::MAX));
    assert_eq!(rows[0].1["flag"].as_bool(), Some(true));
    assert_eq!(rows[1].1["n"].as_i64(), Some(i64::MIN));
    assert!(scan(&br#"{"records":[]}"#[..], "records", limits(), |_, _| panic!()).is_ok());
}

#[test]
fn retains_captured_object_order_at_every_depth() {
    let body = br#"{"records":[{"z":1,"a":2,"nested":{"y":3,"b":4},"array":[{"q":1,"c":2}]}]}"#;
    scan(&body[..], "records", limits(), |row, _| {
        assert_eq!(row.as_object().unwrap().keys().map(String::as_str).collect::<Vec<_>>(), ["z", "a", "nested", "array"]);
        assert_eq!(row["nested"].as_object().unwrap().keys().map(String::as_str).collect::<Vec<_>>(), ["y", "b"]);
        assert_eq!(row["array"][0].as_object().unwrap().keys().map(String::as_str).collect::<Vec<_>>(), ["q", "c"]);
        Ok(())
    }).unwrap();
}

#[test]
fn rejects_duplicate_keys_bad_shapes_numbers_depth_and_trailing_data() {
    for body in [r#"{}"#, r#"[]"#, r#"{"other":[]}"#, r#"{"records":{},"x":0}"#,
                 r#"{"records":[null]}"#, r#"{"records":[[]]}"#, r#"{"records":[],"records":[]}"#,
                 r#"{"records":[{"a":1,"a":2}]}"#, r#"{"records":[{"nested":{"a":1,"a":2}}]}"#,
                 r#"{"records":[{"n":9223372036854775808}]}"#, r#"{"records":[{"n":18446744073709551616}]}"#,
                 r#"{"records":[{"n":-9223372036854775809}]}"#, r#"{"records":[{"n":1e400}]}"#,
                 r#"{"records":[]} null"#, r#"{"records":[{}]"#] {
        assert!(scan(body.as_bytes(), "records", limits(), |_, _| Ok(())).is_err(), "{body}");
    }
    let small = Limits { max_depth: 1, ..limits() };
    assert!(scan(&br#"{"records":[{"a":{"b":1}}]}"#[..], "records", small, |_, _| Ok(())).is_err());
}

#[test]
fn bounds_raw_and_encoded_bytes_before_a_large_record_can_escape() {
    let large = format!(r#"{{"records":[{{"text":"{}"}}]}}"#, "x".repeat(200_000));
    let mut emitted = 0;
    let error = scan(large.as_bytes(), "records", limits(), |_, _| { emitted += 1; Ok(()) }).unwrap_err();
    assert_eq!(emitted, 0);
    assert_eq!(error.code, "limit_exceeded");
    let small = Limits { max_record: 2, ..limits() };
    assert!(scan(&br#"{"records":[{"a":1}]}"#[..], "records", small, |_, _| Ok(())).is_err());
    let small = Limits { max_bytes: 4, ..limits() };
    assert_eq!(scan(&br#"{"records":[]}"#[..], "records", small, |_, _| Ok(())).unwrap_err().code, "limit_exceeded");
}

#[test]
fn bounds_record_count_and_preserves_consumer_refusal() {
    let small = Limits { max_records: 1, ..limits() };
    let mut emitted = 0;
    assert!(scan(&br#"{"records":[{},{}]}"#[..], "records", small, |_, _| { emitted += 1; Ok(()) }).is_err());
    assert_eq!(emitted, 1);
    let error = scan(&br#"{"records":[{}]}"#[..], "records", limits(), |_, _| Err(Rejected::new("candidate_refused", "stop"))).unwrap_err();
    assert_eq!(error.code, "candidate_refused");
    let symmetric = Limits { min_integer: -i64::MAX, ..limits() };
    assert!(scan(&br#"{"records":[{"n":-9223372036854775808}]}"#[..], "records", symmetric, |_, _| Ok(())).is_err());
}

#[test]
fn python_record_encoding_preserves_float_byte_boundaries_explicitly() {
    let python = Limits { max_record: 11, record_encoding: RecordEncoding::Python, ..limits() };
    let native = Limits { max_record: 11, ..limits() };
    let fixed = br#"{"records":[{"v":0.00001}]}"#;
    assert!(scan(&fixed[..], "records", python, |_, _| Ok(())).is_ok());
    assert!(scan(&fixed[..], "records", native, |_, _| Ok(())).is_err());
    let exponent = br#"{"records":[{"v":1e-6}]}"#;
    let python = Limits { max_record: 10, ..python };
    let native = Limits { max_record: 10, ..native };
    assert!(scan(&exponent[..], "records", python, |_, _| Ok(())).is_err());
    assert!(scan(&exponent[..], "records", native, |_, _| Ok(())).is_ok());
}
