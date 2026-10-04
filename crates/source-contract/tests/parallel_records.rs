//! Parallel JSON arrays are selected by contract, without source-specific code.
use source_contract::{Engine, Lookups, Raw, Steps, Val};

const CONTRACT: &str = r#"
read:
  format: json
  limits: { max_bytes: 1048576, max_records: 3 }
  tables:
    filings:
      each:
        parallel:
          path: filings.recent
          anchor: accessionNumber
          fields: { accession: accessionNumber, form: form }
          lengths: equal
      columns:
        ordinal: { ordinal: {} }
        accession: { text: { path: accession } }
        form: { text: { path: form, null_if: [""] } }
        cik: { text: { path: cik, from: document } }
"#;

fn engine(contract: &str) -> Engine {
    Engine::from_yaml(contract, Steps::new()).unwrap()
}

#[test]
fn aligns_arrays_and_keeps_document_context() {
    let data = br#"{"cik": "320193", "filings": {"recent": {"accessionNumber": ["a", "b"], "form": ["10-K", "8-K"]}}}"#;
    let reading = engine(CONTRACT).read(data, &Lookups::new()).unwrap();
    assert_eq!(reading.tables["filings"].len(), 2);
    assert_eq!(reading.tables["filings"][1]["accession"], Val::Str("b".into()));
    assert_eq!(reading.tables["filings"][1]["form"], Val::Str("8-K".into()));
    assert_eq!(reading.tables["filings"][1]["cik"], Val::Str("320193".into()));
    assert_eq!(reading.tables["filings"][1]["ordinal"], Val::Int(2));
}

