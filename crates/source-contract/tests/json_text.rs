use source_contract::{Engine, Lookups, Steps, Val};

const CONTRACT: &str = r#"
read:
  format: json
  tables:
    rows:
      columns:
        value: {text: {path: value, coerce: python, trim: false}}
"#;

#[test]
fn explicit_python_text_preserves_json_types_order_and_escapes() {
    let engine = Engine::from_yaml(CONTRACT, Steps::new()).unwrap();
    for (json, expected) in [
        (r#"true"#, "True"), (r#"false"#, "False"), ("-0", "0"),
        ("9007199254740993", "9007199254740993"), ("1e-5", "1e-05"), ("1e16", "1e+16"),
        ("-0.0", "-0.0"), ("0.0001", "0.0001"),
        ("1315490761899226.2", "1315490761899226.2"),
        (r#"{"z":true,"a":[null,"a'b","a\"b","a'\"b","\u000b"]}"#,
         "{'z': True, 'a': [None, \"a'b\", 'a\"b', 'a\\'\"b', '\\x0b']}"),
        (r#"{"$":"t","@x":"v","item":[1,2]}"#, "{'$': 't', '@x': 'v', 'item': [1, 2]}"),
        ("[]", "[]"), ("{}", "{}"),
    ] {
        let data = format!("{{\"value\":{json}}}");
        let reading = engine.read(data.as_bytes(), &Lookups::new()).unwrap();
        assert_eq!(reading.tables["rows"][0]["value"], Val::Str(expected.into()), "{json}");
    }
    assert_eq!(engine.read(br#"{"value":null}"#, &Lookups::new()).unwrap().tables["rows"][0]["value"], Val::Null);
}

#[test]
fn scalar_defaults_and_non_json_contracts_are_not_silently_reinterpreted() {
    let strict = Engine::from_yaml(&CONTRACT.replace("coerce: python, ", ""), Steps::new()).unwrap();
    assert_eq!(strict.read(br#"{"value":true}"#, &Lookups::new()).unwrap().tables["rows"][0]["value"], Val::Str("true".into()));
    assert_eq!(strict.read(br#"{"value":{}}"#, &Lookups::new()).unwrap_err().code, "invalid_path");
    for contract in [CONTRACT.replace("coerce: python", "coerce: true"),
                     CONTRACT.replace("coerce: python", "coerce: guess"),
                     CONTRACT.replace("format: json", "format: csv")] {
        assert!(Engine::from_yaml(&contract, Steps::new()).is_err());
    }
}
