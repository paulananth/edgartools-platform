//! Terms found in a page's text (ticket 149): `regex_extract` takes a pattern's capture group,
//! `found` says whether a text holds one, `first_found` takes the first block of a page that does.
//! Every name and number below is invented.

use source_contract::{Engine, Lookups, Steps, Val};

const PAGE: &str = "<html><body><p>Invented Holdings Inc.</p>\
    <p>2,500,000 Shares of Common Stock</p>\
    <p>We expect the price to be between $14.00 and $16.00 per share. Listing: Invented Exchange under the symbol \"INVT\".</p>\
    <p>BALANCE SHEETS</p><p>(in thousands)</p>\
    <table><tr><td></td><td>2025</td><td>2024</td></tr>\
    <tr><td>Total assets</td><td>$ 1,234</td><td>(56)</td></tr>\
    <tr><td>Total liabilities</td><td>789</td><td>700</td></tr></table></body></html>";

const CONTRACT: &str = "read:
  format: html
  limits: {max_bytes: 100000, max_records: 100}
  tables:
    offering:
      each: .
      columns:
        shares:
          first_found:
            path: block
            from: document
            within: 20
            transforms:
              - regex_extract: {pattern: '^([0-9][0-9,]*) Shares of Common Stock', group: 1}
        price_low:
          first_found:
            path: block
            from: document
            transforms:
              - regex_extract: {pattern: 'between \\$([0-9.]+) and', group: 1}
        symbol:
          first_found:
            path: block
            from: document
            transforms:
              - regex_extract: {pattern: 'under the symbol \"([A-Z]+)\"', group: 1}
        warrants:
          first_found:
            path: block
            from: document
            transforms:
              - regex_extract: {pattern: '([0-9]+) warrants', group: 1}
    lines:
      each: row
      select:
        found:
          path: c1.$
          transforms:
            - regex_extract: {pattern: '^(?i:total assets)$', group: 0}
      columns:
        label: {text: {path: c1.$}}
        above: {text: {path: '@above'}}
        above2: {text: {path: '@above2'}}
        first: {text: {path: c2.$, transforms: [{regex_replace: {pattern: '[$,\\s]', with: ''}}]}}
        second: {text: {path: c3.$, transforms: [{regex_extract: {pattern: '^\\(([0-9]+)\\)$', group: 1}}]}}
";

fn engine(contract: &str) -> Result<Engine, String> {
    Engine::from_yaml(contract, Steps::new()).map_err(|e| e.to_string())
}

#[test]
fn the_first_block_holding_a_pattern_gives_its_group_and_a_page_without_it_gives_null() {
    let tables = engine(CONTRACT).unwrap().read(PAGE.as_bytes(), &Lookups::new()).unwrap().tables;
    let row = &tables["offering"][0];
    assert_eq!(row["shares"], Val::Str("2,500,000".into()));
    assert_eq!(row["price_low"], Val::Str("14.00".into()));
    assert_eq!(row["symbol"], Val::Str("INVT".into()));
    assert_eq!(row["warrants"], Val::Null);
}

#[test]
fn rows_are_kept_when_their_label_matches_and_carry_what_is_above_their_table() {
    let tables = engine(CONTRACT).unwrap().read(PAGE.as_bytes(), &Lookups::new()).unwrap().tables;
    let lines = &tables["lines"];
    assert_eq!(lines.len(), 1);
    assert_eq!(lines[0]["label"], Val::Str("Total assets".into()));
    assert_eq!(lines[0]["above"], Val::Str("(in thousands)".into()));
    assert_eq!(lines[0]["above2"], Val::Str("BALANCE SHEETS".into()));
    assert_eq!(lines[0]["first"], Val::Str("1234".into()));
    // A parenthesised cell is captured without its brackets; a plain one has no match and is empty.
    assert_eq!(lines[0]["second"], Val::Str("56".into()));
}

#[test]
fn a_group_the_pattern_lacks_or_a_missing_transforms_list_is_refused_when_the_contract_loads() {
    let bad_group = CONTRACT.replace("group: 1}\n        price_low", "group: 4}\n        price_low");
    assert!(engine(&bad_group).err().is_some_and(|e| e.contains("not in the pattern")));
    let no_transforms = "read:\n  format: html\n  tables:\n    t:\n      each: .\n      columns:\n        a: {found: {path: c1.$}}\n";
    assert!(engine(no_transforms).err().is_some_and(|e| e.contains("requires transforms")));
}

fn capture(metadata: &str) -> Vec<u8> {
    use std::io::Write;
    let mut out = std::io::Cursor::new(Vec::new());
    let mut archive = zip::ZipWriter::new(&mut out);
    let options = zip::write::SimpleFileOptions::default();
    archive.start_file("metadata.json", options).unwrap();
    archive.write_all(metadata.as_bytes()).unwrap();
    archive.start_file("payload", options).unwrap();
    archive.write_all(PAGE.as_bytes()).unwrap();
    archive.finish().unwrap();
    out.into_inner()
}

const ZIPPED: &str = "read:
  format: html
  container: zip
  member: payload
  context:
    accession: {type: text, zip_json: {member: metadata.json, path: scope.accession}}
  limits: {max_bytes: 100000, max_records: 100}
  tables:
    filing:
      each: .
      columns:
        accession: {context: {name: accession}}
";

#[test]
fn a_context_field_is_filled_from_a_json_member_of_the_zip_and_never_by_the_caller() {
    let engine = engine(ZIPPED).unwrap();
    let good = capture(r#"{"scope": {"accession": "0000000000-26-000001", "cik": "1"}}"#);
    let rows = engine.read(&good, &Lookups::new()).unwrap().tables.remove("filing").unwrap();
    assert_eq!(rows[0]["accession"], Val::Str("0000000000-26-000001".into()));
    let lacking = capture(r#"{"scope": {"cik": "1"}}"#);
    assert_eq!(engine.read(&lacking, &Lookups::new()).unwrap_err().code, "zip_json");
    let caller: source_contract::Row = [("accession".to_string(), Val::Str("x".into()))].into_iter().collect();
    assert_eq!(engine.read_with_context(&good, &Lookups::new(), &caller).unwrap_err().code, "invalid_context");
    let unzipped = ZIPPED.replace("  container: zip\n  member: payload\n", "");
    assert!(engine_error(&unzipped).contains("zip_json"));
}

fn engine_error(contract: &str) -> String {
    engine(contract).err().unwrap_or_default()
}
