//! Bounded research probes of the unchanged Source Contract prototype.
//! These characterize partial projection and counterexamples, not deployment readiness.

use source_contract::{Engine, Val};
use std::path::PathBuf;

fn research_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../docs/research/experiments/custom-parsing/rust")
}

fn engine() -> Engine {
    // Intentionally register no custom callback: that would retain custom code.
    Engine::load(&research_dir().join("gleif-level1.yaml")).unwrap()
}

fn fixture() -> String {
    std::fs::read_to_string(research_dir().join("gleif-two-records.xml")).unwrap()
}

fn configured(yaml: &str) -> Engine {
    let path = std::env::temp_dir().join(format!(
        "source-contract-config-research-{}-{:?}.yaml",
        std::process::id(),
        std::thread::current().id()
    ));
    std::fs::write(&path, yaml).unwrap();
    let engine = Engine::load(&path).unwrap();
    std::fs::remove_file(path).unwrap();
    engine
}

#[test]
fn config_projects_multiple_namespaced_gleif_rows_with_optional_scalars() {
    let result = engine().parse(fixture().as_bytes()).unwrap();
    let rows = &result["gleif_projection"];
    assert_eq!(rows.len(), 2);
    // The Python native-decoder probe reads this exact golden file too.
    // JSON is a YAML subset; reuse the crate's existing dependency.
    let golden: serde_yaml::Value = serde_yaml::from_str(
        &std::fs::read_to_string(research_dir().join("../rust_scalar_expected.json")).unwrap(),
    )
    .unwrap();
    let expected_rows = golden.as_sequence().unwrap();
    assert_eq!(rows.len(), expected_rows.len());
    for (actual, expected) in rows.iter().zip(expected_rows) {
        for (key, value) in expected.as_mapping().unwrap() {
            let expected_value = match value {
                serde_yaml::Value::Null => Val::Null,
                serde_yaml::Value::String(value) => Val::Str(value.clone()),
                serde_yaml::Value::Number(value) => Val::Int(value.as_i64().unwrap()),
                other => panic!("unexpected golden scalar: {other:?}"),
            };
            assert_eq!(actual[key.as_str().unwrap()], expected_value);
        }
    }
    assert_eq!(rows[0]["ordinal"], Val::Int(1));
    assert_eq!(rows[0]["lei"], Val::Str("5493001KJTIIGC8Y1R12".into()));
    assert_eq!(rows[0]["name"], Val::Str("Acme & Company".into()));
    assert_eq!(rows[0]["category"], Val::Str("GENERAL".into()));
    assert_eq!(rows[0]["country"], Val::Str("US".into()));
    assert_eq!(rows[0]["postal_code"], Val::Str("10001".into()));
    assert_eq!(rows[0]["language"], Val::Str("en".into()));
    assert_eq!(rows[1]["ordinal"], Val::Int(2));
    assert_eq!(rows[1]["lei"], Val::Str("529900T8BM49AURSDO55".into()));
    assert_eq!(rows[1]["name"], Val::Str("Example Limited".into()));
    assert_eq!(rows[1]["country"], Val::Str("GB".into()));
    assert_eq!(rows[1]["postal_code"], Val::Null);
    assert_eq!(rows[1]["language"], Val::Null);
}

#[test]
fn cdata_legal_name_is_lost_by_existing_xml_reader() {
    let xml = fixture().replace(
        "<lei:LegalName>Example Limited</lei:LegalName>",
        "<lei:LegalName><![CDATA[Café Limited]]></lei:LegalName>",
    );
    let result = engine().parse(xml.as_bytes()).unwrap();
    assert_eq!(result["gleif_projection"][1]["name"], Val::Null);
}

#[test]
fn wrong_root_is_empty_success_instead_of_a_validation_error() {
    let xml = fixture().replace("lei:LEIData", "lei:OtherData");
    assert!(engine().parse(xml.as_bytes()).unwrap()["gleif_projection"].is_empty());
}

#[test]
fn malformed_xml_is_empty_success_instead_of_a_validation_error() {
    let result = engine().parse(b"<LEIData><LEIRecords></LEIData>").unwrap();
    assert!(result["gleif_projection"].is_empty());
}

#[test]
fn wrong_namespace_still_projects_rows() {
    let xml = fixture().replace("http://www.gleif.org/data/schema/leidata/2016", "urn:wrong");
    assert_eq!(
        engine().parse(xml.as_bytes()).unwrap()["gleif_projection"].len(),
        2
    );
}

