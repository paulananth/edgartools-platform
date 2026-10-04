//! Explicit caller facts, separate from the captured document and its records.
use serde_yaml::Value;
use crate::{setting, Rejected, Row, Val};

pub(crate) fn validate(read: &Value) -> Result<(), String> {
    if let Some(specs) = read.get("context") {
        let specs = specs.as_mapping().filter(|m| m.len() <= 32).ok_or("read.context names at most 32 fields")?;
        for (name, spec) in specs {
            let name = name.as_str().filter(|s| !s.is_empty() && s.len() <= 64 && s.chars().all(|c| c.is_ascii_alphanumeric() || c == '_'))
                .ok_or("context names use at most 64 letters, digits or underscores")?;
            let args = spec.as_mapping().ok_or(format!("context {name} must declare its type"))?;
            if args.keys().any(|k| !matches!(k.as_str(), Some("type" | "nullable" | "max_bytes"))) {
                return Err(format!("context {name} has an unknown argument"));
            }
            if !matches!(setting(spec, "type"), Some("text" | "integer" | "boolean")) {
                return Err(format!("context {name} type is text, integer or boolean"));
            }
            if spec.get("nullable").is_some_and(|v| v.as_bool().is_none()) {
                return Err(format!("context {name} nullable must be boolean"));
            }
            if let Some(bound) = spec.get("max_bytes") {
                if setting(spec, "type") != Some("text") || !bound.as_u64().is_some_and(|n| (1..=4096).contains(&n)) {
                    return Err(format!("context {name} max_bytes requires text and an integer 1..4096"));
                }
            }
        }
    }
    for (_, table) in read["tables"].as_mapping().into_iter().flatten() {
        for (_, expr) in table["columns"].as_mapping().into_iter().flatten() {
            references(expr, read)?;
        }
        if let Some(take) = table.get("take") {
            let call = take.as_mapping().filter(|m| m.len() == 1).ok_or("table.take is one context or const call")?;
            if let Some(args) = call.get(Value::String("context".into())) {
                reference(args, read)?;
                let name = setting(args, "name").unwrap();
                if setting(&read["context"][name], "type") != Some("integer") {
                    return Err("table.take context must be integer (optionally nullable)".into());
                }
            } else if let Some(args) = call.get(Value::String("const".into())) {
                let args = args.as_mapping().filter(|m| m.len() == 1).ok_or("table.take const names value only")?;
                let value = args.get(Value::String("value".into())).ok_or("table.take const names no value")?;
                if !value.is_null() && value.as_i64().is_none() {
                    return Err("table.take is a signed integer or null".into());
                }
            } else {
                return Err("table.take is one context or const call".into());
            }
        }
    }
    Ok(())
}

pub(crate) fn reference(args: &Value, read: &Value) -> Result<(), String> {
    let call = args.as_mapping().filter(|m| m.len() == 1).ok_or("context call names one field")?;
    let name = call.get(Value::String("name".into())).and_then(Value::as_str).ok_or("context call names no field")?;
    if read.get("context").and_then(|v| v.get(name)).is_none() {
        return Err(format!("context {name} is not declared"));
    }
    Ok(())
}

fn references(expr: &Value, read: &Value) -> Result<(), String> {
    if let Some(args) = expr.get("context") { reference(args, read)?; }
    if let Some(key) = expr.get("lookup").and_then(|v| v.get("key")) { references(key, read)?; }
    if let Some(calls) = expr.get("steps").and_then(Value::as_sequence) {
        for call in calls { references(call, read)?; }
    }
    if let Some(inputs) = expr.get("custom").and_then(|v| v.get("inputs")).and_then(Value::as_mapping) {
        for (_, call) in inputs { references(call, read)?; }
    }
    Ok(())
}

pub(crate) fn check(read: &Value, values: &Row) -> Result<(), Rejected> {
    let specs = read.get("context").and_then(Value::as_mapping);
    if specs.map_or(0, |s| s.len()) != values.len() {
        return Err(Rejected::new("invalid_context", "context keys differ from the declared fields"));
    }
    for (name, value) in values {
        let spec = specs.and_then(|s| s.get(Value::String(name.clone())))
            .ok_or_else(|| Rejected::new("invalid_context", format!("context {name} is not declared")))?;
        let valid = match value {
            Val::Null => spec.get("nullable").and_then(Value::as_bool) == Some(true),
            Val::Int(_) => setting(spec, "type") == Some("integer"),
            Val::Bool(_) => setting(spec, "type") == Some("boolean"),
            Val::Str(text) => setting(spec, "type") == Some("text") && text.len() as u64 <= spec.get("max_bytes").and_then(Value::as_u64).unwrap_or(4096),
            Val::Float(_) | Val::UInt(_) | Val::List(_) | Val::Map(_) => false,
        };
        if !valid { return Err(Rejected::new("invalid_context", format!("context {name} has the wrong type or size"))); }
    }
    Ok(())
}

pub(crate) fn take(table: &Value, values: &Row) -> usize {
    let Some(expr) = table.get("take") else { return usize::MAX };
    let value = if let Some(args) = expr.get("context") {
        values.get(setting(args, "name").unwrap()).unwrap().clone()
    } else {
        super::yaml_val(expr["const"].get("value"))
    };
    match value {
        Val::Null => usize::MAX,
        Val::Int(n) if n > 0 => usize::try_from(n).unwrap_or(usize::MAX),
        _ => 0,
    }
}

#[cfg(feature = "python")]
pub(crate) fn from_json(text: &str) -> Result<Row, Rejected> {
    let invalid = || Rejected::new("invalid_context", "context is a bounded object of exact scalar values");
    if text.len() > 32 * 1024 { return Err(invalid()); }
    let parsed: serde_json::Value = serde_json::from_str(text).map_err(|_| invalid())?;
    let values = parsed.as_object().filter(|m| m.len() <= 32).ok_or_else(invalid)?;
    values.iter().map(|(name, value)| {
        let value = match value {
            serde_json::Value::Null => Val::Null,
            serde_json::Value::Bool(b) => Val::Bool(*b),
            serde_json::Value::String(s) => Val::Str(s.clone()),
            serde_json::Value::Number(n) => Val::Int(n.as_i64().ok_or_else(invalid)?),
            _ => return Err(invalid()),
        };
        Ok((name.clone(), value))
    }).collect()
}
