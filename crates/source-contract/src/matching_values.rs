//! Shared name and place comparisons used by configured record-matching rules.

use crate::record_values::{self as values, Object};
use regex::Regex;
use std::sync::LazyLock;
use unicode_general_category::{get_general_category, GeneralCategory};
use unicode_normalization::{char::canonical_combining_class, UnicodeNormalization};

static NAME_TAG: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"[\s\x1c-\x1f]*/[A-Z0-9 .]{1,6}/?[\s\x1c-\x1f]*$").unwrap());
static NAME_PARTS: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"[^A-Z0-9]+").unwrap());
static SPACES: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"[\s\x1c-\x1f]+").unwrap());
static CONFORMED_PUNCTUATION: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r#"[.,;:/()'"\-]"#).unwrap());

pub(crate) const TERRITORIES: &[&str] = &["PR", "GU", "VI", "MP", "AS"];
const FORMS: &[(&str, &str)] = &[
    ("L L C", "LLC"),
    ("L L P", "LLP"),
    ("L P", "LP"),
    ("P L C", "PLC"),
    ("N V", "NV"),
    ("S A", "SA"),
    ("A G", "AG"),
    ("S E", "SE"),
    ("B V", "BV"),
    ("CORPORATION", "CORP"),
    ("INCORPORATED", "INC"),
    ("COMPANY", "CO"),
    ("LIMITED", "LTD"),
    ("HOLDINGS", "HLDGS"),
    ("INTERNATIONAL", "INTL"),
];

/// The approved matching versions use Python 3.12's pinned Unicode 15 mapping.
pub(crate) fn prepare_uppercase(text: &str) -> String {
    let mut result = String::with_capacity(text.len());
    for ch in text.chars() {
        let mapped = ch.to_uppercase();
        if get_general_category(ch) == GeneralCategory::Unassigned
            || mapped
                .clone()
                .any(|mapped| get_general_category(mapped) == GeneralCategory::Unassigned)
        {
            result.push(ch);
        } else {
            result.extend(mapped);
        }
    }
    result
}

pub(crate) fn prepare_name(text: &str, remove_tag: bool) -> String {
    let text = if remove_tag {
        NAME_TAG.replace(&prepare_uppercase(text), "").into_owned()
    } else {
        text.into()
    };
    let decomposed: String = text
        .nfkd()
        .filter(|ch| canonical_combining_class(*ch) == 0)
        .collect::<String>();
    let text = prepare_uppercase(&decomposed).replace('&', " AND ");
    let mut text = format!(" {} ", NAME_PARTS.replace_all(&text, " ").trim());
    for (long, short) in FORMS {
        text = text.replace(&format!(" {long} "), &format!(" {short} "));
    }
    text.trim()
        .strip_prefix("THE ")
        .unwrap_or(text.trim())
        .into()
}

pub(crate) fn prepare_conformed_name(text: &str) -> String {
    let text = prepare_uppercase(text).replace('&', " AND ");
    SPACES
        .replace_all(&CONFORMED_PUNCTUATION.replace_all(&text, " "), " ")
        .trim()
        .into()
}

pub(crate) fn places_agree(left: Option<&str>, right: Option<&str>) -> bool {
    let (Some(left), Some(right)) = (
        left.filter(|s| !s.is_empty()),
        right.filter(|s| !s.is_empty()),
    ) else {
        return false;
    };
    let left = prepare_uppercase(left);
    let right = prepare_uppercase(right);
    if left == right {
        return true;
    }
    if left
        .strip_prefix("US-")
        .is_some_and(|suffix| TERRITORIES.contains(&suffix))
    {
        return right == left[3..];
    }
    let country = left.split('-').next().unwrap_or("");
    country != "US"
        && country == right.split('-').next().unwrap_or("")
        && (!left.contains('-') || !right.contains('-'))
}

