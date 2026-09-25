use std::path::PathBuf;

use source_contract::{blank_missing_token, Engine, Val};

fn engine() -> Engine {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("contracts/thirteenf/contract.yaml");
    Engine::load(&path)
        .unwrap()
        .with_step("blank_missing_token@1", blank_missing_token)
}

#[test]
fn one_information_table_row_matches_the_contract_case() {
    let fixture =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("contracts/thirteenf/fixtures/one-row.xml");
    let bytes = std::fs::read(fixture).unwrap();
    let tables = engine().parse(&bytes).unwrap();
    let rows = &tables["sec_thirteenf_holding"];
    assert_eq!(rows.len(), 1);
    let row = &rows[0];
    assert_eq!(row["holding_index"], Val::Int(1));
    assert_eq!(row["cusip"], Val::Str("88579Y101".into()));
    assert_eq!(row["issuer_name"], Val::Str("3M CO".into()));
    assert_eq!(row["security_title"], Val::Str("COM".into()));
    assert_eq!(row["shares_held"], Val::Float(54242.0));
    assert_eq!(row["market_value"], Val::Float(7_877_566.0));
    assert_eq!(row["discretion_type"], Val::Str("SOLE".into()));
    assert_eq!(row["voting_auth_sole"], Val::Float(7827.0));
    assert_eq!(row["voting_auth_none"], Val::Float(0.0));
    assert_eq!(row["put_call"], Val::Null);
}

#[test]
fn a_different_root_yields_no_rows() {
    let bytes =
        br#"<ownershipDocument><infoTable><cusip>1</cusip></infoTable></ownershipDocument>"#;
    let tables = engine().parse(bytes).unwrap();
    assert!(tables["sec_thirteenf_holding"].is_empty());
}

#[test]
fn the_literal_title_none_is_null() {
    let bytes = br#"<?xml version="1.0"?>
        <informationTable xmlns="urn:thirteenf">
          <infoTable>
            <nameOfIssuer>ACME</nameOfIssuer>
            <titleOfClass>None</titleOfClass>
            <cusip>111111111</cusip>
            <value>10</value>
            <shrsOrPrnAmt><sshPrnamt>2</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
          </infoTable>
        </informationTable>"#;
    let tables = engine().parse(bytes).unwrap();
    assert_eq!(
        tables["sec_thirteenf_holding"][0]["security_title"],
        Val::Null
    );
}
