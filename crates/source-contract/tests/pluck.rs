//! A field of each object in a list (ticket 95): each answer's FIGIs as one list of text.
use serde_json::{json, Value};
use source_contract::{Engine, Lookups, Row, Val};

fn engine(args: Value) -> Result<Engine, source_contract::Rejected> {
    let body = json!({"read": {"format": "json", "tables": {"rows": {"each": "items", "columns": {"ids": {"pluck": args}}}}}});
    Engine::from_yaml(&body.to_string(), source_contract::Steps::new())
}

fn read(args: Value, items: Value) -> Result<Vec<Val>, source_contract::Rejected> {
    let reading = engine(args).unwrap().read_with_context(json!({"items": items}).to_string().as_bytes(), &Lookups::new(), &Row::new())?;
    Ok(reading.tables["rows"].iter().map(|row| row["ids"].clone()).collect())
}

fn texts(values: &[&str]) -> Val { Val::List(values.iter().map(|v| Val::Str((*v).into())).collect()) }

#[test]
fn named_fields_of_each_object_in_order_missing_and_null_skipped() {
    let args = json!({"value": {"value": {"path": "data"}}, "fields": ["figi", "composite"]});
    let items = json!([
        {"data": [{"figi": "F1", "composite": "C1"}, {"figi": "F2", "composite": null}, {"composite": "C3"}]},
        {"data": []},
        {"error": "none"}
    ]);
    assert_eq!(read(args, items).unwrap(), vec![texts(&["F1", "C1", "F2", "C3"]), texts(&[]), Val::Null]);
}

#[test]
fn other_shapes_are_refused() {
    let args = json!({"value": {"value": {"path": "data"}}, "fields": ["figi"]});
    for item in [json!({"data": "F1"}), json!({"data": ["F1"]}), json!({"data": [{"figi": 1}]}), json!({"data": [{"figi": ["F1"]}]})] {
        assert_eq!(read(args.clone(), json!([item])).unwrap_err().code, "value_type");
    }
}

#[test]
fn pluck_takes_a_value_and_1_to_16_field_names() {
    let names: Vec<String> = (0..17).map(|i| format!("f{i}")).collect();
    for args in [json!({"value": {"value": {"path": "data"}}}), json!({"value": {"value": {"path": "data"}}, "fields": []}),
                 json!({"value": {"value": {"path": "data"}}, "fields": names}), json!({"value": {"value": {"path": "data"}}, "fields": [""]}),
                 json!({"value": {"value": {"path": "data"}}, "fields": ["figi"], "extra": 1})] {
        assert!(engine(args).is_err());
    }
}
