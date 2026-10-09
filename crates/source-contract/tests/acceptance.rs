//! The engine's acceptance suite (mastering to-do 15).
//!
//! Codex's research probes (`docs/research/configuration-replacement-results-2026-10-02.md`)
//! showed what the prototype got wrong. Each counterexample that blocked a
//! replacement is turned around here: the engine keeps CDATA, fails closed on
//! a bad document, sets aside a record its checks refuse, reads JSON and runs
//! a declared custom step.

use std::collections::{BTreeMap, BTreeSet};
use std::io::Write;
use std::path::PathBuf;

use source_contract::{Engine, Lookups, Raw, Reading, Rejected, Steps, Val};

const LEI_1: &str = "5493001KJTIIGC8Y1R12";
const LEI_2: &str = "529900T8BM49AURSDO55";

fn fixtures() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures")
}

fn engine() -> Engine {
    Engine::load(&fixtures().join("gleif-level1.yaml"), Steps::new()).unwrap()
}

fn fixture() -> String {
    std::fs::read_to_string(fixtures().join("gleif-two-records.xml")).unwrap()
}

fn scope(leis: &[&str]) -> Lookups {
    BTreeMap::from([(
        "eligible_leis".to_string(),
        leis.iter().map(|l| l.to_string()).collect::<BTreeSet<_>>(),
    )])
}

fn read(xml: &str) -> Result<Reading, Rejected> {
    engine().read(xml.as_bytes(), &scope(&[LEI_1, LEI_2]))
}

fn rejected(xml: &str) -> String {
    read(xml).unwrap_err().code
}

fn configured(yaml: &str, steps: Steps) -> Result<Engine, Rejected> {
    Engine::from_yaml(yaml, steps)
}

#[test]
fn projects_both_namespaced_gleif_rows_as_the_golden_file_says() {
    let reading = read(&fixture()).unwrap();
    let rows = &reading.tables["gleif_projection"];
    let golden: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(fixtures().join("rust_scalar_expected.json")).unwrap())
            .unwrap();
    let expected = golden.as_array().unwrap();
    assert_eq!(rows.len(), expected.len());
    for (actual, expected) in rows.iter().zip(expected) {
        for (key, value) in expected.as_object().unwrap() {
            let value = match value {
                serde_json::Value::Null => Val::Null,
                serde_json::Value::String(text) => Val::Str(text.clone()),
                serde_json::Value::Number(n) => Val::Int(n.as_i64().unwrap()),
                other => panic!("unexpected golden scalar: {other:?}"),
            };
            assert_eq!(actual[key], value, "{key}");
        }
    }
    assert_eq!(rows[0]["language"], Val::Str("en".into()));
    assert!(reading.deferred.is_empty());
}

#[test]
fn cdata_is_kept() {
    let xml = fixture().replace(
        "<lei:LegalName>Example Limited</lei:LegalName>",
        "<lei:LegalName><![CDATA[Café Limited]]></lei:LegalName>",
    );
    assert_eq!(read(&xml).unwrap().tables["gleif_projection"][1]["name"], Val::Str("Café Limited".into()));
}

#[test]
fn a_bad_document_fails_closed() {
    let xml = fixture();
    let header_start = xml.find("  <lei:LEIHeader>").unwrap();
    let header_end = xml.find("  </lei:LEIHeader>").unwrap() + "  </lei:LEIHeader>".len();
    let cases = [
        (xml.replace("lei:LEIData", "lei:OtherData"), "wrong_root"),
        ("<LEIData><LEIRecords></LEIData>".to_string(), "malformed"),
        (xml.replace("http://www.gleif.org/data/schema/leidata/2016", "urn:wrong"), "wrong_namespace"),
        (xml.replace("<?xml version=\"1.0\" encoding=\"UTF-8\"?>", "<!DOCTYPE LEIData []>"), "dtd"),
        (format!("{}{}", &xml[..header_start], &xml[header_end..]), "missing_required"),
        (xml.replace("<lei:RecordCount>2</lei:RecordCount>", "<lei:RecordCount>999</lei:RecordCount>"), "record_count"),
        (
            xml.replace(
                "<lei:RecordCount>2</lei:RecordCount>",
                "<lei:RecordCount>2</lei:RecordCount><lei:RecordCount>2</lei:RecordCount>",
            ),
            "repeated_path",
        ),
        (
            xml.replace(&format!("<lei:LEI>{LEI_1}</lei:LEI>"), &format!("<lei:LEI>{LEI_1}</lei:LEI><lei:LEI>{LEI_2}</lei:LEI>")),
            "repeated_path",
        ),
        ("<!DOCTYPE x [<!ENTITY e \"boom\">]><LEIData>&e;</LEIData>".to_string(), "dtd"),
    ];
    for (bad, code) in cases {
        assert_eq!(rejected(&bad), code, "{bad}");
    }
}

