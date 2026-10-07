use serde_json::{json, Value};
use source_contract::{xml_sequence::{scan, Envelope, Limits}, Rejected};
use std::{cell::Cell, io::{self, Read}};

fn envelope() -> Envelope {
    Envelope { namespace: "urn:feed".into(), root: "Data".into(), header: "Header".into(),
        container: "Records".into(), record: "Record".into(), record_wrapper: None }
}
fn limits() -> Limits { Limits { max_bytes: 100000, max_record: 10000, max_header: 10000, max_records: 100, max_depth: 64 } }
fn document(records: &str) -> String {
    format!("<Data xmlns='urn:feed'><Header><Count>2</Count></Header><Records>{records}</Records></Data>")
}
fn read(xml: &str) -> Result<Vec<Value>, Rejected> {
    let mut rows = Vec::new();
    scan(xml.as_bytes(), &envelope(), limits(), |_| Ok(()), |row, index| {
        assert_eq!(index, rows.len()); rows.push(row); Ok(())
    })?;
    Ok(rows)
}

#[test]
fn namespaced_records_preserve_expanded_attributes_foreign_children_repetition_and_leading_text() {
    let xml = document("<Record xmlns:f='urn:foreign' f:id='A' id='B'> lead<!--comment-->text <Name>One</Name>tail<Name>Two</Name><f:Name>Other</f:Name><Plain xmlns=''>Bare</Plain></Record>");
    assert_eq!(read(&xml).unwrap(), vec![json!({"@{urn:foreign}id":"A", "@id":"B", "$":"leadtext",
        "Name":[{"$":"One"},{"$":"Two"}], "{urn:foreign}Name":{"$":"Other"}, "Plain":{"$":"Bare"}})]);
}

#[test]
fn header_is_checked_before_records_and_receipt_requires_complete_eof() {
    let xml = document("<Record/><Record><Value>é🦀</Value></Record>");
    let mut checked = false;
    let mut rows = Vec::new();
    let stats = scan(xml.as_bytes(), &envelope(), limits(), |value| {
        assert_eq!(value, json!({"Count":{"$":"2"}})); checked = true; Ok(())
    }, |row, _| { rows.push(row); Ok(()) }).unwrap();
    assert!(checked);
    assert_eq!(stats.records, 2); assert_eq!(stats.bytes, xml.len());
    assert_eq!(rows, vec![json!({}),json!({"Value":{"$":"é🦀"}})]);
    assert!(read(&(xml + "trailing")).is_err());
}

#[test]
fn prefix_changes_and_empty_containers_are_valid_and_wrapping_is_configured() {
    let xml = "<f:Data xmlns:f='urn:feed'><f:Header/><g:Records xmlns:g='urn:feed'/></f:Data>";
    assert_eq!(read(xml).unwrap(), Vec::<Value>::new());
    let mut config = envelope(); config.record_wrapper = Some("RecordEnvelope".into());
    let mut row = Value::Null;
    scan(document("<Record/>").as_bytes(), &config, limits(), |_| Ok(()), |value, _| { row = value; Ok(()) }).unwrap();
    assert_eq!(row, json!({"RecordEnvelope":{}}));
}

#[test]
fn xml_text_and_attribute_normalization_preserves_character_references() {
    let xml = document("<Record attr='a\r\nb\tc&#10;d'><Value> a\r\nb&amp;<![CDATA[c\rd]]>&#13;e </Value></Record>");
    assert_eq!(read(&xml).unwrap(), vec![json!({"@attr":"a b c\nd", "Value":{"$":"a\nb&c\nd\re"}})]);
}

