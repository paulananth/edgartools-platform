//! Request only the retained records and decisions that make affected identities whole.

use crate::record_history::lookup_type;
use crate::record_values::{self as values, Object};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
use uuid::Uuid;

#[derive(Deserialize)]
struct Inputs {
    assertions: Vec<Object>,
    decisions: Vec<Object>,
    retained_readings: Vec<Object>,
    retained_decisions: Vec<Object>,
    completed_lookups: BTreeSet<String>,
    completed_identities: BTreeSet<String>,
}

#[derive(Serialize)]
struct Plan {
    lookups: BTreeSet<String>,
    identities: BTreeSet<String>,
    subjects: BTreeSet<String>,
    ready: bool,
}

fn collect_named_records(decision: &Object, keys: &mut BTreeSet<String>) -> Result<(), String> {
    for name in [
        "subject",
        "entity_id",
        "left",
        "right",
        "target",
        "decision_id",
    ] {
        if values::has_value(decision, name) {
            keys.insert(values::read_text(decision, name)?);
        }
    }
    Ok(())
}

pub fn plan_affected_records(raw: &str) -> Result<String, String> {
    let input: Inputs = serde_json::from_str(raw).map_err(|_| "Invalid affected record inputs")?;
    let mut keys = BTreeSet::new();
    let mut plan = Plan {
        lookups: BTreeSet::new(),
        identities: BTreeSet::new(),
        subjects: BTreeSet::new(),
        ready: false,
    };
    for record in &input.assertions {
        keys.insert(values::read_text(record, "subject")?);
    }
    for decision in &input.decisions {
        collect_named_records(decision, &mut keys)?;
        if values::read_text(decision, "operation")? == "retire_source" {
            let index = lookup_type(
                "source_readings",
                &[values::read_text(decision, "source_code")?],
            )?;
            if !input.completed_lookups.contains(&index) {
                plan.lookups.insert(index);
            }
        }
    }
    // Readings already fetched for source retirement contribute their subjects.
    for record in &input.retained_readings {
        keys.insert(values::read_text(record, "subject")?);
    }
    for decision in &input.retained_decisions {
        collect_named_records(decision, &mut keys)?;
    }
    for key in &keys {
        let index = lookup_type("related_decisions", &[key.clone()])?;
        if !input.completed_lookups.contains(&index) {
            plan.lookups.insert(index);
        }
    }
    // The decision closure must be whole before deciding record membership.
    if !plan.lookups.is_empty() {
        return serde_json::to_string(&plan)
            .map_err(|_| "Cannot serialize affected record requests".into());
    }
    let ids: BTreeSet<_> = keys
        .iter()
        .filter_map(|key| Uuid::parse_str(key).ok().map(|id| id.to_string()))
        .collect();
    let decision_ids: BTreeSet<_> = input
        .decisions
        .iter()
        .chain(&input.retained_decisions)
        .map(|decision| values::read_text(decision, "decision_id"))
        .collect::<Result<_, _>>()?;
    plan.subjects = keys
        .difference(&ids)
        .filter(|key| !decision_ids.contains(*key))
        .cloned()
        .collect();
    for subject in &plan.subjects {
        let index = lookup_type("record_readings", &[subject.clone()])?;
        if !input.completed_lookups.contains(&index) {
            plan.lookups.insert(index);
        }
    }
    let sources: BTreeSet<_> = input
        .assertions
        .iter()
        .chain(&input.retained_readings)
        .map(|record| values::read_text(record, "source_code"))
        .collect::<Result<_, _>>()?;
    for source in sources {
        let index = lookup_type("source_retirements", &[source])?;
        if !input.completed_lookups.contains(&index) {
            plan.lookups.insert(index);
        }
    }
    plan.identities = ids
        .difference(&input.completed_identities)
        .cloned()
        .collect();
    plan.ready = plan.lookups.is_empty() && plan.identities.is_empty();
    serde_json::to_string(&plan).map_err(|_| "Cannot serialize affected record requests".into())
}