#[test]
fn equal_lengths_refuses_misalignment_instead_of_truncating() {
    for forms in [r#"[]"#, r#"["10-K"]"#, r#"["10-K", "8-K", "6-K"]"#] {
        let data = format!(r#"{{"filings":{{"recent":{{"accessionNumber":["a","b"],"form":{forms}}}}}}}"#);
        assert_eq!(engine(CONTRACT).read(data.as_bytes(), &Lookups::new()).unwrap_err().code, "parallel_length");
    }
}

#[test]
fn declared_anchor_policy_pads_short_or_missing_arrays_and_ignores_trailing_values() {
    let contract = CONTRACT.replace("lengths: equal", "lengths: anchor");
    for forms in [r#""#, r#", "form": []"#, r#", "form": ["10-K"]"#, r#", "form": ["10-K", "8-K", "6-K"]"#] {
        let data = format!(r#"{{"filings":{{"recent":{{"accessionNumber":["a","b"]{forms}}}}}}}"#);
        let reading = engine(&contract).read(data.as_bytes(), &Lookups::new()).unwrap();
        assert_eq!(reading.tables["filings"].len(), 2);
        assert_eq!(reading.tables["filings"][1]["form"],
                   if forms.contains("8-K") { Val::Str("8-K".into()) } else { Val::Null });
    }
}

#[test]
fn empty_and_absent_groups_yield_no_records() {
    for data in [r#"{}"#, r#"{"filings":{"recent":{}}}"#,
                 r#"{"filings":{"recent":{"accessionNumber":[],"form":[]}}}"#] {
        assert!(engine(CONTRACT).read(data.as_bytes(), &Lookups::new()).unwrap().tables["filings"].is_empty());
    }
}

#[test]
fn arrays_are_arrays_even_when_they_hold_one_value() {
    for data in [r#"{"filings":{"recent":{"accessionNumber":"a"}}}"#,
                 r#"{"filings":{"recent":{"accessionNumber":null}}}"#,
                 r#"{"filings":{"recent":{"accessionNumber":["a"],"form":"10-K"}}}"#,
                 r#"{"filings":{"recent":[]}}"#] {
        assert_eq!(engine(CONTRACT).read(data.as_bytes(), &Lookups::new()).unwrap_err().code, "parallel_shape");
    }
    let data = br#"{"filings":{"recent":{"accessionNumber":["a"],"form":["10-K"]}}}"#;
    assert_eq!(engine(CONTRACT).read(data, &Lookups::new()).unwrap().tables["filings"].len(), 1);
}

#[test]
fn limit_is_checked_against_anchor_before_expanding() {
    let data = br#"{"filings":{"recent":{"accessionNumber":["a","b","c","d"]}}}"#;
    assert_eq!(engine(CONTRACT).read(data, &Lookups::new()).unwrap_err().code, "limit_exceeded");
}

#[test]
fn deferred_evidence_is_the_exact_aligned_record_and_keeps_ordinal() {
    let contract = format!("{CONTRACT}\n      checks:\n        - {{ check: in_set, column: form, values: [10-K], on_fail: defer, reason: other_form }}\n");
    let data = br#"{"filings":{"recent":{"accessionNumber":["a","b"],"form":["10-K","8-K"]}}}"#;
    let reading = engine(&contract).read(data, &Lookups::new()).unwrap();
    assert_eq!(reading.tables["filings"].len(), 1);
    assert_eq!(reading.deferred.len(), 1);
    assert_eq!(reading.deferred[0].ordinal, 2);
    assert_eq!(reading.deferred[0].reason, "other_form");
    let Raw::Map(raw) = &reading.deferred[0].raw else { panic!("record map expected") };
    assert_eq!(raw["accession"], Raw::Text("b".into()));
    assert_eq!(raw["form"], Raw::Text("8-K".into()));
}

#[test]
fn malformed_parallel_contracts_are_refused_on_load() {
    for contract in [
        CONTRACT.replace("format: json", "format: jsonl"),
        CONTRACT.replace("lengths: equal", "lengths: guessing"),
        CONTRACT.replace("lengths: equal", "lengths: 1"),
        CONTRACT.replace("anchor: accessionNumber", "anchor: []"),
        CONTRACT.replace("path: filings.recent", "path: []"),
        CONTRACT.replace("fields: { accession: accessionNumber, form: form }", "fields: {}"),
        CONTRACT.replace("fields: { accession: accessionNumber, form: form }", "fields: { accession: 1 }"),
        CONTRACT.replace("fields: { accession: accessionNumber, form: form }", "fields: { 'bad.alias': form }"),
        CONTRACT.replace("anchor: accessionNumber", "anchor: accessionNumber.$"),
        CONTRACT.replace("lengths: equal", "lengths: equal\n          mystery: true"),
    ] {
        assert_eq!(Engine::from_yaml(&contract, Steps::new()).err().unwrap().code, "contract");
    }
}

#[test]
fn text_can_explicitly_preserve_source_whitespace_and_exact_empty_tokens() {
    let contract = CONTRACT.replace("path: form, null_if: [\"\"]", "path: form, trim: false, null_if: [\"\"]");
    let data = br#"{"filings":{"recent":{"accessionNumber":["a","b"],"form":[" ",""]}}}"#;
    let reading = engine(&contract).read(data, &Lookups::new()).unwrap();
    let rows = &reading.tables["filings"];
    assert_eq!(rows[0]["form"], Val::Str(" ".into()));
    assert_eq!(rows[1]["form"], Val::Null);
    let invalid = CONTRACT.replace("path: form, null_if:", "path: form, trim: [false], null_if:");
    assert_eq!(Engine::from_yaml(&invalid, Steps::new()).err().unwrap().code, "contract");
}

#[test]
fn root_arrays_are_not_objects_with_an_item_array() {
    let contract = CONTRACT.replace("path: filings.recent", "path: '.'");
    for data in ["[]", "[{}]"] {
        assert_eq!(engine(&contract).read(data.as_bytes(), &Lookups::new()).unwrap_err().code, "parallel_shape");
    }
}

#[test]
fn text_defaults_retain_existing_null_token_normalization_unless_trim_is_disabled() {
    let contract = CONTRACT.replace("path: form, null_if: [\"\"]", "path: missing, default: ' x ', null_if: [x]");
    let data = br#"{"filings":{"recent":{"accessionNumber":["a"],"form":["10-K"]}}}"#;
    assert_eq!(engine(&contract).read(data, &Lookups::new()).unwrap().tables["filings"][0]["form"], Val::Null);
    let exact = contract.replace("path: missing", "path: missing, trim: false");
    assert_eq!(engine(&exact).read(data, &Lookups::new()).unwrap().tables["filings"][0]["form"], Val::Str(" x ".into()));
}

#[test]
fn invalid_objects_and_character_sequences_require_explicit_policy() {
    let contract = CONTRACT.replace("lengths: equal", "lengths: anchor\n          on_invalid_object: empty\n          strings: characters");
    for data in [r#"{"filings":null}"#, r#"{"filings":{"recent":false}}"#, r#"{"filings":{"recent":[]}}"#] {
        assert!(engine(&contract).read(data.as_bytes(), &Lookups::new()).unwrap().tables["filings"].is_empty());
        assert_eq!(engine(CONTRACT).read(data.as_bytes(), &Lookups::new()).unwrap_err().code, "parallel_shape");
    }
    let reading = engine(&contract).read("{\"filings\":{\"recent\":{\"accessionNumber\":[\"a\",\"b\",\"c\"],\"form\":\"é🦀\"}}}".as_bytes(), &Lookups::new()).unwrap();
    let rows = &reading.tables["filings"];
    assert_eq!(rows[0]["form"], Val::Str("é".into()));
    assert_eq!(rows[1]["form"], Val::Str("🦀".into()));
    assert_eq!(rows[2]["form"], Val::Null);
    assert_eq!(engine(&contract).read(br#"{"filings":{"recent":{"accessionNumber":[],"form":null}}}"#, &Lookups::new()).unwrap().tables["filings"].len(), 0);
    let long = format!(r#"{{"filings":{{"recent":{{"accessionNumber":"{}"}}}}}}"#, "a".repeat(100));
    assert_eq!(engine(&contract).read(long.as_bytes(), &Lookups::new()).unwrap_err().code, "limit_exceeded");
    // Object policy does not excuse an invalid array inside a valid object.
    assert_eq!(engine(&contract).read(br#"{"filings":{"recent":{"accessionNumber":true}}}"#, &Lookups::new()).unwrap_err().code, "parallel_shape");
    for bad in ["strings: null", "strings: bytes", "on_invalid_object: false", "on_invalid_object: skip"] {
        let contract = format!("{}\n          {bad}\n      columns: {{}}\n", CONTRACT.split("      columns:").next().unwrap());
        assert!(Engine::from_yaml(&contract, Steps::new()).is_err());
    }
}
