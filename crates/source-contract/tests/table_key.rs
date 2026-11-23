//! A table may declare its key; a source extract whose table repeats that key is refused, naming the table and the
//! key columns and never a value (operator, 2026-11-22: "recommend a declared uniqueness check in the source contract").

use source_contract::{Engine, Lookups, Steps};

fn configured(text: &str) -> Result<Engine, String> {
    Engine::from_yaml(text, Steps::new()).map_err(|e| e.detail)
}

const CONTRACT: &str = "read:\n  format: jsonl\n  tables:\n    rows:\n      each: record\n      key: [a, b]\n      columns:\n        a: { text: { path: a } }\n        b: { text: { path: b } }\n";

#[test]
fn distinct_keys_pass() {
    let e = configured(CONTRACT).unwrap();
    let reading = e.read(b"{\"a\":\"x\",\"b\":\"1\"}\n{\"a\":\"x\",\"b\":\"2\"}\n", &Lookups::new()).unwrap();
    assert_eq!(reading.tables["rows"].len(), 2);
}

#[test]
fn a_repeated_key_is_refused_naming_the_table_and_columns_and_no_value() {
    let e = configured(CONTRACT).unwrap();
    let refused = e.read(b"{\"a\":\"secret\",\"b\":\"1\"}\n{\"a\":\"secret\",\"b\":\"1\"}\n", &Lookups::new()).unwrap_err();
    assert_eq!(refused.code, "repeated_key");
    assert_eq!(refused.detail, "rows: key [a, b] repeats");
    assert!(!refused.detail.contains("secret"));
}

#[test]
fn a_key_must_name_declared_columns() {
    let unknown = CONTRACT.replace("key: [a, b]", "key: [a, c]");
    assert!(configured(&unknown).err().unwrap().contains("key names unknown column c"));
    let empty = CONTRACT.replace("key: [a, b]", "key: []");
    assert!(configured(&empty).err().unwrap().contains("key names no column"));
}
