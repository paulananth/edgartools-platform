use source_contract::{Engine, Lookups, Row, Steps, Val};
const CONTRACT: &str = r#"
read:
  format: json
  tables:
    rows:
      each: .
      columns:
        record: {value: {path: .}}
        empty: {value: {path: empty}}
        absent: {value: {path: absent}}
"#;
#[test]
fn complete_json_keeps_scalar_types_empty_containers_and_reserved_keys() {
    let engine = Engine::from_yaml(CONTRACT, Steps::new()).unwrap();
    let result = engine.read(br#"{"empty":[],"object":{},"a":[null,true,1,1.0,{"$":"text","@x":"en","item":[false]}],"big":18446744073709551615}"#, &Lookups::new()).unwrap();
    let row=&result.tables["rows"][0];
    assert_eq!(row["empty"], Val::List(vec![]));
    assert_eq!(row["absent"], Val::Null);
    let Val::Map(record) = &row["record"] else { panic!() };
    assert_eq!(record["object"], Val::Map(Default::default()));
    assert_eq!(record["big"], Val::UInt(u64::MAX));
    let Val::List(array) = &record["a"] else { panic!() };
    assert_eq!(array[..4], [Val::Null, Val::Bool(true), Val::Int(1), Val::Float(1.0)]);
    let Val::Map(nested) = &array[4] else { panic!() };
    assert_eq!(nested["$"], Val::Str("text".into()));
    assert_eq!(nested["@x"], Val::Str("en".into()));
    assert_eq!(nested["item"], Val::List(vec![Val::Bool(false)]));
}
#[test]
fn exact_evidence_never_rounds_out_of_range_integers() {
    let engine=Engine::from_yaml(CONTRACT, Steps::new()).unwrap();
    for data in [b"{\"n\":-9223372036854775809}".as_slice(), b"{\"n\":18446744073709551616}".as_slice()] {
        assert_eq!(engine.read(data, &Lookups::new()).unwrap_err().code,"value_number_range");
    }
    let result=engine.read(br#"{"n":9007199254740993}"#, &Lookups::new()).unwrap();
    let Val::Map(record)=&result.tables["rows"][0]["record"] else {panic!()};
    assert_eq!(record["n"],Val::Int(9007199254740993));
}
#[test]
fn value_is_explicit_and_does_not_change_existing_text_contracts() {
    for (old,new) in [("format: json","format: xml"),("path: .","path: ., default: []"),("path: .","path: ., from: yes")] {
        assert!(Engine::from_yaml(&CONTRACT.replace(old,new),Steps::new()).is_err());
    }
    let repeated=CONTRACT.replace("path: empty","path: a.name");
    let engine=Engine::from_yaml(&repeated,Steps::new()).unwrap();
    assert_eq!(engine.read(br#"{"a":[{"name":"x"}]}"#,&Lookups::new()).unwrap_err().code,"repeated_path");
    let bounded=CONTRACT.replace("format: json","format: json\n  limits: {max_bytes: 2}");
    assert_eq!(Engine::from_yaml(&bounded,Steps::new()).unwrap().read(b"{\"a\":1}",&Lookups::new()).unwrap_err().code,"limit_exceeded");
}
#[test]
fn big_numbers_text_keeps_out_of_range_numbers_exactly_and_default_refuses() {
    let contract = |policy: &str| format!("read:\n  format: json\n  tables:\n    rows:\n      each: .\n      columns:\n        record: {{value: {{path: .{policy}}}}}\n        top: {{value: {{path: top, type: number{policy}}}}}\n");
    let text = Engine::from_yaml(&contract(", big_numbers: text"), Steps::new()).unwrap();
    for (lexeme, kind) in [("18446744073709551616", "beyond unsigned"), ("123456789012345678901234567890", "thirty digits"), ("-9223372036854775809", "large negative")] {
        let raw = format!(r#"{{"top":{lexeme},"units":{{"USD":[{{"val":{lexeme}}},{{"val":5}}]}}}}"#);
        let row = &text.read(raw.as_bytes(), &Lookups::new()).unwrap_or_else(|e| panic!("{kind}: {e:?}")).tables["rows"][0];
        let Val::Map(record) = &row["record"] else { panic!() };
        let Val::Map(units) = &record["units"] else { panic!() };
        let Val::List(facts) = &units["USD"] else { panic!() };
        let Val::Map(first) = &facts[0] else { panic!() };
        assert_eq!(first["val"], Val::Str(lexeme.into()), "{kind}");
        let Val::Map(second) = &facts[1] else { panic!() };
        assert_eq!(second["val"], Val::Int(5), "{kind}: in-range numbers keep their type");
        assert_eq!(row["top"], Val::Str(lexeme.into()), "{kind}");
    }
    let row = &text.read(br#"{"top":9223372036854775808}"#, &Lookups::new()).unwrap().tables["rows"][0];
    assert_eq!(row["top"], Val::UInt(9223372036854775808), "an unsigned 64-bit integer stays a number");
    let integer = Engine::from_yaml(&contract(", big_numbers: text").replace("type: number", "type: integer"), Steps::new()).unwrap();
    assert_eq!(integer.read(br#"{"top":18446744073709551616}"#, &Lookups::new()).unwrap().tables["rows"][0]["top"], Val::Str("18446744073709551616".into()));
    let row = &text.read(br#"{"top":"9223372036854775808"}"#, &Lookups::new());
    assert_eq!(row.as_ref().unwrap_err().code, "value_type", "a text value is still not a number");
    assert_eq!(text.read(br#"{"top":1e400}"#, &Lookups::new()).unwrap_err().code, "malformed", "a float beyond double range refuses when parsed, whatever the policy");
    let refuse = Engine::from_yaml(&contract(""), Steps::new()).unwrap();
    let explicit = Engine::from_yaml(&contract(", big_numbers: refuse"), Steps::new()).unwrap();
    for engine in [&refuse, &explicit] {
        assert_eq!(engine.read(br#"{"top":1,"x":18446744073709551616}"#, &Lookups::new()).unwrap_err().code, "value_number_range");
    }
    assert!(Engine::from_yaml(&contract(", big_numbers: round"), Steps::new()).is_err());
}
#[test]
fn decimals_text_keeps_every_decimal_as_its_json_digits_and_default_stays_float() {
    let contract = |policy: &str| format!("read:\n  format: json\n  tables:\n    rows:\n      each: .\n      columns:\n        record: {{value: {{path: .{policy}}}}}\n        top: {{value: {{path: top, type: number{policy}}}}}\n");
    let text = Engine::from_yaml(&contract(", decimals: text, big_numbers: text"), Steps::new()).unwrap();
    for (lexeme, kind) in [("1.23", "plain"), ("2.50", "trailing zero kept"), ("0.1000000000000000055511151231257827", "beyond double precision"),
                           ("12345678901234567.89", "beyond double digits"), ("-0.000001", "small negative"), ("1E2", "exponent spelling")] {
        let raw = format!(r#"{{"top":{lexeme},"units":{{"USD":[{{"val":{lexeme}}},{{"val":5}},{{"val":18446744073709551616}}]}}}}"#);
        let row = &text.read(raw.as_bytes(), &Lookups::new()).unwrap_or_else(|e| panic!("{kind}: {e:?}")).tables["rows"][0];
        let Val::Map(record) = &row["record"] else { panic!() };
        let Val::Map(units) = &record["units"] else { panic!() };
        let Val::List(facts) = &units["USD"] else { panic!() };
        let vals: Vec<&Val> = facts.iter().map(|f| { let Val::Map(f) = f else { panic!() }; &f["val"] }).collect();
        assert_eq!(vals, [&Val::Str(lexeme.into()), &Val::Int(5), &Val::Str("18446744073709551616".into())], "{kind}");
        assert_eq!(row["top"], Val::Str(lexeme.into()), "{kind}: a decimal kept as text is still a number");
    }
    let float = Engine::from_yaml(&contract(""), Steps::new()).unwrap();
    let explicit = Engine::from_yaml(&contract(", decimals: float"), Steps::new()).unwrap();
    for engine in [&float, &explicit] {
        assert_eq!(engine.read(br#"{"top":1.23}"#, &Lookups::new()).unwrap().tables["rows"][0]["top"], Val::Float(1.23), "default unchanged");
    }
    assert_eq!(text.read(br#"{"top":"1.23"}"#, &Lookups::new()).unwrap_err().code, "value_type", "a text value is still not a number");
    let integer = Engine::from_yaml(&contract(", decimals: text").replace("type: number", "type: integer"), Steps::new()).unwrap();
    assert_eq!(integer.read(br#"{"top":1.5}"#, &Lookups::new()).unwrap_err().code, "value_type", "a decimal is not an integer, as a float is not");
    assert_eq!(integer.read(br#"{"top":15}"#, &Lookups::new()).unwrap().tables["rows"][0]["top"], Val::Int(15));
    assert!(Engine::from_yaml(&contract(", decimals: round"), Steps::new()).is_err());
}
#[test]
fn decimals_text_keeps_digits_in_every_whole_document_route_and_framed_records_refuse() {
    let entries = "read:\n  format: json\n  tables:\n    rows:\n      each: {entries: {path: facts, key_field: name, value_field: body}}\n      columns:\n        val: {value: {path: body.val, decimals: text}}\n        top: {value: {path: top, from: document, decimals: text}}\n";
    let engine = Engine::from_yaml(entries, Steps::new()).unwrap();
    let row = &engine.read(br#"{"top":2.50,"facts":{"a":{"val":1E2}}}"#, &Lookups::new()).unwrap().tables["rows"][0];
    assert_eq!((&row["val"], &row["top"]), (&Val::Str("1E2".into()), &Val::Str("2.50".into())), "entries and from: document");
    let lines = Engine::from_yaml(&format!("{}", "read:\n  format: jsonl\n  tables:\n    rows:\n      each: record\n      columns:\n        val: {value: {path: val, decimals: text}}\n"), Steps::new()).unwrap();
    let rows = &lines.read(b"{\"val\":0.1000000000000000055511151231257827}\n{\"val\":2.50}\n", &Lookups::new()).unwrap().tables["rows"];
    assert_eq!((&rows[0]["val"], &rows[1]["val"]), (&Val::Str("0.1000000000000000055511151231257827".into()), &Val::Str("2.50".into())), "jsonl");
    let framed = Engine::from_yaml("read:\n  format: json\n  tables:\n    rows:\n      each: .\n      columns:\n        val: {value: {path: val, decimals: text}}\n", Steps::new()).unwrap();
    let refused = framed.read_json_value(serde_json::json!({"val": 2.5}), &Lookups::new(), &Row::new()).unwrap_err();
    assert_eq!(refused.code, "contract", "a framed record's numbers were already parsed: refuse rather than return float digits as exact");
}
