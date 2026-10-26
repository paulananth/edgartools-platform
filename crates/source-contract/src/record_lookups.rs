//! Prepare latest-record pointers and lookup changes from accepted records and bindings.

use crate::record_history::lookup_type;
use crate::record_matches::{prepare_identifier_rules, prepare_identifier_value};
use crate::record_values::{self as values, Object};
use indexmap::IndexMap;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
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
    candidate_routes: BTreeMap<String, Vec<PathSegment>>,
}

#[derive(Deserialize, Serialize)]
#[serde(untagged)]
enum PathSegment {
    Field(String),
    Index(usize),
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
fn read_candidate_keys(
    reading: &Object,
    routes: &BTreeMap<String, Vec<PathSegment>>,
) -> Result<Object, String> {
    let mut keys = Object::new();
    for (name, path) in routes {
        let mut current = match &path[0] {
            PathSegment::Field(field) => reading.get(field).cloned(),
            PathSegment::Index(_) => None,
        };
        for part in &path[1..] {
            current = match (current, part) {
                (Some(raw), PathSegment::Field(field)) => {
                    values::read_value::<Object>(&raw)
                        .ok()
                        .and_then(|mut body| body.shift_remove(field))
                }
                (Some(raw), PathSegment::Index(index)) => values::read_value::<Vec<values::Document>>(&raw)
                    .ok()
                    .and_then(|array| array.get(*index).cloned()),
                (None, _) => None,
            };
        }
        if let Some(raw) = current {
            if values::read_value::<String>(&raw).is_ok_and(|value| !value.is_empty()) {
                keys.insert(name.clone(), raw);
            }
        }
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
            for value in values::read_identifier_values(&raw)? {
                let group = lookup_type(
                    "identifier_records",
                    &[
                        namespace.clone(),
                        value,
                        values::read_text(record, "source_code")?,
                        state.into(),
                    ],
                )?;
                entries.insert((group, subject.clone()), pointer.clone());
            }
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
    if input.candidate_routes.iter().any(|(name, path)| name.is_empty() || path.is_empty()
        || path.iter().any(|part| matches!(part, PathSegment::Field(field) if field.is_empty()))) {
        return Err("Candidate routes require names and nonempty paths".into());
    }
    let contracts = prepare_identifier_rules(&input.policy)?;
    let route_bytes = serde_json::to_vec(&input.candidate_routes)
        .map_err(|_| "Invalid candidate route declaration")?;
    let route_digest = format!("{:x}", Sha256::digest(route_bytes));
    let available: BTreeMap<_, _> = input.readings.iter()
        .map(|reading| Ok((values::read_text(reading, "assertion_id")?, reading)))
        .collect::<Result<_, String>>()?;
    let previous: BTreeMap<_, _> = input
        .previous
        .into_iter()
        .filter(|(subject, _)| input.subjects.contains(subject))
        .collect();
    let mut current = previous.clone();
    let mut ordered = Vec::new();
    for reading in &input.readings {
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
        let latest_id = values::read_text(record, "assertion_id")?;
        if let Some(reading) = available.get(&latest_id) {
            record.insert("matching_keys".into(),
                values::write_value(&read_candidate_keys(reading, &input.candidate_routes)?)?);
            record.insert("matching_routes_sha256".into(), values::write_value(&route_digest)?);
        } else if values::read_text(record, "matching_routes_sha256").ok().as_deref()
            != Some(route_digest.as_str()) {
            return Err("Changed candidate routes require the retained latest reading".into());
        }
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
            let found = values::read_identifier_values(&raw)?
                .iter()
                .map(|value| {
                    prepare_identifier_value(&contracts, &namespace, value, &input.normalizers)
                })
                .collect::<Result<Vec<_>, _>>()?;
            if found.is_empty() {
                continue;
            }
            normalized.insert(namespace, values::write_identifier_values(&found, &raw)?);
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

#[derive(Deserialize)]
struct Projection {
    #[serde(rename = "type")]
    record_type: String,
    id: String,
    body: Object,
}

#[derive(Deserialize)]
struct ScopeInputs {
    previous: Vec<Projection>,
    objects: Vec<Projection>,
    identities: Vec<Object>,
    previous_publications: BTreeMap<String, Object>,
}

fn projection_entries(
    objects: &[Projection],
) -> Result<BTreeMap<(String, String), String>, String> {
    let mut entries = BTreeMap::new();
    let mut seen = BTreeSet::new();
    for object in objects {
        if object.id.is_empty() || !seen.insert((&object.record_type, &object.id)) {
            return Err("Projection keys require distinct nonempty identities".into());
        }
        let mut groups = BTreeSet::new();
        match object.record_type.as_str() {
            "entity" => {
                if values::read_text(&object.body, "entity_id")? != object.id {
                    return Err("Projection identity differs from its key".into());
                }
            }
            "relationship" => {
                if values::read_text(&object.body, "relationship_id")? != object.id {
                    return Err("Projection identity differs from its key".into());
                }
                groups.insert(lookup_type(
                    "outgoing_links",
                    &[values::read_text(&object.body, "source_id")?],
                )?);
                groups.insert(lookup_type(
                    "incoming_links",
                    &[values::read_text(&object.body, "target_id")?],
                )?);
            }
            "review" => {
                let flag = |name: &str| -> Result<bool, String> {
                    object.body.get(name).filter(|raw| raw.get() != "null")
                        .map(|raw| values::read_value::<bool>(raw)).transpose()
                        .map(|value| value.unwrap_or(false))
                };
                if flag("waiting_for_end")? && !flag("retired")? {
                    groups.insert(lookup_type("waiting_reviews", &[])?);
                }
                // Generated reviews are addressed by the projection envelope.
                // Older transports also carry an explicit identity; when present
                // it must agree, without adding a field to retained review bytes.
                for field in ["review_id", "deferred_id"] {
                    if object.body.contains_key(field)
                        && values::read_text(&object.body, field)? != object.id
                    {
                        return Err("Projection identity differs from its key".into());
                    }
                }
                let mut keys = BTreeSet::new();
                for field in ["entity_id", "subject"] {
                    if values::has_value(&object.body, field) {
                        keys.insert(values::read_text(&object.body, field)?);
                    }
                }
                for field in ["affected_subjects", "affected_entities", "entities"] {
                    if values::has_value(&object.body, field) {
                        for raw in values::read_array(&object.body, field)? {
                            keys.insert(values::read_value::<String>(&raw)?);
                        }
                    }
                }
                for key in keys {
                    groups.insert(lookup_type("related_reviews", &[key])?);
                }
            }
            _ => return Err("Unsupported current projection index type".into()),
        }
        let pointer = values::write_sorted_json(&values::write_value(&Object::from([
            ("type".into(), values::write_value(&object.record_type)?),
            ("id".into(), values::write_value(&object.id)?),
            ("immutable".into(), values::write_value(&false)?),
        ]))?)?;
        for group in groups {
            entries.insert((group, object.id.clone()), pointer.clone());
        }
    }
    Ok(entries)
}

/// Storage keys for projected links/reviews and monotonic identity publication floors.
/// The caller saves these with the projections and retained identities atomically.
pub fn prepare_scope_lookups(raw: &str) -> Result<String, String> {
    let input: ScopeInputs =
        serde_json::from_str(raw).map_err(|_| "Invalid scope lookup inputs")?;
    let before = projection_entries(&input.previous)?;
    let after = projection_entries(&input.objects)?;
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
    let mut publications = input.previous_publications.clone();
    for (kind, body) in &publications {
        if body.len() != 3 || values::read_text(body, "kind")? != *kind {
            return Err("Invalid retained identity publication floor".into());
        }
        values::read_text(body, "entity_id")?;
        values::read_time(&values::read_text(body, "published_at")?)?;
    }
    for identity in input.identities {
        let kind = values::read_text(&identity, "kind")?;
        let id = values::read_text(&identity, "entity_id")?;
        let at = values::read_text(&identity, "published_at")?;
        let instant = values::read_time(&at)?;
        let newer = match publications.get(&kind) {
            None => true,
            Some(previous) => {
                (instant, id.clone())
                    > (
                        values::read_time(&values::read_text(previous, "published_at")?)?,
                        values::read_text(previous, "entity_id")?,
                    )
            }
        };
        if newer {
            publications.insert(
                kind.clone(),
                Object::from([
                    ("kind".into(), values::write_value(&kind)?),
                    ("entity_id".into(), values::write_value(&id)?),
                    ("published_at".into(), values::write_value(&at)?),
                ]),
            );
        }
    }
    for (kind, body) in &publications {
        let serialized = values::write_sorted_json(&values::write_value(body)?)?;
        let previous = input
            .previous_publications
            .get(kind)
            .map(|body| values::write_value(body).and_then(|raw| values::write_sorted_json(&raw)))
            .transpose()?;
        if previous.as_ref() != Some(&serialized) {
            changes.push(Entry {
                record_type: "identity-publication".into(),
                id: kind.clone(),
                body_json: Some(serialized),
                removed: false,
            });
        }
    }
    changes.sort_by(|a, b| (&a.record_type, &a.id).cmp(&(&b.record_type, &b.id)));
    serde_json::to_string(&(publications, changes))
        .map_err(|_| "Cannot serialize scope lookup changes".into())
}

#[cfg(test)]
mod waiting_index_tests {
    use super::*;

    #[test]
    fn waiting_reviews_leave_the_index_when_retired_or_resolved() {
        let projection = |waiting: bool, retired: bool| -> Projection {
            serde_json::from_str(&format!(
                r#"{{"type":"review","id":"invented-review","body":{{"waiting_for_end":{waiting},"retired":{retired}}}}}"#
            )).unwrap()
        };
        let group = lookup_type("waiting_reviews", &[]).unwrap();
        let active = projection_entries(&[projection(true, false)]).unwrap();
        assert!(active.contains_key(&(group.clone(), "invented-review".into())));
        for object in [projection(false, false), projection(true, true)] {
            assert!(!projection_entries(&[object]).unwrap()
                .contains_key(&(group.clone(), "invented-review".into())));
        }
    }
}
