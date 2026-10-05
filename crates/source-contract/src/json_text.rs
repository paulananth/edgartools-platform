//! Declared Python 3.12 text coercion for finite JSON values. No source loaders.
use crate::tree::{Child, El, ScalarKind};
use crate::Rejected;
use unicode_general_category::{get_general_category, GeneralCategory};

pub(crate) fn scalar(text: &str, kind: ScalarKind, exact: Option<&str>) -> Result<String, Rejected> {
    match kind {
        ScalarKind::Text => Ok(text.to_string()),
        ScalarKind::Boolean => Ok(if text == "true" { "True" } else { "False" }.into()),
        ScalarKind::Number => {
            let raw = exact.unwrap_or(text);
            if !raw.contains(['.', 'e', 'E']) {
                // Python loads integer JSON lexemes exactly; -0 becomes 0.
                return Ok(if raw == "-0" { "0" } else { raw }.into());
            }
            let value: f64 = raw.parse().map_err(|_| Rejected::new("invalid_value", "invalid JSON number"))?;
            python_float(value)
        }
    }
}

pub(crate) fn python_float(value: f64) -> Result<String, Rejected> {
    // serde_json's shortest representation uses round-to-even for halfway
    // decimal choices; Rust Debug rounds some halfway values differently.
    let number = serde_json::Number::from_f64(value)
        .ok_or_else(|| Rejected::new("invalid_value", "Python text requires a finite JSON float"))?;
    let rendered = number.to_string();
    let sign = if value.is_sign_negative() { "-" } else { "" };
    if value == 0.0 { return Ok(format!("{sign}0.0")); }
    let unsigned = rendered.trim_start_matches('-');
    let (mantissa, exponent) = unsigned.split_once('e').map_or((unsigned, 0), |(m, e)| (m, e.parse::<i32>().unwrap()));
    let before = mantissa.find('.').unwrap_or(mantissa.len()) as i32;
    let digits = mantissa.replace('.', "");
    let leading = digits.bytes().take_while(|b| *b == b'0').count();
    let magnitude = exponent + before - 1 - leading as i32;
    let digits = digits[leading..].trim_end_matches('0');
    if !(-4..16).contains(&magnitude) {
        let coefficient = if digits.len() == 1 { digits.into() } else { format!("{}.{}", &digits[..1], &digits[1..]) };
        return Ok(format!("{sign}{coefficient}e{magnitude:+03}"));
    }
    let point = magnitude + 1;
    let fixed = if point <= 0 {
        format!("0.{}{digits}", "0".repeat((-point) as usize))
    } else if point as usize >= digits.len() {
        format!("{digits}{}.0", "0".repeat(point as usize - digits.len()))
    } else { format!("{}.{}", &digits[..point as usize], &digits[point as usize..]) };
    Ok(format!("{sign}{fixed}"))
}

fn quoted(text: &str) -> String {
    // repr uses double quotes only to avoid escaping a single quote.
    let quote = if text.contains('\'') && !text.contains('"') { '"' } else { '\'' };
    let mut result = String::new();
    result.push(quote);
    for c in text.chars() {
        match c {
            '\\' => result.push_str("\\\\"),
            '\n' => result.push_str("\\n"),
            '\r' => result.push_str("\\r"),
            '\t' => result.push_str("\\t"),
            c if c == quote => { result.push('\\'); result.push(c); }
            c if c != ' ' && matches!(get_general_category(c),
                GeneralCategory::Control | GeneralCategory::Format | GeneralCategory::Surrogate |
                GeneralCategory::PrivateUse | GeneralCategory::Unassigned | GeneralCategory::SpaceSeparator |
                GeneralCategory::LineSeparator | GeneralCategory::ParagraphSeparator) => {
                let code = c as u32;
                if code <= 0xff { result.push_str(&format!("\\x{code:02x}")); }
                else if code <= 0xffff { result.push_str(&format!("\\u{code:04x}")); }
                else { result.push_str(&format!("\\U{code:08x}")); }
            }
            c => result.push(c),
        }
    }
    result.push(quote);
    result
}

pub(crate) fn list<'a>(rows: impl IntoIterator<Item = &'a El>) -> Result<String, Rejected> {
    let values = rows.into_iter().map(repr).collect::<Result<Vec<_>, _>>()?;
    Ok(format!("[{}]", values.join(", ")))
}

pub(crate) fn repr(el: &El) -> Result<String, Rejected> {
    if el.scalar {
        return match &el.text {
            None => Ok("None".into()),
            Some(text) if el.kind == ScalarKind::Text => Ok(quoted(text)),
            Some(text) => scalar(text, el.kind, el.exact_number.as_deref()),
        };
    }
    if el.array {
        return match el.children.get("item") {
            Some(Child::Many(rows)) => list(rows.iter()),
            _ => unreachable!("JSON arrays retain item lists"),
        };
    }
    let keys = el.json_keys.as_ref().ok_or_else(|| Rejected::new("invalid_path", "Python text coercion requires a JSON value"))?;
    let mut pairs = Vec::new();
    for key in keys {
        let value = if key == "$" && el.text.is_some() {
            quoted(el.text.as_deref().unwrap())
        } else if let Some(value) = el.attrs.get(key) {
            quoted(value)
        } else {
            match &el.children[key] {
                Child::One(child) => repr(child)?,
                Child::Many(rows) => list(rows.iter())?,
            }
        };
        pairs.push(format!("{}: {value}", quoted(key)));
    }
    Ok(format!("{{{}}}", pairs.join(", ")))
}

pub(crate) fn value(el: &El) -> Result<Option<String>, Rejected> {
    if el.scalar {
        el.text.as_ref().map(|text| scalar(text, el.kind, el.exact_number.as_deref())).transpose()
    } else { repr(el).map(Some) }
}
