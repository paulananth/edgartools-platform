//! PostgreSQL 16 JSONB text bytes, for existing database hash protocols.
//! This is deliberately separate from compact Python JSON. Raw numeric tokens
//! retain decimal scale and arbitrary precision; object keys use byte length
//! then UTF-8 order. No Python object/numeric round trip enters the protocol.

use serde::de::{MapAccess, Visitor};
use serde::{Deserialize, Deserializer};
use serde_json::value::RawValue;
use std::collections::HashMap;
use std::fmt;

const MAX_BYTES: usize = 64 * 1024 * 1024;

struct Pairs<'a>(Vec<(String, &'a RawValue)>);

impl<'de> Deserialize<'de> for Pairs<'de> {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        struct PairVisitor;
        impl<'de> Visitor<'de> for PairVisitor {
            type Value = Pairs<'de>;
            fn expecting(&self, f: &mut fmt::Formatter) -> fmt::Result {
                f.write_str("a JSON object")
            }
            fn visit_map<M: MapAccess<'de>>(self, mut map: M) -> Result<Self::Value, M::Error> {
                let mut pairs = Vec::new();
                while let Some(pair) = map.next_entry()? {
                    pairs.push(pair);
                }
                Ok(Pairs(pairs))
            }
        }
        deserializer.deserialize_map(PairVisitor)
    }
}

fn parse<'a, T: Deserialize<'a>>(raw: &'a str) -> Result<T, String> {
    serde_json::from_str(raw).map_err(|e| e.to_string())
}

fn quote(text: &str) -> Result<String, String> {
    if text.contains('\0') {
        return Err("PostgreSQL JSONB refuses U+0000".into());
    }
    serde_json::to_string(text).map_err(|e| e.to_string())
}

fn numeric(raw: &str) -> Result<String, String> {
    let (negative, raw) = raw.strip_prefix('-').map_or((false, raw), |s| (true, s));
    let (mantissa, exponent) = match raw.split_once(['e', 'E']) {
        Some((m, e)) => (
            m,
            e.parse::<i64>()
                .map_err(|_| "Numeric exponent out of range")?,
        ),
        None => (raw, 0),
    };
    let (whole, fraction) = mantissa.split_once('.').unwrap_or((mantissa, ""));
    if !(-1073741823..=1073741823).contains(&exponent) {
        return Err("PostgreSQL numeric exponent out of range".into());
    }
    let digits = format!("{whole}{fraction}");
    let scale = (fraction.len() as i64)
        .checked_sub(exponent)
        .ok_or("Numeric scale out of range")?
        .max(0);
    if scale > 16383 {
        return Err("PostgreSQL numeric scale out of range".into());
    }
    let point = (whole.len() as i64)
        .checked_add(exponent)
        .ok_or("Numeric weight out of range")?;
    let significant = digits.bytes().position(|b| b != b'0');
    let weight = significant.map_or(0, |i| point.saturating_sub(i as i64));
    if weight > 131072 {
        return Err("PostgreSQL numeric weight out of range".into());
    }
    // Zero retains scale but never its sign or an exponent's integer padding.
    let mut result = if significant.is_none() {
        "0".to_owned()
    } else if point <= 0 {
        "0".to_owned()
    } else if point as usize >= digits.len() {
        let mut text = digits.clone();
        text.extend(std::iter::repeat_n('0', point as usize - digits.len()));
        text.trim_start_matches('0').to_owned()
    } else {
        digits[..point as usize].trim_start_matches('0').to_owned()
    };
    if result.is_empty() {
        result.push('0');
    }
    if scale > 0 {
        result.push('.');
        if significant.is_none() {
            result.extend(std::iter::repeat_n('0', scale as usize));
        } else if point <= 0 {
            result.extend(std::iter::repeat_n('0', (-point) as usize));
            result.push_str(&digits);
        } else {
            result.push_str(&digits[point as usize..]);
        }
    }
    if negative && significant.is_some() {
        result.insert(0, '-');
    }
    Ok(result)
}

// Validate all values, including overwritten duplicate properties. PostgreSQL
// refuses invalid numeric/string values even when a later property wins.
fn validate(root: &RawValue) -> Result<(), String> {
    let mut pending = vec![root];
    while let Some(value) = pending.pop() {
        let raw = value.get();
        match raw.as_bytes()[0] {
            b'{' => {
                for (key, value) in parse::<Pairs>(raw)?.0 {
                    quote(&key)?;
                    pending.push(value);
                }
            }
            b'[' => pending.extend(parse::<Vec<&RawValue>>(raw)?),
            b'"' => {
                quote(&parse::<String>(raw)?)?;
            }
            b'n' | b't' | b'f' => (),
            _ => {
                numeric(raw)?;
            }
        }
    }
    Ok(())
}