#[test]
fn malformed_envelopes_and_unsafe_xml_fail_closed() {
    for xml in [
        "<Data xmlns='wrong'><Header/><Records/></Data>",
        "<Data xmlns='urn:feed'><Records/><Header/></Data>",
        "<Data xmlns='urn:feed'><Header/><Header/><Records/></Data>",
        "<Data xmlns='urn:feed'><Header/><Records/><Records/></Data>",
        "<Data xmlns='urn:feed'><Header/><Records><Other/></Records></Data>",
        "<Data xmlns='urn:feed'><Header/><Records><Record xmlns='wrong'/></Records></Data>",
        "<Data xmlns='urn:feed'><Header/><Records>",
        "<Data xmlns='urn:feed'><Header/><Records/></Data><Data/>",
        "<!DOCTYPE Data [<!ENTITY x 'bad'>]><Data xmlns='urn:feed'><Header/><Records/></Data>",
        "<?xml version='1.0' encoding='ISO-8859-1'?><Data xmlns='urn:feed'><Header/><Records/></Data>",
        "<Data xmlns='urn:feed'><Header/><Records><p:Record/></Records></Data>",
        "<Data xmlns='urn:feed'><Header/><Records><Record>&unknown;</Record></Records></Data>",
        "<Data xmlns='urn:feed'><Header/><Records><Record>&#0;</Record></Records></Data>",
        "<Data xmlns='urn:feed'><Header/><Records><Record a='1' a='2'/></Records></Data>",
        "<Data xmlns='urn:feed'><Header/><Records><Record xmlns:a='urn:x' xmlns:b='urn:x' a:k='1' b:k='2'/></Records></Data>",
        "<Data xmlns='urn:feed'><Header/><Records><Record></Wrong></Records></Data>",
        "<Data xmlns='urn:feed'><Header/><Records>text</Records></Data>",
        "<Data xmlns='urn:feed'><Header/><Records><Record a='<'/></Records></Data>",
        "<Data xmlns='urn:feed'><Header/><Records><Record>]]></Record></Records></Data>",
        "<Data xmlns='urn:feed'><Header/><Records><Record><1Bad/></Record></Records></Data>",
        "<Data xmlns='urn:feed'><Header/><Records><Record :bad='1'/></Records></Data>",
        "<?XML bad?><Data xmlns='urn:feed'><Header/><Records/></Data>",
        "<?a:b bad?><Data xmlns='urn:feed'><Header/><Records/></Data>",
        " <!--comment--><?xml version='1.0'?><Data xmlns='urn:feed'><Header/><Records/></Data>",
        "\u{a0}<Data xmlns='urn:feed'><Header/><Records/></Data>",
        "&#32;<Data xmlns='urn:feed'><Header/><Records/></Data>",
        "<?xml version='1.0' standalone='wat'?><Data xmlns='urn:feed'><Header/><Records/></Data>",
        "<?xml version='1.0' unexpected='yes'?><Data xmlns='urn:feed'><Header/><Records/></Data>",
        "<?xml version='1.0' standalone='yes' encoding='utf-8'?><Data xmlns='urn:feed'><Header/><Records/></Data>",
        "<Data xmlns='urn:feed'><Header/><Records><Record><?instruction x?></Record></Records></Data>",
        "<Data xmlns='urn:feed'><Header/><Records><Record><!--\u{1}--></Record></Records></Data>",
        "<Data xmlns='urn:feed' xmlns:bad='http://www.w3.org/XML/1998/namespace'><Header/><Records/></Data>",
        "<Data xmlns='urn:feed' xmlns:f='urn:bad&#10;uri'><Header/><Records/></Data>",
    ] { assert!(read(xml).is_err(), "accepted {xml}"); }
}

#[test]
fn namespace_uri_entities_are_normalized_before_comparison_and_expanded_names() {
    let xml = "<Data xmlns='urn:fe&#101;d'><Header/><Records><Record xmlns:f='urn:foreign&amp;more' f:id='A'><f:Name>Other</f:Name></Record></Records></Data>";
    assert_eq!(read(xml).unwrap(), vec![json!({"@{urn:foreign&more}id":"A", "{urn:foreign&more}Name":{"$":"Other"}})]);
    let xml = "<Data xmlns='urn:feed' xmlns:xml='http://www.w3.org/XML/1998/namespac&#101;'><Header/><Records><Record xml:lang='en'/></Records></Data>";
    assert_eq!(read(xml).unwrap(), vec![json!({"@{http://www.w3.org/XML/1998/namespace}lang":"en"})]);
    let xml = "<Data xmlns='urn:feed'><Header/><Records><Record xmlns:f='urn:old'><f:Name xmlns:f='urn:new'>New</f:Name><f:Name>Old</f:Name></Record></Records></Data>";
    assert_eq!(read(xml).unwrap(), vec![json!({"{urn:new}Name":{"$":"New"},"{urn:old}Name":{"$":"Old"}})]);
}

