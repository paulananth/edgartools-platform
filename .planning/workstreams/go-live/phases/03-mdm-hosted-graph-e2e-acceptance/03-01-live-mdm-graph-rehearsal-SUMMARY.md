---
plan: 03-01-live-mdm-graph-rehearsal
phase: 03
status: complete
completed: 2026-06-16
---

# Plan 03-01 Summary: Live MDM Graph Rehearsal

## What was built

All four live acceptance activities completed and appended to the existing Phase 1 evidence file
`.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/mdm-hosted-graph.md`
under a new `## Phase 3 Live Checks Actually Run` section.

## Task results

**Task 1 — Dev full E2E rehearsal (D-09/D-10):** `run-aws-mdm-e2e.sh --env dev` exited 0.
Local strict `verify-graph` preflight passed (status: ok, 15 nodes/4 edges, all Native App checks
ok, phase3_acceptance: true, compute_pool: CPU_X64_XS) and gated the 6-stage chain. All 6 AWS
Step Functions stages SUCCEEDED (epoch `1781568895`). GRAPH-01/GRAPH-02 dev precedent cited from
`03-LIVE-DEV-RUN.md` as-is (D-04). Satisfies LIVE-03, GRAPH-01, GRAPH-02.

**Task 2 — Prod --status-only blocker reproduction (D-02):** `run-aws-mdm-e2e.sh --env prod
--status-only` exited 1 on the `infra/aws-prod-application.json` existence check, zero AWS API
calls. BLOCKED cross-reference recorded. Satisfies LIVE-03 (blocked-row proof).

**Task 3 — Dev MDM Postgres re-verify (D-03/D-07):** `mdm check-connectivity` / `mdm migrate`
(idempotent re-apply, seeded: true, 19 tables) / `mdm counts` all exited 0 against dev
`MDM_DATABASE_URL`. DSN masked via `sed 's/:[^:@]*@/:***@/'` before all output; host confirmed
`.snowflake.app`; `MDM_DATABASE_URL` unset after. Masked DSN shape captured under stable heading
for plan 03-02 (D-07). Satisfies MDM-01.

## Commits

- `ae16fe1` evidence(03-01): prod --status-only blocker + dev MDM Postgres re-verify (D-02/D-03/D-07)
- `4fce49f` evidence(03-01): dev full E2E rehearsal + GRAPH precedent citation (D-04/D-09/D-10)

## Security

All three threat-model mitigations honored: DSN masked, no raw secrets committed, prod
--status-only failed before any AWS call (T-03-01/02/03). No `--skip-preflight` used (D-11/D-12).

## Handoff to plan 03-02

The `### Dev postgres_dsn Shape Reference (D-07 — for plan 03-02)` heading in the evidence file
provides the stable format reference for the prod `postgres_dsn` secret. The dev rehearsal
results (epoch 1781568895) and prod blocker proof (exit 1) are the evidence Plan 03-02 references
when updating `01-LAUNCH-GATE-MATRIX.md` BLOCKED rows.
