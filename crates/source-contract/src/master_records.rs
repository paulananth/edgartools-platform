//! Prepare affected master records once, independently of their storage engine.

use crate::field_values::{choose_fields_for_records, FieldInputs};
use crate::record_values::{self as values, Object};
use indexmap::IndexMap;
use serde::Deserialize;
use std::collections::{BTreeMap, BTreeSet};

#[derive(Deserialize)]
struct Command {
    identities: BTreeMap<String, Object>,
    canonical: IndexMap<String, String>,
    bindings: IndexMap<String, String>,
    quarantined: IndexMap<String, String>,
    claims: IndexMap<String, Object>,
    policy: Object,
    overrides: Vec<Object>,
    decisions: Vec<Object>,
    as_of: String,
    policy_digest: String,
    profile_kinds: IndexMap<String, Vec<String>>,
}

fn decision_changes_record(
    decision: &Object,
    record: &str,
    canonical: &IndexMap<String, String>,
) -> Result<bool, String> {
    let operation = values::read_text(decision, "operation")?;
    let keys: &[&str] = match operation.as_str() {
        "bind" => &["entity_id"],
        "merge" => &["left", "right"],
        _ => &[],
    };
    for key in keys {
        let operand = values::read_text(decision, key)?;
        if canonical.get(&operand).is_some_and(|root| root == record) {
            return Ok(true);
        }
    }
    Ok(false)
}

const FIGI_REFERENCES: &[&str] = &["share_class_figi", "composite_figi", "figi"];

/// The records that assert these identifier values share one FIGI.
fn shared_figi(
    claims: &IndexMap<String, Object>,
    contributors: &IndexMap<String, BTreeMap<String, Vec<String>>>,
    namespace: &str,
    candidates: &BTreeSet<String>,
) -> Result<bool, String> {
    let mut subjects = Vec::new();
    for value in candidates {
        if let Some(found) = contributors.get(namespace).and_then(|rows| rows.get(value)) {
            subjects.extend(found.iter().cloned());
        }
    }
    subjects.sort();
    subjects.dedup();
    if subjects.is_empty() {
        return Ok(false);
    }
    for reference in FIGI_REFERENCES {
        let mut token: Option<String> = None;
        let mut agreed = true;
        for subject in &subjects {
            let Some(claim) = claims.get(subject) else {
                agreed = false;
                break;
            };
            let refs = values::read_object(claim, "cross_references")?;
            let Some(raw) = refs.get(*reference) else {
                agreed = false;
                break;
            };
            let text: String = values::read_value(raw)?;
            if text.is_empty() {
                agreed = false;
                break;
            }
            match &token {
                None => token = Some(text),
                Some(held) if held == &text => {}
                Some(_) => {
                    agreed = false;
                    break;
                }
            }
        }
        if agreed && token.is_some() {
            return Ok(true);
        }
    }
    Ok(false)
}

/// Keep one row per detail key, with the approved source order and all contributors.
fn select_detail_rows(
    kind: &str,
    subjects: &[String],
    claims: &IndexMap<String, Object>,
    policy: &Object,
) -> Result<BTreeMap<String, Vec<Object>>, String> {
    let kinds = values::read_object(policy, "kinds")?;
    let block: Object = kinds
        .get(kind)
        .map(|raw| values::read_value(raw))
        .transpose()?
        .unwrap_or_default();
    let defaults = values::read_object(&block, "defaults")?;
    let sources: Vec<String> = values::read_array(&defaults, "sources")?
        .iter()
        .map(|raw| values::read_value(raw))
        .collect::<Result<_, _>>()?;
    let rank: BTreeMap<_, _> = sources
        .iter()
        .enumerate()
        .map(|(n, source)| (source.as_str(), n))
        .collect();
    struct DetailRow {
        priority: (usize, String, String),
        body: Object,
        sources: BTreeSet<String>,
    }
    let mut rows: BTreeMap<String, BTreeMap<String, DetailRow>> = BTreeMap::new();
    for subject in subjects {
        let Some(claim) = claims.get(subject) else {
            continue;
        };
        if !values::has_value(claim, "details") {
            continue;
        }
        let metadata = values::read_object(claim, "source_meta")?;
        let source = values::read_text(&metadata, "source_code")?;
        let priority = (
            rank.get(source.as_str()).copied().unwrap_or(rank.len()),
            source.clone(),
            subject.clone(),
        );
        for (name, raw) in values::read_object(claim, "details")? {
            for item in values::read_value::<Vec<Object>>(&raw)? {
                let key = values::read_text(&item, "key")?;
                let row = rows
                    .entry(name.clone())
                    .or_default()
                    .entry(key)
                    .or_insert_with(|| DetailRow {
                        priority: priority.clone(),
                        body: item.clone(),
                        sources: BTreeSet::new(),
                    });
                if priority < row.priority {
                    row.priority = priority.clone();
                    row.body = item;
                }
                row.sources.insert(source.clone());
            }
        }
    }
    let mut selected = BTreeMap::new();
    for (name, keyed) in rows {
        let mut items = Vec::new();
        for (_, mut row) in keyed {
            row.body
                .insert("sources".into(), values::write_value(&row.sources)?);
            items.push(row.body);
        }
        selected.insert(name, items);
    }
    Ok(selected)
}

