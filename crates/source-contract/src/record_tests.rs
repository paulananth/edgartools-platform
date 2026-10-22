//! Versioned record tests and ordered classification, shared by matching callers.

use crate::matching_values;
use crate::record_values::{self as values, Document, Object};
use indexmap::IndexMap;
use regex::Regex;
use serde::Deserialize;
use std::collections::BTreeSet;
use std::sync::LazyLock;

static SPACES: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"[\s\x1c-\x1f]+").unwrap());
use unicode_general_category::{get_general_category, GeneralCategory};

pub(crate) fn read_path(record: &Object, path: &str) -> Result<Document, String> {
    let mut parts = path.split('.');
    let mut current = values::read_optional_value(record, parts.next().unwrap_or(""))?;
    for part in parts {
        let Ok(object) = values::read_value::<Object>(&current) else {
            return values::write_value(&());
        };
        current = values::read_optional_value(&object, part)?;
    }
    Ok(current)
}

pub(crate) fn display_text(raw: &Document) -> Result<String, String> {
    Ok(match raw.get() {
        "null" => String::new(),
        "true" => "True".into(),
        "false" => "False".into(),
        _ if raw.get().starts_with('"') => values::read_value(raw)?,
        text => text.into(),
    })
}

pub(crate) fn prepare_identifier(text: &str, upper: bool) -> String {
    if upper {
        matching_values::prepare_uppercase(text.trim_matches(crate::text_transform::whitespace))
    } else {
        text.trim_matches(crate::text_transform::whitespace).into()
    }
}

pub(crate) fn normalize_value(
    name: &str,
    raw: &Document,
    doc: &Object,
    declared: &IndexMap<String, bool>,
) -> Result<String, String> {
    let aliases = values::read_object(doc, "normalizers")?;
    let resolved = aliases
        .get(name)
        .map(|raw| values::read_value::<String>(raw))
        .transpose()?
        .unwrap_or_else(|| name.into());
    let text = display_text(raw)?;
    if let Some(upper) = declared.get(&resolved) {
        return Ok(prepare_identifier(&text, *upper));
    }
    match resolved.as_str() {
        "normalize_text@edgar-conformed-v1" => Ok(matching_values::prepare_conformed_name(&text)),
        "normalize_text@legal-form-kept-v1" => Ok(matching_values::prepare_name(&text, false)),
        "normalize_text@sec-legal-form-kept-v1" => Ok(matching_values::prepare_name(&text, true)),
        "normalize_identifier@sec-cik-v1" | "normalize_identifier@crd-v1" => {
            let text: String = text
                .chars()
                .filter(|ch| get_general_category(*ch) == GeneralCategory::DecimalNumber)
                .collect();
            Ok(if resolved == "normalize_identifier@sec-cik-v1" {
                text.trim_start_matches('0').into()
            } else {
                text
            })
        }
        "normalize_identifier@lei-v1" => Ok(matching_values::prepare_uppercase(&text)
            .chars()
            .filter(char::is_ascii_alphanumeric)
            .collect()),
        _ => Err(format!("Policy names an unknown normalizer: {name}")),
    }
}

fn named_values(doc: &Object, raw: &Document, what: &str) -> Result<Vec<Document>, String> {
    if raw.get().starts_with('[') {
        return values::read_value(raw);
    }
    let name = display_text(raw)?;
    let lists = values::read_object(doc, "lists")?;
    values::read_value(
        lists
            .get(&name)
            .ok_or_else(|| format!("Policy names an undeclared {what}: {name}"))?,
    )
}

fn within_counts(name: &str, args: &Object, count: usize) -> Result<bool, String> {
    let lower = args
        .get("min_count")
        .filter(|raw| raw.get() != "null")
        .map(|raw| values::read_value::<f64>(raw))
        .transpose()?;
    let upper = args
        .get("max_count")
        .filter(|raw| raw.get() != "null")
        .map(|raw| values::read_value::<f64>(raw))
        .transpose()?;
    if lower.is_none() && upper.is_none() {
        return Err(format!("{name} requires min_count or max_count"));
    }
    Ok(lower.is_none_or(|min| count as f64 >= min) && upper.is_none_or(|max| count as f64 <= max))
}

