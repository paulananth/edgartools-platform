//! Two lists of text share a value (ticket 93): the one comparison the reading,
//! reduction and combine cannot state.
use serde_json::{json, Value};
use source_contract::{Engine, Lookups, Row, Steps, Val};

fn engine(left: Value, right: Value) -> Engine {
    let body = json!({"read": {"format": "json", "context": {"wanted": {"type": "text"}},
        "tables": {"rows": {"each": "items", "columns": {"same": {"overlap": {"left": left, "right": right}}}}}}});
    Engine::from_yaml(&body.to_string(), Steps::new()).unwrap()
}

fn read(engine: &Engine, items: Value) -> Result<Vec<Val>, source_contract::Rejected> {
    let context: Row = [("wanted".to_string(), Val::Str("C".into()))].into_iter().collect();
    let reading = engine.read_with_context(json!({"items": items}).to_string().as_bytes(), &Lookups::new(), &context)?;
    Ok(reading.tables["rows"].iter().map(|row| row["same"].clone()).collect())
}

#[test]
fn shared_none_and_null() {
    let both = engine(json!({"value": {"path": "a"}}), json!({"value": {"path": "b"}}));
    let items = json!([
        {"a": ["F1", "F2"], "b": ["F9", "F2"]},   // share one
        {"a": ["F1"], "b": ["F9"]},               // share none
        {"a": [], "b": ["F9"]},                   // an empty list shares nothing
        {"a": null, "b": ["F9"]},                 // either null: null
        {"b": ["F9"]}                             // missing: null
    ]);
    assert_eq!(read(&both, items).unwrap(),
               vec![Val::Bool(true), Val::Bool(false), Val::Bool(false), Val::Null, Val::Null]);
}

#[test]
fn only_lists_of_text_are_compared() {
    let both = engine(json!({"value": {"path": "a"}}), json!({"value": {"path": "b"}}));
    for items in [json!([{"a": "F1", "b": ["F1"]}]), json!([{"a": [1], "b": ["1"]}]), json!([{"a": [["F1"]], "b": ["F1"]}])] {
        assert_eq!(read(&both, items).unwrap_err().code, "value_type");
    }
}

#[test]
fn an_expression_nested_inside_overlap_is_registered_and_read() {
    // `context` inside `overlap` must be declared through the children walker, or eval would fail.
    let nested = engine(json!({"value": {"path": "a"}}), json!({"sequence": [{"context": {"name": "wanted"}}]}));
    assert_eq!(read(&nested, json!([{"a": ["B", "C"]}, {"a": ["D"]}])).unwrap(), vec![Val::Bool(true), Val::Bool(false)]);
}

#[test]
fn overlap_takes_left_and_right_only() {
    for args in [json!({"left": {"value": {"path": "a"}}}),
                 json!({"left": {"value": {"path": "a"}}, "right": {"value": {"path": "b"}}, "extra": 1})] {
        let body = json!({"read": {"format": "json", "tables": {"rows": {"each": "items", "columns": {"same": {"overlap": args}}}}}});
        assert!(Engine::from_yaml(&body.to_string(), Steps::new()).is_err());
    }
}
