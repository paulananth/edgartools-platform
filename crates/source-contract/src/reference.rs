//! Bounded reference rows frozen in the same contract as their expressions.
use serde_yaml::Value;
use crate::{setting, yaml_val, Rejected, Val};

fn name(value: &Value) -> bool {
    value.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 128)
}

pub(crate) fn validate(read: &Value) -> Result<(), String> {
    if let Some(tables) = read.get("references") {
        let tables = tables.as_mapping().filter(|m| m.len() <= 16)
            .ok_or("read.references is a mapping of at most 16 tables")?;
        let mut cells = 0usize;
        for (table, rows) in tables {
            if !name(table) { return Err("reference table names are nonempty text of at most 128 bytes".into()); }
            let rows = rows.as_mapping().filter(|m| m.len() <= 10_000)
                .ok_or("a reference table has at most 10000 keyed rows")?;
            for (key, row) in rows {
                if !name(key) { return Err("reference keys are nonempty text of at most 128 bytes".into()); }
                let row = row.as_mapping().filter(|m| !m.is_empty() && m.len() <= 32)
                    .ok_or("a reference row has 1..32 columns")?;
                for (column, value) in row {
                    cells += 1;
                    if cells > 100_000 { return Err("references exceed 100000 cells".into()); }
                    if !name(column) { return Err("reference columns are nonempty text of at most 128 bytes".into()); }
                    let valid = match value {
                        Value::Null | Value::Bool(_) => true,
                        Value::String(s) => s.len() <= 4096,
                        Value::Number(n) => n.as_i64().is_some() || (!n.is_u64() && n.as_f64().is_some_and(f64::is_finite)),
                        _ => false,
                    };
                    if !valid { return Err("reference cells are bounded text, null, boolean, signed integer or finite float".into()); }
                }
            }
        }
    }
    for (_, table) in read["tables"].as_mapping().into_iter().flatten() {
        for (_, expr) in table["columns"].as_mapping().into_iter().flatten() { references(expr, read)?; }
    }
    Ok(())
}

pub(crate) fn validate_call(args: &Value) -> Result<(), String> {
    let map = args.as_mapping().ok_or("lookup arguments must be a mapping")?;
    if map.keys().any(|k| !matches!(k.as_str(), Some("reference" | "column" | "key" | "on_missing" | "trim" | "case"))) {
        return Err("lookup has an unknown argument".into());
    }
    setting(args, "reference").ok_or("lookup names no reference")?;
    setting(args, "column").ok_or("lookup names no column")?;
    args.get("key").ok_or("lookup names no key expression")?;
    if args.get("on_missing").is_some_and(|v| !matches!(v.as_str(), Some("null" | "error"))) {
        return Err("lookup on_missing is quoted null or error".into());
    }
    if args.get("trim").is_some_and(|v| v.as_bool().is_none()) { return Err("lookup trim must be boolean".into()); }
    if args.get("case").is_some_and(|v| !matches!(v.as_str(), Some("upper" | "lower" | "preserve"))) {
        return Err("lookup case is upper, lower or preserve".into());
    }
    Ok(())
}

fn references(expr: &Value, read: &Value) -> Result<(), String> {
    if let Some(args) = expr.get("lookup") {
        validate_call(args)?;
        let table = setting(args, "reference").unwrap();
        let column = setting(args, "column").unwrap();
        let rows = read.get("references").and_then(|r| r.get(table)).and_then(Value::as_mapping)
            .ok_or(format!("lookup reference {table} is not declared"))?;
        if rows.values().any(|row| row.get(column).is_none()) {
            return Err(format!("lookup column {column} is missing from reference {table}"));
        }
    }
    for child in crate::expression_children(expr) { references(child, read)?; }
    Ok(())
}

pub(crate) fn read(read: &Value, args: &Value, key: &Val) -> Result<Val, Rejected> {
    let reference = setting(args, "reference").unwrap();
    let column = setting(args, "column").unwrap();
    let value = match key {
        Val::Null => None,
        Val::Str(key) => {
            let key = if args.get("trim").and_then(Value::as_bool).unwrap_or(false) { key.trim_matches(|c: char| c.is_whitespace() || matches!(c, '\u{1c}'..='\u{1f}')) } else { key.as_str() };
            let key = match setting(args, "case").unwrap_or("preserve") {
                "upper" => key.to_uppercase(), "lower" => key.to_lowercase(), _ => key.to_string(),
            };
            read["references"][reference].get(&key).and_then(|row| row.get(column))
        },
        _ => return Err(Rejected::new("lookup_key", "lookup key must be text or null; declare conversion explicitly")),
    };
    match value {
        Some(Value::Bool(value)) => Ok(Val::Bool(*value)),
        Some(value) => Ok(yaml_val(Some(value))),
        None if setting(args, "on_missing") == Some("error") => Err(Rejected::new("lookup_missing", format!("no key in reference {reference}"))),
        None => Ok(Val::Null),
    }
}