#[test]
fn dtd_without_entities_is_accepted() {
    let xml = fixture().replace(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
        "<!DOCTYPE LEIData []>",
    );
    assert_eq!(
        engine().parse(xml.as_bytes()).unwrap()["gleif_projection"].len(),
        2
    );
}

#[test]
fn missing_header_and_wrong_record_count_do_not_block_projection() {
    let xml = fixture();
    let start = xml.find("  <lei:LEIHeader>").unwrap();
    let end = xml.find("  </lei:LEIHeader>").unwrap() + "  </lei:LEIHeader>".len();
    let no_header = format!("{}{}", &xml[..start], &xml[end..]);
    assert_eq!(
        engine().parse(no_header.as_bytes()).unwrap()["gleif_projection"].len(),
        2
    );
    let wrong_count = xml.replace(
        "<lei:RecordCount>2</lei:RecordCount>",
        "<lei:RecordCount>999</lei:RecordCount>",
    );
    assert_eq!(
        engine().parse(wrong_count.as_bytes()).unwrap()["gleif_projection"].len(),
        2
    );
}

#[test]
fn duplicate_projected_scalar_is_an_error() {
    let xml = fixture().replace(
        "<lei:LEI>5493001KJTIIGC8Y1R12</lei:LEI>",
        "<lei:LEI>5493001KJTIIGC8Y1R12</lei:LEI><lei:LEI>529900T8BM49AURSDO55</lei:LEI>",
    );
    let error = engine().parse(xml.as_bytes()).unwrap_err();
    assert!(error.contains("crosses a repeating group"), "{error}");
}

#[test]
fn duplicate_unprojected_header_is_accepted() {
    let xml = fixture().replace(
        "<lei:RecordCount>2</lei:RecordCount>",
        "<lei:RecordCount>2</lei:RecordCount><lei:RecordCount>2</lei:RecordCount>",
    );
    assert_eq!(
        engine().parse(xml.as_bytes()).unwrap()["gleif_projection"].len(),
        2
    );
}

#[test]
fn invalid_lei_category_and_deletion_flag_are_merely_projected() {
    let xml = fixture()
        .replace("5493001KJTIIGC8Y1R12", "NOT-AN-LEI")
        .replace(
            "<lei:EntityCategory>GENERAL</lei:EntityCategory>",
            "<lei:EntityCategory>UNKNOWN</lei:EntityCategory>",
        )
        .replace(
            "</lei:Entity>",
            "</lei:Entity><lei:Extension><lei:Deletion>true</lei:Deletion></lei:Extension>",
        );
    let result = engine().parse(xml.as_bytes()).unwrap();
    assert_eq!(
        result["gleif_projection"][0]["lei"],
        Val::Str("NOT-AN-LEI".into())
    );
    assert_eq!(
        result["gleif_projection"][0]["category"],
        Val::Str("UNKNOWN".into())
    );
}

#[test]
fn json_gleif_and_sec_parallel_arrays_are_unsupported() {
    let e = configured("read:\n  format: json\n  tables: {}\n");
    for bytes in [
        br#"{"records":[{"LEI":{"$":"5493001KJTIIGC8Y1R12"}}]}"#.as_slice(),
        br#"{"filings":{"recent":{"accessionNumber":["a","b"],"form":["10-K","10-Q"]}}}"#
            .as_slice(),
    ] {
        assert_eq!(
            e.parse(bytes).unwrap_err(),
            "this reader implements xml, not json"
        );
    }
}

#[test]
fn group_by_is_not_an_existing_config_primitive() {
    let e = configured("read:\n  format: xml\n  root: LEIData\n  tables:\n    groups:\n      each: LEIRecords.LEIRecord\n      columns:\n        grouped: { group_by: { field: LEI.$ } }\n");
    assert_eq!(
        e.parse(fixture().as_bytes()).unwrap_err(),
        "primitive group_by is not implemented"
    );
}

#[test]
fn configured_custom_step_without_custom_code_is_not_a_replacement() {
    let e = configured("read:\n  format: xml\n  root: LEIData\n  tables:\n    rows:\n      each: LEIRecords.LEIRecord\n      columns:\n        lei: { custom: { step: lei@1, inputs: { value: { text: { path: LEI.$ } } } } }\n");
    assert_eq!(
        e.parse(fixture().as_bytes()).unwrap_err(),
        "no value step lei@1"
    );
}
