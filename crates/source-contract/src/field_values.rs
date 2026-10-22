//! One configured choice of field values and profiles, shared by every database.

use crate::record_values::read_time;
use crate::record_values::{self as values, Document, Object};
use chrono::Duration;
use indexmap::IndexMap;
use serde::Deserialize;
use std::collections::BTreeSet;

#[derive(Deserialize)]
struct Command {
    kind: String,
    subjects: Vec<String>,
    claims: IndexMap<String, Object>,
    policy: Object,
    overrides: Vec<Object>,
    as_of: String,
    policy_digest: String,
    entity_id: String,
    profile_kinds: IndexMap<String, Vec<String>>,
}

pub(crate) struct FieldInputs<'a> {
    pub kind: &'a String,
    pub subjects: &'a Vec<String>,
    pub claims: &'a IndexMap<String, Object>,
    pub policy: &'a Object,
    pub overrides: &'a Vec<Object>,
    pub as_of: &'a String,
    pub policy_digest: &'a String,
    pub entity_id: &'a String,
    pub profile_kinds: &'a IndexMap<String, Vec<String>>,
}

const AUTHORITY: &[&str] = &["defaults", "fields", "field_group", "field_groups"];
const OTHER: &[&str] = &[
    "version",
    "rules",
    "bars",
    "lists",
    "normalizers",
    "identifiers",
    "projection",
];

pub fn describe_field_rules() -> (Vec<String>, Vec<String>) {
    (
        AUTHORITY.iter().map(|name| (*name).into()).collect(),
        OTHER.iter().map(|name| (*name).into()).collect(),
    )
}

fn prepare_review(reason: &str, subject: &str, profile: &Object) -> Result<Object, String> {
    Ok(IndexMap::from([
        ("reason".into(), values::write_value(&reason)?),
        ("subject".into(), values::write_value(&subject)?),
        ("profile".into(), values::write_value(profile)?),
    ]))
}

fn select_authority(
    policy: &Object,
    kind: &str,
    fallback: &str,
) -> Result<(String, Option<Document>), String> {
    let block = values::read_object(&values::read_object(policy, "kinds")?, kind)?;
    if block.is_empty() {
        return Ok((fallback.into(), None));
    }
    let unknown: BTreeSet<_> = block
        .keys()
        .filter(|key| !AUTHORITY.contains(&key.as_str()) && !OTHER.contains(&key.as_str()))
        .cloned()
        .collect();
    if !unknown.is_empty() {
        return Err(format!(
            "A kind section must be declared authority-bearing or not: {}",
            unknown.into_iter().collect::<Vec<_>>().join(", ")
        ));
    }
    let mut covered = Object::from([("kind".into(), values::write_value(&kind)?)]);
    for name in AUTHORITY {
        if values::has_value(&block, name) {
            covered.insert((*name).into(), block[*name].clone());
        }
    }
    Ok((
        values::calculate_content_hash(&values::write_value(&covered)?)?,
        block.get("version").cloned(),
    ))
}

fn select_profile_authority(
    policy: &Object,
    role: &str,
    fallback: &str,
) -> Result<(String, Option<Document>), String> {
    let rules = values::read_object(&values::read_object(policy, "profile_fields")?, role)?;
    if !values::has_value(policy, "kinds") || rules.is_empty() {
        return Ok((fallback.into(), None));
    }
    let covered = Object::from([
        ("role".into(), values::write_value(&role)?),
        ("fields".into(), values::write_value(&rules)?),
    ]);
    Ok((
        values::calculate_content_hash(&values::write_value(&covered)?)?,
        Some(values::write_value(&role)?),
    ))
}