pub(crate) fn evaluate_record_test(
    name: &str,
    args: &Object,
    record: &Object,
    doc: &Object,
    normalizers: &IndexMap<String, bool>,
) -> Result<bool, String> {
    let field = || read_path(record, &values::read_text(args, "field")?);
    match name {
        "evidence_present@1" => Ok(values::has_content(&read_path(
            record,
            &values::read_text(args, "document")?,
        )?)),
        "field_in_set@1" => {
            let held = field()?;
            for candidate in values::read_array(args, "values")? {
                if values::values_match(&held, &candidate)? {
                    return Ok(true);
                }
            }
            Ok(false)
        }
        "fields_all_empty@1" => {
            for path in named_values(
                doc,
                &values::read_optional_value(args, "fields")?,
                "field list",
            )? {
                if values::has_content(&read_path(record, &values::read_value::<String>(&path)?)?) {
                    return Ok(false);
                }
            }
            Ok(true)
        }
        "token_match@1" | "token_match@2" => {
            let raw = field()?;
            let text = normalize_value(
                &values::read_text(args, "normalizer")?,
                &raw,
                doc,
                normalizers,
            )?;
            let listed = named_values(
                doc,
                &values::read_optional_value(args, "token_list")?,
                "token list",
            )?
            .iter()
            .map(|raw| values::read_value::<String>(raw))
            .collect::<Result<Vec<_>, _>>()?;
            let mut found = BTreeSet::new();
            for entry in &listed {
                if entry == "AND" {
                    continue;
                }
                let token = SPACES.replace_all(entry, " ");
                let boundary = |ch: Option<&u8>| {
                    ch.is_none_or(|ch| !ch.is_ascii_uppercase() && !ch.is_ascii_digit())
                };
                if text.match_indices(token.as_ref()).any(|(at, _)| {
                    boundary(text.as_bytes().get(at.wrapping_sub(1)))
                        && boundary(text.as_bytes().get(at + token.len()))
                }) {
                    found.insert(entry.clone());
                }
            }
            if (name == "token_match@1" || listed.iter().any(|entry| entry == "AND"))
                && display_text(&raw)?.contains('&')
                && format!(" {text} ").contains(" AND ")
            {
                found.insert("&".into());
            }
            if values::has_value(args, "exclude_list") {
                for excluded in named_values(doc, &args["exclude_list"], "exclude list")? {
                    found.remove(&values::read_value::<String>(&excluded)?);
                }
            }
            within_counts("token_match", args, found.len())
        }
        "values_overlap@1" => {
            let raw = field()?;
            let held = if raw.get() == "null" {
                Vec::new()
            } else {
                values::read_value::<Vec<Document>>(&raw).map_err(|_| {
                    format!(
                        "values_overlap reads a list field; {} is not",
                        values::read_text(args, "field").unwrap_or_default()
                    )
                })?
            };
            let wanted = named_values(
                doc,
                &values::read_optional_value(args, "values")?,
                "value list",
            )?;
            let mut found: Vec<Document> = Vec::new();
            for value in held {
                let mut shared = false;
                for candidate in &wanted {
                    if values::values_match(&value, candidate)? {
                        shared = true;
                        break;
                    }
                }
                let mut duplicate = false;
                for candidate in &found {
                    if values::values_match(&value, candidate)? {
                        duplicate = true;
                        break;
                    }
                }
                if shared && !duplicate {
                    found.push(value);
                }
            }
            within_counts("values_overlap", args, found.len())
        }
        "name_shape@1" => {
            let held = field()?;
            let text = if values::has_content(&held) {
                display_text(&held)?
                    .trim_matches(crate::text_transform::whitespace)
                    .to_owned()
            } else {
                String::new()
            };
            if text.is_empty() {
                return Ok(false);
            }
            let forbidden = values::read_object(args, "forbid_characters")?;
            for item in values::read_array(&forbidden, "value")? {
                if text.contains(&values::read_value::<String>(&item)?) {
                    return Ok(false);
                }
            }
            if values::has_value(&values::read_object(args, "forbid_digits")?, "value")
                && text
                    .chars()
                    .any(|ch| get_general_category(ch) == GeneralCategory::DecimalNumber)
            {
                return Ok(false);
            }
            let normalized = normalize_value(
                &values::read_text(args, "normalizer")?,
                &values::write_value(&text)?,
                doc,
                normalizers,
            )?;
            let tokens: Vec<_> = normalized
                .split(|ch: char| crate::text_transform::whitespace(ch) || ch == ',')
                .filter(|s| !s.is_empty())
                .collect();
            let min: usize =
                values::read_value(args.get("min_tokens").ok_or("Missing min_tokens")?)?;
            let max: usize =
                values::read_value(args.get("max_tokens").ok_or("Missing max_tokens")?)?;
            if tokens.len() < min || tokens.len() > max {
                return Ok(false);
            }
            let suffixes: BTreeSet<String> = named_values(
                doc,
                &values::read_optional_value(args, "suffix_list")?,
                "suffix list",
            )?
            .iter()
            .map(|raw| values::read_value(raw))
            .collect::<Result<_, _>>()?;
            Ok(tokens
                .iter()
                .filter(|word| !suffixes.contains(**word))
                .count()
                >= 2
                && tokens
                    .iter()
                    .all(|word| word.bytes().all(|ch| ch.is_ascii_uppercase())))
        }
        "identifier_match@1"
        | "identifier_cardinality@1"
        | "kind_equal@1"
        | "name_census_match@1"
        | "gleif_entity_eligible@1"
        | "holds_no_other_lei@1"
        | "jurisdiction_agrees@1"
        | "jurisdictions_do_not_conflict@1"
        | "postal_agrees@1"
        | "cascade_pass@1" => Err("Binding and compatibility tests run in the Merge Stage".into()),
        _ => Err(format!("Policy names an unknown primitive: {name}")),
    }
}

