# Measure EDGARTOOLS_PROD load timelines

## Destination

A decision-complete measurement specification for the `EDGARTOOLS_PROD` load timeline: every
source/target's start and completion time is either proven from retained evidence or explicitly
unavailable, the entity-kind timeline is assembled from active Dataset Contracts, and one private
report can be produced without any new production write unless the operator authorizes it at the
point of risk. Reaching the end of this map means the measurement is fully specified and nothing
about how to measure it is still an open question; the measurement itself is then handed off to
whoever runs it.

## Notes

- Domain: the production data platform — MDM (mastering), Silver, Bookkeeping (work control) and
  the Change Journal. Read `CONTEXT.md` for the business words; translate engine terms before
  using them.
- Skills every session should consult: `data-operations` (the repository's copy at
  `skills/data-operations/SKILL.md`; the installed skill bundle does not carry it),
  `mdm-engineering`, `bookkeeping`, `change-journal`, and `aws-snowflake-operations` before any
  Snowflake command.
- Standing preferences for this effort:
  - Retained evidence first. No provider request, no capture target, no reset, no replay, no
    credential rotation as part of a measurement.
  - Never print or copy credentials, DSNs, host values, source row values, record identifiers or
    raw Snowflake output. The retained `create-instance.json` is credential-bearing and is never
    read raw.
  - A timestamp that is not retained is `unavailable` with a reason. A file modification time is
    never a substitute for an event timestamp.
  - A run's step intervals are event intervals, not CPU time. Target wall time is never a sum of
    step intervals.
  - Source-record counts are never presented as unique master counts.
  - Every time shown to the operator is local ET.
- The qualification gate on Snowflake Postgres is recorded as deferred in
  `docs/specs/mdm/state-of-build.md`. A newer approved evidence record may clear it; until then no
  new production source load is submitted.
- The full approved measurement plan this map decomposes is at `local://measure-prod-mdm-loads-plan.md`.

## Decisions so far

<!-- one line per closed ticket; the detail lives in the ticket -->
- [Is the hosted Snowflake Postgres qualification and credential gate cleared?](issues/01-hosted-qualification-and-credential-gate.md): both gates stay closed, and the live env files still carry the unrotated credentials, so the measurement is retrospective-only.
- [Which initialization timestamps are actually retained?](issues/02-retained-initialization-timestamps.md): the instance request start and end are exact, but the READY transition and per-store migration durations are unavailable, so the init-to-final interval stays null.
- [What is the exact source/target inventory and dependency order for this checkout?](issues/03-source-target-inventory-and-dependencies.md): 17 measured names, no hard source dependency in the sequence, and 13 contributing contracts from the merge-kind files.
- [Which retained runs can be verified, and how does the evidence join?](issues/04-retained-run-evidence-join.md): the Bookkeeping export is the only run-state source, the load logs join to it on run id for half the invocations, and the rebuilt manifest tree is a separate later wave with no verification state.

## Not yet specified

- The per-target evidence package's shape: how the retained load logs, the
  `hosted-prod/manifests/load/<source>/<target>/` bundle manifests and the Bookkeeping run records
  join into one per-target evidence row once the evidence tickets report. The join key and the
  precedence between a log summary and a Bookkeeping status are not yet sharp.
- What a target that was never loaded in production looks like in the report: absent from the
  timeline, or present as `blocked` with the reason. The entity-kind completion rule depends on
  this answer.
- How the report presents a target whose retained evidence covers only part of its declared steps
  (for example a `local: true` target's local read work, or a `mastering_other_keys` target that
  is not one of the 13 sequence entries).
- Whether the per-source wall time for a source with two targets (GLEIF, ADV, ownership) is one
  interval spanning both or two intervals, once the entity timeline's contribution model is set.

## Out of scope

- Credential rotation of the MDM application and admin credentials. The plan treats them as
  exposed and requires rotation before further production access, but rotation is an operator
  action with its own procedure, not a measurement decision.
- Resetting, rebuilding or cold-replaying `EDGARTOOLS_PROD`. The environment is already
  populated; the measurement reads it.
- Running capture targets, the separate `sec.company/merge-batch` target, or any provider request.
- Counting MDM masters directly from implementation tables. The current CLI exposes no approved
  record-reader count.
