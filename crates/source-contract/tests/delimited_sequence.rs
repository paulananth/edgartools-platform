//! A large CSV or TSV is read as a stream, one record at a time, and gives the
//! same rows as reading the file whole (ticket 89).
use source_contract::delimited_sequence::{scan, Format, Limits};
use source_contract::{Engine, Lookups, Row, Steps, Val};

const COLUMNS: &str = "      columns:\n        a: { text: { path: a } }\n        b: { number: { path: b } }\n";

fn whole(format: &str) -> Engine {
    Engine::from_yaml(&format!("read:\n  format: {format}\n  tables:\n    rows:\n      each: record\n{COLUMNS}"), Steps::new()).unwrap()
}

fn projection() -> Engine {
    Engine::from_yaml(&format!("read:\n  format: json\n  tables:\n    rows:\n      each: .\n{COLUMNS}"), Steps::new()).unwrap()
}

fn limits() -> Limits {
    Limits { max_bytes: 1 << 20, max_record: 1024, max_records: 1000 }
}

fn streamed(bytes: &[u8], format: Format, encoding: &str, limits: Limits) -> Result<(Vec<Row>, usize), source_contract::Rejected> {
    let engine = projection();
    let mut rows = Vec::new();
    let stats = scan(bytes, format, encoding, limits, |record, _| {
        rows.extend(engine.read_json_value(record, &Lookups::new(), &Row::new())?.tables["rows"].clone());
        Ok(())
    })?;
    Ok((rows, stats.records))
}

#[test]
fn streamed_rows_equal_the_rows_read_whole_for_csv_and_tsv() {
    let csv = b"a,b\n\"x, y\",1\nz,\n\"say \"\"q\"\"\",3\n";
    let tsv = b"a\tb\nx, y\t1\nz\t\nsay \"q\t3\n";
    for (bytes, format, name) in [(&csv[..], Format::Csv, "csv"), (&tsv[..], Format::Tsv, "tsv")] {
        let read = whole(name).read(bytes, &Lookups::new()).unwrap().tables["rows"].clone();
        let (rows, count) = streamed(bytes, format, "utf-8", limits()).unwrap();
        assert_eq!(rows, read, "{name}");
        assert_eq!(count, 3);
    }
    let (rows, _) = streamed(tsv, Format::Tsv, "utf-8", limits()).unwrap();
    assert_eq!(rows[2]["a"], Val::Str("say \"q".into())); // TSV does not unquote
}

#[test]
fn a_ragged_row_bytes_records_and_encoding_are_refused_as_reading_whole_refuses_them() {
    assert_eq!(streamed(b"a\tb\n1\t2\t3\n", Format::Tsv, "utf-8", limits()).unwrap_err().code, "malformed");
    let few = Limits { max_records: 1, ..limits() };
    assert_eq!(streamed(b"a\tb\n1\t2\n3\t4\n", Format::Tsv, "utf-8", few).unwrap_err().code, "limit_exceeded");
    let small = Limits { max_bytes: 8, ..limits() };
    assert_eq!(streamed(b"a\tb\n1\t2\n3\t4\n", Format::Tsv, "utf-8", small).unwrap_err().code, "limit_exceeded");
    let short = Limits { max_record: 3, ..limits() };
    assert_eq!(streamed(b"a\tb\n12\t34\n", Format::Tsv, "utf-8", short).unwrap_err().code, "limit_exceeded");
    // Bytes as written: the quotes count, and so does a long header.
    let exact = Limits { max_record: 8, ..limits() };
    assert_eq!(streamed(b"a,b\n\"1\",\"2\"\n", Format::Csv, "utf-8", exact).unwrap().1, 1);
    assert_eq!(streamed(b"a,b\n\"\"\"1\",\"2\"\n", Format::Csv, "utf-8", exact).unwrap_err().code, "limit_exceeded");
    assert_eq!(streamed(b"abcdefgh,b\n1,2\n", Format::Csv, "utf-8", exact).unwrap_err().code, "limit_exceeded");
    assert_eq!(streamed(b"a\ta\n1\t2\n", Format::Tsv, "utf-8", limits()).unwrap_err().code, "malformed");
    assert_eq!(streamed(b"a\tb\nA\x81B\t1\n", Format::Tsv, "windows-1252", limits()).unwrap_err().code, "encoding");
    let (rows, _) = streamed(b"a\tb\nSOCI\xC9T\xC9\t1\n", Format::Tsv, "windows-1252", limits()).unwrap();
    assert_eq!(rows[0]["a"], Val::Str("SOCI\u{c9}T\u{c9}".into()));
    assert_eq!(streamed(b"a\tb\nSOCI\xC9T\xC9\t1\n", Format::Tsv, "utf-8", limits()).unwrap_err().code, "malformed");
    assert_eq!(streamed(b"a\n1\n", Format::Tsv, "latin-9", limits()).unwrap_err().code, "contract");
    assert!(Format::named("psv").is_err());
}

#[test]
fn a_file_with_only_its_header_has_no_records() {
    let (rows, count) = streamed(b"a\tb\n", Format::Tsv, "utf-8", limits()).unwrap();
    assert!(rows.is_empty() && count == 0);
}
