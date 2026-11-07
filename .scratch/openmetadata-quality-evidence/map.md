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
- PR [Preserve verified per-load quality evidence for OpenMetadata (#1479)](https://github.com/paulananth/edgartools-platform/pull/1479),
  [Report Bookkeeping load evidence in OpenMetadata (#1432)](https://github.com/paulananth/edgartools-platform/pull/1432),
  and [Explain OpenMetadata catalog and per-load visibility (#1418)](https://github.com/paulananth/edgartools-platform/pull/1418)
  were closed at the operator's request. Their branches remain preserved.
  Restore implementation work on a fresh branch from current `main`.

## Decisions so far

- Use OpenMetadata as shipped, with its existing APIs and UI.
- Keep incomplete or absent quality evidence unknown. A successful HTTP send is
  not publication until the exact result reads back.
- Require an owner, documented resume procedure, disposable measured resume
  and operator-set maximum recovery time before enabling the new receipt format.

## Not yet specified

- The recovery-time maximum; set it after measuring a disposable resume in
  [Set and Prove the Recovery Maximum](issues/04-set-and-prove-recovery-maximum.md).
- Which existing captured local run is suitable for end-to-end verification;
  select it after read-only inspection in
  [Verify a Completed Load End to End](issues/05-verify-a-completed-load-end-to-end.md).

## Out of scope

- Modifications to OpenMetadata's frontend or its pipeline execution behavior.
- New provider acquisition or source activation.
