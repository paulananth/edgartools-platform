//! A framed typed record uses the same interpreter as an ordinary JSON read.
use source_contract::{Engine, Lookups, Row, Steps, Val};
use serde_json::{json, Value};

fn engine(read: Value) -> Engine {
    Engine::from_yaml(&json!({"read": read}).to_string(), Steps::new()).unwrap()
}

#[test]
fn framed_records_preserve_values_python_text_and_recursive_object_order() {
    let engine = engine(json!({"format":"json","tables":{"rows":{"each":".","columns":{
        "evidence":{"value":{"path":"."}},
        "text":{"text":{"path":"nested","coerce":"python"}},
        "integer":{"integer":{"path":"integer"}},
        "negative_zero":{"value":{"path":"zero"}}
    }}}}));
    let value: Value = serde_json::from_str(r#"{"z":true,"a":null,"nested":{"y":1e-5,"b":[false,"é🦀"]},"integer":9007199254740993,"zero":-0.0}"#).unwrap();
    let framed = engine.read_json_value(value.clone(), &Lookups::new(), &Row::new()).unwrap();
    let eager = engine.read(&serde_json::to_vec(&value).unwrap(), &Lookups::new()).unwrap();
    assert_eq!(framed, eager);
    assert_eq!(framed.tables["rows"][0]["text"], Val::Str("{'y': 1e-05, 'b': [False, 'é🦀']}".into()));
    match framed.tables["rows"][0]["negative_zero"] { Val::Float(value) => assert!(value.is_sign_negative()), _ => panic!("lost float type") }
}

#[test]
fn framed_object_iteration_preserves_source_positions_and_reference_selection() {
    let engine = engine(json!({"format":"json","references":{"scope":{"A":{"selected":true}}},
        "tables":{"rows":{"each":{"objects":{"path":"."}},
        "select":{"lookup":{"reference":"scope","column":"selected","key":{"value":{"path":"key"}},"on_missing":"null"}},
        "columns":{"position":{"ordinal":{}},"value":{"value":{"path":"key"}}}}}}));
    let value: Value = serde_json::from_str(r#"{"z":{"key":"B"},"a":{"key":"A"}}"#).unwrap();
    let framed = engine.read_json_value(value.clone(), &Lookups::new(), &Row::new()).unwrap();
    assert_eq!(framed, engine.read(&serde_json::to_vec(&value).unwrap(), &Lookups::new()).unwrap());
    assert_eq!(framed.tables["rows"][0]["position"], Val::Int(2));
}

#[test]
fn framed_projection_preserves_assertion_and_deferred_refusals() {
    let read = json!({"format":"json","assertions":[{"test":{"test":{"path":".","kind":"object"}},"reason":"object-required"}],
        "tables":{"rows":{"each":".","columns":{"key":{"text":{"path":"key"}}},
        "checks":[{"check":"required","path":"key","reason":"no-key","on_fail":"defer"}]}}});
    let engine = engine(read);
    for value in [json!({}), json!({"key":"A"}), json!([1])] {
        assert_eq!(engine.read_json_value(value.clone(), &Lookups::new(), &Row::new()),
                   engine.read(&serde_json::to_vec(&value).unwrap(), &Lookups::new()));
    }
}

#[test]
fn framed_projection_enforces_context_even_for_an_empty_selected_table() {
    let engine = engine(json!({"format":"json","context":{"capture":{"type":"text"}},
        "tables":{"rows":{"each":".","select":{"const":{"value":false}},"columns":{}}}}));
    assert_eq!(engine.read_json_value(json!({}), &Lookups::new(), &Row::new()).unwrap_err().code, "invalid_context");
}

#[test]
fn framed_projection_byte_budget_uses_the_worker_python_encoding() {
    let engine = engine(json!({"format":"json","limits":{"max_bytes":11},"tables":{"rows":{"each":".","columns":{"x":{"value":{"path":"x"}}}}}}));
    let value = json!({"x":1e-5});
    assert_eq!(engine.read_json_value(value, &Lookups::new(), &Row::new()).unwrap(),
               engine.read(br#"{"x":1e-05}"#, &Lookups::new()).unwrap());
    assert_eq!(engine.read_json_value(json!({"x":1.23456789}), &Lookups::new(), &Row::new()).unwrap_err().code, "limit_exceeded");
}

#[test]
fn framed_projection_refuses_other_formats_and_containers() {
    for read in [json!({"format":"jsonl","tables":{"rows":{"columns":{}}}}),
                 json!({"format":"json","container":"zip","tables":{"rows":{"columns":{}}}})] {
        assert_eq!(engine(read).read_json_value(json!({}), &Lookups::new(), &Row::new()).unwrap_err().code,"contract");
    }
}