fn choose_values(
    rules: &Object,
    subjects: &[String],
    records: &IndexMap<String, Object>,
    overrides: &[Object],
    as_of: &str,
    authority: &str,
    version: Option<&Document>,
    defaults: &Object,
) -> Result<(Object, Vec<Object>), String> {
    let mut candidates: IndexMap<String, Vec<Object>> = IndexMap::new();
    for subject in subjects {
        if let Some(record) = records.get(subject) {
            for (name, claim) in values::read_object(record, "fields")? {
                candidates
                    .entry(name)
                    .or_default()
                    .push(values::read_value(&claim)?);
            }
        }
    }
    let mut names: Vec<_> = rules.keys().cloned().collect();
    if !defaults.is_empty() {
        let extra: BTreeSet<_> = candidates
            .keys()
            .filter(|key| !rules.contains_key(*key))
            .cloned()
            .collect();
        names.extend(extra);
    }
    let mut fields = Object::new();
    let mut reviews = Vec::new();
    for name in names {
        let mut rule = defaults.clone();
        rule.extend(values::read_object(rules, &name)?);
        let sources: Vec<String> =
            values::read_value(rule.get("sources").ok_or("Field rule requires sources")?)?;
        let clear_sources: Vec<String> = rule
            .get("clear_sources")
            .map(|raw| values::read_value(raw))
            .transpose()?
            .unwrap_or_default();
        let supplied = candidates.get(&name).cloned().unwrap_or_default();
        let mut metadata = Vec::new();
        for claim in &supplied {
            let source = values::read_text(claim, "source_code")?;
            let operation = values::read_text(claim, "op")?;
            let mut effective = None;
            let mut fresh = true;
            if sources.contains(&source)
                && (operation != "clear" || clear_sources.contains(&source))
            {
                if let Some(raw) = claim.get("effective_at").filter(|raw| raw.get() != "null") {
                    let moment = read_time(&values::read_value::<String>(raw)?)?;
                    effective = Some(
                        moment.timestamp() as f64
                            + moment.timestamp_subsec_micros() as f64 / 1_000_000.0,
                    );
                    if let Some(days) = rule.get("max_age_days").filter(|raw| raw.get() != "null") {
                        let days: f64 = values::read_value(days)?;
                        let micros = (days * 86_400_000_000.0).round_ties_even();
                        if !micros.is_finite() || micros.abs() > i64::MAX as f64 {
                            return Err("Field freshness interval is out of range".into());
                        }
                        fresh = moment
                            .checked_add_signed(Duration::microseconds(micros as i64))
                            .ok_or("Field freshness interval is out of range")?
                            >= read_time(as_of)?;
                    }
                }
            }
            metadata.push((
                source,
                operation,
                effective,
                fresh,
                values::read_text(claim, "record_key")?,
                values::read_text(claim, "assertion_id")?,
            ));
        }
        let (indices, unauthorized) = crate::survivorship::rank(
            &sources,
            &clear_sources,
            values::has_value(&rule, "allow_unknown_effective"),
            &metadata,
        );
        let mut eligible: Vec<_> = indices
            .into_iter()
            .map(|index| supplied[index].clone())
            .collect();
        for index in unauthorized {
            reviews.push(Object::from([
                ("reason".into(), values::write_value(&"unauthorized_clear")?),
                ("field".into(), values::write_value(&name)?),
                (
                    "assertion_id".into(),
                    values::read_optional_value(&supplied[index], "assertion_id")?,
                ),
            ]));
        }
        let active: Vec<_> = overrides
            .iter()
            .filter(|body| {
                values::read_text(body, "subject").is_ok_and(|subject| subjects.contains(&subject))
                    && values::read_text(body, "field").is_ok_and(|field| field == name)
                    && !values::has_value(body, "profile_id")
            })
            .collect();
        if active.len() > 1 {
            return Err("Conflicting active steward overrides".into());
        }
        let chosen = if let Some(item) = active.first() {
            let chosen = Object::from([
                ("op".into(), values::write_value(&"value")?),
                ("value".into(), values::read_optional_value(item, "value")?),
                (
                    "assertion_id".into(),
                    values::read_optional_value(item, "decision_id")?,
                ),
                ("source_code".into(), values::write_value(&"steward")?),
                (
                    "reason".into(),
                    values::read_optional_value(item, "reason")?,
                ),
            ]);
            let mut disagreement = false;
            for claim in &eligible {
                if !values::values_match(
                    &values::read_optional_value(claim, "value")?,
                    &chosen["value"],
                )? {
                    disagreement = true;
                    break;
                }
            }
            if disagreement {
                reviews.push(Object::from([
                    (
                        "reason".into(),
                        values::write_value(&"override_source_disagreement")?,
                    ),
                    ("field".into(), values::write_value(&name)?),
                    (
                        "override".into(),
                        values::read_optional_value(item, "decision_id")?,
                    ),
                ]));
            }
            chosen
        } else if !eligible.is_empty() {
            eligible.remove(0)
        } else {
            continue;
        };
        let selected = values::read_optional_value(&chosen, "value")?;
        let selected_key = values::write_sorted_json(&selected)?;
        let mut conflicts = Vec::new();
        for claim in eligible {
            if values::write_sorted_json(&values::read_optional_value(&claim, "value")?)?
                != selected_key
            {
                conflicts.push(claim);
            }
        }
        let mut result = Object::from([
            ("value".into(), selected),
            (
                "cleared".into(),
                values::write_value(&(values::read_text(&chosen, "op")? == "clear"))?,
            ),
            ("winner".into(), values::write_value(&chosen)?),
            ("policy_digest".into(), values::write_value(&authority)?),
            ("conflicts".into(), values::write_value(&conflicts)?),
        ]);
        if let Some(version) = version.filter(|raw| values::has_content(raw)) {
            result.insert("kind_version".into(), (*version).clone());
        }
        fields.insert(name, values::write_value(&result)?);
    }
    Ok((fields, reviews))
}

