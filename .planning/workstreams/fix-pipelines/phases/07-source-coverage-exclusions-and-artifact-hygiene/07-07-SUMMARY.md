---
phase: 07
plan: 07
subsystem: dev-rehearsal-and-verification-ledger
tags: [rehearsal, mdm, snowflake-graph, generation-lifecycle, verification]
requires: [07-00, 07-01, 07-02, 07-03, 07-04, 07-05, 07-06]
provides: [relationship-generation-rehearsal-script, phase7-verification-ledger]
affects: []
key-files:
  created:
    - scripts/ops/verify-relationship-generations.sh
    - tests/integration/test_relationship_generation_e2e.py
    - .planning/workstreams/fix-pipelines/phases/07-source-coverage-exclusions-and-artifact-hygiene/07-DEV-REHEARSAL.md
    - .planning/workstreams/fix-pipelines/phases/07-source-coverage-exclusions-and-artifact-hygiene/07-VERIFICATION.md
  modified:
    - .planning/workstreams/fix-pipelines/ROADMAP.md
key-decisions:
  - Task 1 (build the rehearsal script + test) was executed autonomously; Task 2
    (execute the bounded dev rehearsal) is a `checkpoint:human-verify` step
    (`autonomous: false` in 07-07-PLAN.md) that requires a human operator with real
    AWS-dev (`sec_platform_deployer`) and Snowflake-dev (`SNOW_CONNECTION=snowconn`)
    credentials, and the plan's own `<verify>` clause requires a human to review
    evidence and type `approved`. This was not run -- it cannot be run without live
    credentials and without the risk of mutating shared dev MDM/graph state, which
    the plan itself gates behind human sign-off, not autonomous execution.
  - scripts/ops/verify-relationship-generations.sh is the repeatable backbone Task 2
    will use. It mirrors the real CLI surface confirmed by reading
    edgar_warehouse/mdm/cli.py (generation-plan/generation-build-partition/
    generation-fan-in/generation-retry-failed-partitions/generation-activate/
    sync-graph/verify-graph/graph-activate/graph-rollback/coverage-report/
    publication-status/merge) rather than inventing new CLI surface, and follows
    the established SNOW_BIN/UV_BIN-override testing convention already set by the
    sibling scripts/ops/verify-neo4j-phase7-capabilities.sh (AWS_BIN/UV_BIN here).
  - The credential guard (`SNOW_CONNECTION` must equal exactly `snowconn`) is the
    very first statement in the script, before any variable assignment or function
    definition references aws/uv -- this trivially satisfies "fails before Snowflake
    commands" for the whole script, not just a subset of stages.
  - Evidence recording redacts before writing, not after: `run_stage_command` pipes
    raw command output through `redact()` first, and only ever passes the already-
    redacted text into `record()` (which itself never receives a raw secret, even
    in its own argv/subprocess boundary). All secret-shaped output found by the
    redaction patterns is masked before it ever reaches disk.
  - Manifest chaining across stages (generation_id, partition_id) is read from the
    real bronze-storage side-channel files (`reference/mdm_generation/runs/<run_id>/
    generation.json` / `partitions.jsonl`) that `_handle_generation_plan` already
    writes as a side effect -- not parsed from command stdout -- since that's the
    only place the real CLI actually persists them (confirmed by reading
    `_write_generation_manifest`/`_read_generation_id_for_run` in cli.py).
  - Task 1's integration test goes beyond pure structural grep: it builds fake
    `aws`/`uv` binaries (via the new AWS_BIN/UV_BIN overrides) that let the full
    `--all` chain actually execute hermetically -- including real manifest file
    read/write against a local WAREHOUSE_BRONZE_ROOT -- proving the stage-chaining
    logic genuinely works, not just that stage names appear in the script text.
    This follows the precedent already set by
    tests/integration/test_neo4j_phase7_capabilities.py in this same phase.
  - Task 3's ledger (07-VERIFICATION.md) does not mark Phase 7 `passed`. Every
    `Complete`/`Partial` verdict in its requirement table matches what
    REQUIREMENTS.md's existing traceability table already states (unchanged by
    this plan) -- RSYNC-01 and RSYNC-04 remain honestly `Partial`, since a live
    rehearsal proves what already exists, it does not retroactively finish
    undelivered scope.
  - ROADMAP.md's Phase 7 plan checkboxes were stale (07-01 through 07-06 all showed
    `[ ]` despite each having a completed SUMMARY.md) -- corrected to `[x]` as part
    of this plan's "update Phase 7 roadmap progress" action, rather than perpetuating
    the undercount.
