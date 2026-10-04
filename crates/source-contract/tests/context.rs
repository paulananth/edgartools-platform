use source_contract::{Engine, Lookups, Row, Steps, Val};

const CONTRACT: &str = "read:\n  format: json\n  context:\n    cik: {type: integer}\n    label: {type: text, max_bytes: 4}\n    flag: {type: boolean}\n    bound: {type: integer, nullable: true}\n  limits: {max_records: 3}\n  tables:\n    rows:\n      each: rows\n      take: {context: {name: bound}}\n      columns:\n        cik: {context: {name: cik}}\n        label: {context: {name: label}}\n        flag: {context: {name: flag}}\n        value: {text: {path: value}}\n        ordinal: {ordinal: {}}\n";
fn context(bound: Val) -> Row {
    [("cik", Val::Int(9007199254740993)), ("label", Val::Str("éé".into())), ("flag", Val::Bool(true)), ("bound", bound)]
        .into_iter().map(|(k,v)| (k.into(),v)).collect()
}

#[test]
fn context_keeps_exact_values_and_does_not_replace_document_fields() {
    let engine = Engine::from_yaml(CONTRACT, Steps::new()).unwrap();
    let rows = engine.read_with_context(br#"{"cik":5,"rows":[{"value":"first"},{"value":"second"}]}"#, &Lookups::new(), &context(Val::Null)).unwrap().tables.remove("rows").unwrap();
    assert_eq!(rows.len(), 2);
    assert_eq!(rows[0]["cik"], Val::Int(9007199254740993));
    assert_eq!(rows[0]["flag"], Val::Bool(true));
    assert_eq!(rows[1]["value"], Val::Str("second".into()));
    assert_eq!(rows[1]["ordinal"], Val::Int(2));
}

#[test]
fn first_n_matches_unlimited_positive_zero_and_negative_loader_bounds() {
    let engine = Engine::from_yaml(CONTRACT, Steps::new()).unwrap();
    for (bound, count) in [(Val::Null, 2), (Val::Int(1), 1), (Val::Int(0), 0), (Val::Int(-1), 0), (Val::Int(i64::MAX), 2)] {
        assert_eq!(engine.read_with_context(br#"{"rows":[{"value":"a"},{"value":"b"}]}"#, &Lookups::new(), &context(bound)).unwrap().tables["rows"].len(), count);
    }
    assert_eq!(engine.read_with_context(br#"{"rows":[{},{},{},{}]}"#, &Lookups::new(), &context(Val::Int(0))).unwrap_err().code, "limit_exceeded");
}

#[test]
fn declared_types_keys_nullability_and_utf8_bytes_fail_closed() {
    let engine = Engine::from_yaml(CONTRACT, Steps::new()).unwrap();
    for (name, value) in [("cik", Val::Bool(true)), ("cik", Val::Float(1.0)), ("cik", Val::Null), ("label", Val::Str("ééé".into())), ("flag", Val::Int(1)), ("bound", Val::Str("1".into()))] {
        let mut values = context(Val::Null); values.insert(name.into(), value);
        assert_eq!(engine.read_with_context(b"{}", &Lookups::new(), &values).unwrap_err().code, "invalid_context");
    }
    let mut values = context(Val::Null); values.remove("flag");
    assert_eq!(engine.read_with_context(b"{}", &Lookups::new(), &values).unwrap_err().code, "invalid_context");
    let mut values = context(Val::Null); values.insert("output".into(), Val::Str("elsewhere".into()));
    assert_eq!(engine.read_with_context(b"{}", &Lookups::new(), &values).unwrap_err().code, "invalid_context");
    assert_eq!(engine.read(b"{}", &Lookups::new()).unwrap_err().code, "invalid_context");
}

#[test]
fn malformed_context_or_take_contracts_fail_on_load_even_on_empty_documents() {
    for (from, to) in [("type: integer", "type: float"), ("nullable: true", "nullable: yes"), ("max_bytes: 4", "max_bytes: 4097"), ("max_bytes: 4", "max_bytes: 0"), ("name: cik", "name: absent"), ("name: cik", "name: cik, default: 1"), ("take: {context: {name: bound}}", "take: {context: {name: label}}"), ("take: {context: {name: bound}}", "take: {const: {value: true}}"), ("take: {context: {name: bound}}", "take: {text: {path: value}}"), ("type: boolean", "type: boolean, max_bytes: 4")] {
        assert!(Engine::from_yaml(&CONTRACT.replace(from,to), Steps::new()).is_err(), "{to}");
    }
}
