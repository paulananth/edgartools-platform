---
phase: 8
slug: 08-production-mdm-secrets-and-connectivity
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-20
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | N/A — operator-execution/evidence-capture phase against live production infrastructure, no application code or test-suite changes |
| **Config file** | none |
| **Quick run command** | `uv run --extra mdm-runtime edgar-warehouse mdm check-connectivity` (itself the verification act) |
| **Full suite command** | `check-connectivity` + `migrate` + `counts` in sequence, as already proven in dev (D-03) |
| **Estimated runtime** | N/A |

---

## Sampling Rate

- **After every task commit:** Inspect the exit code and (where applicable) JSON/CLI
  output of the live command just run — e.g. `aws secretsmanager describe-secret`
  `VersionIdsToStages` presence after population, `mdm check-connectivity`/`migrate`/
  `counts` exit `0`.
- **After every plan wave:** Confirm the corresponding evidence file
  (`evidence/mdm-prod-secrets-and-connectivity.md`) section has been updated with the
  command, masked output, and exit code/status. Confirm `MDM_DATABASE_URL` is unset
  immediately after the three CLI commands and that fact is recorded as an evidence
  line.
- **Before `/gsd:verify-work`:** Both secrets' presence (`describe-secret` only, never
  `get-secret-value`/`put-secret-value` output) and the connectivity/migrate/counts
  exit codes must be present in evidence, and the launch gate matrix MDM rows must be
  flipped to PASS only after operator approval.
- **Max feedback latency:** immediate (each command's exit code/output is the
  feedback signal — no build/test pipeline in between).

---

## Per-Task Verification Map

Tasks are defined by 08-01-populate-prod-mdm-secrets-PLAN.md and
08-02-verify-prod-mdm-connectivity-PLAN.md; each task's verification is one of the
methods in the Manual-Only Verifications table below, keyed to the requirement it
satisfies. No `{tests/*}`-style automated commands apply to this phase — there is no
application code or test framework in scope.

---

## Wave 0 Requirements

None — no test infrastructure changes needed for this phase (no new source files, no
application code).

*Existing infrastructure (AWS Secrets Manager CLI, `edgar_warehouse/mdm/cli.py`
commands, and the v1.5 runbook) covers all phase requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|--------------------|
| Production Snowflake Postgres MDM instance existence is verified before any DSN is written | MDM-02 | No Terraform/SQL in this repo provisions a prod Postgres instance; existence must be confirmed against live Snowflake before population | Run the `snow sql`/Snowsight existence check (08-01 Task 1); if absent, STOP with a documented 5-whys BLOCKED rather than fabricating a DSN |
| `edgartools-prod/mdm/postgres_dsn` and `edgartools-prod/mdm/snowflake` are populated without printing secret values | MDM-02 | Live AWS Secrets Manager write against production; only `describe-secret` metadata may be recorded | Run `bootstrap-aws-mdm-secrets.sh --dsn-stdin` and the `snowflake` secret `put-secret-value`, then confirm via `aws secretsmanager describe-secret --query '{Name,ARN,LastChangedDate,VersionIdsToStages}'` — never `get-secret-value` |
| Prod MDM Postgres connectivity, migration, and counts checks pass without printing the DSN | MDM-02 | Live AWS/Snowflake Postgres connection; output must never expose the DSN | Run `edgar-warehouse mdm check-connectivity`, `mdm migrate`, `mdm counts` against prod `MDM_DATABASE_URL`; record exit codes/output in `evidence/mdm-prod-secrets-and-connectivity.md`, then `unset MDM_DATABASE_URL` and record that fact |
| Launch gate matrix MDM secret/container readiness rows flip to PASS only on confirmed evidence | MDM-02 | Requires human operator sign-off before editing the shared gate contract | After operator approval, update the MDM rows in `01-LAUNCH-GATE-MATRIX.md` (archived at `milestones/v1.5-phases/01-.../`), cross-referencing the evidence file; do not flip rows whose underlying check did not run |

---

## Validation Sign-Off

- [x] All tasks have manual verification mapped to a requirement (no automated test framework applies)
- [x] Sampling continuity: exit-code/output check after every live command
- [x] Wave 0 covers all MISSING references (none — no Wave 0 needed)
- [x] No watch-mode flags (N/A — no test runner)
- [x] Feedback latency < immediate (command exit codes are the signal)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