/// Choose field values from explicit records and versioned rules, without a database branch.
pub(crate) fn choose_fields_for_records(
    input: FieldInputs<'_>,
) -> Result<(Object, Vec<Object>, Vec<Object>), String> {
    let FieldInputs {
        kind,
        subjects,
        claims,
        policy,
        overrides,
        as_of,
        policy_digest,
        entity_id,
        profile_kinds,
    } = input;
    let mut profiles: IndexMap<String, Object> = IndexMap::new();
    let mut profile_claims: IndexMap<String, IndexMap<String, Object>> = IndexMap::new();
    let mut reviews = Vec::new();
    for subject in subjects {
        let Some(record) = claims.get(subject) else {
            continue;
        };
        for raw in values::read_array(record, "profiles")? {
            let profile: Object = values::read_value(&raw)?;
            let role = values::read_text(&profile, "role")?;
            let problem = if !profile_kinds
                .get(&role)
                .is_some_and(|kinds| kinds.contains(kind))
            {
                Some("incompatible_profile")
            } else if !values::has_value(&profile, "authority")
                || !values::has_value(&profile, "registration")
            {
                Some("unproven_profile")
            } else if !values::has_value(&profile, "valid_from") {
                Some("undated_profile")
            } else if values::has_value(&profile, "valid_to")
                && read_time(&values::read_text(&profile, "valid_from")?)?
                    >= read_time(&values::read_text(&profile, "valid_to")?)?
            {
                Some("invalid_profile_interval")
            } else {
                None
            };
            if let Some(reason) = problem {
                reviews.push(prepare_review(reason, subject, &profile)?);
                continue;
            }
            let identity = vec![
                values::write_value(&entity_id)?,
                values::write_value(&role)?,
                values::read_optional_value(&profile, "authority")?,
                values::read_optional_value(&profile, "registration")?,
                values::read_optional_value(&profile, "jurisdiction")?,
                values::read_optional_value(&profile, "valid_from")?,
            ];
            let id = values::calculate_content_hash(&values::write_value(&identity)?)?;
            if !profiles.contains_key(&id) {
                let mut kept = profile.clone();
                kept.insert("profile_id".into(), values::write_value(&id)?);
                kept.insert(
                    "evidence".into(),
                    values::write_value(&Vec::<String>::new())?,
                );
                profiles.insert(id.clone(), kept);
            }
            let kept = profiles.get_mut(&id).ok_or("Missing prepared profile")?;
            let mut evidence: Vec<String> = values::read_value(&kept["evidence"])?;
            evidence.push(values::read_text(record, "assertion_id")?);
            kept.insert("evidence".into(), values::write_value(&evidence)?);
            kept.shift_remove("fields");
            let key = crate::readings::identify_profile(raw.get())?;
            let fields =
                values::read_object(&values::read_object(record, "profile_fields")?, &key)?;
            profile_claims.entry(id).or_default().insert(
                subject.clone(),
                Object::from([
                    ("fields".into(), values::write_value(&fields)?),
                    (
                        "profiles".into(),
                        values::write_value(&Vec::<String>::new())?,
                    ),
                ]),
            );
        }
    }
    let (authority, version) = select_authority(&policy, &kind, &policy_digest)?;
    let kinds = values::read_object(&policy, "kinds")?;
    if !kinds.is_empty() && values::has_value(&policy, "fields") {
        return Err("A kind's field rules belong in one place, not two".into());
    }
    let block = values::read_object(&kinds, kind)?;
    let rules = if kinds.is_empty() {
        values::read_object(&values::read_object(&policy, "fields")?, &kind)?
    } else {
        values::read_object(&block, "fields")?
    };
    let defaults = values::read_object(&block, "defaults")?;
    let (fields, problems) = choose_values(
        &rules,
        &subjects,
        &claims,
        &overrides,
        &as_of,
        &authority,
        version.as_ref(),
        &defaults,
    )?;
    reviews.extend(problems);
    for (id, profile) in &mut profiles {
        let evidence: BTreeSet<String> = values::read_value(&profile["evidence"])?;
        profile.insert("evidence".into(), values::write_value(&evidence)?);
        let role = values::read_text(profile, "role")?;
        let (authority, version) = select_profile_authority(&policy, &role, &policy_digest)?;
        let rules = values::read_object(&values::read_object(&policy, "profile_fields")?, &role)?;
        let mut active = Vec::new();
        for item in overrides {
            if values::read_text(item, "profile_id").is_ok_and(|value| value == *id) {
                let mut kept = item.clone();
                kept.shift_remove("profile_id");
                active.push(kept);
            }
        }
        let (fields, mut problems) = choose_values(
            &rules,
            &subjects,
            &profile_claims[id],
            &active,
            &as_of,
            &authority,
            version.as_ref(),
            &Object::new(),
        )?;
        profile.insert("fields".into(), values::write_value(&fields)?);
        for problem in &mut problems {
            problem.insert("profile_id".into(), values::write_value(id)?);
        }
        reviews.extend(problems);
    }
    let mut profiles: Vec<_> = profiles.into_iter().collect();
    profiles.sort_by(|a, b| a.0.cmp(&b.0));
    let profiles: Vec<_> = profiles.into_iter().map(|(_, value)| value).collect();
    Ok((fields, profiles, reviews))
}

pub fn choose_field_values(raw: &str) -> Result<String, String> {
    let command: Command =
        serde_json::from_str(raw).map_err(|_| "Invalid field-selection command")?;
    let result = choose_fields_for_records(FieldInputs {
        kind: &command.kind,
        subjects: &command.subjects,
        claims: &command.claims,
        policy: &command.policy,
        overrides: &command.overrides,
        as_of: &command.as_of,
        policy_digest: &command.policy_digest,
        entity_id: &command.entity_id,
        profile_kinds: &command.profile_kinds,
    })?;
    serde_json::to_string(&result).map_err(|_| "Selected fields cannot be serialized".into())
}
