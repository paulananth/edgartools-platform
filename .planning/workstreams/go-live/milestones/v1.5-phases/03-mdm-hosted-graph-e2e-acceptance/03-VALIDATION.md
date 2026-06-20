---
phase: 3
slug: 03-mdm-hosted-graph-e2e-acceptance
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-15
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | N/A — operational acceptance phase, no application code or test-suite changes |
| **Config file** | none |
| **Quick run command** | exit-code / JSON-payload check after each live command (see Sampling Rate) |
| **Full suite command** | N/A |
| **Estimated runtime** | N/A |

---

## Sampling Rate

- **After every task commit:** Inspect the exit code and (where applicable) JSON
  payload `status`/`passed` fields of the live command just run — e.g.
  `mdm verify-graph` payload `status: "ok"`, `run-aws-mdm-e2e.sh` exit `0` for the
  dev rehearsal, exit `1` (failing the `infra/aws-prod-application.json`
  existence check) for the prod `--status-only` reproduction.
- **After every plan wave:** Confirm the corresponding evidence file
  (`evidence/mdm-hosted-graph.md`) section has been updated with the command,
  masked output, and exit code/status.
- **Before `/gsd:verify-work`:** All five evidence categories below must be
  present in `evidence/mdm-hosted-graph.md` and `runbook/mdm-secrets.md`.
- **Max feedback latency:** immediate (each command's exit code/JSON payload
  is the feedback signal — no build/test pipeline in between).

---

## Per-Task Verification Map

Tasks are defined by the planner; each task's verification must be one of the
methods in the Manual-Only Verifications table below, keyed to the
requirement it satisfies. No `{tests/*}`-style automated commands apply to
this phase — there is no application code or test framework in scope.

---

## Wave 0 Requirements

None — no test infrastructure changes needed for this phase (no new source
files, no application code).

*Existing infrastructure (live AWS/Snowflake CLIs and scripts) covers all
phase requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|--------------------|
| Dev MDM Postgres connectivity, migration, and counts checks pass without printing the DSN | MDM-01 | Live AWS/Snowflake Postgres connection; output must be masked before inspection | Run `edgar-warehouse mdm check-connectivity`, `mdm migrate`, `mdm counts` against dev `MDM_DATABASE_URL`; mask the DSN with `sed 's/:[^:@]*@/:***@/'` before recording exit codes/output in `evidence/mdm-hosted-graph.md` |
| `mdm sync-graph` materializes hosted graph tables for the dev rehearsal scope | GRAPH-01 | Requires a live Snowflake graph connection from the dev E2E run | Confirm `run-aws-mdm-e2e.sh --env dev` reaches and completes the `mdm_sync_graph` stage; record stage status from the run's JSON/log output |
| Strict `mdm verify-graph` passes SQL parity and Native App checks (compute pool, `GRAPH_INFO`, `BFS`, `WCC`) | GRAPH-02 | Requires live Snowflake Native App graph compute; cites existing `03-LIVE-DEV-RUN.md` plus fresh dev rehearsal output | Confirm `mdm verify-graph` payload `status: "ok"` with all parity checks `ok` and Native App `graph_info`/`bfs`/`wcc` all `ok`, from both the cited precedent and the new dev rehearsal run |
| `run-aws-mdm-e2e.sh` reaches migrate/run/backfill/sync/verify/counts on dev, and the local `verify-graph` preflight gates the prod `--status-only` blocker reproduction | LIVE-03 | End-to-end AWS Step Functions execution + read-only prod blocker check; not unit-testable | Run `run-aws-mdm-e2e.sh --env dev` (full E2E, default preflight) to a `SUCCEEDED` 6-stage result; separately run `run-aws-mdm-e2e.sh --env prod --status-only` and confirm it fails on the `infra/aws-prod-application.json` existence check (exit 1) as the BLOCKED-row proof |

---

## Validation Sign-Off

- [x] All tasks have manual verification mapped to a requirement (no automated test framework applies)
- [x] Sampling continuity: exit-code/JSON-payload check after every live command
- [x] Wave 0 covers all MISSING references (none — no Wave 0 needed)
- [x] No watch-mode flags (N/A — no test runner)
- [x] Feedback latency < immediate (command exit codes are the signal)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
