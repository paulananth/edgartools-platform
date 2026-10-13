//! Completeness needs key presence without coercing or copying a subtree.
use source_contract::{Engine, Lookups, Steps, Val};
use serde_json::json;

fn predicate(path: &str, mode: &str, kind: &str) -> Engine {
    Engine::from_yaml(&json!({"read":{"format":"json","tables":{"r":{"each":".",
        "columns":{"found":{"test":{"path":path,"path_mode":mode,"kind":kind}}}}}}}).to_string(), Steps::new()).unwrap()
}

#[test]
fn exact_members_include_null_empty_arrays_and_special_names() {
    for (body, name) in [(br#"{"x":null}"#.as_slice(), "x"), (br#"{"x":[]}"#, "x"),
                         (br#"{"a.b":0}"#, "a.b"), (br#"{"$":""}"#, "$"),
                         (br#"{"@x":""}"#, "@x"), (br#"{"x[y]":false}"#, "x[y]")] {
        let engine = predicate(name, "member", "present");
        assert_eq!(engine.read(body, &Lookups::new()).unwrap().tables["r"][0]["found"], Val::Bool(true));
        assert_eq!(engine.read(b"{}", &Lookups::new()).unwrap().tables["r"][0]["found"], Val::Bool(false));
    }
}

#[test]
fn tree_and_literal_paths_keep_traversal_and_null_policies() {
    for mode in ["tree", "literal"] {
        let engine = predicate("a.b", mode, "present");
        assert_eq!(engine.read(br#"{"a":{"b":null}}"#, &Lookups::new()).unwrap().tables["r"][0]["found"], Val::Bool(true));
        assert_eq!(engine.read(br#"{"a.b":null}"#, &Lookups::new()).unwrap().tables["r"][0]["found"], Val::Bool(false));
    }
    assert_eq!(predicate("x", "member", "null").read(br#"{"x":null}"#, &Lookups::new()).unwrap().tables["r"][0]["found"], Val::Bool(true));
    for body in [b"[]".as_slice(), b"null", b"42", b"false"] {
        assert_eq!(predicate("x", "member", "present").read(body, &Lookups::new()).unwrap().tables["r"][0]["found"], Val::Bool(false));
    }
}
