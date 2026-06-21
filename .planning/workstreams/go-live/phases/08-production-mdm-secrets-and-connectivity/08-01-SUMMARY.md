---
phase: 08-production-mdm-secrets-and-connectivity
plan: 01
subsystem: mdm-secrets
tags: [aws-secrets-manager, snowflake-postgres, mdm, blocked]
dependency-graph:
  requires: []
  provides: []
  affects: [08-02-verify-prod-mdm-connectivity]
tech-stack:
  added: []
  patterns: ["secret-safe BLOCKED evidence with 5-whys (Phase 7 precedent)"]
key-files:
  created:
    - .planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/evidence/mdm-prod-secrets-and-connectivity.md
  modified: []
decisions:
  - "Task 1 precondition check found no genuine production AWS access and no production Snowflake connection configured in this execution environment; stopped at BLOCKED evidence rather than fabricating a DSN or credential, per the plan's explicit instruction and the Phase 7 precedent."
  - "Task 3's acceptance criteria were already satisfied by HANDOFF.json content written in a prior session (08-research); no new edit was made."
metrics:
  duration: "~25min"
  completed: 2026-06-20
---

# Phase 8 Plan 1: Populate prod MDM secrets Summary

Precondition check found the production Snowflake-hosted Postgres MDM instance unverifiable from this environment (no prod Snowflake connection, no genuine prod AWS access) — execution correctly stopped at secret-safe BLOCKED evidence instead of populating secrets with fabricated values.

## What Happened

### Task 1: Precondition — confirm prod Snowflake Postgres MDM instance exists

**Outcome: BLOCKED.**

Checked three independent angles, all non-secret:

1. **AWS prod access.** The `aws-admin-prod` profile's `credential_process` resolves to the same underlying identity as `default`. `aws sts get-caller-identity --profile aws-admin-prod` returned IAM user `cli-access` in account `077127448006` — the known **dev** account (per bucket/state-machine naming conventions in CLAUDE.md), not a distinct production account.
2. **Snowflake prod connection.** `infra/scripts/go-live.sh` documents the canonical prod connection name as `edgartools-prod`. `snow connection list` shows only two connections (`snowconn` = dev, one personal/OAuth) — no `edgartools-prod` connection exists. Attempting `snow sql --connection edgartools-prod` fails with "Connection edgartools-prod is not configured."
3. **Strengthener (read-only, non-secret).** `SHOW POSTGRES INSTANCES` against the one reachable (dev) account showed exactly one instance, `EDGARTOOLS_DEV_MDM` — no production-named instance in that account. This rules out a same-account prod instance but says nothing about a genuinely separate production Snowflake account, which is unreachable from this environment.

**Conclusion:** the production Postgres MDM instance's existence/readiness is unverifiable from this execution environment — not confirmed-absent, not confirmed-present. Combined with the absent genuine prod AWS access, Task 2 cannot proceed without fabricating values, which is explicitly prohibited.

Evidence file created: `evidence/mdm-prod-secrets-and-connectivity.md`, containing a full 5-whys root-cause chain and a "Required Operator Action Before Retry" section. No host string, DSN, credential, or raw connector error appears in the file (verified via grep gate — see Self-Check).

**Commit:** `e21f777` — `docs(08-01): record BLOCKED precondition for prod MDM Postgres instance check`

### Task 2: Populate both required prod MDM secrets + capture presence evidence

**Not executed.** Per the plan's explicit gating ("Only execute if Task 1 confirmed the prod Postgres instance exists"), Task 2 is correctly skipped because Task 1 resulted in BLOCKED. No `put-secret-value` call was made against `edgartools-prod/mdm/postgres_dsn` or `edgartools-prod/mdm/snowflake`. Task 2's verify gate (`grep -q "VersionIdsToStages" ...`) is **not applicable** here — it is not a failed check, it is a gate that never runs because its precondition (Task 1 success) was not met. The evidence file deliberately omits `VersionIdsToStages` because no secret was populated; this is the expected, correct state for a BLOCKED outcome, not a missing artifact.

### Task 3: Clarify neo4j/api_keys out-of-scope in HANDOFF.json

**Pre-satisfied by a prior session — no new edit made.** Reading `.planning/HANDOFF.json`, the blocker entry at `blockers[0]` already contains the exact required clarifying language: it names `edgartools-prod/mdm/postgres_dsn` and `edgartools-prod/mdm/snowflake` as the only 2 secrets actually in scope for Phase 8/MDM-02, and explicitly states `edgartools-prod/mdm/neo4j` and `edgartools-prod/mdm/api_keys` "are confirmed OUT OF SCOPE for Phase 8." This was written during the `08-research` task in an earlier session (per HANDOFF.json's own `completed_tasks` log), before this plan-execution pass began.

Ran the plan's exact Task 3 verify commands against the unmodified file:
```
python3 -c "import json; json.load(open('.planning/HANDOFF.json'))" && echo "valid json"
→ valid json
grep -qi "not Phase 8\|out of scope\|NOT Phase 8" .planning/HANDOFF.json && echo "PASS" || echo "FAIL"
→ PASS
```

Both of Task 3's acceptance criteria pass against the file's existing content. No edit was made in this execution pass, and no commit was made for Task 3 — there is nothing to commit since the file is unchanged from this plan's perspective.

## Deviations from Plan

**1. [Files-modified scope] `.planning/HANDOFF.json` listed in plan frontmatter `files_modified` was not actually modified.**
- **Found during:** Task 3
- **Reason:** The required content already exists in the file from a prior session's `08-research` work. Editing it again would be a no-op edit producing a content-free commit, which is not warranted.
- **Action:** Documented here instead of editing. No commit was made for this file.

No other deviations. Tasks 1 and 3 executed per plan; Task 2 correctly not executed per the plan's own gating logic — a legitimate BLOCKED outcome is an explicitly valid result per this plan's `<success_criteria>`.

## Known Stubs

None. No code/UI stubs were introduced — this plan only writes evidence/handoff documentation.

## Threat Flags

None. No new security-relevant surface was introduced beyond what the plan's own `<threat_model>` already covers (T-08-01 through T-08-04, T-08-SC). The BLOCKED outcome means T-08-04 (DSN pointed at non-existent instance) was successfully mitigated by stopping before any write.

## Required Operator Action Before Retry

1. Provision/confirm a production Snowflake-hosted Postgres MDM instance and configure an `edgartools-prod` SnowCLI connection pointing at the genuine production Snowflake account — enter credentials directly via `snow connection add` or the Snowflake config file, never pasted into chat or committed.
2. Configure genuine production AWS admin credentials under the `aws-admin-prod` profile such that `aws sts get-caller-identity --profile aws-admin-prod` resolves to the real production AWS account, not `077127448006`.
3. Once both are confirmed, re-run this plan's Task 1 precondition check, then proceed to Task 2 secret population using `bootstrap-aws-mdm-secrets.sh --dsn-stdin` and the documented raw `put-secret-value` pattern.

## Self-Check

```
test -f .planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/evidence/mdm-prod-secrets-and-connectivity.md
→ FOUND
git log --oneline --all | grep e21f777
→ FOUND: e21f777 docs(08-01): record BLOCKED precondition for prod MDM Postgres instance check
```

## Self-Check: PASSED