#[derive(Deserialize)]
struct Command {
    action: String,
    #[serde(default)]
    name: String,
    #[serde(default)]
    args: Object,
    #[serde(default)]
    record: Object,
    #[serde(default)]
    doc: Object,
    #[serde(default)]
    normalizers: IndexMap<String, bool>,
    #[serde(default)]
    rule: Object,
    #[serde(default)]
    value: Option<Document>,
    #[serde(default)]
    values: Vec<Document>,
}

pub fn apply_record_rules(raw: &str) -> Result<String, String> {
    let command: Command = serde_json::from_str(raw).map_err(|_| "Invalid record rule inputs")?;
    let result = match command.action.as_str() {
        "read_matching_field" => crate::record_pairs::read_matching_field(&command.record, &command.name)?,
        "test_record" => values::write_value(&evaluate_record_test(
            &command.name,
            &command.args,
            &command.record,
            &command.doc,
            &command.normalizers,
        )?)?,
        "prepare_matching_value" => values::write_value(&normalize_value(
            &command.name,
            &command.value.unwrap_or(values::write_value(&())?),
            &command.doc,
            &command.normalizers,
        )?)?,
        "prepare_matching_values" => values::write_value(
            &command
                .values
                .iter()
                .map(|raw| normalize_value(&command.name, raw, &command.doc, &command.normalizers))
                .collect::<Result<Vec<_>, _>>()?,
        )?,
        "classify_record" => {
            let mut chosen = None;
            for raw in values::read_array(&command.rule, "steps")? {
                let step: Object = values::read_value(&raw)?;
                let mut applies = true;
                if !values::has_value(&step, "otherwise") {
                    for raw in values::read_array(&step, "when")? {
                        let test: Object = values::read_value(&raw)?;
                        let passed = evaluate_record_test(
                            &values::read_text(&test, "primitive")?,
                            &values::read_object(&test, "args")?,
                            &command.record,
                            &command.doc,
                            &command.normalizers,
                        )?;
                        if passed == values::has_value(&test, "negate") {
                            applies = false;
                            break;
                        }
                    }
                }
                if applies {
                    chosen = Some((
                        values::read_text(&step, "verdict")?,
                        display_text(&values::read_optional_value(&step, "step")?)?,
                    ));
                    break;
                }
            }
            values::write_value(&chosen.ok_or("Classification requires a catch-all step")?)?
        }
        _ => return Err("Unsupported record rule operation".into()),
    };
    Ok(result.get().into())
}