#[test]
fn records_the_checks_refuse_are_set_aside_with_the_readers_reasons() {
    let deletion = "</lei:Entity><lei:Extension><lei:Deletion>true</lei:Deletion></lei:Extension>";
    let cases = [
        (fixture().replacen(LEI_1, "NOT-AN-LEI", 1), "invalid_lei"),
        (fixture().replacen(LEI_1, "5493001KJTIIGC8Y1R13", 1), "invalid_lei_checksum"),
        (fixture().replacen("</lei:Entity>", deletion, 1), "gleif_deletion_flag"),
        (
            fixture().replacen(
                "<lei:EntityCategory>GENERAL</lei:EntityCategory>",
                "<lei:EntityCategory>UNKNOWN</lei:EntityCategory>",
                1,
            ),
            "invalid_identity_kind",
        ),
    ];
    for (xml, reason) in cases {
        let reading = read(&xml).unwrap();
        assert_eq!(reading.tables["gleif_projection"].len(), 1, "{reason}");
        let set_aside = &reading.deferred[0];
        assert_eq!((set_aside.table.as_str(), set_aside.ordinal, set_aside.reason.as_str()),
                   ("gleif_projection", 1, reason));
    }
    // The raw record is kept the way the Python readers shape it.
    let reading = engine().read(fixture().as_bytes(), &scope(&[LEI_2])).unwrap();
    let Raw::Map(raw) = &reading.deferred[0].raw else { panic!("raw record") };
    assert_eq!(reading.deferred[0].reason, "outside_approved_company_scope");
    assert_eq!(raw["LEI"], Raw::Map(BTreeMap::from([("$".to_string(), Raw::Text(LEI_1.into()))])));
}

#[test]
fn a_lookup_the_caller_does_not_supply_fails_closed() {
    assert_eq!(engine().read(fixture().as_bytes(), &Lookups::new()).unwrap_err().code, "missing_lookup");
}

