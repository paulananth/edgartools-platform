use source_contract::{Engine, Lookups, Steps, Val};

const BASE: &str = r#"
read:
  format: json
  assertions:
  - test: {test: {path: '.', kind: object}}
    reason: require an object
  tables:
    rows:
      each: nonexistent
      columns:
        value: {value: {path: '.'}}
"#;

#[test]
fn document_assertions_run_even_when_no_table_rows_exist() {
    let engine = Engine::from_yaml(BASE, Steps::new()).unwrap();
    assert!(engine.read(b"{}", &Lookups::new()).unwrap().tables["rows"].is_empty());
    for input in ["null", "[]", "false", "1", "\"x\""] {
        let error = engine.read(input.as_bytes(), &Lookups::new()).unwrap_err();
        assert_eq!(error.code, "assertion_failed");
        assert!(error.detail.contains("require an object"));
    }
    for (value, code) in [("false", "assertion_condition"), ("null", "assertion_failed"), ("1", "assertion_condition")] {
        let body = BASE.replace("{test: {path: '.', kind: object}}", &format!("{{const: {{value: {value}}}}}"));
        assert_eq!(Engine::from_yaml(&body, Steps::new()).unwrap().read(b"{}", &Lookups::new()).unwrap_err().code, code);
    }
}

#[test]
fn assertions_validate_expression_context_reference_and_shape_before_reading() {
    for expression in ["{unknown: {}}", "{context: {name: undeclared}}", "{lookup: {reference: missing, column: x, key: {const: {value: x}}}}"] {
        let body = BASE.replace("{test: {path: '.', kind: object}}", expression);
        assert!(Engine::from_yaml(&body, Steps::new()).is_err());
    }
    for body in [BASE.replace("reason: require an object", "reason: ''"),
                 BASE.replace("reason: require an object", "reason: require an object\n    extra: 1"),
                 BASE.replace("assertions:", "assertions: invalid\n  ignored:")] {
        assert!(Engine::from_yaml(&body, Steps::new()).is_err());
    }
    let body = BASE.replace("assertions:\n", "context: {allowed: {type: boolean}}\n  assertions:\n")
        .replace("{test: {path: '.', kind: object}}", "{context: {name: allowed}}");
    let engine = Engine::from_yaml(&body, Steps::new()).unwrap();
    let mut context = source_contract::Row::new();
    context.insert("allowed".into(), Val::Bool(true));
    assert!(engine.read_with_context(b"{}", &Lookups::new(), &context).is_ok());
    context.insert("allowed".into(), Val::Bool(false));
    assert_eq!(engine.read_with_context(b"{}", &Lookups::new(), &context).unwrap_err().code, "assertion_failed");
}

#[test]
fn assertion_expression_inventory_enables_exact_python_json_formatting() {
    let body = r#"
read:
  format: json
  references:
    accepted:
      "{'z': 9223372036854775807, 'a': True}": {allowed: true}
  assertions:
  - test:
      lookup:
        reference: accepted
        column: allowed
        key: {text: {path: '.', coerce: python, trim: false}}
    reason: ordered exact JSON required
  tables:
    rows:
      each: missing
      columns:
        unused: {const: {value: null}}
"#;
    let engine = Engine::from_yaml(body, Steps::new()).unwrap();
    assert!(engine.read(br#"{"z":9223372036854775807,"a":true}"#, &Lookups::new()).is_ok());
    assert_eq!(engine.read(br#"{"a":true,"z":9223372036854775807}"#, &Lookups::new()).unwrap_err().code, "assertion_failed");
}
