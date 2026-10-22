//! Prepare retained inputs and their indexed references without copying mastered results.

use crate::record_values::{self as values, Object};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Deserialize)]
struct Inputs {
    readings: Vec<Object>,
    decisions: Vec<Object>,
    identities: Vec<Object>,
}

#[derive(Serialize)]
struct Entry {
    #[serde(rename = "type")]
    record_type: String,
    id: String,
    body_json: String,
}

fn retain_input(
    evidence: &mut BTreeMap<(String, String), Entry>,
    entry: Entry,
) -> Result<(), String> {
    let key = (entry.record_type.clone(), entry.id.clone());
    if evidence
        .get(&key)
        .is_some_and(|previous| previous.body_json != entry.body_json)
    {
        return Err("Retained input identity has contradictory content".into());
    }
    evidence.insert(key, entry);
    Ok(())
}

pub(crate) fn lookup_type(name: &str, keys: &[String]) -> Result<String, String> {
    Ok(format!(
        "lookup/{name}/{}",
        values::write_sorted_json(&values::write_value(&keys)?)?
    ))
}

fn describe_reference(record_type: &str, id: &str) -> Result<String, String> {
    values::write_sorted_json(&values::write_value(&Object::from([
        ("type".into(), values::write_value(&record_type)?),
        ("id".into(), values::write_value(&id)?),
        ("immutable".into(), values::write_value(&true)?),
    ]))?)
}

fn retain_reference(
    indexes: &mut BTreeMap<(String, String), Entry>,
    name: &str,
    key: String,
    record_type: &str,
    id: &str,
) -> Result<(), String> {
    let record_type_key = lookup_type(name, &[key])?;
    indexes.insert(
        (record_type_key.clone(), id.into()),
        Entry {
            record_type: record_type_key,
            id: id.into(),
            body_json: describe_reference(record_type, id)?,
        },
    );
    Ok(())
}

pub fn prepare_record_history(raw: &str) -> Result<String, String> {
    let input: Inputs = serde_json::from_str(raw).map_err(|_| "Invalid retained input history")?;
    let mut evidence = BTreeMap::new();
    let mut indexes = BTreeMap::new();
    for reading in input.readings {
        let id = values::read_text(&reading, "assertion_id")?;
        let subject = values::read_text(&reading, "subject")?;
        retain_input(
            &mut evidence,
            Entry {
                record_type: "source-reading".into(),
                id: id.clone(),
                body_json: values::write_sorted_json(&values::write_value(&reading)?)?,
            },
        )?;
        retain_reference(
            &mut indexes,
            "record_readings",
            subject.clone(),
            "source-reading",
            &id,
        )?;
        retain_reference(
            &mut indexes,
            "source_readings",
            values::read_text(&reading, "source_code")?,
            "source-reading",
            &id,
        )?;
        let mut named = BTreeSet::new();
        for raw in values::read_array(&reading, "relationships")? {
            let relationship: Object = values::read_value(&raw)?;
            named.insert(if values::has_value(&relationship, "source_subject") {
                values::read_text(&relationship, "source_subject")?
            } else {
                subject.clone()
            });
            if values::has_value(&relationship, "target_subject") {
                named.insert(values::read_text(&relationship, "target_subject")?);
            }
        }
        for target in named {
            retain_reference(
                &mut indexes,
                "related_readings",
                target,
                "source-reading",
                &id,
            )?;
        }
    }
    for decision in input.decisions {
        let id = values::read_text(&decision, "decision_id")?;
        retain_input(
            &mut evidence,
            Entry {
                record_type: "decision".into(),
                id: id.clone(),
                body_json: values::write_sorted_json(&values::write_value(&decision)?)?,
            },
        )?;
        for name in [
            "subject",
            "entity_id",
            "left",
            "right",
            "target",
            "decision_id",
        ] {
            if values::has_value(&decision, name) {
                retain_reference(
                    &mut indexes,
                    "related_decisions",
                    values::read_text(&decision, name)?,
                    "decision",
                    &id,
                )?;
            }
        }
        if values::read_text(&decision, "operation")? == "retire_source" {
            retain_reference(
                &mut indexes,
                "source_retirements",
                values::read_text(&decision, "source_code")?,
                "decision",
                &id,
            )?;
        }
    }
    for identity in input.identities {
        let id = values::read_text(&identity, "entity_id")?;
        retain_input(
            &mut evidence,
            Entry {
                record_type: "identity".into(),
                id,
                body_json: values::write_sorted_json(&values::write_value(&identity)?)?,
            },
        )?;
    }
    serde_json::to_string(&(
        evidence.into_values().collect::<Vec<_>>(),
        indexes.into_values().collect::<Vec<_>>(),
    ))
    .map_err(|_| "Cannot serialize retained input history".into())
}