#[test]
fn json_records_are_read_with_the_same_paths() {
    let e = configured(
        "read:\n  format: json\n  tables:\n    rows:\n      each: records\n      columns:\n        lei: { text: { path: LEI.$ } }\n        lang: { text: { path: Entity.LegalName.@lang } }\n        n: { number: { path: n } }\n",
        Steps::new(),
    )
    .unwrap();
    let reading = e
        .read(br#"{"records":[{"LEI":{"$":"A"},"Entity":{"LegalName":{"@lang":"en","$":"X"}},"n":2},{"LEI":{"$":"B"}}]}"#, &Lookups::new())
        .unwrap();
    let rows = &reading.tables["rows"];
    assert_eq!((rows[0]["lei"].clone(), rows[0]["lang"].clone(), rows[0]["n"].clone()),
               (Val::Str("A".into()), Val::Str("en".into()), Val::Float(2.0)));
    assert_eq!(rows[1]["lei"], Val::Str("B".into()));
    assert_eq!(e.read(b"{\"records\": [", &Lookups::new()).unwrap_err().code, "malformed");
}

#[test]
fn jsonl_and_csv_read_one_record_per_line() {
    let jsonl = configured(
        "read:\n  format: jsonl\n  tables:\n    rows:\n      each: record\n      columns:\n        a: { text: { path: a } }\n",
        Steps::new(),
    )
    .unwrap();
    let rows = jsonl.read(b"{\"a\":\"x\"}\n\n{\"a\":\"y\"}\n", &Lookups::new()).unwrap().tables["rows"].clone();
    assert_eq!(rows.iter().map(|r| r["a"].clone()).collect::<Vec<_>>(), [Val::Str("x".into()), Val::Str("y".into())]);
    let csv = configured(
        "read:\n  format: csv\n  tables:\n    rows:\n      each: record\n      columns:\n        a: { text: { path: a } }\n        b: { number: { path: b } }\n",
        Steps::new(),
    )
    .unwrap();
    let rows = csv.read(b"a,b\n\"x, y\",1\nz,\n", &Lookups::new()).unwrap().tables["rows"].clone();
    assert_eq!(rows[0]["a"], Val::Str("x, y".into()));
    assert_eq!((rows[1]["a"].clone(), rows[1]["b"].clone()), (Val::Str("z".into()), Val::Null));
    assert_eq!(csv.read(b"a,b\n1,2,3\n", &Lookups::new()).unwrap_err().code, "malformed");
}

fn zipped(members: &[(&str, &str)]) -> Vec<u8> {
    let mut out = std::io::Cursor::new(Vec::new());
    let mut zip = zip::ZipWriter::new(&mut out);
    for (name, body) in members {
        zip.start_file(*name, zip::write::SimpleFileOptions::default()).unwrap();
        zip.write_all(body.as_bytes()).unwrap();
    }
    zip.finish().unwrap();
    out.into_inner()
}

#[test]
fn a_zip_holds_exactly_one_member_within_its_bound() {
    let contract = |max: usize| {
        format!("read:\n  format: jsonl\n  container: zip\n  limits: {{ max_bytes: 100000, max_member_bytes: {max} }}\n  tables:\n    rows:\n      each: record\n      columns:\n        a: {{ text: {{ path: a }} }}\n")
    };
    let e = configured(&contract(1000), Steps::new()).unwrap();
    let one = zipped(&[("a.jsonl", "{\"a\":\"x\"}\n")]);
    assert_eq!(e.read(&one, &Lookups::new()).unwrap().tables["rows"][0]["a"], Val::Str("x".into()));
    let two = zipped(&[("a.jsonl", "{}"), ("b.jsonl", "{}")]);
    assert_eq!(e.read(&two, &Lookups::new()).unwrap_err().code, "zip_members");
    let small = configured(&contract(4), Steps::new()).unwrap();
    assert_eq!(small.read(&one, &Lookups::new()).unwrap_err().code, "limit_exceeded");
    assert_eq!(e.read(b"not a zip", &Lookups::new()).unwrap_err().code, "malformed");
}

#[test]
fn limits_on_bytes_and_records_fail_closed() {
    let e = configured(
        "read:\n  format: jsonl\n  limits: { max_bytes: 30, max_records: 2 }\n  tables:\n    rows:\n      each: record\n      columns:\n        a: { text: { path: a } }\n",
        Steps::new(),
    )
    .unwrap();
    assert_eq!(e.read(b"{}\n{}\n{}\n", &Lookups::new()).unwrap_err().code, "limit_exceeded");
    assert_eq!(e.read(&[b' '; 31], &Lookups::new()).unwrap_err().code, "limit_exceeded");
}

#[test]
fn dates_counts_and_order_are_checked_per_record() {
    let e = configured(
        r#"read:
  format: json
  tables:
    links:
      each: records
      columns:
        start: { date: { path: Period.Start.$ } }
        end: { date: { path: Period.End.$ } }
      checks:
        - { check: count, path: Period, equals: 1, on_fail: defer, reason: ambiguous_relationship_period }
        - { check: required, column: start, on_fail: defer, reason: invalid_relationship_interval }
        - { check: before, column: start, until: end, on_fail: defer, reason: invalid_relationship_interval }
"#,
        Steps::new(),
    )
    .unwrap();
    let reading = e
        .read(
            br#"{"records":[
              {"Period":{"Start":{"$":"2020-01-01T05:00:00+05:00"}}},
              {"Period":[{"Start":{"$":"2020-01-01T00:00:00Z"}},{"Start":{"$":"2021-01-01T00:00:00Z"}}]},
              {"Period":{"Start":{"$":"2021-01-01T00:00:00Z"},"End":{"$":"2020-01-01T00:00:00Z"}}}
            ]}"#,
            &Lookups::new(),
        )
        .unwrap();
    assert_eq!(reading.tables["links"][0]["start"], Val::Str("2020-01-01T00:00:00+00:00".into()));
    assert_eq!(reading.tables["links"][0]["end"], Val::Null);
    assert_eq!(
        reading.deferred.iter().map(|d| (d.ordinal, d.reason.as_str())).collect::<Vec<_>>(),
        [(2, "ambiguous_relationship_period"), (3, "invalid_relationship_interval")]
    );
    let bad = e.read(br#"{"records":[{"Period":{"Start":{"$":"2020-01-01"}}}]}"#, &Lookups::new());
    assert_eq!(bad.unwrap_err().code, "invalid_value");
}

