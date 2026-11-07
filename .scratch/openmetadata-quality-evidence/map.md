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
- [Restore Verified Per-Load Quality Evidence](issues/01-verified-per-load-quality-evidence.md): [Restore verified per-load OpenMetadata quality results](https://github.com/paulananth/edgartools-platform/pull/1484) merged with CI passing; the remaining attempt, recovery, and UI gates stay open in their own tickets.

## Not yet specified


## Out of scope

- Modifications to OpenMetadata's frontend or its pipeline execution behavior.
- New provider acquisition or source activation.
