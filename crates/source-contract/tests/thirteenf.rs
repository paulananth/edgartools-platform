use std::path::PathBuf;

use source_contract::{Engine, Lookups, Steps, Val};

fn engine() -> Engine {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("contracts/thirteenf/contract.yaml");
    Engine::load(&path, Steps::new()).unwrap()
}

#[test]
fn one_information_table_row_matches_the_contract_case() {
    let fixture =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("contracts/thirteenf/fixtures/one-row.xml");
    let bytes = std::fs::read(fixture).unwrap();
    let tables = engine().read(&bytes, &Lookups::new()).unwrap().tables;
    let rows = &tables["sec_thirteenf_holding"];
    assert_eq!(rows.len(), 1);
    let row = &rows[0];
    assert_eq!(row["holding_index"], Val::Int(1));
    assert_eq!(row["cusip"], Val::Str("88579Y101".into()));
    assert_eq!(row["issuer_name"], Val::Str("3M CO".into()));
    assert_eq!(row["security_title"], Val::Str("COM".into()));
    assert_eq!(row["shares_held"], Val::Float(54242.0));
    assert_eq!(row["share_type"], Val::Str("SH".into()));
    assert_eq!(row["market_value"], Val::Float(7_877_566.0));
    assert_eq!(row["discretion_type"], Val::Str("SOLE".into()));
    assert_eq!(row["voting_auth_sole"], Val::Float(7827.0));
    assert_eq!(row["voting_auth_none"], Val::Float(0.0));
    assert_eq!(row["put_call"], Val::Null);
}

// The prototype read a different root as no rows; the engine fails closed
// (mastering to-do 15). The configured source.read worker uses this engine.
#[test]
fn a_different_root_is_rejected() {
    let bytes =
        br#"<ownershipDocument><infoTable><cusip>1</cusip></infoTable></ownershipDocument>"#;
    assert_eq!(engine().read(bytes, &Lookups::new()).unwrap_err().code, "wrong_root");
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
    let tables = engine().read(bytes, &Lookups::new()).unwrap().tables;
    assert_eq!(
        tables["sec_thirteenf_holding"][0]["security_title"],
        Val::Null
    );
}

#[test]
fn text_null_if_is_configured_and_runs_without_custom_steps() {
    let fixture =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("contracts/thirteenf/fixtures/one-row.xml");
    let xml = String::from_utf8(std::fs::read(fixture).unwrap()).unwrap()
        .replace("88579Y101", " None ")
        .replace("3M CO", " NaN ")
        .replace("<ns1:titleOfClass>COM</ns1:titleOfClass>", "<ns1:titleOfClass>   </ns1:titleOfClass>");
    let bytes = xml.into_bytes();
    let tables = engine().read(&bytes, &Lookups::new()).unwrap().tables;
    let row = &tables["sec_thirteenf_holding"][0];
    assert_eq!(row["cusip"], Val::Null);
    assert_eq!(row["issuer_name"], Val::Null);
    assert_eq!(row["security_title"], Val::Null);
}

#[test]
fn text_null_if_rejects_a_non_list_configuration() {
    let contract = include_str!("../contracts/thirteenf/contract.yaml");
    let malformed = contract.replace("null_if: [\"\", \"none\", \"nan\"]", "null_if: none");
    let error = Engine::from_yaml(&malformed, Steps::new()).err().unwrap();
    assert_eq!(error.detail, "text null_if must be a list");
}
