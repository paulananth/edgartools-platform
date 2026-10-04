use source_contract::{Engine, Lookups, Steps, Val};

const CONTRACT: &str = r#"
read:
  format: json
  limits: {max_records: 3}
  tables:
    rows:
      take: {const: {value: 0}}
      each:
        parallel:
          path: .
          anchor: ids
          fields: {id: ids, name: names}
          lengths: anchor
          validation: selected
          objects: indexed
      columns:
        ordinal: {ordinal: {}}
        id: {text: {path: id}}
        name: {text: {path: name}}
"#;

fn engine(contract: &str) -> Engine { Engine::from_yaml(contract, Steps::new()).unwrap() }

#[test]
fn selected_validation_skips_only_unused_field_access() {
    let bytes = br#"{"ids":["a","b"],"names":null}"#;
    assert!(engine(CONTRACT).read(bytes, &Lookups::new()).unwrap().tables["rows"].is_empty());
    for contract in [CONTRACT.replace("validation: selected", "validation: all"),
                     CONTRACT.replace("          validation: selected\n", ""),
                     CONTRACT.replace("value: 0", "value: 1")] {
        assert_eq!(engine(&contract).read(bytes, &Lookups::new()).unwrap_err().code, "parallel_shape");
    }
    // Selecting nothing still checks anchor type and full record safety.
    for bytes in [br#"{"ids":null}"#.as_slice(), br#"{"ids":[1,2,3,4]}"#.as_slice()] {
        let code = if bytes.contains(&b'n') { "parallel_shape" } else { "limit_exceeded" };
        assert_eq!(engine(CONTRACT).read(bytes, &Lookups::new()).unwrap_err().code, code);
    }
}

#[test]
fn declared_object_sequences_keep_length_and_integer_index_distinct() {
    assert!(engine(CONTRACT).read(br#"{"ids":{"0":"a"},"names":null}"#, &Lookups::new()).unwrap().tables["rows"].is_empty());
    let selected = CONTRACT.replace("value: 0", "value: 1");
    assert_eq!(engine(&selected).read(br#"{"ids":{"0":"a"},"names":[]}"#, &Lookups::new()).unwrap_err().code, "parallel_index");
    let reading = engine(&selected).read(br#"{"ids":["a"],"names":{}}"#, &Lookups::new()).unwrap();
    assert_eq!(reading.tables["rows"][0]["name"], Val::Null);
    assert_eq!(reading.tables["rows"][0]["ordinal"], Val::Int(1));
    assert_eq!(engine(&selected).read(br#"{"ids":["a"],"names":{"0":"x"}}"#, &Lookups::new()).unwrap_err().code, "parallel_index");
    assert_eq!(engine(&selected.replace("objects: indexed", "objects: reject")).read(br#"{"ids":["a"],"names":{}}"#, &Lookups::new()).unwrap_err().code, "parallel_shape");
}

#[test]
fn first_n_does_not_change_source_count_checks_or_exceed_anchor_budget() {
    let contract = CONTRACT.replace("  tables:", "  record_count: {path: count, table: rows}\n  tables:");
    assert!(engine(&contract).read(br#"{"count":2,"ids":["a","b"],"names":null}"#, &Lookups::new()).unwrap().tables["rows"].is_empty());
    assert_eq!(engine(&contract).read(br#"{"count":2,"ids":["a"],"names":null}"#, &Lookups::new()).unwrap_err().code, "record_count");
}

#[test]
fn unknown_policies_and_selected_equal_lengths_are_refused_on_load() {
    for contract in [CONTRACT.replace("validation: selected", "validation: false"),
                     CONTRACT.replace("validation: selected", "validation: skip"),
                     CONTRACT.replace("objects: indexed", "objects: empty"),
                     CONTRACT.replace("objects: indexed", "objects: true"),
                     CONTRACT.replace("lengths: anchor", "lengths: equal")] {
        assert!(Engine::from_yaml(&contract, Steps::new()).is_err());
    }
}
