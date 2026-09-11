wayfinder:map

## Destination

All existing hand-copied Step Functions duplication across `load_history` and
`daily_incremental` — the windowed fundamentals-mode stage (3 instances) and
the force-capable fetch trio (4 instances) — is replaced by two shared,
unit-tested factory functions in a new `infra/scripts/pipeline_stage_helpers.py`
module, with byte-identical-output regression proof for every migrated call
site. Reaching the end of this map means the spec is fully implemented,
reviewed, and merged — not just designed.

## Notes

**This map carries execution into itself** (the stated override to
wayfinder's default "plan, don't do" — every ticket here is a build task,
not an open decision). `/to-spec` + `/gof-pattern-selector` already settled
every design question; the merged
[spec](spec.md) (PR #600, corrected in place post-merge for the
subprocess-isolation finding — `write_load_history_definition` and
`write_warehouse_mdm_gold_definition` are independent `python3 -` subprocesses
with no shared runtime, so the two functions live in a new sibling module
imported via `sys.path.insert(0, SCRIPT_DIR)`, exactly as `mdm_tail_helper.py`
already established) is the source design document every ticket implements.

A `/gof-refactor-reviewer` consult already ran against the pre-code plan and
returned three corrections, already folded into Ticket 01 below:
`EcsNetworkContext` bundles the four network params instead of repeating them
across both public functions; `choice_comment` is generated from
`fetch_state_name` inside `force_capable_fetch_stage` rather than threaded in
as a parameter (the ADV/FirmRoster wording difference is a copy-paste
accident, not a real behavioral difference worth preserving); the CIK-window
`ItemReader` key expression is hardcoded in the windowed branch rather than
exposed as a parameter, since it has never varied across any existing call
site.

Per this repo's CLAUDE.md hard rules: run `/gof-refactor-reviewer` again
against the actual diff (not just the pre-code plan) before committing each
ticket, and the full 3-axis `/code-review` (Standards, Spec, GoF) before
merging.

## Decisions so far

(none yet — map just created)

## Not yet specified

(none — the merged spec resolved every open design question; nothing here
is fog)

## Out of scope

- Wiring the three fundamentals modes into `daily_incremental` — that's
  `fundamentals-daily-integration`'s own map/tickets (Phase 3/Ticket 04);
  this map only proves the shared function that work should call.
- Consolidating the file's 7 duplicated `ecs_state()` local closures, unless
  required to implement the two new functions cleanly.
- Any change to actual task profiles, concurrency, tolerated-failure
  percentage, or failure-routing targets — this is a structural refactor of
  how existing behavior is expressed, not a behavior change.
- Any new pipeline stage that doesn't already exist today.
- Any change to how either pipeline is deployed, versioned, or rolled back.
