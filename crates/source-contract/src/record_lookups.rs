//! Prepare latest-record pointers and lookup changes from accepted records and bindings.

use crate::record_history::lookup_type;
use crate::record_matches::{prepare_identifier_rules, prepare_identifier_value};
use crate::record_values::{self as values, Object};
use indexmap::IndexMap;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Deserialize)]
struct Inputs {
    readings: Vec<Object>,
    previous: BTreeMap<String, Object>,
    subjects: BTreeSet<String>,
    bindings: BTreeMap<String, String>,
    quarantined: BTreeMap<String, String>,
    policy: Object,
    normalizers: IndexMap<String, bool>,
    batch_id: String,
    occurrences: BTreeMap<String, Object>,
}
#[derive(Serialize)]
struct Entry {
    #[serde(rename = "type")]
    record_type: String,
    id: String,
    body_json: Option<String>,
    removed: bool,
}

fn read_revision(body: &Object) -> Result<(usize, String, usize, String), String> {
    let revision = values::read_optional_value(body, "revision")?;
    let mapping = body
        .get("mapping_version")
        .cloned()
        .unwrap_or(values::write_value(&1)?);
    if !revision.get().bytes().all(|ch| ch.is_ascii_digit())
        || !mapping.get().bytes().all(|ch| ch.is_ascii_digit())
    {
        return Err("Reading revisions must be nonnegative integers".into());
    }
    Ok((
        revision.get().len(),
        revision.get().into(),
        mapping.get().len(),
        mapping.get().into(),
    ))
}
fn read_candidate_keys(reading: &Object) -> Result<Object, String> {
    let identifiers = values::read_object(reading, "identifiers")?;
    let census = values::read_object(
        &values::read_object(&values::read_object(reading, "provenance")?, "matching")?,
        "name_census",
    )?;
    let mut keys = Object::new();
    if values::has_value(&identifiers, "lei") {
        keys.insert("lei".into(), identifiers["lei"].clone());
    }
    if let Some(first) = values::read_array(&census, "leis")?.first() {
        let pair: Vec<values::Document> = values::read_value(first)?;
        if let Some(value) = pair.first() {
            if values::has_content(value) {
                keys.insert("census_lei".into(), value.clone());
            }
        }
    }
    let cascade = values::read_object(&census, "cascade")?;
    if values::has_value(&cascade, "lei") {
        keys.insert("cascade_lei".into(), cascade["lei"].clone());
    }
    Ok(keys)
}
fn collect_entries(
    records: &BTreeMap<String, Object>,
) -> Result<BTreeMap<(String, String), String>, String> {
    let mut entries = BTreeMap::new();
    for (subject, record) in records {
        entries.insert(
            ("source-record".into(), subject.clone()),
            values::write_sorted_json(&values::write_value(record)?)?,
        );
        let pointer = values::write_sorted_json(&values::write_value(&Object::from([(
            "subject".into(),
            values::write_value(subject)?,
        )]))?)?;
        if values::has_value(record, "entity_id") {
            entries.insert(
                (
                    lookup_type("master_members", &[values::read_text(record, "entity_id")?])?,
                    subject.clone(),
                ),
                pointer.clone(),
            );
        }
        let state = if values::has_value(record, "entity_id") {
            "bound"
        } else {
            "unbound"
        };
        for (namespace, raw) in values::read_object(record, "normalized_identifiers")? {
            let value: String = values::read_value(&raw)?;
            let group = lookup_type(
                "identifier_records",
                &[
                    namespace,
                    value,
                    values::read_text(record, "source_code")?,
                    state.into(),
                ],
            )?;
            entries.insert((group, subject.clone()), pointer.clone());
        }
        for (namespace, raw) in values::read_object(record, "cross_references")? {
            if raw.get() == "null" {
                continue;
            }
            entries.insert(
                (
                    lookup_type(
                        "cross_reference_records",
                        &[namespace, values::read_value(&raw)?],
                    )?,
                    subject.clone(),
                ),
                pointer.clone(),
            );
        }
        for (name, raw) in values::read_object(record, "matching_keys")? {
            entries.insert(
                (
                    lookup_type(
                        "name_candidates",
                        &[
                            values::read_text(record, "source_code")?,
                            name,
                            values::read_value(&raw)?,
                        ],
                    )?,
                    subject.clone(),
                ),
                pointer.clone(),
            );
        }
    }
    Ok(entries)
}

