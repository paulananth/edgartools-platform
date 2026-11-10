# Verified Per-Load Quality Evidence

Labels: wayfinder:map

## Destination

Every completed load has immutable, verified quality evidence tied to its run,
step and work unit. Bookkeeping admits and aggregates that evidence; the
existing OpenMetadata APIs retain per-load results and exact readback confirms
publication. Operators can find the history and distinguish confirmed, failed,
pending and incomplete evidence in the shipped UI. Keep the versioned receipt
format disabled until its measured recovery is within an operator-set maximum.

## Notes

- Bookkeeping owns execution, verification admission and run completeness.
  OpenMetadata remains the visibility layer; do not customize its frontend or
  imply catalog publication runs a pipeline.
- Follow `skills/bookkeeping/RECOVERY.md`,
  `skills/openmetadata/SKILL.md`, and
  `skills/openmetadata/references/QUALITY-RESULT-HISTORY.md`.
- Reuse captured local data. Do not request new provider data to complete this
  effort.

## Decisions so far

- Use OpenMetadata as shipped, with its existing APIs and UI.
- Keep incomplete or absent quality evidence unknown. A successful HTTP send is
  not publication until the exact result reads back.
- Require an owner, documented resume procedure, disposable measured resume
  and operator-set maximum recovery time before enabling the new receipt format.
- [Restore Verified Per-Load Quality Evidence](issues/01-verified-per-load-quality-evidence.md): Implementation and package verification were restored and merged with CI passing.
- [Land Per-Load Guidance and Work Map](issues/02-land-quality-history-and-recovery-guidance.md): Guidance merged with the current 12 CI checks passing; legacy results remain latest-only and version-2 recovery remains a manual opt-in.
- [Prove Atomic Attempt Supersession](issues/03-prove-atomic-attempt-supersession.md): PostgreSQL rejects stale completion after precheck and preserves a replacement's evidence.
- [Set and Prove the Recovery Maximum](issues/04-set-and-prove-recovery-maximum.md): The recovery proof found and fixed a defect that made the resume impossible — the version-2 receipt named the attempt and a wall-clock time, so a re-executed unit wrote different bytes to the same immutable output. The receipt now names the work unit and reuses its observation time. Both interruption shapes resume over invented data in a disposable PostgreSQL 16 container, measured at 0.146 s to 0.263 s over nine runs, against the operator's 5-minute maximum. The feature stays disabled pending an enablement decision.
- [Verify a Completed Load End to End](issues/05-verify-a-completed-load-end-to-end.md): An already-captured 10-document load, run in an isolated store because the shared server had other agents' runs open, produced admitted version-2 quality evidence — 1 unit, 168 rows checked, 0 failed — published per load and confirmed by exact readback (timestamp, status, counts and result text). Replay loaded nothing new and re-sent no results. The production rules are unchanged; enablement stays an operator decision.
- [Observe Per-Load History in the Shipped OpenMetadata UI](issues/06-observe-history-in-shipped-openmetadata-ui.md): Two further loads of the same already-captured delivery, under two rules versions so each had its own processing identity, gave the case three published results that each name their own run. The shipped 2.0.7 UI shows the newest result's full load reference and renders history as a chart with no per-point tooltip and no result list, so an older load's result text is readable only through the API. Confirmed, failed and never-run are distinguishable, and a pending or incomplete load cannot be presented as confirmed publication: the result status vocabulary is Success, Failed and Aborted only, and the publisher refuses incomplete evidence without changing the published history.

## Not yet specified


## Out of scope

- Modifications to OpenMetadata's frontend or its pipeline execution behavior.
- New provider acquisition or source activation.
