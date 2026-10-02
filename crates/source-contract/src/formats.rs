//! Readers for JSON, JSON Lines, CSV and a ZIP container. Each builds the
//! shared tree; JSON Lines and CSV put each line under `record`.

use std::io::{Cursor, Read};

use crate::tree::{Child, El};
use crate::Rejected;

fn malformed(detail: impl ToString) -> Rejected {
    Rejected::new("malformed", detail)
}

fn from_json(value: serde_json::Value) -> El {
    use serde_json::Value;
    match value {
        Value::Null => El::scalar(None),
        Value::Bool(b) => El::scalar(Some(b.to_string())),
        Value::Number(n) => El::scalar(Some(n.to_string())),
        Value::String(s) => El::scalar(Some(s)),
        Value::Array(items) => {
            let mut el = El::default();
            el.children.insert("item".into(), Child::Many(items.into_iter().map(from_json).collect()));
            el
        }
        Value::Object(map) => {
            let mut el = El::default();
            for (key, value) in map {
                match value {
                    // `$` is the text and `@x` an attribute, as GLEIF's JSON
                    // writes them and the Python readers read them.
                    Value::String(text) if key == "$" => el.text = Some(text),
                    Value::String(text) if key.starts_with('@') => {
                        el.attrs.insert(key, text);
                    }
                    Value::Array(items) => {
                        el.children.insert(key, Child::Many(items.into_iter().map(from_json).collect()));
                    }
                    other => el.add_child(key, from_json(other)),
                }
            }
            el
        }
    }
}

pub fn json(bytes: &[u8]) -> Result<El, Rejected> {
    serde_json::from_slice(bytes).map(from_json).map_err(malformed)
}

fn records(rows: Vec<El>) -> El {
    let mut el = El::default();
    el.children.insert("record".into(), Child::Many(rows));
    el
}

pub fn jsonl(bytes: &[u8], max_records: usize) -> Result<El, Rejected> {
    let mut rows = Vec::new();
    for line in bytes.split(|b| *b == b'\n') {
        if line.iter().all(u8::is_ascii_whitespace) {
            continue;
        }
        if rows.len() == max_records {
            return Err(Rejected::new("limit_exceeded", format!("more than {max_records} records")));
        }
        rows.push(json(line)?);
    }
    Ok(records(rows))
}

pub fn csv(bytes: &[u8], max_records: usize) -> Result<El, Rejected> {
    let mut reader = ::csv::ReaderBuilder::new().has_headers(true).from_reader(bytes);
    let headers = reader.headers().map_err(malformed)?.clone();
    let mut rows = Vec::new();
    for row in reader.records() {
        let row = row.map_err(malformed)?;
        if rows.len() == max_records {
            return Err(Rejected::new("limit_exceeded", format!("more than {max_records} records")));
        }
        let mut el = El::default();
        for (name, cell) in headers.iter().zip(row.iter()) {
            el.add_child(name.to_string(), El::scalar(Some(cell.to_string())));
        }
        rows.push(el);
    }
    Ok(records(rows))
}

/// The one member of a ZIP archive, read no further than `max_member_bytes`.
pub fn zip_member(bytes: &[u8], max_member_bytes: u64) -> Result<Vec<u8>, Rejected> {
    let mut archive = zip::ZipArchive::new(Cursor::new(bytes)).map_err(malformed)?;
    if archive.len() != 1 {
        return Err(Rejected::new("zip_members", format!("{} members, not one", archive.len())));
    }
    let member = archive.by_index(0).map_err(malformed)?;
    if member.encrypted() {
        return Err(Rejected::new("zip_members", "the member is encrypted"));
    }
    let mut out = Vec::new();
    member.take(max_member_bytes + 1).read_to_end(&mut out).map_err(malformed)?;
    if out.len() as u64 > max_member_bytes {
        return Err(Rejected::new("limit_exceeded", format!("the member is over {max_member_bytes} bytes")));
    }
    Ok(out)
}
