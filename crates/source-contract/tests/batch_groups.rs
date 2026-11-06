use serde_json::{from_str, json, Value};
use source_contract::batch_groups::group_batch_records;

fn grouped(input: Value) -> Value {
    from_str(&group_batch_records(&input.to_string()).unwrap()).unwrap()
}

#[test]
fn records_sharing_a_key_form_one_group() {
    assert_eq!(grouped(json!([["b", ["k"]], ["a", ["k"]]])), json!({"a": "a", "b": "a"}));
}

#[test]
fn a_chain_of_keys_forms_one_group() {
    let input = json!([["c", ["y"]], ["b", ["x", "y"]], ["a", ["x"]]]);
    assert_eq!(grouped(input), json!({"a": "a", "b": "a", "c": "a"}));
}

#[test]
fn a_record_with_no_key_or_another_key_stands_alone() {
    let input = json!([["a", []], ["b", ["x"]], ["c", ["y"]]]);
    assert_eq!(grouped(input), json!({"a": "a", "b": "b", "c": "c"}));
}

#[test]
fn two_versions_of_a_record_join_their_keys() {
    let input = json!([["a", ["x"]], ["b", ["y"]], ["a", ["y"]]]);
    assert_eq!(grouped(input), json!({"a": "a", "b": "a"}));
}

#[test]
fn the_order_of_the_input_changes_nothing() {
    let forward = json!([["a", ["x"]], ["b", ["x", "y"]], ["c", ["y"]], ["d", ["z"]]]);
    let reverse = json!([["d", ["z"]], ["c", ["y"]], ["b", ["x", "y"]], ["a", ["x"]]]);
    assert_eq!(grouped(forward), grouped(reverse));
}

#[test]
fn malformed_input_is_refused() {
    assert!(group_batch_records("[[1]]").is_err());
}
