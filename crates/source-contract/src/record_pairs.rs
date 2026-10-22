//! Evaluate configured pair tests with pinned reference data and exact record values.

use crate::matching_values;
use crate::record_tests::{display_text, normalize_value};
use crate::record_values::{self as values, Document, Object};
use indexmap::IndexMap;
use serde::Deserialize;
use std::collections::BTreeSet;

#[derive(Deserialize)]
struct Command {
    rule: Object,
    #[serde(default)]
    left: Object,
    #[serde(default)]
    right: Object,
    #[serde(default)]
    pairs: Option<Vec<[Object; 2]>>,
    code_tables: IndexMap<String, IndexMap<String, String>>,
    normalizers: IndexMap<String, bool>,
    census_version: String,
    cascade_version: String,
}

fn read_field_value(record: &Object, name: &str) -> Result<Document, String> {
    let field = values::read_object(&values::read_object(record, "fields")?, name)?;
    if values::read_text(&field, "op").ok().as_deref() == Some("value") {
        values::read_optional_value(&field, "value")
    } else {
        values::write_value(&())
    }
}
fn read_matching_values(record: &Object) -> Result<Object, String> {
    values::read_object(&values::read_object(record, "provenance")?, "matching")
}
fn field_is_withheld(record: &Object, path: &str) -> Result<bool, String> {
    let quality = values::read_object(&values::read_object(record, "provenance")?, "quality")?;
    for raw in values::read_array(&quality, "withheld")? {
        let held: String = values::read_value(&raw)?;
        if path == held
            || path.starts_with(&format!("{held}."))
            || held.starts_with(&format!("{path}."))
        {
            return Ok(true);
        }
    }
    Ok(false)
}
pub(crate) fn read_matching_field(record: &Object, path: &str) -> Result<Document, String> {
    let qualified = if path.starts_with("matching.") {
        path.into()
    } else {
        format!("fields.{path}")
    };
    if field_is_withheld(record, &qualified)? {
        return values::write_value(&());
    }
    match path.strip_prefix("matching.") {
        Some(name) => values::read_optional_value(&read_matching_values(record)?, name),
        None => read_field_value(record, path),
    }
}
fn read_name(
    args: &Object,
    record: &Object,
    argument: &str,
    command: &Command,
) -> Result<String, String> {
    let name = values::read_text(args, argument)?;
    normalize_value(
        &name,
        &read_field_value(record, "name")?,
        &Object::new(),
        &command.normalizers,
    )
}
fn value_matches_rule(
    body: &Object,
    key: &str,
    expected: &impl serde::Serialize,
) -> Result<bool, String> {
    values::values_match(
        &values::read_optional_value(body, key)?,
        &values::write_value(expected)?,
    )
}
fn read_optional_text(raw: Document) -> Result<Option<String>, String> {
    values::read_value(&raw)
}
fn reference_place(
    args: &Object,
    left: &Object,
    command: &Command,
) -> Result<Option<String>, String> {
    let name = values::read_text(args, "sec_codes")?;
    let table = command
        .code_tables
        .get(&name)
        .ok_or_else(|| format!("Name binding names an unknown code table: {name}"))?;
    let code = display_text(&read_matching_field(
        left,
        &values::read_text(args, "sec_field")?,
    )?)?;
    let code =
        matching_values::prepare_uppercase(code.trim_matches(crate::text_transform::whitespace));
    Ok(table.get(&code).cloned())
}
fn prepared_address(record: &Object, names: &[&str]) -> Result<Object, String> {
    let matching = read_matching_values(record)?;
    let mut country = None;
    for name in names {
        let address = values::read_object(&matching, name)?;
        if country.is_none() && values::has_value(&address, "country") {
            country = address.get("country").cloned();
        }
        if values::has_value(&address, "street")
            && !field_is_withheld(record, &format!("matching.{name}"))?
        {
            return Ok(address);
        }
    }
    Ok(Object::from([(
        "country".into(),
        country.unwrap_or(values::write_value(&())?),
    )]))
}
fn addresses_agree(left: &Object, right: &Object, raw: &Document) -> Result<bool, String> {
    if raw.get() == "null" {
        return Ok(true);
    }
    let parts: Vec<String> = values::read_value(raw)?;
    if !values::has_value(left, "country")
        || !values::values_match(
            &values::read_optional_value(left, "country")?,
            &values::read_optional_value(right, "country")?,
        )?
    {
        return Ok(false);
    }
    for part in parts {
        match part.as_str() {
            "street" => {
                let lines = |body: &Object| -> Result<BTreeSet<String>, String> {
                    let mut result = BTreeSet::new();
                    for name in ["street", "street2"] {
                        let raw = values::read_optional_value(body, name)?;
                        if values::has_content(&raw) {
                            result.extend(
                                display_text(&raw)?
                                    .split('\n')
                                    .filter(|line| !line.is_empty())
                                    .map(str::to_owned),
                            );
                        }
                    }
                    Ok(result)
                };
                if lines(left)?.is_disjoint(&lines(right)?) {
                    return Ok(false);
                }
            }
            "city" => {
                if !values::has_value(left, "city")
                    || !values::values_match(
                        &values::read_optional_value(left, "city")?,
                        &values::read_optional_value(right, "city")?,
                    )?
                {
                    return Ok(false);
                }
            }
            "postcode" => {
                if !matching_values::postal_codes_agree(
                    &display_text(&values::read_optional_value(left, "postcode")?)?,
                    read_optional_text(values::read_optional_value(left, "country")?)?.as_deref(),
                    &display_text(&values::read_optional_value(right, "postcode")?)?,
                    read_optional_text(values::read_optional_value(right, "country")?)?.as_deref(),
                ) {
                    return Ok(false);
                }
            }
            _ => return Err(format!("A pass compares an unknown address part: {part}")),
        }
    }
    Ok(true)
}

