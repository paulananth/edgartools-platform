//! Bounded configurable row iteration; no source identities or loaders.
use serde_yaml::Value;
use crate::{eval, matrix, parallel, setting, validate_expr, Engine, Rejected, Row, Steps, Val};
use crate::tree::{Child, El};

pub(crate) fn validate(each: &Value, format: &str, steps: &Steps, depth: usize) -> Result<(), String> {
    if depth > 8 { return Err("iteration nesting exceeds eight calls".into()); }
    if let Some(path) = each.as_str() { return crate::check_path(path); }
    let map = each.as_mapping().filter(|m| m.len() == 1).ok_or("each requires one iteration call")?;
    let (name, args) = map.iter().next().unwrap();
    match name.as_str() {
        Some("parallel") => parallel::validate(each, format),
        Some("matrix") => matrix::validate(each, format),
        Some("objects" | "entries") => {
            if format != "json" { return Err("each.objects requires JSON".into()); }
            let map = args.as_mapping().ok_or("objects arguments must be a mapping")?;
            let entries = name.as_str() == Some("entries");
            if map.keys().any(|k| !matches!(k.as_str(), Some("path" | "on_invalid")) && !(entries && matches!(k.as_str(), Some("key_field" | "value_field")))) { return Err("objects/entries has an unknown argument".into()); }
            if entries {
                for key in ["key_field", "value_field"] {
                    if !setting(args,key).is_some_and(|name| !name.is_empty() && name.len() <= 64
                        && name.chars().enumerate().all(|(i,c)| c == '_' || c.is_ascii_alphabetic() || (i > 0 && c.is_ascii_digit()))) {
                        return Err("entries requires distinct key_field/value_field identifiers of 1..64 ASCII characters".into());
                    }
                }
                if args["key_field"] == args["value_field"] { return Err("entries key_field/value_field must differ".into()); }
            }
            crate::check_path(setting(args, "path").ok_or("objects requires path")?)?;
            if args.get("on_invalid").is_some_and(|v| !matches!(v.as_str(), Some("empty" | "reject"))) { return Err("objects on_invalid is empty or reject".into()); }
            Ok(())
        }
        Some("choose") => {
            let map = args.as_mapping().ok_or("iteration choose requires a mapping")?;
            if map.len() != 3 || map.keys().any(|k| !matches!(k.as_str(), Some("condition" | "then" | "else"))) { return Err("iteration choose requires condition, then and else only".into()); }
            validate_expr(&args["condition"], steps)?;
            validate(&args["then"], format, steps, depth + 1)?;
            validate(&args["else"], format, steps, depth + 1)
        }
        _ => Err("unknown iteration call".into()),
    }
}

pub(crate) fn expressions(each: &Value) -> Vec<&Value> {
    let mut result = Vec::new();
    if let Some(args) = each.get("choose") {
        if let Some(condition) = args.get("condition") { result.push(condition); }
        for key in ["then", "else"] { if let Some(branch) = args.get(key) { result.extend(expressions(branch)); } }
    }
    result
}

pub(crate) fn needs_order(each: &Value) -> bool {
    each.get("objects").is_some() || each.get("entries").is_some() || each.get("matrix").and_then(|a| a.get("headers_coerce")).and_then(Value::as_str) == Some("python")
        || each.get("choose").is_some_and(|args| ["then", "else"].iter().any(|k| args.get(*k).is_some_and(needs_order)))
}

pub(crate) fn rows(engine: &Engine, context: &Row, document: &El, each: &Value, maximum: usize, take: usize) -> Result<(Vec<El>, usize), Rejected> {
    if let Some(path) = each.as_str() {
        let items = crate::items_of(document, path)?;
        if items.len() > maximum { return Err(Rejected::new("limit_exceeded", "Iteration exceeds max_records")); }
        return Ok((items.iter().take(take).map(|el| (*el).clone()).collect(), items.len()));
    }
    if each.get("matrix").is_some() { return matrix::rows(document, each, maximum, take); }
    if each.get("parallel").is_some() {
        let expanded = parallel::rows(document, each, maximum, take)?;
        return Ok((expanded.rows, expanded.count));
    }
    if let Some(args) = each.get("choose") {
        let branch = match eval(engine, context, document, document, 1, &args["condition"])? {
            Val::Bool(true) => "then", Val::Bool(false) | Val::Null => "else",
            _ => return Err(Rejected::new("choose_condition", "Iteration condition must be boolean or null")),
        };
        return rows(engine, context, document, &args[branch], maximum, take);
    }
    let entries = each.get("entries");
    let args = entries.unwrap_or(&each["objects"]);
    let object = match crate::lookup_value(document, setting(args, "path").unwrap(), true)? {
        crate::Found::El(el) if !el.scalar && !el.array => el,
        _ if setting(args, "on_invalid") == Some("empty") => return Ok((Vec::new(), 0)),
        _ => return Err(Rejected::new("objects_shape", "objects path must name one JSON object")),
    };
    let keys = object.json_keys.as_ref().ok_or_else(|| Rejected::new("objects_order", "JSON object order is missing"))?;
    if keys.len() > maximum { return Err(Rejected::new("limit_exceeded", "Object entries exceed max_records")); }
    let mut result = Vec::new();
    for key in keys.iter().take(take) {
        let el = if let Some(child) = object.children.get(key) {
            match child {
                Child::One(el) => el.clone(),
                Child::Many(items) => { let mut el = El { array: true, ..El::default() }; el.children.insert("item".into(), Child::Many(items.clone())); el }
            }
        } else if key == "$" { El::scalar(object.text.clone()) }
        else { El::scalar(object.attrs.get(key).cloned()) };
        if entries.is_some() {
            let key_field = setting(args,"key_field").unwrap();
            let value_field = setting(args,"value_field").unwrap();
            let mut row = El { json_keys: Some(vec![key_field.into(),value_field.into()]), ..El::default() };
            row.add_child(key_field.into(),El::scalar(Some(key.clone())));
            row.add_child(value_field.into(),el);
            result.push(row);
        } else { result.push(el); }
    }
    Ok((result, keys.len()))
}
