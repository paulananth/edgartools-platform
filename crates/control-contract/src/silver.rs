//! Structural JSON equality for delivered values, preserving exact numbers.
use crate::Document;
use std::collections::BTreeMap;

pub fn canonicalize_numeric_json(raw: &str) -> Result<String, String> {
    let value: Document = serde_json::from_str(raw).map_err(|_| "Invalid Silver JSON")?;
    canonical(&value)
}

fn canonical(value: &Document) -> Result<String, String> {
    let raw = value.get();
    match raw.as_bytes().first() {
        Some(b'{') => {
            let object: BTreeMap<String, Document> =
                serde_json::from_str(raw).map_err(|_| "Invalid Silver object")?;
            let fields = object
                .into_iter()
                .map(|(k, v)| {
                    Ok(format!(
                        "{}:{}",
                        serde_json::to_string(&k).unwrap(),
                        canonical(&v)?
                    ))
                })
                .collect::<Result<Vec<_>, String>>()?;
            Ok(format!("{{{}}}", fields.join(",")))
        }
        Some(b'[') => {
            let items: Vec<Document> =
                serde_json::from_str(raw).map_err(|_| "Invalid Silver array")?;
            Ok(format!(
                "[{}]",
                items
                    .iter()
                    .map(canonical)
                    .collect::<Result<Vec<_>, _>>()?
                    .join(",")
            ))
        }
        Some(b'"') => {
            let text: String = serde_json::from_str(raw).map_err(|_| "Invalid Silver text")?;
            serde_json::to_string(&text).map_err(|_| "Invalid Silver text".into())
        }
        Some(b'-' | b'0'..=b'9') => number(raw),
        _ => Ok(raw.to_string()),
    }
}

fn number(raw: &str) -> Result<String, String> {
    let (negative, raw) = if let Some(rest) = raw.strip_prefix('-') {
        (true, rest)
    } else {
        (false, raw)
    };
    let (mantissa, exponent) = match raw.split_once(['e', 'E']) {
        Some((m, e)) => (
            m,
            e.parse::<i64>()
                .map_err(|_| "Invalid Silver numeric exponent")?,
        ),
        None => (raw, 0),
    };
    let fractional = mantissa.split_once('.').map(|(_, r)| r.len()).unwrap_or(0);
    let digits = mantissa.replace('.', "");
    let digits = digits.trim_start_matches('0');
    if digits.is_empty() {
        return Ok("0".into());
    }
    let trailing = digits.len() - digits.trim_end_matches('0').len();
    let digits = digits.trim_end_matches('0');
    let power = exponent
        .checked_sub(fractional as i64)
        .and_then(|n| n.checked_add(trailing as i64))
        .ok_or("Invalid Silver numeric exponent")?;
    let sign = if negative { "-" } else { "" };
    // Keep exponents compact: canonicalization must not allocate a buffer
    // proportional to a numeric exponent from an input document.
    if power == 0 {
        Ok(format!("{}{}", sign, digits))
    } else {
        Ok(format!("{}{}e{}", sign, digits, power))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn numeric_equality_preserves_large_integers_and_small_values() {
        assert_eq!(
            canonicalize_numeric_json(r#"{"z":-0.0,"x":1.0,"y":1e60}"#).unwrap(),
            r#"{"x":1,"y":1e60,"z":0}"#
        );
        assert_eq!(
            canonicalize_numeric_json("[1.2500,0.001e-2,-123e-1]").unwrap(),
            "[125e-2,1e-5,-123e-1]"
        );
    }
}
