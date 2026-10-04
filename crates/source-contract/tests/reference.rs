use source_contract::{Engine, Lookups, Steps, Val};
const CONTRACT: &str = r#"
read:
  format: json
  references:
    places:
      DE: {iso: US-DE, flag: true, rank: 1}
      XX: {iso: null, flag: false, rank: 2}
  tables:
    rows:
      each: .
      columns:
        iso: {lookup: {reference: places, column: iso, key: {text: {path: code, case: upper}}}}
        flag: {lookup: {reference: places, column: flag, key: {text: {path: code, case: upper}}}}
        rank: {lookup: {reference: places, column: rank, key: {text: {path: code, case: upper}}}}
"#;
#[test]
fn frozen_reference_rows_preserve_scalar_types_and_explicit_null() {
    let engine = Engine::from_yaml(CONTRACT, Steps::new()).unwrap();
    let result = engine.read(br#"{"code":" de "}"#, &Lookups::new()).unwrap();
    let row = &result.tables["rows"][0];
    assert_eq!(row["iso"], Val::Str("US-DE".into()));
    assert_eq!(row["flag"], Val::Bool(true));
    assert_eq!(row["rank"], Val::Int(1));
    let result = engine.read(br#"{"code":"XX"}"#, &Lookups::new()).unwrap();
    assert_eq!(result.tables["rows"][0]["iso"], Val::Null);
    assert_eq!(result.tables["rows"][0]["flag"], Val::Bool(false));
}
#[test]
fn missing_key_is_explicit_and_key_conversion_is_never_implicit() {
    let strict = CONTRACT.replace("column: iso, key:", "column: iso, on_missing: error, key:");
    let engine = Engine::from_yaml(&strict, Steps::new()).unwrap();
    assert_eq!(engine.read(br#"{"code":"unknown"}"#, &Lookups::new()).unwrap_err().code, "lookup_missing");
    assert!(engine.read(br#"{"code":"XX"}"#, &Lookups::new()).is_ok());
    let typed = CONTRACT.replace("{text: {path: code, case: upper}}", "{integer: {path: code}}");
    let engine = Engine::from_yaml(&typed, Steps::new()).unwrap();
    assert_eq!(engine.read(br#"{"code":1}"#, &Lookups::new()).unwrap_err().code, "lookup_key");
    assert_eq!(engine.read(b"{}", &Lookups::new()).unwrap().tables["rows"][0]["iso"], Val::Null);
}
#[test]
fn invalid_reference_contracts_are_rejected_before_source_reading() {
    for (from, to) in [("reference: places", "reference: absent"), ("column: iso", "column: absent"),
                       ("iso: US-DE", "iso: [US-DE]"), ("DE: {iso", "1: {iso"),
                       ("rank: 1", "rank: 18446744073709551615"), ("case: upper", "case: yes"),
                       ("column: iso", "column: iso, on_missing: ignore"), ("column: iso", "column: iso, typo: true"),
                       ("{text: {path: code, case: upper}}", "{context: {name: undeclared}}") ] {
        assert_eq!(Engine::from_yaml(&CONTRACT.replace(from, to), Steps::new()).err().unwrap().code, "contract", "{to}");
    }
    let large = CONTRACT.replace("iso: US-DE", &format!("iso: {}", "a".repeat(4097)));
    assert!(Engine::from_yaml(&large, Steps::new()).is_err());
}
