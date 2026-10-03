use source_contract::{Engine, Lookups, Steps, Val};

fn read(input: &str, options: &str) -> Result<Val, source_contract::Rejected> {
    let contract = format!("read:\n  format: json\n  tables:\n    rows:\n      each: .\n      columns:\n        value: {{ integer: {{ path: value{options} }} }}");
    let engine = Engine::from_yaml(&contract, Steps::new())?;
    Ok(engine.read(input.as_bytes(), &Lookups::new())?.tables["rows"][0]["value"].clone())
}

#[test]
fn integers_retain_precision_and_json_source_kinds() {
    for (input, expected) in [("9007199254740993", 9007199254740993),
        ("9223372036854775807", i64::MAX), ("-9223372036854775808", i64::MIN),
        ("1.9", 1), ("-1.9", -1), ("0.9", 0), ("true", 1), ("false", 0),
        (r#"" +１_٢ ""#, 12), (r#""-٠٠١""#, -1)] {
        assert_eq!(read(&format!(r#"{{"value":{input}}}"#), "").unwrap(), Val::Int(expected));
    }
    assert_eq!(read(r#"{"value":"1.9"}"#, ", on_invalid: null").unwrap(), Val::Null);
}

#[test]
fn integer_boolean_output_uses_truncated_integer_not_float_truthiness() {
    for (input, expected) in [("0.9", false), ("-0.9", false), ("1.9", true),
        ("false", false), ("true", true), (r#""０_０""#, false),
        ("18446744073709551615", true), ("1e300", true)] {
        assert_eq!(read(&format!(r#"{{"value":{input}}}"#), ", as: boolean").unwrap(), Val::Bool(expected));
    }
}

#[test]
fn invalid_missing_and_overflow_policies_are_distinct() {
    for input in [r#"{"value":"bad"}"#, r#"{"value":[]}"#, r#"{"value":{}}"#,
        r#"{"value":"1__2"}"#, r#"{"value":"_1"}"#, r#"{"value":"1_"}"#,
        r#"{"value":"²"}"#, r#"{"value":""}"#] {
        assert_eq!(read(input, "").unwrap_err().code, "invalid_value");
        assert_eq!(read(input, ", on_invalid: null").unwrap(), Val::Null);
        assert_eq!(read(input, ", as: boolean, default: false, on_invalid: default").unwrap(), Val::Bool(false));
    }
    for input in [r#"{}"#, r#"{"value":null}"#] {
        assert_eq!(read(input, ", default: 9").unwrap(), Val::Int(9));
        assert_eq!(read(input, ", as: boolean, default: false").unwrap(), Val::Bool(false));
    }
    for input in ["9223372036854775808", "-9223372036854775809", "9.223372036854776e18", "1e300"] {
        let json = format!(r#"{{"value":{input}}}"#);
        assert_eq!(read(&json, "").unwrap_err().code, "integer_overflow");
        assert_eq!(read(&json, ", on_overflow: null").unwrap(), Val::Null);
        assert_eq!(read(&json, ", default: 9, on_overflow: default").unwrap(), Val::Int(9));
    }
    assert_eq!(read(r#"{"value":-9.223372036854776e18}"#, "").unwrap(), Val::Int(i64::MIN));
}

#[test]
fn malformed_integer_contracts_are_refused() {
    for options in [", as: text", ", as: true", ", default: 1.5", ", as: boolean, default: 0",
        ", default: true", ", from: typo", ", on_invalid: false", ", on_overflow: ignore",
        ", as: boolean, on_overflow: null", ", misspelled: true"] {
        assert_eq!(read("{}", options).unwrap_err().code, "contract");
    }
}

#[test]
fn decimal_digit_table_matches_python_312_and_has_no_saturation() {
    assert_eq!(unicode_general_category::UNICODE_VERSION, (15, 0, 0));
    let digits = "9".repeat(4301);
    assert_eq!(read(&format!(r#"{{"value":"{digits}"}}"#), ", on_invalid: null").unwrap(), Val::Null);
    assert_eq!(read(&format!(r#"{{"value":"{}"}}"#, "0".repeat(4300)), "").unwrap(), Val::Int(0));
    assert_eq!(read(r#"{"value":"9223372036854775808a"}"#, ", on_invalid: null").unwrap(), Val::Null);
}
