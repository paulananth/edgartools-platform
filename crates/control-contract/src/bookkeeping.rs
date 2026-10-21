//! Database-independent control decisions over explicit stored observations.
use super::{canonical, read, Document};
use chrono::{DateTime, Utc};
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

#[derive(Deserialize)]
struct CaptureRun {
    run_id: String,
    state: String,
    capture: Option<Document>,
    created_at: DateTime<Utc>,
    compacted_at: Option<DateTime<Utc>>,
}

pub fn select_latest_capture(raw: &str) -> Result<String, String> {
    let runs: Vec<CaptureRun> =
        serde_json::from_str(raw).map_err(|_| "Invalid capture observations")?;
    let mut groups: BTreeMap<String, Vec<CaptureRun>> = BTreeMap::new();
    for run in runs {
        if !matches!(
            run.state.as_str(),
            "running" | "waiting" | "blocked" | "complete"
        ) {
            return Err("Invalid capture run state".into());
        }
        let key = run
            .capture
            .as_ref()
            .map(|value| canonical(value))
            .transpose()?
            .unwrap_or("null".into());
        groups.entry(key).or_default().push(run);
    }
    // A rerun of an older capture must not make it the newest capture. Group
    // creation order is its earliest start, then its independently earliest id.
    let latest = groups.values().max_by_key(|runs| {
        (
            runs.iter().map(|run| run.created_at).min(),
            runs.iter().map(|run| run.run_id.as_str()).min(),
        )
    });
    let Some(latest) = latest else {
        return Ok("[]".into());
    };
    let open = latest
        .iter()
        .filter(|run| matches!(run.state.as_str(), "running" | "waiting"))
        .count();
    if open != 0 {
        return Err(format!(
            "The newest capture has {open} runs not finished; finish them first"
        ));
    }
    let compacted = latest
        .iter()
        .filter(|run| run.state == "complete" && run.compacted_at.is_some())
        .count();
    if compacted != 0 {
        return Err(format!("The newest capture has {compacted} compacted runs; run that target again over a capture"));
    }
    let mut selected: Vec<&str> = latest
        .iter()
        .filter(|run| run.state == "complete")
        .map(|run| run.run_id.as_str())
        .collect();
    selected.sort_unstable();
    serde_json::to_string(&selected).map_err(|_| "Cannot select capture runs".into())
}

#[derive(Deserialize, Serialize)]
struct VerifiedUnit {
    run: String,
    step: String,
    key: String,
    sha256: String,
    #[serde(skip_serializing)]
    completed_at: DateTime<Utc>,
}

impl VerifiedUnit {
    fn order(&self) -> (DateTime<Utc>, &str, &str) {
        (self.completed_at, self.run.as_str(), self.key.as_str())
    }
}

pub fn select_verified_units(raw: &str) -> Result<String, String> {
    let raw: Document =
        serde_json::from_str(raw).map_err(|_| "Invalid verified unit observations")?;
    let units: Vec<VerifiedUnit> = read(&raw)?;
    let mut hashes: BTreeMap<String, VerifiedUnit> = BTreeMap::new();
    for unit in units {
        if !super::valid_hash(&unit.sha256) {
            return Err("Verified unit has no valid output hash".into());
        }
        let held = hashes
            .entry(unit.sha256.clone())
            .or_insert_with(|| VerifiedUnit {
                run: unit.run.clone(),
                step: unit.step.clone(),
                key: unit.key.clone(),
                sha256: unit.sha256.clone(),
                completed_at: unit.completed_at,
            });
        if unit.order() < held.order() {
            *held = unit;
        }
    }
    let mut units: Vec<_> = hashes.into_values().collect();
    units.sort_by(|left, right| left.order().cmp(&right.order()));
    serde_json::to_string(&units).map_err(|_| "Cannot select verified units".into())
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

    #[test]
    fn old_capture_rerun_never_changes_capture_creation_order() {
        let runs = r#"[
          {"run_id":"a","state":"complete","capture":{"sha256":"old"},"created_at":"2026-01-01T00:00:00Z"},
          {"run_id":"b","state":"complete","capture":{"sha256":"new"},"created_at":"2026-02-01T00:00:00Z"},
          {"run_id":"c","state":"complete","capture":{"sha256":"old"},"created_at":"2026-03-01T00:00:00Z"}]
        "#;
        assert_eq!(select_latest_capture(runs).unwrap(), r#"["b"]"#);
    }

    #[test]
    fn unfinished_latest_capture_is_refused_but_a_blocked_one_is_abandoned() {
        for state in ["running", "waiting"] {
            let raw = format!(
                r#"[{{"run_id":"a","state":"{state}","created_at":"2026-01-01T00:00:00Z"}}]"#
            );
            assert!(select_latest_capture(&raw)
                .unwrap_err()
                .contains("1 runs not finished"));
        }
        assert_eq!(
            select_latest_capture(
                r#"[{"run_id":"a","state":"blocked","created_at":"2026-01-01T00:00:00Z"}]"#
            )
            .unwrap(),
            "[]"
        );
        assert!(select_latest_capture(r#"[{"run_id":"a","state":"complete","created_at":"2026-01-01T00:00:00Z","compacted_at":"2026-01-02T00:00:00Z"}]"#).unwrap_err().contains("1 compacted"));
    }

    #[test]
    fn duplicate_output_chooses_earliest_completion_then_run_and_key() {
        let hash = "a".repeat(64);
        let raw = format!(
            r#"[
          {{"run":"b","step":"read","key":"z","sha256":"{hash}","completed_at":"2026-01-02T00:00:00Z"}},
          {{"run":"a","step":"read","key":"z","sha256":"{hash}","completed_at":"2026-01-01T00:00:00Z"}},
          {{"run":"a","step":"read","key":"a","sha256":"{hash}","completed_at":"2026-01-01T00:00:00Z"}}]"#
        );
        assert_eq!(
            select_verified_units(&raw).unwrap(),
            format!(r#"[{{"run":"a","step":"read","key":"a","sha256":"{hash}"}}]"#)
        );
    }
}
