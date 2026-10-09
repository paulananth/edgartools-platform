//! Readers for JSON, JSON Lines, CSV and a ZIP container. Each builds the
//! shared tree; JSON Lines and CSV put each line under `record`.

use std::io::{Cursor, Read};

use crate::tree::{Child, El, ScalarKind};
use crate::Rejected;

fn malformed(detail: impl ToString) -> Rejected {
    Rejected::new("malformed", detail)
}

fn from_json(value: serde_json::Value) -> El {
    json_value(value, false, false)
}

/// A framed, already validated JSON record: preserve the same tree policies
/// as parsing its typed Python JSON representation, without another parse.
pub(crate) fn json_value(value: serde_json::Value, exact_numbers: bool, python_text: bool) -> El {
    use serde_json::Value;
    match value {
        Value::Null => El::scalar(None),
        Value::Bool(b) => El { kind: ScalarKind::Boolean, ..El::scalar(Some(b.to_string())) },
        Value::Number(n) => El { kind: ScalarKind::Number,
            exact_number: (exact_numbers || python_text).then(|| n.to_string()),
            ..El::scalar(Some(n.to_string())) },
        Value::String(s) => El::scalar(Some(s)),
        Value::Array(items) => {
            let mut el = El { array: true, ..El::default() };
            el.children.insert("item".into(), Child::Many(items.into_iter().map(|v| json_value(v, exact_numbers, python_text)).collect()));
            el
        }
        Value::Object(map) => {
            let mut el = El::default();
            if python_text { el.json_keys = Some(map.keys().cloned().collect()); }
            for (key, value) in map {
                match value {
                    // `$` is the text and `@x` an attribute, as GLEIF's JSON
                    // writes them and the Python readers read them.
                    Value::String(text) if key == "$" => el.text = Some(text),
                    Value::String(text) if key.starts_with('@') => {
                        el.attrs.insert(key, text);
                    }
                    Value::Array(items) => {
                        el.children.insert(key, Child::Many(items.into_iter().map(|v| json_value(v, exact_numbers, python_text)).collect()));
                    }
                    other => el.add_child(key, json_value(other, exact_numbers, python_text)),
                }
            }
            el
        }
    }
}

/// Borrow raw numeric lexemes through serde, without a source-specific parser.
/// The ordinary Value parse first preserves its nesting/range checks. Raw
/// child values borrow the bounded input; no nested subtree bytes are copied.
fn from_raw(raw: &serde_json::value::RawValue, python_text: bool) -> Result<El, Rejected> {
    let text = raw.get();
    match text.as_bytes()[0] {
        b'{' => {
            let map: indexmap::IndexMap<String, &serde_json::value::RawValue> =
                serde_json::from_str(text).map_err(malformed)?;
            let mut el = El::default();
            if python_text { el.json_keys = Some(map.keys().cloned().collect()); }
            for (key, raw) in map {
                if (key == "$" || key.starts_with('@')) && raw.get().starts_with('"') {
                    let value = serde_json::from_str(raw.get()).map_err(malformed)?;
                    if key == "$" { el.text = Some(value) } else { el.attrs.insert(key, value); }
                } else if raw.get().starts_with('[') {
                    let items: Vec<&serde_json::value::RawValue> = serde_json::from_str(raw.get()).map_err(malformed)?;
                    let rows = items.into_iter().map(|raw| from_raw(raw, python_text)).collect::<Result<Vec<_>, _>>()?;
                    el.children.insert(key, Child::Many(rows));
                } else { el.add_child(key, from_raw(raw, python_text)?); }
            }
            Ok(el)
        }
        b'[' => {
            let items: Vec<&serde_json::value::RawValue> = serde_json::from_str(text).map_err(malformed)?;
            let mut el = El { array: true, ..El::default() };
            el.children.insert("item".into(), Child::Many(items.into_iter().map(|raw| from_raw(raw, python_text)).collect::<Result<Vec<_>, _>>()?));
            Ok(el)
        }
        _ => {
            let mut el = from_json(serde_json::from_str(text).map_err(malformed)?);
            if el.kind == ScalarKind::Number { el.exact_number = Some(text.to_string()); }
            Ok(el)
        }
    }
}

pub fn json(bytes: &[u8], exact_numbers: bool, python_text: bool) -> Result<El, Rejected> {
    if exact_numbers || python_text {
        // Validate with the existing parser before recursively borrowing raw
        // values: finite-number and nesting constraints remain unchanged.
        serde_json::from_slice::<serde_json::Value>(bytes).map_err(malformed)?;
        let raw: &serde_json::value::RawValue = serde_json::from_slice(bytes).map_err(malformed)?;
        from_raw(raw, python_text)
    } else {
        serde_json::from_slice(bytes).map(from_json).map_err(malformed)
    }
}

fn records(rows: Vec<El>) -> El {
    let mut el = El::default();
    el.children.insert("record".into(), Child::Many(rows));
    el
}

