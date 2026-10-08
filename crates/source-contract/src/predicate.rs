//! JSON shape/truth tests without materializing or coercing the selected value.
use serde_yaml::Value;
use crate::{check_path, lookup_shape, setting, Found, Rejected, Val};
use crate::tree::{El, ScalarKind};

pub(crate) fn validate(args: &Value) -> Result<(), String> {
    let args = args.as_mapping().ok_or("test arguments must be a mapping")?;
    if args.len() < 2 || args.keys().any(|k| !matches!(k.as_str(), Some("path" | "kind" | "from"))) {
        return Err("test requires path and kind, with optional from".into());
    }
    let args = Value::Mapping(args.clone());
    check_path(setting(&args, "path").ok_or("test names no path")?)?;
    if !matches!(setting(&args, "kind"), Some("truthy" | "null" | "not_null" | "missing" | "array" | "object" | "text")) {
        return Err("test kind is truthy, null, not_null, missing, array, object or text".into());
    }
    if args.get("from").is_some_and(|v| !matches!(v.as_str(), Some("document" | "item"))) {
        return Err("test from is document or item".into());
    }
    Ok(())
}

fn scalar_truth(text: &str, kind: ScalarKind, exact: Option<&str>) -> bool {
    match kind {
        ScalarKind::Text => !text.is_empty(),
        ScalarKind::Boolean => text == "true",
        ScalarKind::Number => {
            let raw = exact.unwrap_or(text);
            if raw.contains(['.', 'e', 'E']) { raw.parse::<f64>().is_ok_and(|v| v != 0.0) }
            else { raw.bytes().any(|c| matches!(c, b'1'..=b'9')) }
        }
    }
}

pub(crate) fn read(start: &El, args: &Value) -> Result<Val, Rejected> {
    let found = lookup_shape(start, setting(args, "path").unwrap())?;
    let result = match setting(args, "kind").unwrap() {
        "null" => matches!(found, Found::Missing) || matches!(found, Found::El(el) if el.scalar && el.text.is_none()),
        "not_null" => !matches!(found, Found::Missing) && !matches!(found, Found::El(el) if el.scalar && el.text.is_none()),
        "missing" => matches!(found, Found::Missing),
        "text" => matches!(found, Found::Text(_, ScalarKind::Text, _)) || matches!(found, Found::El(el) if el.scalar && el.kind == ScalarKind::Text && el.text.is_some()),
        "array" => matches!(found, Found::List(_)) || matches!(found, Found::El(el) if el.array),
        "object" => matches!(found, Found::El(el) if !el.scalar && !el.array),
        "truthy" => match found {
            Found::Missing => false,
            Found::Text(text, kind, exact) => scalar_truth(&text, kind, exact),
            Found::List(rows) => !rows.is_empty(),
            Found::El(el) if el.scalar => el.text.as_deref().is_some_and(|t| scalar_truth(t, el.kind, el.exact_number.as_deref())),
            Found::El(el) => !el.children.is_empty() && (!el.array || el.children.get("item").is_some_and(|c| matches!(c, crate::tree::Child::Many(rows) if !rows.is_empty())))
                || !el.attrs.is_empty() || el.text.is_some(),
        },
        _ => unreachable!(),
    };
    Ok(Val::Bool(result))
}
