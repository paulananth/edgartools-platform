use source_contract::{Engine, Lookups, Steps, Val};

fn engine(expression: &str) -> Result<Engine, source_contract::Rejected> {
    Engine::from_yaml(&format!("read: {{format: json, tables: {{rows: {{each: '.', columns: {{v: {expression}}}}}}}}}"), Steps::new())
}

#[test]
fn project_reads_typed_derived_values_without_reinterpreting_literal_calls() {
    let expression = "{project: {value: {value: {path: nested}}, then: {value: {path: '.'}}}}";
    let raw = br#"{"nested":{"uint":18446744073709551615,"float":-0.0,"empty":[],"call":{"custom":{"step":"absent"}},"flag":false}}"#;
    let direct = engine("{value: {path: nested}}").unwrap().read(raw, &Lookups::new()).unwrap();
    assert_eq!(engine(expression).unwrap().read(raw, &Lookups::new()).unwrap(), direct);
}

#[test]
fn transform_and_lines_reuse_bounded_configured_operations() {
    let expression = "{transform: {value: {value: {path: input}}, transforms: [{lines: [{case: upper}, {trim: true}]}, {slice: {start: 1, end: 6}}]}}";
    let raw = serde_json::to_vec(&serde_json::json!({"input": " élan \n\n second "})).unwrap();
    let result = engine(expression).unwrap().read(&raw, &Lookups::new()).unwrap();
    assert_eq!(result.tables["rows"][0]["v"], Val::Str("LAN\nS".into()));
    assert_eq!(engine(expression).unwrap().read(b"{}", &Lookups::new()).unwrap().tables["rows"][0]["v"], Val::Null);
    assert_eq!(engine(expression).unwrap().read(b"{\"input\":2}", &Lookups::new()).unwrap_err().code, "value_type");
}

#[test]
fn recovery_only_catches_explicit_data_shapes_never_resource_or_contract_errors() {
    let expression = "{recover: {value: {value: {path: input, type: text}}, codes: [value_type], fallback: {const: {value: null}}}}";
    assert_eq!(engine(expression).unwrap().read(b"{\"input\":[]}", &Lookups::new()).unwrap().tables["rows"][0]["v"], Val::Null);
    for code in ["contract", "malformed", "projection_limit", "join_limit", "text_transform_limit"] {
        assert!(engine(&expression.replace("value_type", code)).is_err());
    }
    assert!(engine("{recover: {value: {unknown: {}}, codes: [value_type], fallback: {const: {value: null}}}}").is_err());
    assert!(engine("{project: {value: {const: {value: 1}}, then: {context: {name: missing}}}}").is_err());
    assert!(engine("{transform: {value: {const: {value: ok}}, transforms: [{lines: [{lines: [{trim: true}]}]}]}}").is_err());
}

#[test]
fn projected_scalar_budget_is_checked_before_evaluation() {
    let expression = "{project: {value: {value: {path: input}}, then: {const: {value: ok}}}}";
    let raw = format!("{{\"input\":\"{}\"}}", "x".repeat(1_048_577));
    assert_eq!(engine(expression).unwrap().read(raw.as_bytes(), &Lookups::new()).unwrap_err().code, "projection_limit");
}

#[test]
fn sequences_feed_generic_join_without_flattening_nulls() {
    let expression = "{project: {value: {sequence: [{value: {path: a}}, {value: {path: b}}]}, then: {join: {path: '.', item_path: '.', separator: ' ', item_type: text, max_items: 2}}}}";
    assert_eq!(engine(expression).unwrap().read(br#"{"a":"CT","b":"CORPORATION"}"#, &Lookups::new()).unwrap().tables["rows"][0]["v"], Val::Str("CT CORPORATION".into()));
    assert_eq!(engine(expression).unwrap().read(br#"{"a":"CT","b":null}"#, &Lookups::new()).unwrap_err().code, "join_shape");
}

#[test]
fn projected_iteration_preserves_original_document_and_null_policy() {
    let config = "read: {format: json, tables: {rows: {each: {project: {value: {value: {path: nested}}, on_null: empty}}, columns: {v: {value: {path: id}}, original: {value: {path: id, from: document}}}}}}";
    let reader = Engine::from_yaml(config, Steps::new()).unwrap();
    let result = reader.read(br#"{"id":"outer","nested":{"id":"inner"}}"#, &Lookups::new()).unwrap();
    assert_eq!(result.tables["rows"][0]["v"], Val::Str("inner".into()));
    assert_eq!(result.tables["rows"][0]["original"], Val::Str("outer".into()));
    assert!(reader.read(b"{}", &Lookups::new()).unwrap().tables["rows"].is_empty());
    let row = Engine::from_yaml(&config.replace("on_null: empty", "on_null: row"), Steps::new()).unwrap();
    assert_eq!(row.read(b"{}", &Lookups::new()).unwrap().tables["rows"].len(), 1);
    assert!(Engine::from_yaml(&config.replace("path: nested", "path: nested, type: text"), Steps::new()).unwrap()
        .read(br#"{"nested":[]}"#, &Lookups::new()).is_err());
    assert!(Engine::from_yaml(&config.replace("{value: {path: nested}}", "{context: {name: missing}}"), Steps::new()).is_err());
}

#[test]
fn token_replacements_match_whole_whitespace_tokens_without_splitting_hyphens() {
    let expression = "{transform: {value: {value: {path: input}}, transforms: [{tokens: {SOUTH: S, WEST: W}}]}}";
    let result = engine(expression).unwrap().read(br#"{"input":" SOUTH SOUTH SOUTH-WEST\u001cWEST "}"#, &Lookups::new()).unwrap();
    assert_eq!(result.tables["rows"][0]["v"], Val::Str("S S SOUTH-WEST W".into()));
    assert!(engine("{transform: {value: {const: {value: text}}, transforms: [{tokens: {'two words': one}}]}}").is_err());
}