pub fn text(raw: &str) -> Result<String, String> {
    if raw.len() > MAX_BYTES {
        return Err("JSONB input exceeds 64 MiB".into());
    }
    let root: &RawValue = parse(raw)?;
    validate(root)?;
    // Iteration, not recursive Rust calls: valid deeply nested database inputs
    // do not consume native call stack or acquire a new depth restriction.
    enum Part<'a> {
        Value(&'a RawValue),
        Text(String),
    }
    let mut pending = vec![Part::Value(root)];
    let mut output = String::with_capacity(raw.len());
    while let Some(part) = pending.pop() {
        match part {
            Part::Text(text) => output.push_str(&text),
            Part::Value(value) => {
                let raw = value.get();
                match raw.as_bytes()[0] {
                    b'{' => {
                        let fields: HashMap<String, &RawValue> =
                            parse::<Pairs>(raw)?.0.into_iter().collect();
                        let mut fields: Vec<_> = fields.into_iter().collect();
                        fields.sort_unstable_by(|(a, _), (b, _)| {
                            a.len().cmp(&b.len()).then(a.cmp(b))
                        });
                        pending.push(Part::Text("}".into()));
                        for (i, (key, value)) in fields.iter().enumerate().rev() {
                            pending.push(Part::Value(value));
                            pending.push(Part::Text(format!("{}: ", quote(key)?)));
                            if i > 0 {
                                pending.push(Part::Text(", ".into()));
                            }
                        }
                        output.push('{');
                    }
                    b'[' => {
                        let values: Vec<&RawValue> = parse(raw)?;
                        pending.push(Part::Text("]".into()));
                        for (i, value) in values.into_iter().enumerate().rev() {
                            pending.push(Part::Value(value));
                            if i > 0 {
                                pending.push(Part::Text(", ".into()));
                            }
                        }
                        output.push('[');
                    }
                    b'"' => output.push_str(&quote(&parse::<String>(raw)?)?),
                    b'n' | b't' | b'f' => output.push_str(raw),
                    _ => output.push_str(&numeric(raw)?),
                }
            }
        }
        if output.len() > MAX_BYTES {
            return Err("JSONB output exceeds 64 MiB".into());
        }
    }
    Ok(output)
}

pub fn object(fields: HashMap<String, String>, canonical_inputs: bool) -> Result<String, String> {
    // Authenticated database text is already canonical. Reusing it avoids
    // reparsing every large immutable subtree merely to shape an envelope.
    // The caller MUST verify the final bytes against the committed hash.
    if canonical_inputs {
        let mut fields: Vec<_> = fields.into_iter().collect();
        fields.sort_unstable_by(|(a, _), (b, _)| a.len().cmp(&b.len()).then(a.cmp(b)));
        // Serialized JSONB may exceed the compact request's byte size (notably
        // exponent-form numbers). Preserve the existing publication domain:
        // derive the exact output budget from authenticated stored parts, rather
        // than imposing the general formatter's new 64 MiB limit on old intent.
        let mut quoted = Vec::with_capacity(fields.len());
        let mut budget = 2usize;
        for (key, value) in fields {
            let key = quote(&key)?;
            budget = budget
                .checked_add(key.len())
                .and_then(|n| n.checked_add(value.len()))
                .and_then(|n| n.checked_add(4))
                .ok_or("JSONB output size overflow")?;
            quoted.push((key, value));
        }
        let mut output = String::new();
        output
            .try_reserve(budget)
            .map_err(|_| "JSONB output allocation failed")?;
        output.push('{');
        for (i, (key, value)) in quoted.into_iter().enumerate() {
            let value: &RawValue = parse(&value)?;
            if i > 0 {
                output.push_str(", ");
            }
            output.push_str(&key);
            output.push_str(": ");
            output.push_str(value.get());
        }
        output.push('}');
        debug_assert!(output.len() <= budget);
        return Ok(output);
    }
    let mut raw = String::from("{");
    for (i, (key, value)) in fields.into_iter().enumerate() {
        // A part is exactly one JSON value, never an object-fragment injection.
        let value: &RawValue = parse(&value)?;
        if i > 0 {
            raw.push(',');
        }
        raw.push_str(&quote(&key)?);
        raw.push(':');
        raw.push_str(value.get());
        if raw.len() > MAX_BYTES {
            return Err("JSONB input exceeds 64 MiB".into());
        }
    }
    raw.push('}');
    text(&raw)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn postgres_numeric_spelling() {
        assert_eq!(
            text("[1e-7,1.2300,-0.00,1e3,1.2e-2]").unwrap(),
            "[0.0000001, 1.2300, 0.00, 1000, 0.012]"
        );
    }
    #[test]
    fn overwritten_invalid_values_fail() {
        assert!(text(r#"{"x": "\u0000", "x": 1}"#).is_err());
        assert!(text(r#"{"x": 1e-16384, "x": 1}"#).is_err());
    }
    #[test]
    fn deep_values_need_no_call_stack() {
        let raw = format!("{}0{}", "[".repeat(1024), "]".repeat(1024));
        assert_eq!(text(&raw).unwrap(), raw);
    }
}
