use source_contract::{Engine, Lookups, Steps, Val};
const BASE: &str = r#"
read:
  format: json
  limits: {max_records: 3}
  tables:
    rows:
      each: {objects: {path: '.', on_invalid: empty}}
      select: {test: {path: '.', kind: object}}
      ordinal: selected
      columns:
        rank: {ordinal: {}}
        record: {value: {path: '.'}}
"#;
fn read(body: &str, data: &str) -> Result<source_contract::Reading, source_contract::Rejected> {
    Engine::from_yaml(body, Steps::new()).unwrap().read(data.as_bytes(), &Lookups::new())
}
#[test]
fn object_values_keep_capture_order_select_before_columns_and_compact_rank() {
    let result=read(BASE,r#"{"z":null,"b":{"n":1},"a":{"n":2}}"#).unwrap();
    assert_eq!(result.tables["rows"].len(),2);
    assert_eq!(result.tables["rows"][0]["rank"],Val::Int(1));
    assert_eq!(result.tables["rows"][1]["rank"],Val::Int(2));
    assert!(read(BASE,"null").unwrap().tables["rows"].is_empty());
    assert_eq!(read(BASE,r#"{"a":null,"b":null,"c":null,"d":null}"#).unwrap_err().code,"limit_exceeded");
    let source=BASE.replace("ordinal: selected","ordinal: source");
    assert_eq!(read(&source,r#"{"z":null,"b":{"n":1}}"#).unwrap().tables["rows"][0]["rank"],Val::Int(2));
}
#[test]
fn choose_iterator_validates_both_branches_but_evaluates_only_selected_layout() {
    let body=BASE.replace("each: {objects: {path: '.', on_invalid: empty}}",r#"each: {choose: {condition: {test: {path: fields, kind: array}}, then: {matrix: {headers: fields, rows: data}}, else: {objects: {path: '.', on_invalid: empty}}}}"#);
    assert_eq!(read(&body,r#"{"fields":["id"],"data":[[1]]}"#).unwrap().tables["rows"].len(),1);
    assert_eq!(read(&body,r#"{"z":{"id":1}}"#).unwrap().tables["rows"].len(),1);
    assert!(Engine::from_yaml(&body.replace("matrix:","typo:"),Steps::new()).is_err());
}
#[test]
fn raw_tests_distinguish_missing_null_shapes_and_python_truth_without_numeric_output() {
    for (input, kind, expected) in [("null","null",true),("null","missing",false),("null","not_null",false),
        ("[]","array",true),("{}","object",true),("[]","truthy",false),("{}","truthy",false),
        ("false","truthy",false),("0","truthy",false),("-0.0","truthy",false),("1e-400","truthy",false),
        ("18446744073709551616","truthy",true),("[0]","truthy",true),(r#"" ""#,"truthy",true)] {
        let body=format!("read:\n  format: json\n  tables:\n    rows:\n      each: .\n      columns:\n        v: {{test: {{path: ., kind: '{kind}'}}}}\n");
        assert_eq!(read(&body,input).unwrap().tables["rows"][0]["v"],Val::Bool(expected),"{input} {kind}");
    }
    let body=BASE.replace("rank: {ordinal: {}}","rank: {test: {path: missing, kind: missing}}");
    assert_eq!(read(&body,r#"{"x":{}}"#).unwrap().tables["rows"][0]["rank"],Val::Bool(true));
}
#[test]
fn explicit_matrix_zip_last_headers_and_skip_preserve_assigned_key_order() {
    let body=BASE.replace("each: {objects: {path: '.', on_invalid: empty}}", "each: {matrix: {headers: fields, rows: data, lengths: zip, duplicates: last, headers_coerce: python, on_invalid_row: skip}}")
        .replace("record: {value: {path: '.'}}", "record: {text: {path: '.', coerce: python, trim: false}}");
    let result=read(&body,r#"{"fields":["b","a","b"],"data":[{},[1,2,3,4],[5]]}"#).unwrap();
    assert_eq!(result.tables["rows"][0]["record"],Val::Str("{'b': 3, 'a': 2}".into()));
    assert_eq!(result.tables["rows"][1]["record"],Val::Str("{'b': 5}".into()));
    assert_eq!(read(&body,r#"{"fields":[null,0,{}],"data":[[1,2,3]]}"#).unwrap().tables["rows"][0]["record"],Val::Str("{'None': 1, '0': 2, '{}': 3}".into()));
}
#[test]
fn selection_and_iterator_conditions_validate_context_references_and_features() {
    for replacement in ["select: {context: {name: missing}}", "select: {lookup: {reference: missing, column: x, key: {const: {value: x}}}}", "ordinal: invalid"] {
        let body=if replacement.starts_with("ordinal") { BASE.replace("ordinal: selected",replacement) } else { BASE.replace("select: {test: {path: '.', kind: object}}",replacement) };
        assert!(Engine::from_yaml(&body,Steps::new()).is_err());
    }
    let nonboolean=BASE.replace("select: {test: {path: '.', kind: object}}","select: {const: {value: yes}}");
    assert_eq!(read(&nonboolean,r#"{"x":{}}"#).unwrap_err().code,"select_condition");
}

#[test]
fn values_iterates_singletons_and_arrays_without_coercion_and_enforces_source_bound() {
    let body = "read:\n  format: json\n  limits: {max_records: 3}\n  tables:\n    rows:\n      each: {values: {path: v}}\n      columns:\n        v: {value: {path: '.'}}\n";
    for (raw, expected) in [
        (r#"{}"#, vec![]), (r#"{"v":[]}"#, vec![]),
        (r#"{"v":null}"#, vec![Val::Null]),
        (r#"{"v":false}"#, vec![Val::Bool(false)]),
        (r#"{"v":18446744073709551615}"#, vec![Val::UInt(u64::MAX)]),
        (r#"{"v":"abc"}"#, vec![Val::Str("abc".into())]),
        (r#"{"v":[null,false,7]}"#, vec![Val::Null, Val::Bool(false), Val::Int(7)]),
    ] {
        let result = read(body, raw).unwrap();
        assert_eq!(result.tables["rows"].iter().map(|row| row["v"].clone()).collect::<Vec<_>>(), expected, "{raw}");
    }
    let filtered = body.replace("columns:", "select: {test: {path: '.', kind: text}}\n      columns:");
    assert_eq!(read(&filtered, r#"{"v":[0,1,2,3]}"#).unwrap_err().code, "limit_exceeded");
    for bad in ["{values: {path: v, extra: true}}", "{values: {}}"] {
        assert!(Engine::from_yaml(&body.replace("{values: {path: v}}", bad), Steps::new()).is_err());
    }
    assert!(Engine::from_yaml(&body.replace("format: json", "format: xml"), Steps::new()).is_err());
}

#[test]
fn text_shape_never_accepts_numbers_booleans_containers_or_missing_values() {
    let body = "read:\n  format: json\n  tables:\n    rows:\n      each: .\n      columns:\n        text: {test: {path: v, kind: text}}\n";
    for (raw, expected) in [(r#"{}"#, false), (r#"{"v":null}"#, false),
        (r#"{"v":false}"#, false), (r#"{"v":123}"#, false),
        (r#"{"v":[]}"#, false), (r#"{"v":{}}"#, false),
        (r#"{"v":""}"#, true), (r#"{"v":"123"}"#, true)] {
        assert_eq!(read(body, raw).unwrap().tables["rows"][0]["text"], Val::Bool(expected));
    }
}

#[test]
fn empty_iteration_skips_input_and_columns_without_a_sentinel_path() {
    let body=BASE.replace("each: {objects: {path: '.', on_invalid: empty}}", "each: {empty: {}}")
        .replace("rank: {ordinal: {}}", "rank: {value: {path: '.', type: integer}}");
    assert!(read(&body,r#"{"__no_census_rows__":[{"n":1}]}"#).unwrap().tables["rows"].is_empty());
    for invalid in ["empty: null", "empty: {path: .}", "empty: []"] {
        assert!(Engine::from_yaml(&body.replace("empty: {}", invalid),Steps::new()).is_err());
    }
}