#[test]
fn a_check_can_reject_the_whole_artifact() {
    let e = configured(
        "read:\n  format: jsonl\n  tables:\n    rows:\n      each: record\n      columns:\n        a: { text: { path: a } }\n      checks:\n        - { check: required, column: a, on_fail: reject, reason: missing_a }\n",
        Steps::new(),
    )
    .unwrap();
    let error = e.read(b"{\"a\":\"x\"}\n{}\n", &Lookups::new()).unwrap_err();
    assert_eq!((error.code.as_str(), error.detail.contains("missing_a")), ("check_failed", true));
}

#[test]
fn a_custom_step_runs_and_a_missing_one_fails_when_the_contract_loads() {
    let yaml = "read:\n  format: xml\n  root: LEIData\n  tables:\n    rows:\n      each: LEIRecords.LEIRecord\n      columns:\n        lei: { custom: { step: lower@1, inputs: { value: { text: { path: LEI.$ } } } } }\n";
    let error = configured(yaml, Steps::new()).err().unwrap();
    assert_eq!((error.code.as_str(), error.detail.as_str()), ("contract", "no value step lower@1"));
    let mut steps = Steps::new();
    steps.insert(
        "lower@1".into(),
        Box::new(|v: &Val| match v {
            Val::Str(text) => Ok(Val::Str(text.to_lowercase())),
            other => Ok(other.clone()),
        }),
    );
    let reading = configured(yaml, steps).unwrap().read(fixture().as_bytes(), &Lookups::new()).unwrap();
    assert_eq!(reading.tables["rows"][1]["lei"], Val::Str(LEI_2.to_lowercase()));
}

#[test]
fn an_unknown_primitive_or_check_fails_when_the_contract_loads() {
    // Grouping stays in code (Company preparation): it is no primitive.
    for yaml in [
        "read:\n  format: xml\n  tables:\n    g:\n      each: a\n      columns:\n        grouped: { group_by: { field: LEI.$ } }\n",
        "read:\n  format: xml\n  tables:\n    g:\n      each: a\n      columns: {}\n      checks:\n        - { check: matches, column: a, on_fail: defer, reason: x }\n",
        "read:\n  format: xml\n  tables:\n    g:\n      each: a\n      columns: {}\n      checks:\n        - { check: required, column: a, on_fail: shrug, reason: x }\n",
        "read:\n  format: parquet\n  tables: {}\n",
    ] {
        assert_eq!(configured(yaml, Steps::new()).err().unwrap().code, "contract", "{yaml}");
    }
}

#[test]
fn a_path_selects_from_a_list_and_a_check_can_apply_only_when_a_value_holds() {
    // GLEIF lists a relationship's periods by type; the gates read the one
    // RELATIONSHIP_PERIOD, and an INACTIVE link must state its end.
    let e = configured(
        r#"read:
  format: json
  tables:
    links:
      each: records
      columns:
        status: { text: { path: Status.$ } }
        start: { date: { path: "Periods.Period[PeriodType.$=RELATIONSHIP_PERIOD].Start.$" } }
        end: { date: { path: "Periods.Period[PeriodType.$=RELATIONSHIP_PERIOD].End.$" } }
      checks:
        - { check: count, path: "Periods.Period[PeriodType.$=RELATIONSHIP_PERIOD]", equals: 1, on_fail: defer, reason: ambiguous_relationship_period }
        - { check: required, column: end, when: { column: status, equals: INACTIVE }, on_fail: defer, reason: invalid_relationship_status_interval }
"#,
        Steps::new(),
    )
    .unwrap();
    let period = |kind: &str, start: &str| format!(r#"{{"PeriodType":{{"$":"{kind}"}},"Start":{{"$":"{start}"}}}}"#);
    let accounting = period("ACCOUNTING_PERIOD", "2019-01-01T00:00:00Z");
    let relationship = period("RELATIONSHIP_PERIOD", "2020-01-01T00:00:00Z");
    let records = format!(
        r#"{{"records":[
          {{"Status":{{"$":"ACTIVE"}},"Periods":{{"Period":[{accounting},{relationship}]}}}},
          {{"Status":{{"$":"ACTIVE"}},"Periods":{{"Period":[{relationship},{relationship}]}}}},
          {{"Status":{{"$":"INACTIVE"}},"Periods":{{"Period":{relationship}}}}},
          {{"Status":{{"$":"ACTIVE"}},"Periods":{{"Period":{accounting}}}}}
        ]}}"#
    );
    let reading = e.read(records.as_bytes(), &Lookups::new()).unwrap();
    assert_eq!(reading.tables["links"][0]["start"], Val::Str("2020-01-01T00:00:00+00:00".into()));
    assert_eq!(
        reading.deferred.iter().map(|d| (d.ordinal, d.reason.as_str())).collect::<Vec<_>>(),
        [(2, "ambiguous_relationship_period"), (3, "invalid_relationship_status_interval"),
         (4, "ambiguous_relationship_period")]
    );
}

