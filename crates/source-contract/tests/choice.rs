use source_contract::{Engine, Lookups, Steps, Val};
fn contract(expr: &str) -> String {
    format!("read: {{format: json, tables: {{rows: {{each: '.', columns: {{v: {expr}}}}}}}}}")
}
fn read(expr: &str, raw: &[u8]) -> Result<Val, source_contract::Rejected> {
    Ok(Engine::from_yaml(&contract(expr), Steps::new()).unwrap().read(raw, &Lookups::new())?.tables["rows"][0]["v"].clone())
}
#[test]
fn coalesce_keeps_exact_falsey_values_in_null_mode() {
    let expr = "{coalesce: {values: [{value: {path: v}}, {const: {value: fallback}}], skip: 'null'}}";
    for (raw, expected) in [(b"{\"v\":false}".as_slice(), Val::Bool(false)), (b"{\"v\":0}", Val::Int(0)),
                           (b"{\"v\":\"\"}", Val::Str("".into())), (b"{\"v\":[]}", Val::List(vec![])),
                           (b"{\"v\":{}}", Val::Map(Default::default()))] {
        assert_eq!(read(expr, raw).unwrap(), expected);
    }
    assert_eq!(read(expr, b"{\"v\":null}").unwrap(), Val::Str("fallback".into()));
}
#[test]
fn coalesce_falsey_skips_only_empty_or_zero_values() {
    let expr = "{coalesce: {values: [{value: {path: v}}, {const: {value: fallback}}], skip: falsey}}";
    for raw in ["null", "false", "0", "0.0", "-0.0", "\"\"", "[]", "{}"] {
        assert_eq!(read(expr, format!("{{\"v\":{raw}}}").as_bytes()).unwrap(), Val::Str("fallback".into()));
    }
    for raw in ["true", "-1", "18446744073709551615", "\" \"", "[null]", "{\"k\":null}"] {
        assert_ne!(read(expr, format!("{{\"v\":{raw}}}").as_bytes()).unwrap(), Val::Str("fallback".into()));
    }
    assert_eq!(read("{coalesce: {values: [{const: {value: null}}, {const: {value: ''}}], skip: falsey}}", b"{}").unwrap(), Val::Null);
}
#[test]
fn choose_conditions_are_boolean_or_null_and_return_typed_values() {
    let expr = "{choose: {condition: {value: {path: flag}}, then: {value: {path: a}}, else: {value: {path: b}}}}";
    assert_eq!(read(expr, b"{\"flag\":true,\"a\":18446744073709551615,\"b\":false}").unwrap(), Val::UInt(u64::MAX));
    assert_eq!(read(expr, b"{\"flag\":false,\"a\":1,\"b\":false}").unwrap(), Val::Bool(false));
    assert_eq!(read(expr, b"{\"a\":1,\"b\":[]}").unwrap(), Val::List(vec![]));
    for flag in ["1", "\"true\"", "[]", "{}"] {
        assert_eq!(read(expr, format!("{{\"flag\":{flag}}}").as_bytes()).unwrap_err().code, "choose_condition");
    }
}
#[test]
fn lazy_calls_do_not_read_unselected_invalid_values_but_selected_refusals_propagate() {
    let raw = b"{\"bad\":18446744073709551616}";
    assert_eq!(read("{coalesce: {values: [{const: {value: ok}}, {value: {path: bad}}], skip: 'null'}}", raw).unwrap(), Val::Str("ok".into()));
    assert_eq!(read("{choose: {condition: {value: {path: flag}}, then: {value: {path: bad}}, else: {const: {value: ok}}}}", raw).unwrap(), Val::Str("ok".into()));
    assert_eq!(read("{choose: {condition: {value: {path: flag}}, then: {value: {path: bad}}, else: {const: {value: ok}}}}", br#"{"flag":true,"bad":18446744073709551616}"#).unwrap_err().code, "value_number_range");
}
#[test]
fn all_branches_and_bounded_argument_shapes_are_validated() {
    for expr in ["{coalesce: {values: [], skip: 'null'}}", "{coalesce: {values: [{const: {value: 1}}], skip: unknown}}",
                 "{coalesce: {values: [{const: {value: 1}}], skip: 'null', typo: 1}}",
                 "{coalesce: {values: [{const: {value: 1}}, {unknown: {}}], skip: 'null'}}",
                 "{choose: {condition: {const: {value: true}}, then: {const: {value: 1}}, else: {unknown: {}}}}",
                 "{choose: {condition: {const: {value: true}}, then: {const: {value: 1}}}}"] {
        assert!(Engine::from_yaml(&contract(expr), Steps::new()).is_err(), "{expr}");
    }
    let values = vec!["{const: {value: null}}"; 17].join(",");
    assert!(Engine::from_yaml(&contract(&format!("{{coalesce: {{values: [{values}], skip: 'null'}}}}")), Steps::new()).is_err());
    assert!(Engine::from_yaml(&contract("{choose: {condition: {const: {value: true}}, then: {const: {value: 1}}, else: {context: {name: absent}}}}"), Steps::new()).is_err());
}
#[test]
fn child_feature_and_reference_traversal_reaches_both_operators() {
    let expr = "{choose: {condition: {value: {path: flag}}, then: {coalesce: {values: [{text: {path: n, coerce: python}}], skip: 'null'}}, else: {const: {value: null}}}}";
    assert_eq!(read(expr, b"{\"flag\":true,\"n\":18446744073709551616}").unwrap(), Val::Str("18446744073709551616".into()));
    let expr = "{choose: {condition: {const: {value: true}}, then: {const: {value: ok}}, else: {coalesce: {values: [{lookup: {reference: absent, column: v, key: {const: {value: k}}}}], skip: 'null'}}}}";
    assert!(Engine::from_yaml(&contract(expr), Steps::new()).is_err());
}
#[test]
fn lookup_normalizes_after_fallback_with_default_exact_matching_preserved() {
    let contract = r#"read:
  format: json
  references: {places: {DE: {country: US}, X0: {country: GB}}}
  tables:
    rows:
      each: .
      columns:
        v:
          lookup:
            reference: places
            column: country
            trim: true
            case: upper
            key: {coalesce: {values: [{value: {path: state}}, {value: {path: country}}], skip: falsey}}
"#;
    let engine = Engine::from_yaml(contract, Steps::new()).unwrap();
    for (raw, result) in [(r#"{"state":" de ","country":"X0"}"#, Val::Str("US".into())),
                          (r#"{"state":" ","country":"X0"}"#, Val::Null),
                          (r#"{"state":"","country":" x0 "}"#, Val::Str("GB".into()))] {
        assert_eq!(engine.read(raw.as_bytes(), &Lookups::new()).unwrap().tables["rows"][0]["v"], result);
    }
    let exact = Engine::from_yaml(&contract.replace("trim: true", "trim: false").replace("case: upper", "case: preserve"), Steps::new()).unwrap();
    assert_eq!(exact.read(br#"{"state":" de "}"#, &Lookups::new()).unwrap().tables["rows"][0]["v"], Val::Null);
    for (old, new) in [("trim: true", "trim: 1"), ("case: upper", "case: title")] {
        assert!(Engine::from_yaml(&contract.replace(old, new), Steps::new()).is_err());
    }
}
