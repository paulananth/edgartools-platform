//! Replay retained decisions through the single identity kernel, preserving exact payloads.

use crate::identity::{self, Decision, Identity};
use crate::record_values::{self as values, Object};
use serde::Deserialize;
use std::collections::{HashMap, HashSet};

#[derive(Deserialize)]
struct Command {
    identities: Vec<Object>,
    decisions: Vec<Object>,
    as_of: String,
}

fn read_optional_text(body: &Object, name: &str) -> Result<Option<String>, String> {
    body.get(name)
        .map(|raw| values::read_value(raw))
        .transpose()
        .map(Option::flatten)
}

fn read_record_key(body: &Object, name: &str) -> Result<Option<String>, String> {
    body.get(name)
        .map(|raw| {
            if raw.get().starts_with('"') {
                values::read_value(raw)
            } else {
                Ok(match raw.get() {
                    "null" => "None",
                    "true" => "True",
                    "false" => "False",
                    other => other,
                }
                .into())
            }
        })
        .transpose()
}

fn read_instant(body: &Object, name: &str) -> Result<i64, String> {
    Ok(values::read_time(&values::read_text(body, name)?)?.timestamp_micros())
}

pub fn replay_record_decisions(raw: &str) -> Result<String, String> {
    let command: Command = serde_json::from_str(raw).map_err(|_| "Invalid decision inputs")?;
    let clock = values::read_time(&command.as_of)?.timestamp_micros();
    let identities = command
        .identities
        .iter()
        .map(|body| {
            Ok(Identity {
                id: read_record_key(body, "entity_id")?.ok_or("Missing identity")?,
                kind: values::read_text(body, "kind")?,
                published: read_instant(body, "published_at")?,
            })
        })
        .collect::<Result<Vec<_>, String>>()?;
    let mut active = Vec::new();
    for (position, body) in command.decisions.into_iter().enumerate() {
        let at = read_instant(&body, "at")?;
        if at <= clock {
            active.push((body, at, position));
        }
    }
    let mut revoked = HashSet::new();
    let mut by_id = HashMap::new();
    for (body, _, _) in &active {
        let operation = values::read_text(body, "operation")?;
        by_id.insert(values::read_text(body, "decision_id")?, operation.clone());
        if ["reverse", "revoke"].contains(&operation.as_str()) {
            if let Some(target) = body
                .get("target")
                .and_then(|raw| values::read_value::<String>(raw).ok())
            {
                revoked.insert(target);
            }
        }
    }
    let mut decisions = Vec::with_capacity(active.len());
    for (body, at, _) in &active {
        let id = values::read_text(body, "decision_id")?;
        let op = values::read_text(body, "operation")?;
        let target = if ["reverse", "revoke"].contains(&op.as_str()) {
            read_optional_text(body, "target")?
        } else {
            None
        };
        let named = ["bind", "quarantine"].contains(&op.as_str())
            || (op == "revoke"
                && target
                    .as_ref()
                    .and_then(|id| by_id.get(id))
                    .is_some_and(|op| op == "bind"));
        let live_merge = op == "merge" && !revoked.contains(&id);
        let evidence = values::has_value(body, "evidence");
        let expires = if op == "override"
            && !revoked.contains(&id)
            && evidence
            && values::has_value(body, "expires_at")
        {
            Some(read_instant(body, "expires_at")?)
        } else {
            None
        };
        decisions.push(Decision {
            id,
            at: *at,
            op: op.clone(),
            target,
            subject: if named {
                read_optional_text(body, "subject")?
            } else {
                None
            },
            entity: if named {
                read_record_key(body, "entity_id")?
            } else {
                None
            },
            entity_present: values::has_value(body, "entity_id"),
            left: read_record_key(body, "left")?,
            right: read_record_key(body, "right")?,
            survivor: if live_merge && values::has_value(body, "survivor") {
                read_optional_text(body, "survivor")?
            } else {
                None
            },
            source: if op == "retire_source" {
                read_optional_text(body, "source_code")?
            } else {
                None
            },
            expires,
            evidence,
            depends: if live_merge {
                body.get("depends_on")
                    .map(|raw| values::read_value(raw))
                    .transpose()?
                    .unwrap_or_default()
            } else {
                Vec::new()
            },
        });
    }
    let state = identity::replay(identities, decisions, clock)?;
    let overrides: Vec<_> = state
        .overrides
        .iter()
        .map(|index| &active[*index].0)
        .collect();
    let result = Object::from([
        ("canonical".into(), values::write_value(&state.canonical)?),
        ("bindings".into(), values::write_value(&state.bindings)?),
        ("exclusions".into(), values::write_value(&state.exclusions)?),
        ("overrides".into(), values::write_value(&overrides)?),
        (
            "override_positions".into(),
            values::write_value(
                &state
                    .overrides
                    .iter()
                    .map(|index| active[*index].2)
                    .collect::<Vec<_>>(),
            )?,
        ),
        ("retired".into(), values::write_value(&state.retired)?),
        (
            "quarantined".into(),
            values::write_value(&state.quarantined)?,
        ),
    ]);
    serde_json::to_string(&result).map_err(|_| "Cannot serialize replayed decisions".into())
}

/// Owned records that are unbound must not fall back to their old stored binding.
pub fn resolve_record_bindings(raw: &str) -> Result<String, String> {
    #[derive(Deserialize)]
    struct Inputs {
        subjects: Vec<String>,
        bindings: indexmap::IndexMap<String, String>,
        canonical: indexmap::IndexMap<String, String>,
    }
    let input: Inputs = serde_json::from_str(raw).map_err(|_| "Invalid record binding inputs")?;
    let mut result = indexmap::IndexMap::new();
    for subject in input.subjects {
        let record = input
            .bindings
            .get(&subject)
            .map(|identity| {
                input
                    .canonical
                    .get(identity)
                    .cloned()
                    .ok_or_else(|| "Unknown bound identity".to_owned())
            })
            .transpose()?;
        result.insert(subject, record);
    }
    serde_json::to_string(&result).map_err(|_| "Cannot serialize current record bindings".into())
}
