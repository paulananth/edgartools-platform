use source_contract::{Engine, Lookups, Steps, Val};
const CONTRACT: &str = r#"
read:
  format: json
  context:
    run: {type: text}
  references:
    places:
      DE: {country: US}
  tables:
    rows:
      each: .
      columns:
        record:
          object:
            fields:
              cik: {integer: {path: cik}}
              evidence: {value: {path: evidence}}
              business_address:
                object:
                  fields:
                    street: {text: {path: street, trim: false, null_if: [""]}}
                    country: {lookup: {reference: places, column: country, key: {text: {path: code}}}}
              origin:
                object:
                  fields:
                    run: {context: {name: run}}
                    ordinal: {ordinal: {}}
              empty: {object: {fields: {}}}
"#;
#[test]
fn nested_records_keep_exact_values_context_and_reference_results() {
    let engine = Engine::from_yaml(CONTRACT, Steps::new()).unwrap();
    let context = [("run".into(), Val::Str("trial".into()))].into();
    let result = engine.read_with_context(br#"{"cik":9007199254740993,"street":"  x  ","code":"DE","evidence":[true,null,18446744073709551615]}"#, &Lookups::new(), &context).unwrap();
    let Val::Map(record) = &result.tables["rows"][0]["record"] else { panic!() };
    assert_eq!(record["cik"], Val::Int(9007199254740993));
    assert_eq!(record["evidence"], Val::List(vec![Val::Bool(true), Val::Null, Val::UInt(u64::MAX)]));
    assert_eq!(record["empty"], Val::Map(Default::default()));
    assert_eq!(record["business_address"], Val::Map([("street".into(), Val::Str("  x  ".into())), ("country".into(), Val::Str("US".into()))].into()));
    assert_eq!(record["origin"], Val::Map([("run".into(), Val::Str("trial".into())), ("ordinal".into(), Val::Int(1))].into()));
}
#[test]
fn nested_contract_calls_are_validated_before_reading() {
    for (old, new) in [("name: run", "name: absent"), ("reference: places", "reference: absent"),
                       ("column: country", "column: absent"), ("fields: {}", "fields: [], typo: true"),
                       ("fields: {}", "fields: {1: {const: {value: x}}}"),
                       ("fields: {}", "fields: {'': {const: {value: x}}}"),
                       ("fields: {}", "fields: {x: {unknown: {}}}"),
                       ("format: json", "format: csv")] {
        assert!(Engine::from_yaml(&CONTRACT.replace(old, new), Steps::new()).is_err(), "{new}");
    }
    let fields = (0..129).map(|n| format!("f{n}: {{ordinal: {{}}}}")).collect::<Vec<_>>().join(", ");
    assert!(Engine::from_yaml(&CONTRACT.replace("fields: {}", &format!("fields: {{{fields}}}")), Steps::new()).is_err());
    let long = format!("fields: {{{}: {{ordinal: {{}}}}}}", "x".repeat(129));
    assert!(Engine::from_yaml(&CONTRACT.replace("fields: {}", &long), Steps::new()).is_err());
}
#[test]
fn nested_refusals_propagate_without_partial_records() {
    let engine = Engine::from_yaml(CONTRACT, Steps::new()).unwrap();
    let context = [("run".into(), Val::Str("trial".into()))].into();
    assert_eq!(engine.read_with_context(br#"{"cik":1,"evidence":18446744073709551616}"#, &Lookups::new(), &context).unwrap_err().code, "value_number_range");
    let strict = Engine::from_yaml(&CONTRACT.replace("column: country", "column: country, on_missing: error"), Steps::new()).unwrap();
    assert_eq!(strict.read_with_context(b"{}", &Lookups::new(), &context).unwrap_err().code, "lookup_missing");
}
#[test]
fn feature_detection_reaches_calls_and_skips_literals_inside_objects() {
    let json = "read: {format: json, tables: {rows: {each: '.', columns: {r: {object: {fields: {text: {text: {path: n, coerce: python}}}}}}}}}";
    let engine = Engine::from_yaml(json, Steps::new()).unwrap();
    assert_eq!(engine.read(br#"{"n":18446744073709551616}"#, &Lookups::new()).unwrap().tables["rows"][0]["r"],
               Val::Map([("text".into(), Val::Str("18446744073709551616".into()))].into()));
    let csv = "read: {format: csv, tables: {rows: {each: record, columns: {r: {object: {fields: {text: {text: {path: n}}, literal: {const: {value: {text: {coerce: python}, value: {path: '.'}}}}}}}}}}}";
    let engine = Engine::from_yaml(csv, Steps::new()).unwrap();
    let Val::Map(record) = &engine.read(b"n\nhello\n", &Lookups::new()).unwrap().tables["rows"][0]["r"] else {panic!()};
    assert_eq!(record["text"], Val::Str("hello".into()));
    assert_eq!(record["literal"], Val::Null); // unchanged scalar const behavior
}
