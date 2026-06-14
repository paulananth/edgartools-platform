---
phase: 2
slug: aws-and-snowflake-production-deployment-dry-run
status: draft
nyquist_compliant: false
wave_0_complete: true
created: 2026-06-14
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | None applicable — this phase produces documentation/runbooks and evidence-file updates, not application code. No pytest/jest suite covers `infra/scripts/*.sh` or the Terraform roots. |
| **Config file** | none |
| **Quick run command** | `terraform plan` via Pattern 1 (temporary `versions.tf` edit + `override.tf` local-backend, fully reverted) — the one executable check in this phase |
| **Full suite command** | n/a |
| **Estimated runtime** | ~60 seconds (terraform init + plan) |

---

## Sampling Rate

- **Per task commit:** No commits are expected from Pattern 1 itself (edit-then-revert,
  no commit). If Pattern 0 is authorized (RESEARCH.md Open Question 3), run
  `terraform validate` (`-backend=false` or via `override.tf`) in each of the 4 fixed
  Terraform roots as that task's verification.
- **Per wave merge:** Re-run Pattern 1's `terraform plan` for `accounts/prod` to
  confirm the documented resource count is still accurate.
- **Before `/gsd:verify-work`:** Manual review of updated `01-LAUNCH-GATE-MATRIX.md`
  rows and `evidence/{aws,snowflake}.md` for secret-safety (no DSNs/ARNs/tokens/raw
  connector errors), per Phase 1 D-13/D-15.
- **Max feedback latency:** ~60 seconds (bounded by the `terraform plan` smoke check).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-xx | 01 | 1 | (infra) | T-02-04 | `terraform plan` for `accounts/prod` succeeds via Pattern 1 (temp `versions.tf` edit + `override.tf`), then edit/override are fully reverted (`git status --short` clean, no `.terraform*`/`override.tf`/`*.tfvars`/`*backend.hcl` left) | smoke | `terraform init -input=false && terraform plan -input=false -no-color` (with Pattern 1 setup); revert via `git checkout -- versions.tf && rm -rf override.tf .terraform*` | n/a | ⬜ pending |
| 02-01-xx | 01 | 1 | LIVE-02 | — | `deploy-aws-application.sh --env prod ...` flags, resolution order, and generated-manifest shape documented correctly against script source + dev manifest precedent | manual-only (documentation review) | n/a — verified by reading script source and cross-checking against the dev manifest shape | n/a | ⬜ pending |
| 02-01-xx | 01 | 1 | SNOW-01 | T-02-01 | `deploy-snowflake-stack.sh --env prod` structural blocker proven and documented (missing `backend.hcl`) | smoke | `bash infra/scripts/deploy-snowflake-stack.sh --env prod --snow-connection edgartools-prod --run-validation 2>&1 \| head -5` — exits non-zero with a `backend.hcl` message | n/a (proven this session, not committed as a test) | ⬜ pending |
| 02-01-xx | 01 | 1 | SNOW-02 | T-02-03 | dbt prod-target command documented with placeholders (D-04); dev-precedent command documented and labeled (D-03) | manual-only / dev-precedent smoke if credentials available | `uv run --with dbt-snowflake dbt compile --target dev` (requires real dev creds, operator-supplied at execution time) | n/a | ⬜ pending |

*Task IDs use the `02-01-xx` placeholder pending the planner's actual task numbering — the
planner MUST map each row above to a concrete task ID when PLAN.md files are written.*

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

None — no test framework exists for this domain and none is being introduced. The
"tests" here are the documented bash/terraform commands themselves, executed once
during Phase 2 for the rows that can run today (Pattern 1 + the SNOW-01 structural-
blocker smoke check), and recorded as evidence in `evidence/{aws,snowflake}.md`.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `deploy-aws-application.sh --env prod ...` flag set, resolution order, and `infra/aws-prod-application.json` manifest shape are documented correctly | LIVE-02 | No prod AWS app exists yet to run the script against (D-01); verification is a documentation cross-check against script source + the existing dev manifest shape | Read `infra/scripts/deploy-aws-application.sh` end-to-end; for each documented flag, confirm the flag name, default, and resolution order match the source; compare the documented manifest shape against the dev `infra/aws-dev-application.json` (or equivalent) top-level keys |
| Snowflake native-pull stack readiness (integration, stage, pipe, stream, task, procedure, access) for prod | SNOW-01 | No prod Snowflake connection exists (`snow connection list` confirms only 2 unrelated personal connections) — nothing to query live | Document the exact `snow sql`/`SHOW`/`DESCRIBE` commands that would confirm each object's readiness against a real prod connection; record as the BLOCKED row's required fix |
| `EDGARTOOLS_GOLD_STATUS` / dynamic table status and freshness for prod | (success criterion 5) | Depends on a successful prod dbt run, which depends on SNOW-02's BLOCKED prerequisites | Document the exact `snow sql` query (table + `SHOW DYNAMIC TABLES` / `INFORMATION_SCHEMA` freshness columns) as the required-fix command for the BLOCKED row |
| Updated `01-LAUNCH-GATE-MATRIX.md` rows correctly reflect documented-blocker-with-runbook vs PASS vs still-BLOCKED, with no secrets/DSNs/ARNs/raw errors in evidence files | (all) | Requires human judgment on secret-safety and matrix-row classification, not a scripted check | Manual review pass over `01-LAUNCH-GATE-MATRIX.md` diff and `evidence/{aws,snowflake}.md` diffs before `/gsd:verify-work` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify (Pattern 1 `terraform plan` + SNOW-01 smoke) or are listed under Manual-Only Verifications
- [x] Sampling continuity: no test framework exists for this domain (documented above) — N/A for the "3 consecutive tasks" rule
- [x] Wave 0 covers all MISSING references — none required (no test framework introduced)
- [x] No watch-mode flags
- [x] Feedback latency < 60s (Pattern 1 `terraform plan`)
- [ ] `nyquist_compliant: true` set in frontmatter (set after plan-checker confirms task IDs map correctly to the table above)

**Approval:** pending
