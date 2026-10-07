use source_contract::{Engine,Lookups,Steps,Val};
const BASE: &str = r#"read:
  format: json
  limits: {max_bytes: 4194304}
  tables:
    rows:
      each: .
      columns:
        result:
          join:
            path: lines
            item_path: text
            separator: "\n"
            trim: true
            skip_empty: true
            null_if_empty: true
            max_items: 3
"#;
fn result(body:&str, raw:&str)->Result<Val,source_contract::Rejected>{
    Ok(Engine::from_yaml(body,Steps::new()).unwrap().read(raw.as_bytes(),&Lookups::new())?.tables["rows"][0]["result"].clone())
}
#[test]
fn projected_text_join_preserves_order_and_python_whitespace(){
    assert_eq!(result(BASE,r#"{"lines":[{"text":" \u001cSuite\u001f "},{"text":"\u00a0"},{"text":"Wing"}]}"#).unwrap(),Val::Str("Suite\nWing".into()));
    let body=BASE.replace("trim: true","trim: false").replace("skip_empty: true","skip_empty: false");
    assert_eq!(result(&body,r#"{"lines":[{"text":" "},{"text":""}]}"#).unwrap(),Val::Str(" \n".into()));
    let body=BASE.replace("item_path: text","item_path: .");
    assert_eq!(result(&body,r#"{"lines":[" A ","B"]}"#).unwrap(),Val::Str("A\nB".into()));
}
#[test]
fn missing_null_and_empty_outputs_have_explicit_meaning(){
    for raw in ["{}",r#"{"lines":null}"#,r#"{"lines":[]}"#,r#"{"lines":[{"text":" "}]}"#]{assert_eq!(result(BASE,raw).unwrap(),Val::Null);}
    assert_eq!(result(&BASE.replace("null_if_empty: true","null_if_empty: false"),r#"{"lines":[]}"#).unwrap(),Val::Str("".into()));
}
#[test]
fn structured_and_nontext_values_refuse_even_after_an_empty_item(){
    for raw in [r#"{"lines":{}}"#,r#"{"lines":false}"#,r#"{"lines":0}"#,r#"{"lines":"A"}"#,
        r#"{"lines":[{}]}"#,r#"{"lines":[null]}"#,r#"{"lines":[{"text":false}]}"#,r#"{"lines":[{"text":0}]}"#,
        r#"{"lines":[{"text":null}]}"#,r#"{"lines":[{"text":[]}]}"#,r#"{"lines":[{"text":" "},{"text":{}}]}"#]{
        assert_eq!(result(BASE,raw).unwrap_err().code,"join_shape","{raw}");
    }
}
#[test]
fn raw_count_and_utf8_output_bounds_apply_before_omission_and_publication(){
    assert_eq!(result(BASE,r#"{"lines":[{"text":""},{"text":""},{"text":""},{"text":""}]}"#).unwrap_err().code,"join_limit");
    let exactly="x".repeat(1_048_576);
    assert_eq!(result(BASE,&serde_json::json!({"lines":[{"text":exactly}]}).to_string()).unwrap(),Val::Str(exactly));
    let overflow="é".repeat(524_289);
    assert_eq!(result(BASE,&serde_json::json!({"lines":[{"text":overflow}]}).to_string()).unwrap_err().code,"join_limit");
}
#[test]
fn malformed_join_contracts_fail_before_reading(){
    for (old,new) in [("max_items: 3","max_items: 0"),("max_items: 3","max_items: true"),("max_items: 3","max_items: 100001"),
        ("trim: true","trim: yes"),("separator: \"\\n\"","separator: 4"),("item_path: text","item_path: []"),
        ("max_items: 3","unknown: 3"),("skip_empty: true","from: somewhere")]{
        assert!(Engine::from_yaml(&BASE.replace(old,new),Steps::new()).is_err(),"{new}");
    }
}
#[test]
fn nullable_objects_omit_only_declared_nulls_and_keep_exact_base_values(){
    let body=BASE.replace("          join:\n            path: lines\n            item_path: text\n            separator: \"\\n\"\n            trim: true\n            skip_empty: true\n            null_if_empty: true\n            max_items: 3",
        "          object:\n            omit_nulls: true\n            null_if_empty: true\n            fields:\n              a: {value: {path: a}}\n              b: {value: {path: b}}");
    assert_eq!(result(&body,"{}").unwrap(),Val::Null);
    let actual=result(&body,r#"{"a":false,"b":0}"#).unwrap();
    assert_eq!(actual,Val::Map([("a".into(),Val::Bool(false)),("b".into(),Val::Int(0))].into()));
    let base=body.replace("omit_nulls: true","base: {value: {path: base}}\n            omit_nulls: true");
    assert_eq!(result(&base,r#"{"base":{"unknown":null}}"#).unwrap(),Val::Map([("unknown".into(),Val::Null)].into()));
    assert_eq!(result(&base,r#"{"base":{"a":null}}"#).unwrap_err().code,"object_field_conflict");
    assert!(Engine::from_yaml(&body.replace("omit_nulls: true","omit_nulls: 1"),Steps::new()).is_err());
    assert!(Engine::from_yaml(&body.replace("null_if_empty: true","null_if_empty: []"),Steps::new()).is_err());
}
#[test]
fn typed_values_preserve_nonblank_text_and_reject_wrong_types_before_null_coercion(){
    let body=BASE.replace("          join:\n            path: lines\n            item_path: text\n            separator: \"\\n\"\n            trim: true\n            skip_empty: true\n            null_if_empty: true\n            max_items: 3", "          value: {path: a, type: text, null_if_blank: true}");
    assert_eq!(result(&body,r#"{"a":" \u001cA\u001f "}"#).unwrap(),Val::Str(" \u{1c}A\u{1f} ".into()));
    for raw in ["{}",r#"{"a":null}"#,r#"{"a":"\u001c\u001f "}"#]{ assert_eq!(result(&body,raw).unwrap(),Val::Null); }
    for raw in [r#"{"a":false}"#,r#"{"a":0}"#,r#"{"a":{}}"#,r#"{"a":[]}"#]{assert_eq!(result(&body,raw).unwrap_err().code,"value_type");}
    let trimmed=body.replace("null_if_blank: true","null_if_blank: true, trim: true");
    assert_eq!(result(&trimmed,r#"{"a":" \u001cA\u001f "}"#).unwrap(),Val::Str("A".into()));
    for raw in ["{}",r#"{"a":" "}"#] { assert_eq!(result(&body.replace("type: text","type: text, nullable: false"),raw).unwrap_err().code,"value_type"); }
    for options in ["type: unknown","type: text, nullable: 0","type: text, trim: 'true'","type: text, null_if_blank: null"]{
        assert!(Engine::from_yaml(&body.replace("type: text, null_if_blank: true",options),Steps::new()).is_err());
    }
    let integer=body.replace("type: text","type: integer");
    assert_eq!(result(&integer,r#"{"a":18446744073709551615}"#).unwrap(),Val::UInt(u64::MAX));
    assert_eq!(result(&integer,r#"{"a":1.0}"#).unwrap_err().code,"value_type");
    let number=body.replace("type: text","type: number");
    assert_eq!(result(&number,r#"{"a":1.0}"#).unwrap(),Val::Float(1.0));
    assert_eq!(result(&number,r#"{"a":true}"#).unwrap_err().code,"value_type");
}
#[test]
fn literal_reserved_keys_retain_nontext_types_in_typed_reads(){
    let body=BASE.replace("          join:\n            path: lines\n            item_path: text\n            separator: \"\\n\"\n            trim: true\n            skip_empty: true\n            null_if_empty: true\n            max_items: 3", "          value: {path: node.$}");
    for (raw,expected) in [(r#"{"node":{"$":false}}"#,Val::Bool(false)),
        (r#"{"node":{"$":18446744073709551615}}"#,Val::UInt(u64::MAX)),
        (r#"{"node":{"$":[]}}"#,Val::List(vec![])),(r#"{"node":{"$":{}}}"#,Val::Map(Default::default()))]{
        assert_eq!(result(&body,raw).unwrap(),expected);
    }
    assert_eq!(result(&body.replace("node.$","node.@id"),r#"{"node":{"@id":false}}"#).unwrap(),Val::Bool(false));
    let typed=body.replace("path: node.$","path: node.$, type: text");
    assert_eq!(result(&typed,r#"{"node":{"$":false}}"#).unwrap_err().code,"value_type");
}
#[test]
fn joined_item_shape_is_explicit_for_reserved_text_paths(){
    let body=BASE.replace("item_path: text","item_path: $\n            item_type: object");
    assert_eq!(result(&body,r#"{"lines":[{"$":" A "}]}"#).unwrap(),Val::Str("A".into()));
    for raw in [r#"{"lines":["A"]}"#,r#"{"lines":[{"$":false}]}"#,r#"{"lines":[{"$":0}]}"#,r#"{"lines":[{"$":[]}]}"#]{
        assert_eq!(result(&body,raw).unwrap_err().code,"join_shape");
    }
    let text=BASE.replace("item_path: text","item_path: .\n            item_type: text");
    assert_eq!(result(&text,r#"{"lines":[" A "]}"#).unwrap(),Val::Str("A".into()));
    assert_eq!(result(&text,r#"{"lines":[{"$":"A"}]}"#).unwrap_err().code,"join_shape");
    assert!(Engine::from_yaml(&body.replace("item_type: object","item_type: false"),Steps::new()).is_err());
}
#[test]
fn literal_paths_do_not_promote_scalar_or_repeated_parents(){
    let expression="          value: {path: node.$, path_mode: literal}";
    let body=BASE[..BASE.find("          join:").unwrap()].to_owned()+expression+"\n";
    for raw in [r#"{"node":"A"}"#,r#"{"node":[{"$":"A"}]}"#,r#"{"node":null}"#] {
        assert_eq!(result(&body,raw).unwrap(),Val::Null,"{raw}");
    }
    assert_eq!(result(&body,r#"{"node":{"$":"A"}}"#).unwrap(),Val::Str("A".into()));
    assert_eq!(result(&body.replace(", path_mode: literal",""),r#"{"node":"A"}"#).unwrap(),Val::Str("A".into()));
    assert!(Engine::from_yaml(&body.replace("node.$","node[0].$"),Steps::new()).is_err());
    assert!(Engine::from_yaml(&body.replace("path_mode: literal","path_mode: unknown"),Steps::new()).is_err());
}
