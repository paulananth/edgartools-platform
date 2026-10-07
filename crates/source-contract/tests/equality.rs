use source_contract::{Engine, Lookups, Row, Steps, Val};

fn contract(expression: &str) -> String {
    format!("read:\n  format: json\n  context:\n    count: {{type: integer}}\n  assertions:\n  - test: {expression}\n    reason: publication count disagreement\n  tables:\n    rows:\n      each: missing\n      columns: {{}}\n")
}

#[test]
fn header_count_is_compared_directly_to_exact_integer_context() {
    let engine = Engine::from_yaml(&contract("{equal: {left: {integer: {path: RecordCount.$}}, right: {context: {name: count}}}}"), Steps::new()).unwrap();
    let mut context = Row::new();
    context.insert("count".into(), Val::Int(3));
    assert!(engine.read_with_context(br#"{"RecordCount":{"$":"3"}}"#, &Lookups::new(), &context).is_ok());
    for input in [r#"{"RecordCount":{"$":"4"}}"#, r#"{}"#] {
        assert_eq!(engine.read_with_context(input.as_bytes(), &Lookups::new(), &context).unwrap_err().code, "assertion_failed");
    }
    assert!(engine.read_with_context(br#"{"RecordCount":{"$":"3.0"}}"#, &Lookups::new(), &context).is_err());
}

#[test]
fn equality_preserves_types_without_python_truth_or_numeric_coercion() {
    let mut context = Row::new();
    context.insert("count".into(), Val::Int(3));
    for (left, right, matches) in [("true", "1", false), ("1", "1.0", false),
                                  ("'3'", "3", false), ("null", "null", true),
                                  ("true", "true", true), ("'name'", "'name'", true)] {
        let expr = "{equal: {left: {const: {value: LEFT}}, right: {const: {value: RIGHT}}}}"
            .replace("LEFT", left).replace("RIGHT", right);
        let engine = Engine::from_yaml(&contract(&expr), Steps::new()).unwrap();
        assert_eq!(engine.read_with_context(b"{}", &Lookups::new(), &context).is_ok(), matches, "{left}/{right}");
    }
}

#[test]
fn equal_children_are_validated_before_source_read() {
    for expr in ["{equal: {left: {const: {value: 1}}}}",
                 "{equal: {left: {const: {value: 1}}, right: {const: {value: 1}}, extra: 0}}",
                 "{equal: {left: {unknown: {}}, right: {const: {value: 1}}}}",
                 "{equal: {left: {const: {value: 1}}, right: {context: {name: absent}}}}",
                 "{equal: {left: {lookup: {reference: missing, column: count, key: {const: {value: x}}}}, right: {const: {value: 1}}}}"] {
        assert!(Engine::from_yaml(&contract(expr), Steps::new()).is_err(), "{expr}");
    }
}

#[test]
fn nested_equal_still_enables_exact_python_json_expression_features() {
    let expr = "{equal: {left: {text: {path: '.', coerce: python, trim: false}}, right: {const: {value: \"{'flag': True, 'n': 3}\"}}}}";
    let engine = Engine::from_yaml(&contract(expr), Steps::new()).unwrap();
    let mut context = Row::new();
    context.insert("count".into(), Val::Int(3));
    assert!(engine.read_with_context(br#"{"flag":true,"n":3}"#, &Lookups::new(), &context).is_ok());
}

#[test]
fn nested_lists_preserve_order_and_maps_compare_typed_fields() {
    let expr = "{equal: {left: {value: {path: left}}, right: {value: {path: right}}}}";
    let engine = Engine::from_yaml(&contract(expr), Steps::new()).unwrap();
    let mut context = Row::new();
    context.insert("count".into(), Val::Int(3));
    assert!(engine.read_with_context(br#"{"left":{"a":[1,true],"b":null},"right":{"b":null,"a":[1,true]}}"#, &Lookups::new(), &context).is_ok());
    for input in [br#"{"left":true,"right":1}"#.as_slice(),
                  br#"{"left":1,"right":1.0}"#.as_slice(),
                  br#"{"left":[1,true],"right":[true,1]}"#.as_slice(),
                  br#"{"left":{"a":1},"right":{"a":true}}"#.as_slice()] {
        assert_eq!(engine.read_with_context(input, &Lookups::new(), &context).unwrap_err().code, "assertion_failed");
    }
}
