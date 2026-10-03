use source_contract::{Engine, Lookups, Steps};

const CONTRACT: &str = include_str!("../contracts/thirteenf/contract.yaml");

#[test]
fn rejects_text_and_cdata_outside_the_xml_root() {
    let engine = Engine::from_yaml(CONTRACT, Steps::new()).unwrap();
    for bytes in [
        "junk<informationTable/>",
        "<informationTable/>junk",
        "<informationTable/>\u{a0}",
        "<![CDATA[junk]]><informationTable/>",
        "<informationTable/><![CDATA[junk]]>",
        "</informationTable>",
    ] {
        assert_eq!(engine.read(bytes.as_bytes(), &Lookups::new()).unwrap_err().code, "malformed");
    }
    assert!(engine.read(b" \n<informationTable/> \n", &Lookups::new()).is_ok());
}

#[test]
fn refuses_malformed_safety_gates_at_contract_load() {
    for extra in [
        "require: { path: missing }",
        "limits: { max_bytes: -1 }",
        "limits: { max_records: 0 }",
        "limits: { max_bytes: true }",
        "limits: { typo: 1 }",
        "record_count: { path: count, table: missing }",
        "root: 1",
        "on_parse_error: ignored",
    ] {
        let contract = format!("read:\n  format: xml\n  {extra}\n  tables:\n    rows:\n      columns:\n        value: {{ const: {{ value: null }} }}\n");
        assert!(Engine::from_yaml(&contract, Steps::new()).is_err(), "{extra}");
    }
    let contract = "read: { format: xml, tables: { rows: { checks: {}, columns: { value: {const: {value: null}} } } } }";
    assert!(Engine::from_yaml(contract, Steps::new()).is_err());
}