pub fn prepare_master_records(raw: &str) -> Result<String, String> {
    let command: Command = serde_json::from_str(raw).map_err(|_| "Invalid master record inputs")?;
    let Command {
        identities,
        canonical,
        bindings,
        quarantined,
        claims,
        policy,
        overrides,
        decisions,
        as_of,
        policy_digest,
        profile_kinds,
    } = command;
    let mut groups: IndexMap<String, Vec<String>> = IndexMap::new();
    let mut flagged = BTreeSet::new();
    for record in quarantined.values() {
        flagged.insert(
            canonical
                .get(record)
                .ok_or("Unknown quarantined identity")?
                .clone(),
        );
    }
    for (subject, record) in &bindings {
        groups
            .entry(
                canonical
                    .get(record)
                    .ok_or("Unknown bound identity")?
                    .clone(),
            )
            .or_default()
            .push(subject.clone());
    }
    let mut projected = IndexMap::new();
    let mut reviews = Vec::new();
    for (record, identity) in identities {
        let root = canonical.get(&record).ok_or("Unknown identity")?;
        let kind = values::read_text(&identity, "kind")?;
        if root != &record {
            projected.insert(
                record.clone(),
                Object::from([
                    ("entity_id".into(), values::write_value(&record)?),
                    ("kind".into(), values::write_value(&kind)?),
                    ("canonical_id".into(), values::write_value(root)?),
                    ("status".into(), values::write_value(&"alias")?),
                ]),
            );
            continue;
        }
        // Keep the original binding order for review ownership; selection uses sorted members.
        let mut members = groups.entry(record.clone()).or_default().clone();
        members.sort();
        let mut identifiers: IndexMap<String, BTreeSet<String>> = IndexMap::new();
        let mut contributors: IndexMap<String, BTreeMap<String, Vec<String>>> = IndexMap::new();
        let mut conflicts = Vec::new();
        for subject in &members {
            let Some(claim) = claims.get(subject) else {
                continue;
            };
            if values::read_text(claim, "kind")? != kind {
                conflicts.push(Object::from([
                    ("reason".into(), values::write_value(&"kind_conflict")?),
                    ("subject".into(), values::write_value(subject)?),
                ]));
            }
            for (namespace, raw) in values::read_object(claim, "identifiers")? {
                let value: String = values::read_value(&raw)?;
                contributors
                    .entry(namespace.clone())
                    .or_default()
                    .entry(value.clone())
                    .or_default()
                    .push(subject.clone());
                identifiers.entry(namespace).or_default().insert(value);
            }
        }
        for (namespace, candidates) in &identifiers {
            if candidates.len() <= 1 {
                continue;
            }
            // One CUSIP offered two ISINs stays one Security when those
            // records share a FIGI (operator, 2026-10-24: "resolve using
            // figi"). FIGI still does not join two Securities.
            if namespace == "isin" && shared_figi(&claims, &contributors, namespace, candidates)? {
                continue;
            }
            conflicts.push(Object::from([
                (
                    "reason".into(),
                    values::write_value(&"authoritative_identifier_conflict")?,
                ),
                ("namespace".into(), values::write_value(namespace)?),
                ("values".into(), values::write_value(candidates)?),
            ]));
        }
        if !conflicts.is_empty() {
            for decision in &decisions {
                if decision_changes_record(decision, &record, &canonical)? {
                    return Err("Identity decision has unresolved authoritative identifier or kind conflict".into());
                }
            }
        }
        let (fields, profiles, field_reviews) = choose_fields_for_records(FieldInputs {
            kind: &kind,
            subjects: &members,
            claims: &claims,
            policy: &policy,
            overrides: &overrides,
            as_of: &as_of,
            policy_digest: &policy_digest,
            entity_id: &record,
            profile_kinds: &profile_kinds,
        })?;
        let accepted = conflicts.is_empty();
        let mut body = Object::from([
            ("entity_id".into(), values::write_value(&record)?),
            ("kind".into(), values::write_value(&kind)?),
            ("canonical_id".into(), values::write_value(&record)?),
            (
                "status".into(),
                values::write_value(&if accepted { "accepted" } else { "review" })?,
            ),
            (
                "fields".into(),
                values::write_value(&if accepted { fields } else { Object::new() })?,
            ),
            (
                "profiles".into(),
                values::write_value(&if accepted { profiles } else { Vec::new() })?,
            ),
            (
                "identifiers".into(),
                values::write_value(&identifiers.into_iter().collect::<BTreeMap<_, _>>())?,
            ),
            ("subjects".into(), values::write_value(&members)?),
        ]);
        if accepted {
            let details = select_detail_rows(&kind, &members, &claims, &policy)?;
            if !details.is_empty() {
                body.insert("details".into(), values::write_value(&details)?);
            }
        }
        if flagged.contains(&record) {
            body.insert("quarantined".into(), values::write_value(&true)?);
        }
        projected.insert(record.clone(), body);
        for mut review in conflicts.into_iter().chain(field_reviews) {
            review.insert("entity_id".into(), values::write_value(&record)?);
            reviews.push(review);
        }
    }
    for (subject, claim) in &claims {
        if bindings.contains_key(subject) {
            continue;
        }
        let relationships = values::read_array(claim, "relationships")?;
        let only_relationships = !relationships.is_empty()
            && !values::has_value(claim, "fields")
            && !values::has_value(claim, "identifiers")
            && relationships.iter().all(|raw| {
                values::read_value::<Object>(raw)
                    .is_ok_and(|link| values::has_value(&link, "source_subject"))
            });
        if !only_relationships {
            reviews.push(Object::from([
                ("reason".into(), values::write_value(&"binding_required")?),
                ("subject".into(), values::write_value(subject)?),
                (
                    "assertion_id".into(),
                    values::read_optional_value(claim, "assertion_id")?,
                ),
            ]));
        }
    }
    for decision in &overrides {
        if !values::has_value(decision, "subject") {
            reviews.push(Object::from([
                (
                    "reason".into(),
                    values::write_value(&"ambiguous_override_owner")?,
                ),
                (
                    "decision_id".into(),
                    values::read_optional_value(decision, "decision_id")?,
                ),
            ]));
        }
    }
    serde_json::to_string(&(projected, reviews, groups))
        .map_err(|_| "Cannot serialize prepared master records".into())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn command(namespace: &str, left_figi: &str, right_figi: &str) -> String {
        format!(
            r#"{{
              "identities": {{"e1": {{"entity_id": "e1", "kind": "security"}}}},
              "canonical": {{"e1": "e1"}},
              "bindings": {{"s1": "e1", "s2": "e1"}},
              "quarantined": {{}},
              "claims": {{
                "s1": {{"kind": "security", "identifiers": {{"{namespace}": "LEFT"}},
                        "cross_references": {{"share_class_figi": "{left_figi}"}}}},
                "s2": {{"kind": "security", "identifiers": {{"{namespace}": "RIGHT"}},
                        "cross_references": {{"share_class_figi": "{right_figi}"}}}}
              }},
              "policy": {{"kinds": {{"security": {{"version": "t", "defaults": {{"sources": []}}}}}}}},
              "overrides": [],
              "decisions": [{{"operation": "bind", "entity_id": "e1"}}],
              "as_of": "2026-10-24T00:00:00Z",
              "policy_digest": "test",
              "profile_kinds": {{}}
            }}"#
        )
    }

    #[test]
    fn two_isins_that_share_a_figi_stay_on_one_security() {
        let prepared = prepare_master_records(&command("isin", "BBG000000001", "BBG000000001"))
            .expect("shared figi");
        assert!(prepared.contains("\"isin\":[\"LEFT\",\"RIGHT\"]"));
        assert!(!prepared.contains("authoritative_identifier_conflict"));
    }

    #[test]
    fn two_isins_without_one_figi_are_still_refused() {
        let error = prepare_master_records(&command("isin", "BBG000000001", "BBG000000002"))
            .expect_err("different figi");
        assert_eq!(
            error,
            "Identity decision has unresolved authoritative identifier or kind conflict"
        );
    }

    #[test]
    fn two_cusips_are_not_resolved_by_a_shared_figi() {
        let error = prepare_master_records(&command("cusip", "BBG000000001", "BBG000000001"))
            .expect_err("cusip");
        assert_eq!(
            error,
            "Identity decision has unresolved authoritative identifier or kind conflict"
        );
    }
}
