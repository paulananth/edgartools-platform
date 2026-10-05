//! Header-named JSON rows. Layout is declared by configuration, not a feed.
use std::collections::BTreeSet;
use serde_yaml::Value;
use crate::tree::{Child, El, ScalarKind};
use crate::{check_path, json_text, setting, Rejected};

pub(crate) fn validate(each: &Value, format: &str) -> Result<(), String> {
    let outer = each.as_mapping().filter(|m| m.len() == 1).ok_or("each requires one call")?;
    let args = outer.get(Value::String("matrix".into())).and_then(Value::as_mapping)
        .ok_or("each.matrix must be a mapping")?;
    if format != "json" { return Err("each.matrix requires JSON".into()); }
    if args.keys().any(|k| !matches!(k.as_str(), Some("headers" | "rows" | "lengths" | "duplicates" | "headers_coerce" | "on_invalid_row"))) {
        return Err("each.matrix has an unknown argument".into());
    }
    for (key, choices) in [("lengths", ["equal", "zip"]), ("duplicates", ["reject", "last"]),
                           ("headers_coerce", ["text", "python"]), ("on_invalid_row", ["reject", "skip"])] {
        if each["matrix"].get(key).is_some_and(|v| !v.as_str().is_some_and(|s| choices.contains(&s))) {
            return Err(format!("invalid matrix {key}"));
        }
    }
    for name in ["headers", "rows"] {
        let path = setting(&each["matrix"], name).ok_or("matrix paths must be text")?;
        check_path(path)?;
        if path == "." || path.contains(['[', ']', '@', '$']) {
            return Err("matrix paths name JSON arrays without filters or attributes".into());
        }
    }
    Ok(())
}

fn array<'a>(document: &'a El, path: &str) -> Result<&'a [El], Rejected> {
    let mut node = document;
    let parts: Vec<_> = path.split('.').collect();
    for (i, part) in parts.iter().enumerate() {
        match node.children.get(*part) {
            Some(Child::Many(rows)) if i + 1 == parts.len() => return Ok(rows),
            Some(Child::One(next)) if !next.scalar && !next.array && i + 1 < parts.len() => node = next,
            _ => return Err(Rejected::new("matrix_shape", format!("{path} must name a JSON array"))),
        }
    }
    unreachable!()
}

pub(crate) fn rows(document: &El, each: &Value, maximum: usize, take: usize) -> Result<(Vec<El>, usize), Rejected> {
    let spec = &each["matrix"];
    let headers = array(document, setting(spec, "headers").unwrap())?;
    let python_headers = setting(spec, "headers_coerce") == Some("python");
    if (!python_headers && headers.is_empty()) || headers.len() > 128 {
        return Err(Rejected::new("matrix_header", "Require 1..128 header names"));
    }
    let mut names = Vec::new();
    let mut seen = BTreeSet::new();
    for header in headers {
        let name = if python_headers {
            json_text::value(header)?.unwrap_or_else(|| "None".into())
        } else {
            header.text.clone().filter(|s| header.scalar && header.kind == ScalarKind::Text
                && !s.is_empty() && s.len() <= 128 && s.chars().all(|c| c.is_ascii_alphanumeric() || c == '_'))
                .ok_or_else(|| Rejected::new("matrix_header", "Headers require simple nonempty text names"))?
        };
        if name.len() > 128 { return Err(Rejected::new("matrix_header", "Header name exceeds 128 bytes")); }
        if !seen.insert(name.clone()) && setting(spec, "duplicates") != Some("last") {
            return Err(Rejected::new("matrix_header", "Duplicate header name"));
        }
        names.push(name);
    }
    let input = array(document, setting(spec, "rows").unwrap())?;
    if input.len() > maximum { return Err(Rejected::new("limit_exceeded", "Matrix row count exceeds max_records")); }
    let mut output = Vec::new();
    for (index, row) in input.iter().enumerate() {
        let cells = match row.children.get("item") {
            Some(Child::Many(cells)) if row.array => cells,
            _ if setting(spec, "on_invalid_row") == Some("skip") => continue,
            _ => return Err(Rejected::new("matrix_shape", "Each matrix row must be an array")),
        };
        if cells.len() != names.len() && setting(spec, "lengths") != Some("zip") { return Err(Rejected::new("matrix_length", "Row length differs from header count")); }
        if index < take {
            let mut record = El { json_keys: Some(Vec::new()), ..El::default() };
            for (name, cell) in names.iter().zip(cells) {
                if !record.children.contains_key(name) { record.json_keys.as_mut().unwrap().push(name.clone()); }
                record.children.insert(name.clone(), Child::One(cell.clone()));
            }
            output.push(record);
        }
    }
    Ok((output, input.len()))
}
