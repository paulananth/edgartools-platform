//! Generic JSON parallel arrays, with row count pinned to a declared anchor.
use serde_yaml::Value;
use std::borrow::Cow;

use crate::tree::{Child, El, ScalarKind};
use crate::{check_path, setting, Rejected};

pub(crate) fn validate(each: &Value, format: &str) -> Result<(), String> {
    let outer = each.as_mapping().filter(|m| m.len() == 1).ok_or("each is a path or one parallel call")?;
    let args = outer.get(Value::String("parallel".into())).and_then(Value::as_mapping)
        .ok_or("each.parallel must be a mapping")?;
    if format != "json" {
        return Err("each.parallel requires one JSON document".into());
    }
    for key in args.keys() {
        if !matches!(key.as_str(), Some("path" | "anchor" | "fields" | "lengths" | "on_invalid_object" | "strings" | "on_empty_anchor")) {
            return Err("each.parallel has an unknown argument".into());
        }
    }
    let spec = &each["parallel"];
    let path = setting(spec, "path").ok_or("each.parallel names no path")?;
    if path != "." { array_path(path)?; }
    array_path(setting(spec, "anchor").ok_or("each.parallel names no anchor")?)?;
    if spec.get("lengths").is_some_and(|v| !matches!(v.as_str(), Some("equal" | "anchor"))) {
        return Err("each.parallel.lengths is equal or anchor".into());
    }
    if spec.get("on_invalid_object").is_some_and(|v| !matches!(v.as_str(), Some("reject" | "empty"))) {
        return Err("each.parallel.on_invalid_object is reject or empty".into());
    }
    if spec.get("strings").is_some_and(|v| !matches!(v.as_str(), Some("reject" | "characters"))) {
        return Err("each.parallel.strings is reject or characters".into());
    }
    if spec.get("on_empty_anchor").is_some_and(|v| !matches!(v.as_str(), Some("validate_fields" | "ignore_fields"))) {
        return Err("each.parallel.on_empty_anchor is validate_fields or ignore_fields".into());
    }
    if setting(spec, "on_empty_anchor") == Some("ignore_fields") && setting(spec, "lengths") != Some("anchor") {
        return Err("each.parallel.on_empty_anchor ignore_fields requires lengths anchor".into());
    }
    let fields = spec.get("fields").and_then(Value::as_mapping).filter(|m| !m.is_empty())
        .ok_or("each.parallel.fields is a nonempty mapping")?;
    for (name, path) in fields {
        let name = name.as_str().ok_or("a parallel field name must be text")?;
        if name.is_empty() || !name.chars().all(|c| c.is_ascii_alphanumeric() || c == '_') {
            return Err("a parallel field name uses letters, digits or underscores".into());
        }
        array_path(path.as_str().ok_or("a parallel field path must be text")?)?;
    }
    Ok(())
}

fn array_path(path: &str) -> Result<(), String> {
    check_path(path)?;
    if path == "." || path.contains(['[', ']', '@', '$']) {
        return Err("a parallel array path names an array, without filters or attributes".into());
    }
    Ok(())
}

fn object_at<'a>(start: &'a El, path: &str) -> Result<Option<&'a El>, Rejected> {
    let mut current = start;
    if path != "." {
        for part in path.split('.') {
            current = match current.children.get(part) {
                None => return Ok(None),
                Some(Child::One(el)) if !el.scalar && !el.array => el,
                _ => return Err(Rejected::new("parallel_shape", format!("{path} must be one object"))),
            };
        }
    }
    if current.scalar || current.array {
        return Err(Rejected::new("parallel_shape", format!("{path} must be one object")));
    }
    Ok(Some(current))
}

fn array<'a>(container: &'a El, path: &str, strings: bool, character_bound: usize) -> Result<Option<Cow<'a, [El]>>, Rejected> {
    let (parent, name) = path.rsplit_once('.').unwrap_or((".", path));
    let Some(parent) = object_at(container, parent)? else { return Ok(None) };
    match parent.children.get(name) {
        None => Ok(None),
        Some(Child::Many(values)) => Ok(Some(Cow::Borrowed(values))),
        Some(Child::One(el)) if strings && el.scalar && el.kind == ScalarKind::Text && el.text.is_some() => {
            Ok(Some(Cow::Owned(el.text.as_ref().unwrap().chars().take(character_bound).map(|c| El::scalar(Some(c.to_string()))).collect())))
        }
        Some(Child::One(_)) => Err(Rejected::new("parallel_shape", format!("{path} must be an array"))),
    }
}

pub(crate) fn rows(document: &El, each: &Value, max_records: usize) -> Result<Vec<El>, Rejected> {
    let spec = &each["parallel"];
    let path = setting(spec, "path").unwrap(); // validated on load
    let container = match object_at(document, path) {
        Err(_) if setting(spec, "on_invalid_object") == Some("empty") => return Ok(Vec::new()),
        other => other?,
    };
    let Some(container) = container else { return Ok(Vec::new()) };
    let strings = setting(spec, "strings") == Some("characters");
    let count = array(container, setting(spec, "anchor").unwrap(), strings, max_records.saturating_add(1))?.map_or(0, |values| values.len());
    if count > max_records {
        return Err(Rejected::new("limit_exceeded", format!("parallel anchor has more than {max_records} records")));
    }
    let equal = setting(spec, "lengths").unwrap_or("equal") == "equal";
    if count == 0 && setting(spec, "on_empty_anchor") == Some("ignore_fields") { return Ok(Vec::new()); }
    let mut columns = Vec::new();
    for (name, path) in spec["fields"].as_mapping().unwrap() {
        let path = path.as_str().unwrap();
        let values = array(container, path, strings, count.saturating_add(1))?;
        if equal && values.as_ref().map_or(0, |values| values.len()) != count {
            return Err(Rejected::new("parallel_length", format!("{path} does not match the anchor's {count} records")));
        }
        columns.push((name.as_str().unwrap(), values));
    }
    Ok((0..count).map(|index| {
        let mut row = El::default();
        for (name, values) in &columns {
            let value = values.as_ref().and_then(|values| values.get(index)).cloned().unwrap_or_else(|| El::scalar(None));
            row.children.insert((*name).into(), Child::One(value));
        }
        row
    }).collect())
}
