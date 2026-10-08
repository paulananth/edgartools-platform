//! Runtime membership is indexed, declared, exact and bounded before rows.
use source_contract::{Engine, Lookups, Row, Steps, Val};
use serde_json::{json, Value};

fn recipe() -> Value {
    json!({"read":{"format":"json", "lookup_sets":{"scope":{
        "max_values":3,"max_bytes":8,"max_value_bytes":4}},
        "tables":{"rows":{"each":"items",
            "select":{"member":{"lookup":"scope","key":{"value":{"path":"key"}}}},
            "columns":{"key":{"value":{"path":"key"}}}}}}})
}
fn engine(body: Value) -> Engine { Engine::from_yaml(&body.to_string(), Steps::new()).unwrap() }
fn sets(values: &[&str]) -> Lookups {
    [("scope".into(), values.iter().map(|v| (*v).into()).collect())].into_iter().collect()
}

#[test]
fn membership_is_exact_text_and_null_without_coercion_or_case_changes() {
    let engine = engine(recipe());
    let input = json!({"items":[{"key":"A"},{"key":"a"},{"key":"é"},{"key":""},{"key":null},{}]});
    let chosen = sets(&["A","é",""]);
    let eager = engine.read(input.to_string().as_bytes(), &chosen).unwrap();
    let scope = engine.prepare_json_projection(&chosen).unwrap();
    assert_eq!(eager, scope.read_json_value(input, &Row::new()).unwrap());
    assert_eq!(eager.tables["rows"].iter().map(|r| r["key"].clone()).collect::<Vec<_>>(),
               vec![Val::Str("A".into()),Val::Str("é".into()),Val::Str("".into())]);
    for value in [json!(false),json!(0),json!([]),json!({})] {
        assert_eq!(scope.read_json_value(json!({"items":[{"key":value}]}),&Row::new()).unwrap_err().code,"lookup_key");
    }
}

#[test]
fn declared_sets_and_byte_count_bounds_are_checked_before_empty_rows() {
    let engine = engine(recipe());
    for chosen in [Lookups::new(),[("wrong".into(),Default::default())].into_iter().collect()] {
        assert_eq!(engine.read(br#"{"items":[]}"#,&chosen).unwrap_err().code,"invalid_lookup");
        assert_eq!(engine.prepare_json_projection(&chosen).err().unwrap().code,"invalid_lookup");
    }
    for chosen in [sets(&["1","2","3","4"]),sets(&["12345"]),sets(&["1234","5678","9"]),sets(&["ééé"])] {
        assert_eq!(engine.prepare_json_projection(&chosen).err().unwrap().code,"limit_exceeded");
    }
    assert!(engine.prepare_json_projection(&sets(&[])).is_ok());
    assert!(engine.prepare_json_projection(&sets(&["éé"])).is_ok());
}

#[test]
fn membership_children_validate_and_unselected_bad_keys_are_not_evaluated() {
    let mut body = recipe();
    body["read"]["tables"]["rows"]["select"] = json!({"choose":{
        "condition":{"test":{"path":"enabled","kind":"truthy"}},
        "then":{"member":{"lookup":"scope","key":{"value":{"path":"invalid"}}}},
        "else":{"equal":{"left":{"const":{"value":1}},"right":{"const":{"value":1}}}}}});
    let engine = engine(body.clone());
    engine.read(br#"{"items":[{"key":"A","invalid":[]}]}"#,&sets(&[])).unwrap();
    body["read"]["tables"]["rows"]["select"]["choose"]["then"]["member"]["key"] = json!({"unknown":{}});
    assert!(Engine::from_yaml(&body.to_string(),Steps::new()).is_err());
    body["read"]["tables"]["rows"]["select"]["choose"]["then"] = json!({"member":{"lookup":"absent","key":{"const":{"value":"x"}}}});
    assert!(Engine::from_yaml(&body.to_string(),Steps::new()).is_err());
    // Literal data does not become a membership expression.
    body["read"]["tables"]["rows"]["select"] = json!({"const":{"value":false}});
    body["read"]["tables"]["rows"]["columns"]["literal"] = json!({"const":{"value":"member"}});
    assert!(Engine::from_yaml(&body.to_string(),Steps::new()).is_ok());
}

#[test]
fn malformed_declarations_and_membership_arguments_refuse_at_load() {
    for spec in [json!([]),json!({}),json!({"max_values":0,"max_bytes":8,"max_value_bytes":4}),
                 json!({"max_values":1,"max_bytes":8,"max_value_bytes":16385})] {
        let mut body=recipe(); body["read"]["lookup_sets"]["scope"]=spec;
        assert!(Engine::from_yaml(&body.to_string(),Steps::new()).is_err());
    }
    for args in [json!({"lookup":"scope"}),json!({"lookup":"scope","key":{"const":{"value":"A"}},"extra":true}),
                 json!({"lookup":0,"key":{"const":{"value":"A"}}})] {
        let mut body=recipe(); body["read"]["tables"]["rows"]["select"]=json!({"member":args});
        assert!(Engine::from_yaml(&body.to_string(),Steps::new()).is_err());
    }
}
