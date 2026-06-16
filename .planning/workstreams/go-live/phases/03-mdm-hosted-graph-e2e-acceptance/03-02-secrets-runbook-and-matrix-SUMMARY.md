---
plan: 03-02-secrets-runbook-and-matrix
phase: 03
status: complete
completed: 2026-06-16
---

# Plan 03-02 Summary: Secrets Runbook and Matrix Updates

## What was built

Two documentation-only deliverables authored inline (no live commands run):

1. **`runbook/mdm-secrets.md`** (new file) — placeholder-only population runbook
   for `edgartools-prod/mdm/postgres_dsn` and `edgartools-prod/mdm/snowflake`.

2. **`01-LAUNCH-GATE-MATRIX.md`** (in-place edit) — rows 22-25 updated with
   cross-phase runbook link and Phase 3 evidence section headings; Required
   Production Identifiers secret checklist annotated per D-06.

## Task results

**Task 1 — `runbook/mdm-secrets.md`:** Created with 7 required sections:
(1) header disclaimer — all values are `<PLACEHOLDER>` tokens, no real secrets;
(2) `postgres_dsn` via `bootstrap-aws-mdm-secrets.sh --dsn-stdin`, with D-07
shape reference citing plan 03-01's evidence heading; (3) `snowflake` raw
`put-secret-value` with all 7 `MDM_SNOWFLAKE_*` keys matching `_snowflake_setting()`
in `export.py`; (4) `neo4j` annotated not-required/legacy; (5) `api_keys` annotated
deferred; (6) `describe-secret` presence checks for both required secrets (D-08);
(7) security note forbidding `get-secret-value`/`put-secret-value` output in evidence.
Automated gate: all 7 `MDM_SNOWFLAKE_*` keys present, `describe-secret` present,
no `get-secret-value --secret-id` invocation, neo4j and api_keys annotated. PASS.

**Task 2 — `01-LAUNCH-GATE-MATRIX.md` rows 22-25 + Required Production Identifiers:**
- Row 22 (MDM Postgres secret + connectivity): Required Fix cell links to
  `runbook/mdm-secrets.md` (cross-phase link via `../03-.../runbook/mdm-secrets.md`);
  Required Rerun Proof cell references `### Dev MDM Postgres Re-Verification (D-03)`
  and `### Dev postgres_dsn Shape Reference (D-07)` — dev precedent only, row stays BLOCKED.
- Row 23 (sync-graph): Required Rerun Proof references `### Dev Rehearsal — Full E2E
  (D-09/D-10)` for the `mdm_sync_graph` stage — dev precedent only, stays BLOCKED.
- Row 24 (verify-graph): Required Rerun Proof references the same dev rehearsal section
  (preflight + `mdm_verify_graph` stage) plus `### GRAPH-01/GRAPH-02 Dev Precedent
  Citation (D-04)` — dev precedent only, stays BLOCKED.
- Row 25 (AWS E2E): Required Rerun Proof references `### Dev Rehearsal — Full E2E`
  (all 6 stages SUCCEEDED) and `### Prod --status-only Structural-Blocker Reproduction
  (D-02)` (exit 1 proof) — rows stay BLOCKED, dev rehearsal is dev precedent only.
- Required Production Identifiers: `postgres_dsn` and `snowflake` annotated with
  runbook reference (boxes unchecked); `neo4j` annotated "not required / legacy";
  `api_keys` annotated "deferred, consumer unclear". No boxes checked (population not
  yet executed against real prod values — out of Phase 3 scope).
Automated gate: all 5 checks passed. PASS.

## Commit

- `cf7af8f` docs(03-02): MDM prod secret runbook + launch gate matrix updates

## Security

All three threat-model mitigations honored: runbook contains `<PLACEHOLDER>` tokens
only (T-03-01); security note explicitly forbids pasting `put-secret-value`/
`get-secret-value` output into evidence (T-03-02); matrix cells reference section
descriptions and evidence headings only, no raw ARNs or DSNs (T-03-03). No
`get-secret-value --secret-id` invocation appears in the runbook. No `--skip-preflight`
reference added to either file (D-11/D-12 preserved).

## Phase 3 completion

Both Wave 1 (plan 03-01) and Wave 2 (plan 03-02) are complete. All Phase 3
requirements are satisfied:
- MDM-01: dev Postgres re-verify (03-01) + secret runbook (03-02)
- GRAPH-01: sync-graph stage + cited 03-LIVE-DEV-RUN.md precedent (03-01) + matrix row (03-02)
- GRAPH-02: E2E chain + verify-graph stage + cited precedent (03-01) + matrix row (03-02)
- LIVE-03: preflight-gates-E2E + prod --status-only repro (03-01) + matrix row (03-02)

Next: run gsd-verifier for Phase 3 to confirm all acceptance gates are met.
