//! Exact JSON values shared by mastering calculations. No storage or source policy.

use chrono::{DateTime, FixedOffset};
use indexmap::IndexMap;
use serde::{de::DeserializeOwned, Serialize};
use serde_json::value::{to_raw_value, RawValue};
use sha2::{Digest, Sha256};

pub(crate) type Document = Box<RawValue>;
pub(crate) type Object = IndexMap<String, Document>;

pub(crate) fn read_time(raw: &str) -> Result<DateTime<FixedOffset>, String> {
    DateTime::parse_from_rfc3339(raw)
        .or_else(|_| DateTime::parse_from_str(raw, "%Y-%m-%d %H:%M:%S%.f%#z"))
        .or_else(|_| DateTime::parse_from_str(raw, "%Y-%m-%dT%H:%M:%S%.f%#z"))
        .or_else(|_| DateTime::parse_from_str(raw, "%Y%m%dT%H%M%S%.f%#z"))
        .map_err(|_| "Effective time must include a timezone".into())
}

pub(crate) fn read_value<T: DeserializeOwned>(raw: &RawValue) -> Result<T, String> {
    serde_json::from_str(raw.get()).map_err(|_| "Invalid record value".into())
}

pub(crate) fn write_value(value: &impl Serialize) -> Result<Document, String> {
    to_raw_value(value).map_err(|_| "Record value cannot be serialized".into())
}

pub(crate) fn read_object(body: &Object, key: &str) -> Result<Object, String> {
    body.get(key)
        .map(|raw| read_value(raw))
        .transpose()
        .map(|value| value.unwrap_or_default())
}

pub(crate) fn read_array(body: &Object, key: &str) -> Result<Vec<Document>, String> {
    body.get(key)
        .map(|raw| read_value(raw))
        .transpose()
        .map(|value| value.unwrap_or_default())
}

pub(crate) fn read_text(body: &Object, key: &str) -> Result<String, String> {
    read_value(
        body.get(key)
            .ok_or_else(|| format!("Missing record field: {key}"))?,
    )
}

pub(crate) fn read_optional_value(body: &Object, key: &str) -> Result<Document, String> {
    body.get(key).cloned().map_or_else(|| write_value(&()), Ok)
}

pub(crate) fn has_content(raw: &RawValue) -> bool {
    match raw.get().as_bytes().first() {
        Some(b'n') | Some(b'f') => false,
        Some(b'"') => read_value::<String>(raw).is_ok_and(|value| !value.is_empty()),
        Some(b'[') => read_value::<Vec<Document>>(raw).is_ok_and(|value| !value.is_empty()),
        Some(b'{') => read_value::<Object>(raw).is_ok_and(|value| !value.is_empty()),
        Some(b't') => true,
        _ => raw.get().parse::<f64>().is_ok_and(|value| value != 0.0),
    }
}

pub(crate) fn has_value(body: &Object, key: &str) -> bool {
    body.get(key).is_some_and(|raw| has_content(raw))
}

/// Canonical JSON keeps number lexemes supplied by the transport, sorting object keys only.
pub(crate) fn write_sorted_json(raw: &RawValue) -> Result<String, String> {
    match raw.get().as_bytes().first() {
        Some(b'{') => {
            let values: Object = read_value(raw)?;
            let sorted: std::collections::BTreeMap<_, _> = values.into_iter().collect();
            let mut output = Vec::new();
            for (key, value) in sorted {
                output.push(format!(
                    "{}:{}",
                    write_value(&key)?.get(),
                    write_sorted_json(&value)?
                ));
            }
            Ok(format!("{{{}}}", output.join(",")))
        }
        Some(b'[') => {
            let values: Vec<Document> = read_value(raw)?;
            let parts = values
                .iter()
                .map(|value| write_sorted_json(value))
                .collect::<Result<Vec<_>, _>>()?;
            Ok(format!("[{}]", parts.join(",")))
        }
        Some(b'"') => Ok(write_value(&read_value::<String>(raw)?)?.get().into()),
        _ => Ok(raw.get().into()),
    }
}