#[test]
fn header_and_record_callback_refusals_are_preserved() {
    let xml = document("<Record/>");
    let failure = Rejected::new("pinned_metadata", "count mismatch");
    let mut called = false;
    let result = scan(xml.as_bytes(), &envelope(), limits(), |_| Err(failure.clone()), |_, _| { called = true; Ok(()) });
    assert_eq!(result.unwrap_err(), failure); assert!(!called);
    let failure = Rejected::new("candidate", "refused");
    assert_eq!(scan(xml.as_bytes(), &envelope(), limits(), |_| Ok(()), |_, _| Err(failure.clone())).unwrap_err(), failure);
}

#[test]
fn byte_record_count_encoded_size_and_depth_limits_are_independent() {
    let xml = document("<Record><V>value</V></Record>");
    for bound in [Limits { max_bytes: xml.len()-1, ..limits() }, Limits { max_record: 1, ..limits() },
        Limits { max_records: 0, ..limits() }, Limits { max_depth: 3, ..limits() }] {
        assert!(scan(xml.as_bytes(), &envelope(), bound, |_| Ok(()), |_, _| Ok(())).is_err());
    }
    let huge = document(&format!("<Record><V>{}</V></Record>", "x".repeat(100000)));
    assert!(scan(huge.as_bytes(), &envelope(), limits(), |_| Ok(()), |_, _| Ok(())).is_err());
}

#[test]
fn namespace_expansion_refuses_before_accumulating_the_remaining_record() {
    struct Counted<'a> { source: &'a [u8], read: &'a Cell<usize> }
    impl Read for Counted<'_> {
        fn read(&mut self, buffer: &mut [u8]) -> io::Result<usize> {
            let size = buffer.len().min(64).min(self.source.len());
            buffer[..size].copy_from_slice(&self.source[..size]);
            self.source = &self.source[size..];
            self.read.set(self.read.get() + size);
            Ok(size)
        }
    }
    for attributes in [false, true] {
        let uri = format!("urn:{}", "x".repeat(2000));
        let children: String = (0..1000).map(|n| format!("<f:N{n}/>")).collect();
        let payload = if attributes { format!("<Record f:a='value'>{children}</Record>") }
            else { format!("<Record>{children}</Record>") };
        let xml = document(&payload).replace("xmlns='urn:feed'", &format!("xmlns='urn:feed' xmlns:f='{uri}'"));
        let read = Cell::new(0);
        let source = Counted { source: xml.as_bytes(), read: &read };
        assert!(scan(source, &envelope(), Limits { max_record: 1024, ..limits() }, |_| Ok(()), |_, _| Ok(())).is_err());
        assert!(read.get() < 3000, "read {} of {} bytes before refusing expanded namespace keys", read.get(), xml.len());
    }
}

#[test]
fn independent_header_budget_preserves_record_budget() {
    let xml = document("<Record/>");
    let small = Limits { max_record: 2, max_header: 100, ..limits() };
    let mut count = 0;
    scan(xml.as_bytes(), &envelope(), small, |_| Ok(()), |row, _| {
        assert_eq!(row, json!({})); count += 1; Ok(())
    }).unwrap();
    assert_eq!(count, 1);
    assert!(scan(document("<Record><Value>large</Value></Record>").as_bytes(),
        &envelope(), small, |_| Ok(()), |_, _| Ok(())).is_err());
    for max_header in [0, 2] {
        let mut seen = false;
        assert!(scan(xml.as_bytes(), &envelope(), Limits { max_header, ..small },
            |_| Ok(()), |_, _| { seen = true; Ok(()) }).is_err());
        assert!(!seen);
    }
}