requirements-completed: []
requirements-partially-addressed: []
completed: 2026-07-15
---

# 07-07: Bounded Dev Rehearsal — Task 1 Complete, Tasks 2-3's Ledger Filed Pending

## Scope note

This plan's three tasks have different completion characters:

- **Task 1** (build the repeatable rehearsal script + automated test): fully executed
  and verified against its own `<verify>` command.
- **Task 2** (execute the bounded dev rehearsal): a `checkpoint:human-verify` step,
  `autonomous: false`. Not run. `07-DEV-REHEARSAL.md` is filed as the fill-in-the-blank
  evidence ledger a human operator completes while running it against real AWS-dev/
  Snowflake-dev.
- **Task 3** (close the verification ledger): `07-VERIFICATION.md` is filed, but its
  own gate says Phase 7 verification status stays `pending`, not `passed`, until
  Task 2's human sign-off exists. No requirement is marked complete on the strength of
  live evidence that doesn't exist.

No requirement IDs are claimed complete or partially-addressed *by this plan* — Phase 7's
16 requirement IDs were already scored by 07-00 through 07-06; this plan adds the
rehearsal tooling and an honest ledger, it does not change any requirement's status.

## Task 1: Build repeatable end-to-end generation verification

**`scripts/ops/verify-relationship-generations.sh`** — a stage-based bash script
(`--all` or `--stage <name>`) covering: `preflight` (ownership guard against
`edgartools-dev-load-history` running), `watermark` (`mdm publication-status`),
`plan`/`build-partitions`/`fan-in`/`activate-generation` (MDM-side generation
lifecycle), `sync-graph`/`verify-graph`/`graph-activate` (Snowflake-side), `coverage-report`,
`hosted-e2e` (delegates to the existing `scripts/ops/neo4j-snowflake-migration.py
--hosted-e2e` for identity/property/traversal parity SQL), `retry-failed`
(`generation-retry-failed-partitions`), and two operator-gated optional stages
(`entity-merge`, `graph-rollback`) that skip cleanly when their required IDs aren't
supplied.

Every command is dev-scoped behind a `SNOW_CONNECTION=snowconn` guard that runs before
any other statement in the file. Evidence is JSONL, redacted before it's written
(DSN/password/token/SecretString patterns), under `./evidence/relationship-generations/
<run-id>/evidence.jsonl`. `--all` halts on the first stage failure rather than
continuing — a failed generation never reaches the later activation/rollback stages.

**`tests/integration/test_relationship_generation_e2e.py`** — 9 tests, all hermetic (no
live AWS/Snowflake). Key coverage:
- Credential guard fires before any command, both when `SNOW_CONNECTION` is unset and
  when it's wrong (proven by pointing `AWS_BIN`/`UV_BIN` at sentinel scripts that would
  print a marker string if ever invoked — the marker never appears).
- `--help` lists every stage; missing `--all`/`--stage` fails cleanly.
- Optional stages (`entity-merge`, `graph-rollback`) skip cleanly without their args.
- Redaction actually removes a DSN password and a quoted `PASSWORD:` value from the
  evidence file before it's ever written.
- The full `--all` chain runs against fake `aws`/`uv` binaries and actually completes
  the real manifest read/write logic (partition ID extraction from `partitions.jsonl`,
  generation ID extraction from `generation.json`) against a real local
  `WAREHOUSE_BRONZE_ROOT` — every one of the 14 stages is proven to run, in order, with
  both optional stages exercised (not skipped).
- An injected failure at `fan-in` halts `--all` at exit 1, and none of
  `activate-generation`/`sync-graph`/`verify-graph`/`graph-activate` ever run afterward
  — the mechanical proof that a failed generation cannot reach activation.
- The script contains no `NEO4J_URI`/`NEO4J_PASSWORD`/`bolt://`/`neo4j+s://` tokens.

**Verify**: `uv run pytest tests/integration/test_relationship_generation_e2e.py` — 9
passed. Full regression suite (`tests/mdm tests/application tests/unit
tests/architecture tests/integration/test_relationship_generation_e2e.py`) — 778 passed,
1 deselected (a pre-existing, unrelated failure — see Deviations).

