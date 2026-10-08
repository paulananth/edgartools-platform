//! Declared, bounded indexed sets for configured membership expressions.
use serde_yaml::Value;
use crate::{expression_children, read_expressions, setting, Lookups, Rejected, Val};

fn valid_name(value: &Value) -> bool {
    value.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 128)
}

pub(crate) fn validate_call(args: &Value) -> Result<(), String> {
    let map = args.as_mapping().filter(|m| m.len() == 2)
        .ok_or("member requires lookup and key only")?;
    if map.keys().any(|k| !matches!(k.as_str(), Some("lookup" | "key")))
        || !args.get("lookup").is_some_and(valid_name) || args.get("key").is_none() {
        return Err("member requires a bounded lookup name and a key expression".into());
    }
    Ok(())
}

pub(crate) fn validate(read: &Value) -> Result<(), String> {
    if let Some(specs) = read.get("lookup_sets") {
        let specs = specs.as_mapping().filter(|m| m.len() <= 16)
            .ok_or("lookup_sets declares at most sixteen sets")?;
        for (name, spec) in specs {
            if !valid_name(name) { return Err("lookup set names are bounded nonempty text".into()); }
            let map = spec.as_mapping().filter(|m| m.len() == 3)
                .ok_or("lookup set requires max_values, max_bytes and max_value_bytes")?;
            if map.keys().any(|k| !matches!(k.as_str(), Some("max_values" | "max_bytes" | "max_value_bytes"))) {
                return Err("lookup set has an unknown bound".into());
            }
            for (bound, maximum) in [("max_values", 1_000_000), ("max_bytes", 64 * 1024 * 1024), ("max_value_bytes", 16_384)] {
                if !spec.get(bound).and_then(Value::as_u64).is_some_and(|n| n > 0 && n <= maximum) {
                    return Err(format!("lookup set {bound} must be positive and at most {maximum}"));
                }
            }
        }
    }
    fn visit(expr: &Value, read: &Value) -> Result<(), String> {
        if let Some(args) = expr.get("member") {
            validate_call(args)?;
            if read.get("lookup_sets").and_then(|sets| sets.get(setting(args,"lookup").unwrap())).is_none() {
                return Err("member names an undeclared lookup set".into());
            }
        }
        for child in expression_children(expr) { visit(child, read)?; }
        Ok(())
    }
    for expr in read_expressions(read) { visit(expr, read)?; }
    Ok(())
}

pub(crate) fn check(read: &Value, sets: &Lookups) -> Result<(), Rejected> {
    let Some(specs) = read.get("lookup_sets").and_then(Value::as_mapping) else { return Ok(()) };
    let invalid = || Rejected::new("invalid_lookup", "runtime sets must exactly match declared lookup_sets");
    if sets.len() != specs.len() { return Err(invalid()); }
    let mut total = 0usize;
    for (name, spec) in specs {
        let values = sets.get(name.as_str().unwrap()).ok_or_else(invalid)?;
        if values.len() as u64 > spec["max_values"].as_u64().unwrap() {
            return Err(Rejected::new("limit_exceeded", "lookup set exceeds max_values"));
        }
        let mut bytes = 0usize;
        for value in values {
            if value.len() as u64 > spec["max_value_bytes"].as_u64().unwrap() {
                return Err(Rejected::new("limit_exceeded", "lookup key exceeds max_value_bytes"));
            }
            bytes = bytes.checked_add(value.len()).ok_or_else(|| Rejected::new("limit_exceeded", "lookup byte count overflow"))?;
            if bytes as u64 > spec["max_bytes"].as_u64().unwrap() {
                return Err(Rejected::new("limit_exceeded", "lookup set exceeds max_bytes"));
            }
        }
        total = total.checked_add(bytes).ok_or_else(|| Rejected::new("limit_exceeded", "lookup byte count overflow"))?;
        if total > 64 * 1024 * 1024 { return Err(Rejected::new("limit_exceeded", "lookup sets exceed aggregate byte bound")); }
    }
    Ok(())
}

pub(crate) fn member(sets: &Lookups, name: &str, key: &Val) -> Result<Val, Rejected> {
    let values = sets.get(name).ok_or_else(|| Rejected::new("invalid_lookup", "lookup set is missing"))?;
    match key {
        Val::Null => Ok(Val::Bool(false)),
        Val::Str(key) => Ok(Val::Bool(values.contains(key))),
        _ => Err(Rejected::new("lookup_key", "membership key must be text or null; declare conversion explicitly")),
    }
}

/// Python ingestion uses raw counts before deduplication or allocation.
#[cfg(feature = "python")]
pub(crate) fn input_bounds(read: &Value, name: &str) -> Result<Option<(usize,usize,usize)>, Rejected> {
    let Some(specs) = read.get("lookup_sets") else { return Ok(None) };
    let spec = specs.get(name).ok_or_else(|| Rejected::new("invalid_lookup", "runtime lookup set is undeclared"))?;
    Ok(Some((spec["max_values"].as_u64().unwrap() as usize,
             spec["max_bytes"].as_u64().unwrap() as usize,
             spec["max_value_bytes"].as_u64().unwrap() as usize)))
}
