//! Typed JSON evidence; no text flattening or domain interpretation.
use std::collections::BTreeMap;
use serde_yaml::Value;
use crate::{check_path, lookup_value, setting, Found, Rejected, Val};
use crate::tree::{Child, El, ScalarKind};

pub(crate) fn validate(args: &Value) -> Result<(), String> {
    let map = args.as_mapping().ok_or("value arguments must be a mapping")?;
    if map.keys().any(|k| !matches!(k.as_str(), Some("path" | "from"))) {
        return Err("value names path and optional from only".into());
    }
    if args.get("from").is_some_and(|v| !matches!(v.as_str(), Some("document" | "item"))) {
        return Err("value from is document or item".into());
    }
    check_path(setting(args, "path").ok_or("value names no path")?)
}

fn scalar(text: Option<&str>, kind: ScalarKind, exact: Option<&str>) -> Result<Val, Rejected> {
    let Some(text) = text else { return Ok(Val::Null) };
    match kind {
        ScalarKind::Text => Ok(Val::Str(text.into())),
        ScalarKind::Boolean => Ok(Val::Bool(text == "true")),
        ScalarKind::Number => {
            let text = exact.unwrap_or(text);
            if text.contains(['.', 'e', 'E']) {
                text.parse::<f64>().ok().filter(|n| n.is_finite()).map(Val::Float)
            } else {
                text.parse::<i64>().ok().map(Val::Int).or_else(|| text.parse::<u64>().ok().map(Val::UInt))
            }.ok_or_else(|| Rejected::new("value_number_range", "JSON evidence number exceeds its exact integer or finite float range"))
        }
    }
}

fn element(el: &El) -> Result<Val, Rejected> {
    if el.scalar { return scalar(el.text.as_deref(), el.kind, el.exact_number.as_deref()); }
    if el.array {
        return match el.children.get("item") {
            Some(Child::Many(items)) => items.iter().map(element).collect::<Result<Vec<_>, _>>().map(Val::List),
            _ => Err(Rejected::new("value_shape", "array has no item sequence")),
        };
    }
    let mut values = BTreeMap::new();
    if let Some(text) = &el.text { values.insert("$".into(), Val::Str(text.clone())); }
    for (key, text) in &el.attrs { values.insert(key.clone(), Val::Str(text.clone())); }
    for (key, child) in &el.children {
        let value = match child {
            Child::One(el) => element(el)?,
            Child::Many(items) => Val::List(items.iter().map(element).collect::<Result<Vec<_>, _>>()?),
        };
        values.insert(key.clone(), value);
    }
    Ok(Val::Map(values))
}

pub(crate) fn read(start: &El, args: &Value) -> Result<Val, Rejected> {
    match lookup_value(start, setting(args, "path").unwrap(), true)? {
        Found::Missing => Ok(Val::Null),
        Found::El(el) => element(el),
        Found::Text(text, kind, exact) => scalar(Some(&text), kind, exact),
        Found::List(items) => items.into_iter().map(element).collect::<Result<Vec<_>, _>>().map(Val::List),
    }
}
