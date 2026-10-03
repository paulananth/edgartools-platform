use source_contract::{Engine, Lookups, Steps, Val};

fn read(value: &str, options: &str) -> Result<Val, source_contract::Rejected> {
    let contract = format!("read:\n  format: json\n  tables:\n    rows:\n      each: .\n      columns:\n        value: {{ date: {{ path: value, kind: calendar{options} }} }}\n");
    let engine = Engine::from_yaml(&contract, Steps::new())?;
    Ok(engine.read(value.as_bytes(), &Lookups::new())?.tables["rows"][0]["value"].clone())
}

#[test]
fn calendar_supports_iso_calendar_basic_and_week_dates() {
    for (input, expected) in [("2024-02-29", "2024-02-29"), ("20240229", "2024-02-29"),
        ("2020-W01-1", "2019-12-30"), ("2020W011", "2019-12-30"),
        ("2020-W01", "2019-12-30"), ("2020W01", "2019-12-30"),
        ("0001-01-01", "0001-01-01"), ("9999-12-31", "9999-12-31")] {
        assert_eq!(read(&format!(r#"{{"value":"{input}"}}"#), "").unwrap(), Val::Str(expected.into()));
    }
}

#[test]
fn explicit_prefix_matches_calendar_loader_and_is_unicode_safe() {
    assert_eq!(read(r#"{"value":"2024-02-29T12:00:00-05:00"}"#, ", prefix_length: 10").unwrap(), Val::Str("2024-02-29".into()));
    assert_eq!(read(r#"{"value":"2024-02-29suffix"}"#, ", prefix_length: 10").unwrap(), Val::Str("2024-02-29".into()));
    assert_eq!(read(r#"{"value":"🦀2024-02-29"}"#, ", prefix_length: 10, on_invalid: null").unwrap(), Val::Null);
}

#[test]
fn invalid_policy_does_not_coerce_or_trim_invalid_dates() {
    for value in ["2023-02-29", "2024-13-01", "2024-2-01", " 2024-01-01", "2024-01-01 ", "0000-01-01", "2021-W53-1", "2024-01-01T00:00:00Z", "garbage"] {
        let input = format!(r#"{{"value":"{value}"}}"#);
        assert_eq!(read(&input, "").unwrap_err().code, "invalid_value");
        assert_eq!(read(&input, ", on_invalid: null").unwrap(), Val::Null);
    }
}

#[test]
fn missing_defaults_differ_from_invalid_policy() {
    for input in [r#"{}"#, r#"{"value":null}"#, r#"{"value":""}"#] {
        assert_eq!(read(input, ", default: missing").unwrap(), Val::Str("missing".into()));
    }
    assert_eq!(read(r#"{"value":"garbage"}"#, ", default: missing, on_invalid: null").unwrap(), Val::Null);
}

#[test]
fn calendar_options_are_validated_and_do_not_change_instant_dates() {
    for options in [", prefix_length: 0", ", prefix_length: 33", ", prefix_length: true", ", prefix_length: 1.5", ", on_invalid: default"] {
        assert_eq!(read(r#"{}"#, options).unwrap_err().code, "contract");
    }
    for option in ["prefix_length: 10", "on_invalid: null", "kind: true", "kind: wrong"] {
        let contract = format!("read:\n  format: json\n  tables:\n    rows:\n      each: .\n      columns:\n        value: {{date: {{path: value, {option}}}}}");
        assert_eq!(Engine::from_yaml(&contract, Steps::new()).err().unwrap().code, "contract");
    }
}
