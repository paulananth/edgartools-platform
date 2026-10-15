//! One text from parts (ticket 94): the key that matches an answer to its request by position.
use serde_json::{json, Value};
use source_contract::{Engine, Lookups, Row, Val};

fn read(parts: Value, items: Value) -> Result<Vec<Val>, source_contract::Rejected> {
    let body = json!({"read": {"format": "json", "context": {"batch": {"type": "text"}},
        "tables": {"rows": {"each": "items", "columns": {"key": {"concat": parts}}}}}});
    let engine = Engine::from_yaml(&body.to_string(), source_contract::Steps::new()).unwrap();
    let context: Row = [("batch".to_string(), Val::Str("b1".into()))].into_iter().collect();
    let reading = engine.read_with_context(json!({"items": items}).to_string().as_bytes(), &Lookups::new(), &context)?;
    Ok(reading.tables["rows"].iter().map(|row| row["key"].clone()).collect())
}

#[test]
fn text_and_integers_in_order_with_a_nested_context() {
    let parts = json!([{"context": {"name": "batch"}}, {"const": {"value": ":"}}, {"ordinal": {}}, {"value": {"path": "n"}}]);
    assert_eq!(read(parts, json!([{"n": -7}, {"n": "x"}])).unwrap(),
               vec![Val::Str("b1:1-7".into()), Val::Str("b1:2x".into())]);
}

#[test]
fn a_null_part_makes_the_whole_null() {
    assert_eq!(read(json!([{"value": {"path": "a"}}, {"value": {"path": "b"}}]), json!([{"a": "x"}])).unwrap(), vec![Val::Null]);
}

#[test]
fn other_types_and_long_text_are_refused() {
    for item in [json!({"a": 1.5}), json!({"a": true}), json!({"a": ["x"]}), json!({"a": {"x": 1}})] {
        assert_eq!(read(json!([{"value": {"path": "a"}}]), json!([item])).unwrap_err().code, "value_type");
    }
    let long = "x".repeat(600 * 1024);
    assert_eq!(read(json!([{"value": {"path": "a"}}, {"value": {"path": "a"}}]), json!([{"a": long}])).unwrap_err().code, "concat_limit");
}

#[test]
fn concat_takes_a_list_of_at_most_128_parts() {
    for parts in [json!({"a": 1}), Value::Array(vec![json!({"ordinal": {}}); 129])] {
        let body = json!({"read": {"format": "json", "tables": {"rows": {"each": "items", "columns": {"key": {"concat": parts}}}}}});
        assert!(Engine::from_yaml(&body.to_string(), source_contract::Steps::new()).is_err());
    }
}