pub fn jsonl(bytes: &[u8], max_records: usize, exact_numbers: bool, python_text: bool) -> Result<El, Rejected> {
    let mut rows = Vec::new();
    for line in bytes.split(|b| *b == b'\n') {
        if line.iter().all(u8::is_ascii_whitespace) {
            continue;
        }
        if rows.len() == max_records {
            return Err(Rejected::new("limit_exceeded", format!("more than {max_records} records")));
        }
        rows.push(json(line, exact_numbers, python_text)?);
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

/// One member of a ZIP archive, read no further than `max_member_bytes`: the
/// only member, or, when `pattern` is given, the one member whose name it matches.
pub fn zip_member(bytes: &[u8], max_member_bytes: u64, pattern: Option<&str>) -> Result<Vec<u8>, Rejected> {
    let mut archive = zip::ZipArchive::new(Cursor::new(bytes)).map_err(malformed)?;
    let index = match pattern {
        None if archive.len() == 1 => 0,
        None => return Err(Rejected::new("zip_members", format!("{} members, not one", archive.len()))),
        Some(pattern) => {
            let found: Vec<usize> = (0..archive.len())
                .filter(|&i| archive.name_for_index(i).is_some_and(|name| matches_pattern(pattern, name)))
                .collect();
            match found[..] {
                [index] => index,
                [] => return Err(Rejected::new("zip_members", format!("no member matches {pattern}"))),
                _ => return Err(Rejected::new("zip_members", format!("{} members match {pattern}, not one", found.len()))),
            }
        }
    };
    let member = archive.by_index(index).map_err(malformed)?;
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

/// Whether a member name matches a pattern: `*` stands for any run of
/// characters, `?` for one; everything else matches itself.
pub(crate) fn matches_pattern(pattern: &str, name: &str) -> bool {
    let (pattern, name): (Vec<char>, Vec<char>) = (pattern.chars().collect(), name.chars().collect());
    let (mut p, mut n, mut star, mut mark) = (0, 0, None, 0);
    while n < name.len() {
        if p < pattern.len() && (pattern[p] == '?' || pattern[p] == name[n]) {
            p += 1;
            n += 1;
        } else if p < pattern.len() && pattern[p] == '*' {
            star = Some(p);
            mark = n;
            p += 1;
        } else if let Some(s) = star {
            p = s + 1;
            mark += 1;
            n = mark;
        } else {
            return false;
        }
    }
    pattern[p..].iter().all(|c| *c == '*')
}

/// Encodings a text format may declare (`read.encoding`); UTF-8 when none is.
pub const ENCODINGS: [&str; 2] = ["utf-8", "windows-1252"];

/// The text of an artifact in the first declared encoding that reads it, as
/// UTF-8 bytes. With [utf-8, windows-1252], valid UTF-8 is read as UTF-8 and
/// anything else as windows-1252. A byte no declared encoding defines refuses
/// the artifact; nothing is replaced or guessed.
/// `encodings` is what `validate` admitted: one name, or utf-8 then one other.
pub fn decode<'a>(bytes: &'a [u8], encodings: &[String]) -> Result<std::borrow::Cow<'a, [u8]>, Rejected> {
    let Some((last, first)) = encodings.split_last() else {
        return Err(Rejected::new("encoding", "no encoding is declared"));
    };
    if first.iter().any(|e| e == "utf-8") && std::str::from_utf8(bytes).is_ok() {
        return Ok(std::borrow::Cow::Borrowed(bytes));
    }
    decode_one(bytes, last)
}

fn decode_one<'a>(bytes: &'a [u8], encoding: &str) -> Result<std::borrow::Cow<'a, [u8]>, Rejected> {
    match encoding {
        "windows-1252" => {
            let mut out = String::with_capacity(bytes.len());
            for (offset, byte) in bytes.iter().enumerate() {
                out.push(match byte {
                    0x80..=0x9F => WINDOWS_1252[(byte - 0x80) as usize].ok_or_else(|| {
                        Rejected::new("encoding", format!("byte 0x{byte:02X} at {offset} is not windows-1252"))
                    })?,
                    _ => char::from(*byte),
                });
            }
            Ok(std::borrow::Cow::Owned(out.into_bytes()))
        }
        "utf-8" => Ok(std::borrow::Cow::Borrowed(bytes)),
        other => Err(Rejected::new("encoding", format!("{other} is not a declared encoding"))),
    }
}

/// Windows-1252 bytes 0x80 to 0x9F; the rest is Latin-1. Five bytes are undefined.
const WINDOWS_1252: [Option<char>; 32] = [
    Some('\u{20AC}'), None, Some('\u{201A}'), Some('\u{0192}'), Some('\u{201E}'), Some('\u{2026}'), Some('\u{2020}'), Some('\u{2021}'),
    Some('\u{02C6}'), Some('\u{2030}'), Some('\u{0160}'), Some('\u{2039}'), Some('\u{0152}'), None, Some('\u{017D}'), None,
    None, Some('\u{2018}'), Some('\u{2019}'), Some('\u{201C}'), Some('\u{201D}'), Some('\u{2022}'), Some('\u{2013}'), Some('\u{2014}'),
    Some('\u{02DC}'), Some('\u{2122}'), Some('\u{0161}'), Some('\u{203A}'), Some('\u{0153}'), None, Some('\u{017E}'), Some('\u{0178}'),
];
