//! Database-independent control decisions over explicit stored observations.
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

const MANIFEST: &str = "manifest.hash";
const ACCOUNTING: &str = "work.accounting";
const DELIVERED: &str = "journal.delivered";
const CHECK_NAMES: [&str; 3] = [MANIFEST, ACCOUNTING, DELIVERED];
const SUMMARY: [(&str, &str); 3] = [
    ("expected", "expected"),
    ("pending_deliveries", "pending"),
    ("verified", "verified"),
];

#[derive(Deserialize)]
struct Resume {
    run_id: uuid::Uuid,
    state: String,
    compacted: bool,
    checks_token: String,
    completion_token: String,
}

pub fn prepare_run_resume(raw: &str) -> Result<String, String> {
    let input: Resume = serde_json::from_str(raw).map_err(|_| "Invalid resume observations")?;
    if input.compacted {
        return Err("Compacted runs are audit-only; start a new run".into());
    }
    if !["running", "waiting", "blocked", "complete"].contains(&input.state.as_str()) {
        return Err("Invalid resume state".into());
    }
    let wire = BTreeMap::from([
        ("run_id", input.run_id.to_string()),
        ("expected_state", input.state),
        ("expected_checks", hex_bytes(input.checks_token.as_bytes())),
        ("expected_completion", input.completion_token),
        ("state", "running".into()),
        ("checks", hex_bytes(b"{}")),
    ]);
    serde_json::to_string(&wire).map_err(|_| "Cannot prepare run resume".into())
}

#[derive(Deserialize)]
struct RunChecks {
    checks: Vec<String>,
    expected: u64,
    verified: u64,
    pending_deliveries: u64,
    manifest_verified: bool,
}

pub fn prepare_run_checks(raw: &str) -> Result<String, String> {
    let observed: RunChecks = serde_json::from_str(raw).map_err(|_| "Invalid run observations")?;
    let mut checks = BTreeMap::new();
    for name in observed.checks {
        let passed = match name.as_str() {
            MANIFEST => observed.manifest_verified,
            ACCOUNTING => observed.verified == observed.expected,
            DELIVERED => observed.pending_deliveries == 0,
            _ => return Err("Unsupported run check".into()),
        };
        checks.insert(name, passed);
    }
    serde_json::to_string(&checks).map_err(|_| "Cannot prepare run checks".into())
}

#[derive(Deserialize)]
struct Completion {
    run_id: uuid::Uuid,
    expected: u64,
    actual: u64,
    verified: u64,
    pending_deliveries: u64,
    unsealed_expansions: u64,
    checks: BTreeMap<String, bool>,
}

fn hex_bytes(raw: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut text = String::with_capacity(raw.len() * 2);
    for byte in raw {
        text.push(HEX[(byte >> 4) as usize] as char);
        text.push(HEX[(byte & 15) as usize] as char);
    }
    text
}

pub fn prepare_run_completion(raw: &str) -> Result<String, String> {
    let input: Completion =
        serde_json::from_str(raw).map_err(|_| "Invalid completion observations")?;
    for count in [
        input.expected,
        input.actual,
        input.verified,
        input.pending_deliveries,
        input.unsealed_expansions,
    ] {
        if count > i64::MAX as u64 {
            return Err("Invalid completion counter".into());
        }
    }
    if input.verified > input.actual || input.unsealed_expansions > input.actual {
        return Err("Inconsistent completion observations".into());
    }
    if input
        .checks
        .keys()
        .any(|key| !CHECK_NAMES.contains(&key.as_str()))
    {
        return Err("Unsupported run check".into());
    }
    let complete = !input.checks.is_empty()
        && input.checks.values().all(|passed| *passed)
        && input.actual == input.expected
        && input.verified == input.actual
        && input.pending_deliveries == 0
        && input.unsealed_expansions == 0;
    let checks =
        serde_json::to_string(&input.checks).map_err(|_| "Cannot prepare completion checks")?;
    let summary = BTreeMap::from([
        (SUMMARY[0].0, input.expected),
        (SUMMARY[1].0, input.pending_deliveries),
        (SUMMARY[2].0, input.verified),
    ]);
    let summary =
        serde_json::to_string(&summary).map_err(|_| "Cannot prepare completion summary")?;
    let wire = BTreeMap::from([
        ("run_id", input.run_id.to_string()),
        ("expected", input.expected.to_string()),
        ("actual", input.actual.to_string()),
        ("verified", input.verified.to_string()),
        ("pending", input.pending_deliveries.to_string()),
        ("unsealed", input.unsealed_expansions.to_string()),
        (
            "state",
            if complete { "complete" } else { "waiting" }.into(),
        ),
        ("checks", hex_bytes(checks.as_bytes())),
        ("summary", hex_bytes(summary.as_bytes())),
    ]);
    serde_json::to_string(&wire).map_err(|_| "Cannot prepare run completion".into())
}

