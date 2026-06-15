---
phase: 03
slug: 03-mdm-hosted-graph-e2e-acceptance
type: plan-outline
created: 2026-06-15
---

# Phase 3 — Plan Outline

Operational-acceptance phase. No application code changes. Deliverables are live
command runs captured as non-secret evidence/runbook Markdown, plus launch-gate
matrix updates.

## Controlling constraint (drives plan count and waves)

There is exactly **one** evidence destination (`evidence/mdm-hosted-graph.md`).
GSD's same-wave rule forbids two plans in the same wave writing the same file,
so all live-execution work that produces evidence is consolidated into a single
Wave-1 plan. The documentation/runbook + matrix-update work depends on that
evidence and runs in Wave 2.

## Evidence-file decision (carry into per-plan step)

Phase 3 **appends** to the existing Phase 1 file
`01-production-readiness-inventory-and-launch-gate-contract/evidence/mdm-hosted-graph.md`
(mirroring how Phase 2 appended `## Phase 2 Read-Only Checks Actually Run` to
`evidence/aws.md`/`evidence/snowflake.md` in place). RESEARCH's "Launch Gate
Matrix Integration" calls that file "this phase's destination"; CONTEXT
canonical_refs calls it "evidence template to populate"; matrix rows 22-25
already link to the bare `evidence/mdm-hosted-graph.md`, so appending means **no
matrix link edits** are needed (only row content/status text). This must be
stated explicitly in 03-01 so the executor does not create a divergent
`03-.../evidence/` file.

## Outline

| Plan ID | Objective | Wave | Depends On | Requirements |
|---------|-----------|------|------------|--------------|
| 03-01-live-mdm-graph-rehearsal | Run the live acceptance commands and append all evidence to the existing `01-.../evidence/mdm-hosted-graph.md`: (a) full dev `run-aws-mdm-e2e.sh --env dev` E2E rehearsal with default local `verify-graph` preflight gating the 6-stage Step Functions chain (items 1+4; D-09/D-10; LIVE-03/GRAPH-02, plus incidental fresh `verify-graph` payload for GRAPH-01); (b) read-only prod `run-aws-mdm-e2e.sh --env prod --status-only` blocker reproduction failing on missing `infra/aws-prod-application.json` (exit 1, zero AWS calls) (item 2; D-02; LIVE-03); (c) live dev MDM Postgres `check-connectivity`/`migrate`/`counts` re-verification on `MDM_DATABASE_URL` with masked DSN (item 3; D-03/D-07; MDM-01); (d) cite existing `neo4j-snowflake/.../03-LIVE-DEV-RUN.md` as-is for GRAPH-01/GRAPH-02 with no new standalone verify-graph run (D-04). Two-surface env-var separation kept as distinct tasks (Postgres tasks use `MDM_DATABASE_URL` only; graph/E2E tasks use Snowflake settings only). | 1 | — | MDM-01, GRAPH-01, GRAPH-02, LIVE-03 |
| 03-02-secrets-runbook-and-matrix | Documentation-only: (a) author `runbook/mdm-secrets.md` with full `put-secret-value` placeholder commands for `edgartools-prod/mdm/postgres_dsn` (via `bootstrap-aws-mdm-secrets.sh`) and `edgartools-prod/mdm/snowflake` (raw, with inferred JSON key shape), dev DSN structure-only shape reference, and `describe-secret` presence-check commands; `neo4j` annotated legacy/N-A and `api_keys` annotated deferred — no population commands for either (item 5; D-05–D-08); (b) update `01-LAUNCH-GATE-MATRIX.md` MDM/hosted-graph BLOCKED rows (22-25) "Required Fix"/"Required Rerun Proof" cells to reference the new runbook + appended evidence (rows stay BLOCKED per Dev-Vs-Prod rule) and annotate the "Required Production Identifiers" secret checklist (item 6). Threat model must cover secret-value leakage into runbook/evidence (mitigated by describe-secret-only, never get-secret-value; never paste put-secret-value output). | 2 | 03-01 | MDM-01, GRAPH-01, GRAPH-02, LIVE-03 |

## Coverage check

Requirement IDs — each appears in ≥1 plan:
- MDM-01: 03-01 (dev Postgres re-verify), 03-02 (secret runbook + matrix rows)
- GRAPH-01: 03-01 (sync-graph stage + cited precedent), 03-02 (matrix row)
- GRAPH-02: 03-01 (E2E chain + verify-graph stage + cited precedent), 03-02 (matrix row)
- LIVE-03: 03-01 (preflight-gates-E2E + prod --status-only repro), 03-02 (matrix row)

Phase-shape items — each covered:
1. Dev rehearsal full E2E → 03-01(a)
2. Prod `--status-only` repro → 03-01(b)
3. Dev MDM Postgres re-verify → 03-01(c)
4. Cite `03-LIVE-DEV-RUN.md` for GRAPH-01/GRAPH-02 → 03-01(d)
5. MDM secret population runbook → 03-02(a)
6. Update `01-LAUNCH-GATE-MATRIX.md` rows / Required Production Identifiers → 03-02(b)
7. Populate `evidence/mdm-hosted-graph.md` → 03-01 (all live evidence appended in place)

## Per-plan-step carry-forwards (not outline blockers)

- **Two-surface env-var separation** is a per-task concern inside 03-01, not a
  split driver: Postgres commands declare `MDM_DATABASE_URL` only; graph/E2E
  commands declare Snowflake settings only. Keep as distinct tasks so the
  env-var conflation error cannot occur.
- **Compute-pool preflight remediation** (RESEARCH Pitfall 1) is not new scope;
  03-01's rehearsal task should be prepared to hit and resolve it with the
  already-documented grant SQL.
- **Dev Postgres reachability** (RESEARCH A1/Open Question 2): 03-01's Postgres
  task attempts the local `MDM_DATABASE_URL` path first, with the documented
  `aws ecs run-task` fallback ready if local DNS/connect fails.
- **Security (both plans need `<threat_model>`):** 03-01 — DSN masking before
  recording `migrate`/`counts` output, no mutation risk in prod `--status-only`
  (fails before any AWS call). 03-02 — secret leakage into runbook/evidence
  mitigated by `describe-secret` presence-check only (never `get-secret-value`),
  never paste `put-secret-value` output. `--skip-preflight` is never invoked or
  documented in either plan (D-11/D-12).