## Task 2: Execute bounded dev failure and recovery rehearsal

Not executed. `07-DEV-REHEARSAL.md` is filed with:
- A precondition checklist (confirm no overlapping runtime owns the dev graph/silver
  surface — beyond what the script's own `preflight` stage checks).
- The exact command to run it.
- A 16-row scenario ledger mapping every item from `07-CONTEXT.md`'s "Required
  phase-exit evidence" list to its proof mechanism — 7 rows already `PASS (automated)`
  citing the specific 07-01..07-06 test that proves them (these don't need live
  re-proving, per `07-VALIDATION.md`'s test-layer table), 8 rows `PENDING` awaiting the
  live run, and 1 row split (`PASS (mechanic, automated)` / `PENDING (live pointer
  confirmation)`) for the "failed generation never activates" invariant, since the
  hermetic test proves the script's halt mechanic but only a live run proves the real
  Snowflake pointer was actually untouched.
- An explicit sign-off block (reviewer / date / verdict), all currently blank.

## Task 3: Close the Phase 7 verification ledger

`07-VERIFICATION.md` maps all 16 Phase 7 requirement IDs to their automated-test
evidence (unchanged from REQUIREMENTS.md's existing traceability table) and marks the
live-evidence column `pending` for every ID whose proof depends on Task 2. The
document's own `verification_status` frontmatter field is `PENDING_HUMAN_APPROVAL`,
and its "Phase exit gate" section states the two conditions (`07-DEV-REHEARSAL.md` has
no `PENDING` rows; its sign-off has a human `approved` verdict) required before this
can flip to `passed`. `ROADMAP.md`'s Phase 7 checklist was corrected from a stale `1/8
plans executed` (07-01 through 07-06 all showed `[ ]` despite completed summaries) to
`6/8`, with 07-07 itself left unchecked and annotated with its Task 2/3 blocker.

## Deviations

- **Pre-existing, unrelated test failure surfaced by this plan's own verify command**:
  `tests/architecture/test_load_history_state_machine.py::
  test_total_cik_limit_check_defaults_to_no_limit_sentinel` fails
  (`expected Next == "ComputeWindows"`, got `"ArtifactPolicyCheck"`). Confirmed via
  `git stash` that this fails identically on the pre-07-07 base commit (`571e691`) —
  it predates this plan. Root cause: the `ArtifactPolicyCheck`/`ArtifactPolicyDefault`
  states (CLAUDE.md's artifact-throttle 5-whys mitigation #2, in
  `deploy-aws-application.sh`) were inserted between `TotalCikLimitCheck` and
  `ComputeWindows`, but this architecture test's `Next` assertion was never updated.
  `deploy-aws-application.sh` is outside 07-07's declared `files_modified`; left
  unfixed and documented in `07-VERIFICATION.md`'s Residual risks rather than fixed
  under this plan's authority or silently re-excluded without comment.
- **Task 2 and part of Task 3 not executed**, as designed — both require a human
  operator with live AWS-dev/Snowflake-dev credentials and explicit approval, which
  this session does not have and the plan does not authorize an assistant to bypass.

## Verification

```bash
uv run pytest tests/integration/test_relationship_generation_e2e.py
# 9 passed

uv run pytest tests/mdm tests/application tests/unit tests/architecture \
  tests/integration/test_relationship_generation_e2e.py \
  --deselect tests/architecture/test_load_history_state_machine.py::test_total_cik_limit_check_defaults_to_no_limit_sentinel
# 778 passed, 1 deselected
```

## Self-Check: PASSED

- Task 1's script and test exist, are executable, pass their own declared verify
  command, and introduce zero regressions elsewhere.
- Task 2 and Task 3 are honestly represented as filed-but-pending, not completed —
  no requirement is marked complete on evidence that doesn't exist, and the ledger's
  own status field says so explicitly.
- The one test failure surfaced by Task 3's verify command was root-caused (5-whys:
  pre-existing state-machine change vs. stale test expectation), confirmed pre-existing
  via `git stash` against the base commit, and documented rather than silently
  papered over.
- `ROADMAP.md`'s stale plan-completion checkboxes were corrected, not perpetuated.