fn test_record_pair(
    name: &str,
    args: &Object,
    command: &Command,
    ignore_flags: bool,
) -> Result<bool, String> {
    let left = &command.left;
    let right = &command.right;
    match name {
        "holds_no_other_lei@1" => Ok(true),
        "name_census_match@1" => {
            let entry = values::read_object(&read_matching_values(left)?, "name_census")?;
            let identifier =
                values::read_optional_value(&values::read_object(right, "identifiers")?, "lei")?;
            let key = read_name(args, left, "sec_normalizer", command)?;
            let updated = read_field_value(right, "gleif_last_update")?;
            let updated = if values::has_content(&updated) {
                updated
            } else {
                values::write_value(&"")?
            };
            Ok(
                value_matches_rule(&entry, "version", &command.census_version)?
                    && value_matches_rule(&entry, "cik_count", &1)?
                    && value_matches_rule(
                        &entry,
                        "ciks",
                        &vec![values::read_optional_value(left, "record_key")?],
                    )?
                    && value_matches_rule(&entry, "lei_count", &1)?
                    && value_matches_rule(&entry, "other_name_holders", &0)?
                    && value_matches_rule(&entry, "leis", &vec![vec![identifier, updated]])?
                    && !key.is_empty()
                    && value_matches_rule(&entry, "key", &key)?
                    && key == read_name(args, right, "gleif_normalizer", command)?,
            )
        }
        "gleif_entity_eligible@1" => {
            if !value_matches_rule(args, "categories", &vec!["GENERAL"])? {
                return Err("Name binding can require only the GENERAL category".into());
            }
            let status = read_field_value(right, "gleif_entity_status")?;
            let registration = read_field_value(right, "gleif_registration_status")?;
            let contains = |name: &str, value: &Document| -> Result<bool, String> {
                for item in values::read_array(args, name)? {
                    if values::values_match(&item, value)? {
                        return Ok(true);
                    }
                }
                Ok(false)
            };
            Ok(
                values::read_text(right, "kind").ok().as_deref() == Some("company")
                    && contains("entity_statuses", &status)?
                    && !contains("refused_registration_statuses", &registration)?,
            )
        }
        "jurisdiction_agrees@1" | "jurisdictions_do_not_conflict@1" => {
            let left = reference_place(args, left, command)?;
            let right = read_optional_text(read_matching_field(
                right,
                &values::read_text(args, "gleif_field")?,
            )?)?;
            if name == "jurisdiction_agrees@1" {
                Ok(matching_values::places_agree(
                    left.as_deref(),
                    right.as_deref(),
                ))
            } else {
                let country = read_optional_text(read_matching_field(
                    &command.left,
                    &values::read_text(args, "sec_business_country")?,
                )?)?;
                Ok(!matching_values::places_conflict(
                    left.as_deref(),
                    right.as_deref(),
                    country.as_deref(),
                ))
            }
        }
        "postal_agrees@1" => Ok(matching_values::postal_codes_agree(
            &display_text(&read_matching_field(
                left,
                &values::read_text(args, "sec_code")?,
            )?)?,
            read_optional_text(read_matching_field(
                left,
                &values::read_text(args, "sec_country")?,
            )?)?
            .as_deref(),
            &display_text(&read_matching_field(
                right,
                &values::read_text(args, "gleif_code")?,
            )?)?,
            read_optional_text(read_matching_field(
                right,
                &values::read_text(args, "gleif_country")?,
            )?)?
            .as_deref(),
        )),
        "cascade_pass@1" => {
            let answer = values::read_object(
                &values::read_object(&read_matching_values(left)?, "name_census")?,
                "cascade",
            )?;
            let key = read_name(args, left, "sec_normalizer", command)?;
            let other_key = read_name(args, right, "gleif_normalizer", command)?;
            if !value_matches_rule(&answer, "version", &command.cascade_version)?
                || !values::values_match(
                    &values::read_optional_value(&answer, "pass")?,
                    &values::read_optional_value(args, "pass")?,
                )?
                || !values::values_match(
                    &values::read_optional_value(&answer, "lei")?,
                    &values::read_optional_value(
                        &values::read_object(right, "identifiers")?,
                        "lei",
                    )?,
                )?
            {
                return Ok(false);
            }
            let updated = read_field_value(right, "gleif_last_update")?;
            let updated = if values::has_content(&updated) {
                updated
            } else {
                values::write_value(&"")?
            };
            if !values::values_match(
                &values::read_optional_value(&answer, "last_update")?,
                &updated,
            )? || key.is_empty()
                || !value_matches_rule(&answer, "key", &key)?
                || !(other_key == key || value_matches_rule(&answer, "via", &"other name")?)
            {
                return Ok(false);
            }
            if !ignore_flags {
                let refused: Vec<String> = values::read_array(args, "refused_flags")?
                    .iter()
                    .map(|raw| values::read_value(raw))
                    .collect::<Result<_, _>>()?;
                for raw in values::read_array(&answer, "flags")? {
                    if refused.contains(&values::read_value::<String>(&raw)?) {
                        return Ok(false);
                    }
                }
            }
            addresses_agree(
                &prepared_address(left, &["address"])?,
                &prepared_address(right, &["headquarters_address", "address"])?,
                &values::read_optional_value(args, "compare")?,
            )
        }
        _ => Err(format!("Name binding test {name} has no implementation")),
    }
}