// Review findings (three-axis review, 2026-10-02).

#[test]
fn numbers_compare_as_the_text_a_rules_file_writes() {
    let e = configured(
        r#"read:
  format: jsonl
  tables:
    rows:
      each: record
      columns:
        v: { number: { path: v } }
        n: { text: { path: n } }
      checks:
        - { check: in_set, column: v, values: [1, 2], on_fail: defer, reason: not_one_or_two }
        - { check: required, column: n, when: { column: v, equals: 1 }, on_fail: defer, reason: one_needs_n }
"#,
        Steps::new(),
    )
    .unwrap();
    let reading = e.read(b"{\"v\":1,\"n\":\"x\"}\n{\"v\":1}\n{\"v\":2}\n{\"v\":3}\n", &Lookups::new()).unwrap();
    assert_eq!(
        reading.deferred.iter().map(|d| (d.ordinal, d.reason.as_str())).collect::<Vec<_>>(),
        [(2, "one_needs_n"), (4, "not_one_or_two")]
    );
}

#[test]
fn a_broken_path_is_refused_when_the_contract_loads() {
    for path in ["b[@k].$", "x[k=v]y", "a..b", "a[=v]"] {
        let yaml = format!("read:\n  format: json\n  tables:\n    t:\n      each: r\n      columns:\n        c: {{ text: {{ path: \"{path}\" }} }}\n");
        assert_eq!(configured(&yaml, Steps::new()).err().unwrap().code, "contract", "{path}");
    }
}

#[test]
fn a_repeated_required_path_fails_closed() {
    let xml = fixture().replace(
        "<lei:ContentDate>2026-10-01T00:00:00Z</lei:ContentDate>",
        "<lei:ContentDate>2026-10-01T00:00:00Z</lei:ContentDate><lei:ContentDate>2026-10-01T00:00:00Z</lei:ContentDate>",
    );
    assert_eq!(rejected(&xml), "repeated_path");
}

#[test]
fn dates_read_as_python_writes_them() {
    let e = configured("read:\n  format: jsonl\n  tables:\n    t:\n      each: record\n      columns:\n        d: { date: { path: d } }\n", Steps::new()).unwrap();
    let rows = e.read(b"{\"d\":\"2024-01-02T03:04:05.5-05:00\"}\n{\"d\":\"2024-01-02T03:04:05Z\"}\n", &Lookups::new()).unwrap().tables["t"].clone();
    // datetime.fromisoformat(...).astimezone(UTC).isoformat()
    assert_eq!(rows[0]["d"], Val::Str("2024-01-02T08:04:05.500000+00:00".into()));
    assert_eq!(rows[1]["d"], Val::Str("2024-01-02T03:04:05+00:00".into()));
}

#[test]
fn a_zip_of_many_tables_reads_the_one_member_its_pattern_names() {
    let contract = "read:\n  format: csv\n  container: zip\n  member: \"Table_B_*.csv\"\n  limits: { max_bytes: 100000, max_member_bytes: 1000 }\n  tables:\n    rows:\n      each: record\n      columns:\n        a: { text: { path: a } }\n";
    let e = configured(contract, Steps::new()).unwrap();
    let many = zipped(&[("Table_A_2026.csv", "a\nx\n"), ("Table_B_2026.csv", "a\ny\n"), ("notes.txt", "")]);
    assert_eq!(e.read(&many, &Lookups::new()).unwrap().tables["rows"][0]["a"], Val::Str("y".into()));
    let none = zipped(&[("Table_A_2026.csv", "a\nx\n")]);
    assert_eq!(e.read(&none, &Lookups::new()).unwrap_err().code, "zip_members");
    let two = zipped(&[("Table_B_1.csv", "a\nx\n"), ("Table_B_2.csv", "a\ny\n")]);
    assert_eq!(e.read(&two, &Lookups::new()).unwrap_err().code, "zip_members");
    let without = contract.replace("  container: zip\n", "");
    assert!(configured(&without, Steps::new()).is_err()); // a member needs a ZIP container
}