pub(crate) fn places_conflict(
    left: Option<&str>,
    right: Option<&str>,
    business_country: Option<&str>,
) -> bool {
    let (Some(left), Some(right)) = (
        left.filter(|s| !s.is_empty()),
        right.filter(|s| !s.is_empty()),
    ) else {
        return false;
    };
    let left = prepare_uppercase(left);
    let right = prepare_uppercase(right);
    if places_agree(Some(&left), Some(&right)) {
        return false;
    }
    let left_country = left.split('-').next().unwrap_or("");
    let right_country = right.split('-').next().unwrap_or("");
    if left_country == right_country && (!left.contains('-') || !right.contains('-')) {
        return false;
    }
    !(left_country == "US"
        && business_country.is_some_and(|country| country != "US" && country == right_country))
}

fn prepare_postal_code(text: &str) -> String {
    let text: String = prepare_uppercase(text)
        .chars()
        .filter(char::is_ascii_alphanumeric)
        .collect();
    if [5, 9].contains(&text.len()) && text.bytes().all(|ch| ch.is_ascii_digit()) {
        text[..5].into()
    } else {
        text
    }
}

pub(crate) fn postal_codes_agree(
    left: &str,
    left_country: Option<&str>,
    right: &str,
    right_country: Option<&str>,
) -> bool {
    let left = prepare_postal_code(left);
    let right = prepare_postal_code(right);
    if left.is_empty()
        || right.is_empty()
        || left_country.is_none_or(|s| s.is_empty())
        || left_country != right_country
    {
        return false;
    }
    left == right
        || (left_country == Some("NL")
            && left.len() == 4
            && left.bytes().all(|ch| ch.is_ascii_digit())
            && right.len() == 6
            && right.starts_with(&left)
            && right[4..].bytes().all(|ch| ch.is_ascii_uppercase()))
}

fn read_text(body: &Object, name: &str) -> Result<String, String> {
    let raw = values::read_optional_value(body, name)?;
    Ok(match raw.get() {
        "null" => String::new(),
        "true" => "True".into(),
        "false" => "False".into(),
        _ if raw.get().starts_with('"') => values::read_value(&raw)?,
        other => other.into(),
    })
}

fn read_optional_text(body: &Object, name: &str) -> Result<Option<String>, String> {
    body.get(name)
        .map(|raw| values::read_value(raw))
        .transpose()
        .map(Option::flatten)
}

pub fn compare_matching_values(raw: &str) -> Result<String, String> {
    let command: Object = serde_json::from_str(raw).map_err(|_| "Invalid matching values")?;
    let result = match values::read_text(&command, "action")?.as_str() {
        "prepare_name" => values::write_value(&prepare_name(
            &read_text(&command, "value")?,
            values::has_value(&command, "remove_tag"),
        ))?,
        "prepare_conformed_name" => {
            values::write_value(&prepare_conformed_name(&read_text(&command, "value")?))?
        }
        "compare_places" => values::write_value(&places_agree(
            read_optional_text(&command, "left")?.as_deref(),
            read_optional_text(&command, "right")?.as_deref(),
        ))?,
        "find_place_conflict" => values::write_value(&places_conflict(
            read_optional_text(&command, "left")?.as_deref(),
            read_optional_text(&command, "right")?.as_deref(),
            read_optional_text(&command, "business_country")?.as_deref(),
        ))?,
        "compare_postal_codes" => values::write_value(&postal_codes_agree(
            &read_text(&command, "left")?,
            read_optional_text(&command, "left_country")?.as_deref(),
            &read_text(&command, "right")?,
            read_optional_text(&command, "right_country")?.as_deref(),
        ))?,
        "prepare_reference_key" => values::write_value(&prepare_uppercase(
            read_text(&command, "value")?.trim_matches(crate::text_transform::whitespace),
        ))?,
        _ => return Err("Unsupported matching comparison".into()),
    };
    Ok(result.get().into())
}
