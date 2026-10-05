use source_contract::{Engine, Lookups, Steps, Val};
const CONTRACT: &str = r#"
read:
  format: json
  limits: {max_records: 2}
  tables:
    rows:
      each: {matrix: {headers: fields, rows: data}}
      columns:
        id: {integer: {path: id}}
        record: {value: {path: .}}
        rank: {ordinal: {}}
"#;
fn read(data: &str) -> Result<source_contract::Reading, source_contract::Rejected> {
    Engine::from_yaml(CONTRACT, Steps::new()).unwrap().read(data.as_bytes(), &Lookups::new())
}
#[test]
fn header_names_preserve_order_types_and_unknown_cells() {
    let result = read(r#"{"fields":["other","id"],"data":[[{"nested":[false,0]},3],[null,4]]}"#).unwrap();
    assert_eq!(result.tables["rows"][0]["id"], Val::Int(3));
    assert_eq!(result.tables["rows"][1]["rank"], Val::Int(2));
    assert_eq!(result.tables["rows"][1]["record"], Val::Map(std::collections::BTreeMap::from([
        ("id".into(), Val::Int(4)), ("other".into(), Val::Null)])));
    assert!(read(r#"{"fields":["id"],"data":[]}"#).unwrap().tables["rows"].is_empty());
}
#[test]
fn malformed_headers_and_rows_refuse() {
    for (data, code) in [
        (r#"{"fields":[],"data":[]}"#, "matrix_header"),
        (r#"{"fields":["id","id"],"data":[]}"#, "matrix_header"),
        (r#"{"fields":[0],"data":[]}"#, "matrix_header"),
        (r#"{"fields":["a.b"],"data":[]}"#, "matrix_header"),
        (r#"{"fields":["id"],"data":[[]]}"#, "matrix_length"),
        (r#"{"fields":["id"],"data":[[1,2]]}"#, "matrix_length"),
        (r#"{"fields":["id"],"data":[{}]}"#, "matrix_shape"),
        (r#"{"fields":["id"],"data":null}"#, "matrix_shape"),
        (r#"{"fields":["id"],"data":[[1],[2],[3]]}"#, "limit_exceeded"),
    ] { assert_eq!(read(data).unwrap_err().code, code); }
}
#[test]
fn selection_still_checks_full_shape_and_count() {
    let selected = CONTRACT.replace("      each:", "      take: {const: {value: 1}}\n      each:");
    let engine = Engine::from_yaml(&selected, Steps::new()).unwrap();
    let result = engine.read(br#"{"fields":["id"],"data":[[1],[2]]}"#, &Lookups::new()).unwrap();
    assert_eq!(result.tables["rows"].len(), 1);
    for (data, code) in [(r#"{"fields":["id"],"data":[[1],[]]}"#, "matrix_length"),
                         (r#"{"fields":["id"],"data":[[1],[2],[3]]}"#, "limit_exceeded")] {
        assert_eq!(engine.read(data.as_bytes(), &Lookups::new()).unwrap_err().code, code);
    }
}
#[test]
fn configuration_rejects_unknown_keys_and_non_json() {
    for body in [CONTRACT.replace("rows: data", "rows: data, extra: true"),
                 CONTRACT.replace("format: json", "format: xml"),
                 CONTRACT.replace("headers: fields", "headers: .")] {
        assert!(Engine::from_yaml(&body, Steps::new()).is_err());
    }
}