fn compare_record_pair(command: &Command, tests: &[Object]) -> Result<(bool, bool), String> {
    let mut passes = true;
    for test in tests {
        if !test_record_pair(
            &values::read_text(test, "primitive")?,
            &values::read_object(test, "args")?,
            command,
            false,
        )? {
            passes = false;
            break;
        }
    }
    let has_flags = tests.iter().any(|test| {
        values::read_text(test, "primitive").ok().as_deref() == Some("cascade_pass@1")
            && values::read_object(test, "args")
                .is_ok_and(|args| values::has_value(&args, "refused_flags"))
    });
    let mut lenient = has_flags;
    if has_flags {
        for test in tests {
            if !test_record_pair(
                &values::read_text(test, "primitive")?,
                &values::read_object(test, "args")?,
                command,
                true,
            )? {
                lenient = false;
                break;
            }
        }
    }
    Ok((passes, lenient))
}

pub fn compare_record_pairs(raw: &str) -> Result<String, String> {
    let mut command: Command =
        serde_json::from_str(raw).map_err(|_| "Invalid record pair inputs")?;
    let tests: Vec<Object> = values::read_array(&command.rule, "when")?
        .iter()
        .map(|raw| values::read_value(raw))
        .collect::<Result<_, _>>()?;
    let mut results = Vec::new();
    if let Some(pairs) = command.pairs.take() {
        for [left, right] in pairs {
            command.left = left;
            command.right = right;
            results.push(compare_record_pair(&command, &tests)?);
        }
    } else {
        results.push(compare_record_pair(&command, &tests)?);
    }
    serde_json::to_string(&results).map_err(|_| "Cannot serialize record pair outcomes".into())
}
