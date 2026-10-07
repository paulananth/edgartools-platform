use source_contract::{Engine, Lookups, Steps, Val};
fn contract(ops: &str) -> String {
    "read: {format: json, tables: {rows: {each: '.', columns: {v: {text: {path: name, trim: false, transforms: @OPS@}}}}}}".replace("@OPS@",ops)
}
fn read(ops: &str, name: &str) -> Result<Val, source_contract::Rejected> {
    let bytes = serde_json::to_vec(&serde_json::json!({"name":name})).unwrap();
    Ok(Engine::from_yaml(&contract(ops), Steps::new()).unwrap().read(&bytes, &Lookups::new())?.tables["rows"][0]["v"].clone())
}
#[test]
fn operations_are_ordered_and_unicode_decomposition_is_pinned() {
    assert_eq!(unicode_normalization::UNICODE_VERSION, (15,0,0));
    assert_eq!(read("[{unicode: nfkd}, {strip_combining: true}, {case: upper}, {replace: {from: '&', to: ' AND '}}, {trim: true}]", "  Électricité & 𝑨\u{1c}").unwrap(), Val::Str("ELECTRICITE  AND  A".into()));
    assert_eq!(read("[{pad: {left: ' ', right: ' '}}, {replace: {from: ' THE ', to: ' X '}}, {trim: true}, {remove_prefix: 'X '}]", "THE INC").unwrap(), Val::Str("INC".into()));
}
#[test]
fn regex_replacement_is_literal_and_handles_empty_matches() {
    assert_eq!(read("[{regex_replace: {pattern: '[A-Z]+', with: '$1'}}]", "THE inc").unwrap(), Val::Str("$1 inc".into()));
    assert_eq!(read("[{regex_replace: {pattern: '', with: '+'}}]", "é").unwrap(), Val::Str("+é+".into()));
}
#[test]
fn invalid_shapes_and_regexes_refuse_at_load_even_in_unselected_branches() {
    for ops in ["[]", "null", "[{unknown: true}]", "[{unicode: nfc}]", "[{trim: false}]", "[{trim: true, case: upper}]", "[{replace: {from: '', to: x}}]", "[{replace: {from: x, to: y, typo: z}}]", "[{regex_replace: {pattern: '(', with: x}}]", "[{regex_replace: {pattern: '(?=x)', with: x}}]"] {
        assert!(Engine::from_yaml(&contract(ops), Steps::new()).is_err(), "{ops}");
        let child = "{choose: {condition: {const: {value: false}}, then: {text: {path: name, transforms: @OPS@}}, else: {const: {value: ok}}}}".replace("@OPS@",ops);
        let yaml="read: {format: json, tables: {rows: {each: '.', columns: {v: @CHILD@}}}}".replace("@CHILD@",&child);
        assert!(Engine::from_yaml(&yaml, Steps::new()).is_err());
    }
    let many = format!("[{}]", vec!["{trim: true}";65].join(","));
    assert!(Engine::from_yaml(&contract(&many), Steps::new()).is_err());
}
#[test]
fn growing_operations_refuse_before_unbounded_output() {
    let huge="x".repeat(1<<20);
    for ops in ["[{replace: {from: x, to: xx}}]", "[{pad: {left: x, right: ''}}]"] {
        assert_eq!(read(ops,&huge).unwrap_err().code,"text_transform_limit");
    }
    let regex = format!("[{{regex_replace: {{pattern: 'x', with: '{}'}}}}]", "y".repeat(4096));
    assert_eq!(read(&regex, &"x".repeat(300)).unwrap_err().code,"text_transform_limit");
    assert_eq!(read("[{unicode: nfkd}]",&"\u{fb03}".repeat(400000)).unwrap_err().code,"text_transform_limit");
}
#[test]
fn repeated_regex_searches_refuse_before_quadratic_scan_cost() {
    assert_eq!(read("[{regex_replace: {pattern: '.*a|b', with: ''}}]", &"b".repeat(16384)).unwrap_err().code, "text_transform_work_limit");
}
#[test]
fn aggregate_regex_compilation_is_bounded_before_more_recipes_are_allocated() {
    let columns=(0..33).map(|n| format!("v{n}: {{text: {{path: name, transforms: [{{regex_replace: {{pattern: 'x{n}', with: ''}}}}]}}}}" )).collect::<Vec<_>>().join(",");
    let yaml=format!("read: {{format: json, tables: {{rows: {{each: '.', columns: {{{columns}}}}}}}}}");
    assert!(Engine::from_yaml(&yaml,Steps::new()).err().unwrap().detail.contains("32 regexes"));
}
#[test]
fn literal_data_that_looks_like_a_transform_is_never_compiled() {
    let yaml="read: {format: json, tables: {rows: {each: '.', columns: {v: {const: {value: {text: {transforms: broken}}}}}}}}";
    assert!(Engine::from_yaml(yaml,Steps::new()).is_ok());
}