#[test]
fn a_csv_declared_windows_1252_reads_its_letters_and_refuses_an_undefined_byte() {
    let contract = |encoding: &str| format!("read:\n  format: csv\n  encoding: {encoding}\n  tables:\n    rows:\n      each: record\n      columns:\n        name: {{ text: {{ path: name }} }}\n");
    let e = configured(&contract("windows-1252"), Steps::new()).unwrap();
    let rows = e.read(b"name\nSOCI\xC9T\xC9 G\xC9N\xC9RALE \x96 \x80\n", &Lookups::new()).unwrap();
    assert_eq!(rows.tables["rows"][0]["name"], Val::Str("SOCIÉTÉ GÉNÉRALE – €".into()));
    assert_eq!(e.read(b"name\nA\x81B\n", &Lookups::new()).unwrap_err().code, "encoding");
    let utf8 = configured(&contract("utf-8"), Steps::new()).unwrap();
    assert_eq!(utf8.read(b"name\nSOCI\xC9T\xC9\n", &Lookups::new()).unwrap_err().code, "malformed"); // never guessed
    assert!(configured(&contract("latin-9"), Steps::new()).is_err());
    let either = configured(&contract("[utf-8, windows-1252]"), Steps::new()).unwrap();
    assert_eq!(either.read(b"name\nSOCI\xC9T\xC9\n", &Lookups::new()).unwrap().tables["rows"][0]["name"], Val::Str("SOCIÉTÉ".into()));
    assert_eq!(either.read("name\nSOCIÉTÉ\n".as_bytes(), &Lookups::new()).unwrap().tables["rows"][0]["name"], Val::Str("SOCIÉTÉ".into()));
    assert!(configured(&contract("[windows-1252, utf-8]"), Steps::new()).is_err()); // UTF-8 is tried first or not at all
    assert!(configured(&contract("[utf-8, utf-8]"), Steps::new()).is_err());
    let json = "read:\n  format: jsonl\n  encoding: windows-1252\n  tables:\n    rows:\n      each: record\n      columns:\n        a: { text: { path: a } }\n";
    assert!(configured(json, Steps::new()).is_err()); // declared for CSV only
}

#[test]
fn a_chosen_member_keeps_its_bound_and_any_format_can_be_chosen() {
    let contract = |max: usize| format!("read:\n  format: jsonl\n  container: zip\n  member: \"b*.jsonl\"\n  limits: {{ max_bytes: 100000, max_member_bytes: {max} }}\n  tables:\n    rows:\n      each: record\n      columns:\n        a: {{ text: {{ path: a }} }}\n");
    let archive = zipped(&[("a.jsonl", "{\"a\":\"x\"}\n"), ("b.jsonl", "{\"a\":\"y\"}\n")]);
    let e = configured(&contract(1000), Steps::new()).unwrap();
    assert_eq!(e.read(&archive, &Lookups::new()).unwrap().tables["rows"][0]["a"], Val::Str("y".into()));
    let small = configured(&contract(4), Steps::new()).unwrap();
    assert_eq!(small.read(&archive, &Lookups::new()).unwrap_err().code, "limit_exceeded");
}

#[test]
fn every_byte_windows_1252_leaves_undefined_refuses_and_a_bad_declaration_never_loads() {
    let contract = |encoding: &str| format!("read:\n  format: csv\n  encoding: {encoding}\n  tables:\n    rows:\n      each: record\n      columns:\n        name: {{ text: {{ path: name }} }}\n");
    for list in ["windows-1252", "[utf-8, windows-1252]"] {
        let e = configured(&contract(list), Steps::new()).unwrap();
        for byte in [0x81u8, 0x8D, 0x8F, 0x90, 0x9D] {
            let body = [b"name\nA".as_slice(), &[byte], b"\n"].concat();
            assert_eq!(e.read(&body, &Lookups::new()).unwrap_err().code, "encoding", "{list} 0x{byte:02X}");
        }
    }
    for bad in ["[]", "[utf-8, 5]", "{ a: 1 }", "[utf-8, windows-1252, utf-8]"] {
        assert!(configured(&contract(bad), Steps::new()).is_err(), "{bad}");
    }
}
