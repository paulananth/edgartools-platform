//! Typed JSON evidence; no text flattening or domain interpretation.
use std::collections::BTreeMap;
use serde_yaml::Value;
use crate::{check_path, lookup_shape, lookup_literal, setting, Found, Rejected, Val};
use crate::tree::{Child, El, ScalarKind};

pub(crate) fn validate(args: &Value) -> Result<(), String> {
    let map = args.as_mapping().ok_or("value arguments must be a mapping")?;
    if map.keys().any(|k| !matches!(k.as_str(), Some("path" | "from" | "type" | "nullable" | "trim" | "null_if_blank" | "path_mode"))) {
        return Err("value has an unknown argument".into());
    }
    if args.get("from").is_some_and(|v| !matches!(v.as_str(), Some("document" | "item"))) {
        return Err("value from is document or item".into());
    }
    if args.get("type").is_some_and(|v| !matches!(v.as_str(),Some("text" | "integer" | "number" | "boolean" | "object" | "array"))) { return Err("value type is text, integer, number, boolean, object or array".into()); }
    for key in ["nullable", "trim", "null_if_blank"] {
        if args.get(key).is_some_and(|v| v.as_bool().is_none()) { return Err("value policies are booleans".into()); }
    }
    if args.get("path_mode").is_some_and(|v| !matches!(v.as_str(),Some("tree"|"literal"))) { return Err("value path_mode is tree or literal".into()); }
    if setting(args,"path_mode") == Some("literal") && setting(args,"path").is_some_and(|p| p.contains(['[',']'])) { return Err("literal paths have no filters".into()); }
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
    let found = if setting(args,"path_mode") == Some("literal") { lookup_literal(start,setting(args,"path").unwrap())? } else { lookup_shape(start,setting(args,"path").unwrap())? };
    let value = match found {
        Found::Missing => Ok(Val::Null),
        Found::El(el) => element(el),
        Found::Text(text, kind, exact) => scalar(Some(&text), kind, exact),
        Found::List(items) => items.into_iter().map(element).collect::<Result<Vec<_>, _>>().map(Val::List),
    }?;
    let valid = match &value {
        Val::Null => args["nullable"].as_bool() != Some(false),
        _ if setting(args,"type").is_none() => true,
        Val::Str(_) => setting(args,"type") == Some("text"),
        Val::Int(_) | Val::UInt(_) => matches!(setting(args,"type"),Some("integer"|"number")),
        Val::Float(_) => setting(args,"type") == Some("number"),
        Val::Bool(_) => setting(args,"type") == Some("boolean"),
        Val::Map(_) => setting(args,"type") == Some("object"),
        Val::List(_) => setting(args,"type") == Some("array"),
    };
    if !valid { return Err(Rejected::new("value_type", "Value differs from declared type or null policy")); }
    if let Val::Str(text) = value {
        if args["trim"].as_bool() != Some(true) && args["null_if_blank"].as_bool() != Some(true) { return Ok(Val::Str(text)); }
        let stripped = text.trim_matches(crate::text_transform::whitespace);
        if args["null_if_blank"].as_bool() == Some(true) && stripped.is_empty() {
            if args["nullable"].as_bool() == Some(false) { return Err(Rejected::new("value_type", "Blank value conflicts with nonnullable policy")); }
            return Ok(Val::Null);
        }
        Ok(Val::Str(if args["trim"].as_bool() == Some(true) { stripped.to_owned() } else { text }))
    } else { Ok(value) }
}
