use source_contract::{Engine, Lookups, Steps, Val};
const BASE: &str = r#"read:
  format: json
  limits: {max_records: 3}
  tables:
    rows:
      each: {entries: {path: '.', key_field: key, value_field: entry}}
      columns:
        key: {text: {path: key, trim: false}}
        entry: {value: {path: entry}}
"#;
fn read(yaml:&str,raw:&str)->Result<source_contract::Reading,source_contract::Rejected>{
    Engine::from_yaml(yaml,Steps::new()).unwrap().read(raw.as_bytes(),&Lookups::new())
}
#[test]
fn entries_preserve_literal_keys_order_reserved_names_and_exact_values(){
    let result=read(BASE,r#"{"a.b":[true,18446744073709551615],"$":"text","@x":null}"#).unwrap();
    let rows=&result.tables["rows"];
    assert_eq!(rows[0]["key"],Val::Str("a.b".into()));
    assert_eq!(rows[0]["entry"],Val::List(vec![Val::Bool(true),Val::UInt(u64::MAX)]));
    assert_eq!(rows[1]["key"],Val::Str("$".into()));
    assert_eq!(rows[1]["entry"],Val::Str("text".into()));
    assert_eq!(rows[2]["key"],Val::Str("@x".into()));
    assert_eq!(rows[2]["entry"],Val::Null);
    let body=BASE.replace("{value: {path: entry}}","{text: {path: '.', trim: false, coerce: python}}");
    assert_eq!(read(&body,r#"{"z":{"b":2,"a":1}}"#).unwrap().tables["rows"][0]["entry"],Val::Str("{'key': 'z', 'entry': {'b': 2, 'a': 1}}".into()));
}
#[test]
fn entries_shape_policy_and_source_count_bounds_are_explicit(){
    for raw in ["null","[]","0","true",r#""text""#]{
        assert_eq!(read(BASE,raw).unwrap_err().code,"objects_shape");
        assert!(read(&BASE.replace("value_field: entry","value_field: entry, on_invalid: empty"),raw).unwrap().tables["rows"].is_empty());
    }
    let take=BASE.replace("columns:","take: {const: {value: 1}}\n      columns:");
    assert_eq!(read(&take,r#"{"a":1,"b":2,"c":3,"d":4}"#).unwrap_err().code,"limit_exceeded");
    assert!(read(BASE,"{}").unwrap().tables["rows"].is_empty());
}
#[test]
fn entries_field_names_and_unused_branches_refuse_at_load(){
    for change in ["key_field: entry","key_field: a.b","key_field: '@x'","key_field: ''","key_field: 1","key_field: 0key"]{
        assert!(Engine::from_yaml(&BASE.replace("key_field: key",change),Steps::new()).is_err(),"{change}");
    }
    assert!(Engine::from_yaml(&BASE.replace("value_field: entry","typo: entry"),Steps::new()).is_err());
    let each="{choose: {condition: {const: {value: false}}, then: {entries: {path: '.', key_field: key, value_field: key}}, else: {objects: {path: '.'}}}}";
    assert!(Engine::from_yaml(&BASE.replace("{entries: {path: '.', key_field: key, value_field: entry}}",each),Steps::new()).is_err());
}
#[test]
fn base_objects_keep_unknown_fields_types_and_refuse_collisions(){
    let body=BASE.replace("{value: {path: entry}}","{object: {base: {value: {path: entry}}, fields: {pin: {const: {value: approved}}}}}");
    let result=read(&body,r#"{"a":{"n":18446744073709551615,"flag":false,"items":[]}}"#).unwrap();
    let Val::Map(map)=&result.tables["rows"][0]["entry"] else {panic!()};
    assert_eq!(map["n"],Val::UInt(u64::MAX));
    assert_eq!(map["flag"],Val::Bool(false));
    assert_eq!(map["items"],Val::List(vec![]));
    assert_eq!(map["pin"],Val::Str("approved".into()));
    assert_eq!(read(&body,r#"{"a":{"pin":"untrusted"}}"#).unwrap_err().code,"object_field_conflict");
    for raw in [r#"{"a":null}"#,r#"{"a":true}"#,r#"{"a":[]}"#]{assert_eq!(read(&body,raw).unwrap_err().code,"object_base");}
}
#[test]
fn base_expressions_are_inventoried_validated_and_evaluated_lazily(){
    let body=BASE.replace("{value: {path: entry}}","{object: {base: {choose: {condition: {test: {path: '.', kind: object}}, then: {value: {path: entry}}, else: {value: {path: unused}}}}, fields: {}}}");
    assert!(read(&body,r#"{"a":{}}"#).is_ok());
    assert!(Engine::from_yaml(&body.replace("{value: {path: unused}}","{context: {name: absent}}"),Steps::new()).is_err());
    assert!(Engine::from_yaml(&body.replace("fields: {}","fields: {}, typo: true"),Steps::new()).is_err());
}

#[test]
fn keyed_entries_authenticate_full_document_but_bound_selected_keys() {
    let body=BASE.replace("value_field: entry", "value_field: entry, keys: ['a.b', '$', missing]");
    let rows=read(&body,r#"{"ignored":0,"$":"exact","a.b":false,"other":{},"tail":null}"#).unwrap().tables.remove("rows").unwrap();
    assert_eq!(rows.len(),2);
    assert_eq!(rows[0]["key"],Val::Str("$".into()));
    assert_eq!(rows[1]["key"],Val::Str("a.b".into()));
    assert_eq!(rows[1]["entry"],Val::Bool(false));
    assert!(read(&body,r#"{"a.b":1} trailing"#).is_err());
    let empty=BASE.replace("value_field: entry", "value_field: entry, keys: []");
    assert!(read(&empty,r#"{"a":0,"b":1,"c":2,"d":3}"#).unwrap().tables["rows"].is_empty());
}

#[test]
fn keyed_entries_refuse_invalid_bounds_and_duplicates() {
    for keys in ["null", "[1]", "['a', 'a']", "{}"] {
        let body=BASE.replace("value_field: entry", &format!("value_field: entry, keys: {keys}"));
        assert!(Engine::from_yaml(&body,Steps::new()).is_err());
    }
    let keys=(0..1001).map(|n|format!("k{n}")).collect::<Vec<_>>().join(",");
    let body=BASE.replace("value_field: entry", &format!("value_field: entry, keys: [{keys}]"));
    assert!(Engine::from_yaml(&body,Steps::new()).is_err());
}