pub(crate) fn calculate_content_hash(raw: &RawValue) -> Result<String, String> {
    Ok(format!(
        "{:x}",
        Sha256::digest(write_sorted_json(raw)?.as_bytes())
    ))
}

fn read_number_text(raw: &str) -> Option<&str> {
    match raw {
        "true" => Some("1"),
        "false" => Some("0"),
        _ if raw.starts_with('-') || raw.as_bytes().first().is_some_and(u8::is_ascii_digit) => {
            Some(raw)
        }
        _ => None,
    }
}

/// Preserve Python's value comparison for overrides, including exact integer/float comparison.
pub(crate) fn values_match(left: &RawValue, right: &RawValue) -> Result<bool, String> {
    if let (Some(a), Some(b)) = (read_number_text(left.get()), read_number_text(right.get())) {
        let ai = !a.contains(['.', 'e', 'E']);
        let bi = !b.contains(['.', 'e', 'E']);
        return Ok(match (ai, bi) {
            (true, true) => a == b,
            (false, false) => a.parse::<f64>().ok() == b.parse::<f64>().ok(),
            _ => {
                let (integer, floating) = if ai { (a, b) } else { (b, a) };
                let value = floating
                    .parse::<f64>()
                    .map_err(|_| "Invalid numeric value")?;
                value.is_finite()
                    && value.fract() == 0.0
                    && integer
                        == if value == 0.0 {
                            "0".into()
                        } else {
                            format!("{value:.0}")
                        }
            }
        });
    }
    match (
        left.get().as_bytes().first(),
        right.get().as_bytes().first(),
    ) {
        (Some(b'{'), Some(b'{')) => {
            let a: Object = read_value(left)?;
            let b: Object = read_value(right)?;
            if a.len() != b.len() {
                return Ok(false);
            }
            for (key, value) in a {
                let Some(other) = b.get(&key) else {
                    return Ok(false);
                };
                if !values_match(&value, other)? {
                    return Ok(false);
                }
            }
            Ok(true)
        }
        (Some(b'['), Some(b'[')) => {
            let a: Vec<Document> = read_value(left)?;
            let b: Vec<Document> = read_value(right)?;
            if a.len() != b.len() {
                return Ok(false);
            }
            for (value, other) in a.iter().zip(&b) {
                if !values_match(value, other)? {
                    return Ok(false);
                }
            }
            Ok(true)
        }
        (Some(b'"'), Some(b'"')) => Ok(read_value::<String>(left)? == read_value::<String>(right)?),
        _ => Ok(left.get() == right.get()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn raw(value: &str) -> Document {
        RawValue::from_string(value.into()).unwrap()
    }

    #[test]
    fn comparing_override_values_keeps_exact_numeric_meaning() {
        assert!(values_match(&raw("1"), &raw("1.0")).unwrap());
        assert!(values_match(&raw("true"), &raw("1")).unwrap());
        assert!(values_match(&raw("false"), &raw("-0.0")).unwrap());
        assert!(!values_match(&raw("9007199254740993"), &raw("9007199254740992.0")).unwrap());
        assert!(values_match(&raw(r#"{"x":[1,true]}"#), &raw(r#"{"x":[1.0,1]}"#)).unwrap());
    }

    #[test]
    fn writing_sorted_json_preserves_the_number_representation_for_hashes() {
        assert_eq!(
            write_sorted_json(&raw(
                r#"{"z":1.0,"a":9999999999999999999999999999999999999999}"#
            ))
            .unwrap(),
            r#"{"a":9999999999999999999999999999999999999999,"z":1.0}"#
        );
        assert_ne!(
            write_sorted_json(&raw("1")).unwrap(),
            write_sorted_json(&raw("1.0")).unwrap()
        );
    }
}
