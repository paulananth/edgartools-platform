use std::path::PathBuf;

use source_contract::{Engine, Lookups, Step, Steps, Val};

/// The Python step `blank_missing_token@1` (`edgar_warehouse/rules/steps.py`)
/// is the one the engine runs; this copy only lets the Rust tests read 13F.
fn blank_missing_token(value: &Val) -> Result<Val, String> {
    let Val::Str(text) = value else { return Ok(value.clone()) };
    let text = text.trim();
    let blank = text.is_empty() || text.eq_ignore_ascii_case("none") || text.eq_ignore_ascii_case("nan");
    Ok(if blank { Val::Null } else { Val::Str(text.to_string()) })
}

fn engine() -> Engine {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("contracts/thirteenf/contract.yaml");
    let mut steps = Steps::new();
    steps.insert("blank_missing_token@1".into(), Box::new(blank_missing_token) as Step);
    Engine::load(&path, steps).unwrap()
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
    assert_eq!(row["market_value"], Val::Float(7_877_566.0));
    assert_eq!(row["discretion_type"], Val::Str("SOLE".into()));
    assert_eq!(row["voting_auth_sole"], Val::Float(7827.0));
    assert_eq!(row["voting_auth_none"], Val::Float(0.0));
    assert_eq!(row["put_call"], Val::Null);
}

// The prototype read a different root as no rows; the engine fails closed
// (mastering to-do 15). 13F is not on the engine yet.
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