pub fn prepare_record_lookups(raw: &str) -> Result<String, String> {
    let input: Inputs =
        serde_json::from_str(raw).map_err(|_| "Invalid source-record lookup inputs")?;
    let contracts = prepare_identifier_rules(&input.policy)?;
    let previous: BTreeMap<_, _> = input
        .previous
        .into_iter()
        .filter(|(subject, _)| input.subjects.contains(subject))
        .collect();
    let mut current = previous.clone();
    let mut ordered = Vec::new();
    for reading in input.readings {
        ordered.push((read_revision(&reading)?, reading));
    }
    ordered.sort_by(|(left, _), (right, _)| left.cmp(right));
    for (revision, reading) in ordered {
        let subject = values::read_text(&reading, "subject")?;
        if !input.subjects.contains(&subject) {
            return Err("A reading lies outside its affected record scope".into());
        }
        let id = values::read_text(&reading, "assertion_id")?;
        if let Some(previous) = current.get(&subject) {
            let before = read_revision(previous)?;
            if revision == before && values::read_text(previous, "assertion_id")? != id {
                return Err("Source native revision has contradictory publications".into());
            }
            if revision <= before {
                continue;
            }
        }
        let mut record = Object::new();
        for name in [
            "subject",
            "source_code",
            "record_key",
            "kind",
            "revision",
            "publication_key",
            "assertion_id",
            "effective_at",
            "identifiers",
        ] {
            record.insert(name.into(), values::read_optional_value(&reading, name)?);
        }
        record.insert(
            "mapping_version".into(),
            reading
                .get("mapping_version")
                .cloned()
                .unwrap_or(values::write_value(&1)?),
        );
        record.insert(
            "cross_references".into(),
            values::write_value(&values::read_object(&reading, "cross_references")?)?,
        );
        record.insert(
            "matching_keys".into(),
            values::write_value(&read_candidate_keys(&reading)?)?,
        );
        record.insert("batch_id".into(), values::write_value(&input.batch_id)?);
        record.insert(
            "bronze".into(),
            input
                .occurrences
                .get(&id)
                .map(|occurrence| {
                    let mut origin = Object::new();
                    for name in ["object", "sha256", "locator"] {
                        origin.insert(name.into(), values::read_optional_value(occurrence, name)?);
                    }
                    values::write_value(&origin)
                })
                .transpose()?
                .unwrap_or(values::write_value(&())?),
        );
        current.insert(subject, record);
    }
    for (subject, record) in &mut current {
        record.insert(
            "entity_id".into(),
            values::write_value(&input.bindings.get(subject))?,
        );
        record.insert(
            "quarantined_id".into(),
            values::write_value(&input.quarantined.get(subject))?,
        );
        let mut normalized = Object::new();
        for (namespace, raw) in values::read_object(record, "identifiers")? {
            if raw.get() == "null" {
                continue;
            }
            let value = prepare_identifier_value(
                &contracts,
                &namespace,
                &values::read_value::<String>(&raw)?,
                &input.normalizers,
            )?;
            normalized.insert(namespace, values::write_value(&value)?);
        }
        record.insert(
            "normalized_identifiers".into(),
            values::write_value(&normalized)?,
        );
    }
    let before = collect_entries(&previous)?;
    let after = collect_entries(&current)?;
    let mut changes = Vec::new();
    for ((record_type, id), body) in &after {
        if before.get(&(record_type.clone(), id.clone())) != Some(body) {
            changes.push(Entry {
                record_type: record_type.clone(),
                id: id.clone(),
                body_json: Some(body.clone()),
                removed: false,
            });
        }
    }
    for ((record_type, id), _) in before {
        if !after.contains_key(&(record_type.clone(), id.clone())) {
            changes.push(Entry {
                record_type,
                id,
                body_json: None,
                removed: true,
            });
        }
    }
    changes
        .sort_by(|left, right| (&left.record_type, &left.id).cmp(&(&right.record_type, &right.id)));
    serde_json::to_string(&(current, changes))
        .map_err(|_| "Cannot serialize source-record lookup changes".into())
}