pub fn completion_storage_contract() -> Result<String, String> {
    #[derive(Serialize)]
    struct SummaryPart {
        prefix: String,
        counter: &'static str,
    }
    #[derive(Serialize)]
    struct Contract {
        checks: Vec<String>,
        passing: Vec<String>,
        summary: Vec<SummaryPart>,
        suffix: &'static str,
    }
    fn enumerate(
        index: usize,
        checks: &mut BTreeMap<&str, bool>,
        all: &mut Vec<String>,
        passing: &mut Vec<String>,
    ) {
        if index == CHECK_NAMES.len() {
            let body = serde_json::to_string(checks).expect("Fixed boolean check contract");
            if !checks.is_empty() && checks.values().all(|value| *value) {
                passing.push(body.clone());
            }
            all.push(body);
            return;
        }
        enumerate(index + 1, checks, all, passing);
        for value in [false, true] {
            checks.insert(CHECK_NAMES[index], value);
            enumerate(index + 1, checks, all, passing);
        }
        checks.remove(CHECK_NAMES[index]);
    }
    let (mut checks, mut passing) = (Vec::new(), Vec::new());
    enumerate(0, &mut BTreeMap::new(), &mut checks, &mut passing);
    checks.sort();
    passing.sort();
    let summary = SUMMARY
        .iter()
        .enumerate()
        .map(|(index, (key, counter))| {
            Ok(SummaryPart {
                prefix: format!(
                    "{}{}:",
                    if index == 0 { "{" } else { "," },
                    serde_json::to_string(key).map_err(|_| "Invalid summary key")?
                ),
                counter,
            })
        })
        .collect::<Result<Vec<_>, String>>()?;
    serde_json::to_string(&Contract {
        checks,
        passing,
        summary,
        suffix: "}",
    })
    .map_err(|_| "Invalid control storage contract".into())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn resume_preparation_preserves_observed_state_and_refuses_compaction() {
        for state in ["running", "waiting", "blocked", "complete"] {
            let raw = format!(
                r#"{{"run_id":"00000000-0000-0000-0000-000000000001","state":"{state}","compacted":false,"checks_token":"{{}}","completion_token":""}}"#
            );
            let wire: BTreeMap<String, String> =
                serde_json::from_str(&prepare_run_resume(&raw).unwrap()).unwrap();
            assert_eq!(wire["expected_state"], state);
            assert_eq!(wire["state"], "running");
            assert_eq!(wire["checks"], "7b7d");
            assert!(prepare_run_resume(&raw.replace("false", "true")).is_err());
            assert!(prepare_run_resume(&raw.replace(state, "invented-state")).is_err());
        }
    }

    #[test]
    fn completion_checks_require_accounting_and_deliveries() {
        assert_eq!(prepare_run_checks(r#"{"checks":["work.accounting","journal.delivered","manifest.hash"],"expected":2,"verified":1,"pending_deliveries":1,"manifest_verified":true}"#).unwrap(),
                   r#"{"journal.delivered":false,"manifest.hash":true,"work.accounting":false}"#);
        assert!(prepare_run_checks(r#"{"checks":["invented"],"expected":0,"verified":0,"pending_deliveries":0,"manifest_verified":true}"#).is_err());
    }

    #[test]
    fn completion_requires_exact_accounting_sealed_children_and_durable_delivery() {
        let good = r#"{"run_id":"00000000-0000-0000-0000-000000000001","expected":2,"actual":2,"verified":2,"pending_deliveries":0,"unsealed_expansions":0,"checks":{"work.accounting":true}}"#;
        let wire: BTreeMap<String, String> =
            serde_json::from_str(&prepare_run_completion(good).unwrap()).unwrap();
        assert_eq!(wire["state"], "complete");
        for (before, after) in [
            ("\"actual\":2", "\"actual\":3"),
            ("\"verified\":2", "\"verified\":1"),
            ("\"pending_deliveries\":0", "\"pending_deliveries\":1"),
            ("\"unsealed_expansions\":0", "\"unsealed_expansions\":1"),
            ("\"work.accounting\":true", "\"work.accounting\":false"),
        ] {
            let wire: BTreeMap<String, String> = serde_json::from_str(
                &prepare_run_completion(&good.replace(before, after)).unwrap(),
            )
            .unwrap();
            assert_eq!(wire["state"], "waiting");
        }
        assert!(prepare_run_completion(&good.replace("\"actual\":2", "\"actual\":1")).is_err());
        assert!(prepare_run_completion(
            &good.replace("\"work.accounting\":true", "\"work.accounting\":1")
        )
        .is_err());
    }
}
