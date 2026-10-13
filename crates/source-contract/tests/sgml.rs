//! An SGML submission file as a container (profiling ticket 07): the reading
//! takes the one document whose text holds `<XML>`, as `container: zip` takes
//! one member, and a context field may be filled from an SGML header line.
//! Every name and number below is invented.

use source_contract::{Engine, Lookups, Row, Steps, Val};

const CONTRACT: &str = "read:
  format: xml
  container: sgml
  root: sampleDocument
  context:
    accession: {type: text, sgml_header: ACCESSION NUMBER}
    folder: {type: text}
  limits: {max_bytes: 100000, max_member_bytes: 2000}
  tables:
    filing:
      each: .
      columns:
        accession: {context: {name: accession}}
        folder: {context: {name: folder}}
        period: {text: {path: periodOfReport.$}}
        code: {text: {path: item.code.$}}
";

fn document(name: &str, kind: &str, text: &str) -> String {
    format!("<DOCUMENT>\n<TYPE>{kind}\n<SEQUENCE>1\n<FILENAME>{name}\n<DESCRIPTION>SAMPLE\n<TEXT>\n{text}\n</TEXT>\n</DOCUMENT>\n")
}

fn xml(code: &str) -> String {
    format!("<XML>\n<?xml version=\"1.0\"?>\n<sampleDocument>\n<periodOfReport>2026-01-02</periodOfReport>\n<item><code>{code}</code></item>\n</sampleDocument>\n</XML>")
}

fn submission(header: &str, documents: &[String]) -> Vec<u8> {
    format!("<SEC-DOCUMENT>0000000000-26-000001.txt : 20260102\n<SEC-HEADER>0000000000-26-000001.hdr.sgml : 20260102\n<ACCEPTANCE-DATETIME>20260102120000\n{header}</SEC-HEADER>\n{}</SEC-DOCUMENT>\n", documents.concat()).into_bytes()
}

const HEADER: &str = "ACCESSION NUMBER:\t\t0000000000-26-000001\nCONFORMED SUBMISSION TYPE:\t4\n\nREPORTING-OWNER:\n\n\tOWNER DATA:\n\t\tCOMPANY CONFORMED NAME:\t\t\tSAMPLE OWNER\n";

fn caller() -> Row {
    [("folder".to_string(), Val::Str("f1".into()))].into_iter().collect()
}

fn engine(contract: &str) -> Result<Engine, String> {
    Engine::from_yaml(contract, Steps::new()).map_err(|e| e.to_string())
}

#[test]
fn the_one_xml_document_is_read_and_the_header_fills_its_context() {
    let file = submission(HEADER, &[document("sample.xml", "4", &xml("P")), document("ex24.txt", "EX-24", "POWER OF ATTORNEY")]);
    let rows = engine(CONTRACT).unwrap().read_with_context(&file, &Lookups::new(), &caller()).unwrap().tables.remove("filing").unwrap();
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0]["accession"], Val::Str("0000000000-26-000001".into()));
    assert_eq!(rows[0]["folder"], Val::Str("f1".into()));
    assert_eq!(rows[0]["period"], Val::Str("2026-01-02".into()));
    assert_eq!(rows[0]["code"], Val::Str("P".into()));
}

#[test]
fn none_or_several_xml_documents_are_refused_and_a_member_pattern_chooses() {
    let e = engine(CONTRACT).unwrap();
    let none = submission(HEADER, &[document("ex24.txt", "EX-24", "TEXT ONLY")]);
    assert_eq!(e.read_with_context(&none, &Lookups::new(), &caller()).unwrap_err().code, "sgml_documents");
    let two = submission(HEADER, &[document("a.xml", "4", &xml("P")), document("b.xml", "4", &xml("S"))]);
    assert_eq!(e.read_with_context(&two, &Lookups::new(), &caller()).unwrap_err().code, "sgml_documents");
    let chosen = engine(&CONTRACT.replace("  container: sgml\n", "  container: sgml\n  member: \"b*.xml\"\n")).unwrap();
    let rows = chosen.read_with_context(&two, &Lookups::new(), &caller()).unwrap().tables.remove("filing").unwrap();
    assert_eq!(rows[0]["code"], Val::Str("S".into()));
}

#[test]
fn a_header_line_missing_or_repeated_is_refused() {
    let e = engine(CONTRACT).unwrap();
    let doc = [document("sample.xml", "4", &xml("P"))];
    let missing = submission("CONFORMED SUBMISSION TYPE:\t4\n", &doc);
    assert_eq!(e.read_with_context(&missing, &Lookups::new(), &caller()).unwrap_err().code, "sgml_header");
    let repeated = submission(&format!("{HEADER}ACCESSION NUMBER:\t0000000000-26-000002\n"), &doc);
    assert_eq!(e.read_with_context(&repeated, &Lookups::new(), &caller()).unwrap_err().code, "sgml_header");
}

#[test]
fn the_caller_never_supplies_a_header_field() {
    let e = engine(CONTRACT).unwrap();
    let file = submission(HEADER, &[document("sample.xml", "4", &xml("P"))]);
    let mut values = caller();
    values.insert("accession".into(), Val::Str("0000000000-26-000009".into()));
    assert_eq!(e.read_with_context(&file, &Lookups::new(), &values).unwrap_err().code, "invalid_context");
    assert!(e.validate_context(&caller()).is_ok());
}

#[test]
fn a_file_that_is_not_a_submission_or_a_document_over_its_limit_is_refused() {
    let e = engine(CONTRACT).unwrap();
    assert_eq!(e.read_with_context(b"<sampleDocument/>", &Lookups::new(), &caller()).unwrap_err().code, "malformed");
    let big = submission(HEADER, &[document("sample.xml", "4", &xml(&"P".repeat(3000)))]);
    assert_eq!(e.read_with_context(&big, &Lookups::new(), &caller()).unwrap_err().code, "limit_exceeded");
    let wrong_root = submission(HEADER, &[document("sample.xml", "4", "<XML>\n<otherDocument/>\n</XML>")]);
    assert_eq!(e.read_with_context(&wrong_root, &Lookups::new(), &caller()).unwrap_err().code, "wrong_root");
}

#[test]
fn the_contract_ties_each_setting_to_its_container() {
    assert!(engine(&CONTRACT.replace("  format: xml\n", "  format: json\n")).is_err()); // an SGML document is XML
    let no_container = CONTRACT.replace("  container: sgml\n", "");
    assert!(engine(&no_container).is_err()); // a header field needs the SGML container
    let plain = no_container.replace("    accession: {type: text, sgml_header: ACCESSION NUMBER}\n", "    accession: {type: text}\n");
    assert!(engine(&plain).is_ok()); // the same columns, the accession supplied by the caller
    assert!(engine(&CONTRACT.replace("type: text, sgml_header", "type: integer, sgml_header")).is_err());
    assert!(engine(&plain.replace("  root: sampleDocument\n", "  root: sampleDocument\n  member: \"*.xml\"\n")).is_err());
}
