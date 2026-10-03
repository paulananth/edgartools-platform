//! Exact integer and integer-derived boolean conversion, with declared policies.
use serde_yaml::Value;
use unicode_general_category::{get_general_category, GeneralCategory};
use crate::{Rejected, Val};
use crate::tree::ScalarKind;

fn boolean(args: &Value) -> bool { args.get("as").and_then(Value::as_str) == Some("boolean") }

pub fn validate(args: &Value) -> Result<(), String> {
    let map = args.as_mapping().ok_or("integer arguments must be a mapping")?;
    for key in map.keys() {
        if !matches!(key.as_str(), Some("path" | "from" | "as" | "default" | "on_invalid" | "on_overflow")) {
            return Err("unknown integer argument".into());
        }
    }
    if args.get("as").is_some_and(|v| !matches!(v.as_str(), Some("integer" | "boolean"))) {
        return Err("integer as must be integer or boolean".into());
    }
    if args.get("from").is_some_and(|v| !matches!(v.as_str(), Some("document" | "record"))) {
        return Err("integer from must be document or record".into());
    }
    for name in ["on_invalid", "on_overflow"] {
        if let Some(policy) = args.get(name) {
            if !(policy.is_null() || matches!(policy.as_str(), Some("error" | "null" | "default"))) {
                return Err(format!("integer {name} must be error, null or default"));
            }
        }
    }
    if boolean(args) && args.get("on_overflow").is_some() {
        return Err("integer as boolean has no signed integer output to overflow".into());
    }
    if let Some(value) = args.get("default") {
        if !value.is_null() && (if boolean(args) { value.as_bool().is_none() } else { value.as_i64().is_none() }) {
            return Err("integer default must match its declared output type".into());
        }
    }
    Ok(())
}

pub fn default(args: &Value) -> Val {
    if boolean(args) {
        args.get("default").and_then(Value::as_bool).map_or(Val::Null, Val::Bool)
    } else {
        args.get("default").and_then(Value::as_i64).map_or(Val::Null, Val::Int)
    }
}

fn failure(args: &Value, name: &str, code: &str) -> Result<Val, Rejected> {
    match args.get(name) {
        Some(value) if value.is_null() || value.as_str() == Some("null") => Ok(Val::Null),
        Some(value) if value.as_str() == Some("default") => Ok(default(args)),
        _ => Err(Rejected::new(code, "integer conversion failed")),
    }
}

pub fn invalid(args: &Value) -> Result<Val, Rejected> { failure(args, "on_invalid", "invalid_value") }

/// Unicode decimal digits occur in consecutive blocks of ten; adjacent sets
/// (the mathematical styles) retain that periodic value. The pinned Unicode
/// table supplies category membership rather than accepting other numerals.
fn digit(c: char) -> Option<u32> {
    if c.is_ascii_digit() { return c.to_digit(10) }
    if get_general_category(c) != GeneralCategory::DecimalNumber { return None }
    let mut start = c as u32;
    while start > 0 && char::from_u32(start - 1).is_some_and(|previous|
        get_general_category(previous) == GeneralCategory::DecimalNumber) {
        start -= 1;
    }
    Some((c as u32 - start) % 10)
}

fn decimal(text: &str) -> Option<String> {
    let text = text.trim();
    let mut out = String::new();
    let mut digits = 0;
    let mut previous_digit = false;
    for (index, c) in text.chars().enumerate() {
        if index == 0 && matches!(c, '+' | '-') {
            out.push(c);
        } else if let Some(n) = digit(c) {
            out.push(char::from_digit(n, 10).unwrap());
            previous_digit = true;
            digits += 1;
        } else if c == '_' && previous_digit {
            previous_digit = false;
        } else { return None }
    }
    // Python 3.12's default decimal conversion budget. Count decimal digits,
    // not underscores or the sign; artifacts also retain their byte limit.
    (previous_digit && digits <= 4300).then_some(out)
}

pub fn read(text: &str, kind: ScalarKind, args: &Value) -> Result<Val, Rejected> {
    if kind == ScalarKind::Boolean {
        let n = i64::from(text == "true");
        return Ok(if boolean(args) { Val::Bool(n != 0) } else { Val::Int(n) })
    }
    if kind == ScalarKind::Number && text.contains(['.', 'e', 'E']) {
        let Ok(value) = text.parse::<f64>() else { return invalid(args) };
        if !value.is_finite() { return invalid(args) }
        let value = value.trunc();
        if boolean(args) { return Ok(Val::Bool(value != 0.0)) }
        // The positive bound is exclusive: i64::MAX rounds to 2^63 as f64.
        if !(-9223372036854775808.0..9223372036854775808.0).contains(&value) {
            return failure(args, "on_overflow", "integer_overflow")
        }
        return Ok(Val::Int(value as i64))
    }
    let Some(normalized) = decimal(text) else { return invalid(args) };
    if boolean(args) {
        return Ok(Val::Bool(normalized.chars().any(|c| c.is_ascii_digit() && c != '0')))
    }
    match normalized.parse::<i64>() {
        Ok(value) => Ok(Val::Int(value)),
        Err(_) => failure(args, "on_overflow", "integer_overflow"),
    }
}
