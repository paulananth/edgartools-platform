# Phase 6: Production AWS Infrastructure And Application Deploy - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-19
**Phase:** 6-production-aws-infrastructure-and-application-deploy
**Areas discussed:** First real apply (state backend & approval gate), Secret container strategy, Pipeline notifications opt-in, versions.tf bug-fix ownership

---

## First Real Apply: State Backend & Approval Gate

| Option | Description | Selected |
|--------|-------------|----------|
| Plan 06-01 creates `edgartools-prod-tfstate` via AWS CLI | Explicit `create-bucket`/`put-bucket-versioning`/`put-bucket-encryption` sequence, evidenced as its own first step | ✓ |
| Plan 06-01 creates it via a tiny separate Terraform root | Minimal bootstrap Terraform config provisions bucket + lock table | |
| Out of scope — operator creates manually | Document requirements only; operator provisions outside go-live commits | |

**User's choice:** Plan 06-01 creates it via AWS CLI.
**Notes:** Confirmed live via `aws s3api head-bucket --bucket edgartools-prod-tfstate` → 404 Not Found before asking, so the decision is grounded in real state, not a dry-run assumption.

| Option | Description | Selected |
|--------|-------------|----------|
| Show plan output, get explicit go-ahead, then apply | Executor runs `terraform plan`, posts counts, waits for explicit confirmation before `apply` | ✓ |
| Auto-apply if plan shows 0 destroys, additive only | Skip the confirmation turn for purely-additive plans | |
| Plan only in 06-01; apply is a separate manual operator step | Plan/evidence in Phase 6; actual `apply` command run by operator outside agent execution | |

**User's choice:** Show plan output, get explicit go-ahead, then apply.
**Notes:** This is the project's first-ever real prod `terraform apply` — no auto-apply shortcut, even for additive-only plans.

| Option | Description | Selected |
|--------|-------------|----------|
| Add `use_lockfile = true` to backend.hcl | S3-native locking, no DynamoDB table | ✓ |
| No locking — single-operator workflow | Skip locking infra for now | |

**User's choice:** Add `use_lockfile = true`.

| Option | Description | Selected |
|--------|-------------|----------|
| Saved plan file (`terraform apply tfplan`) | Apply is byte-identical to what was approved | ✓ |
| Re-plan fresh at apply time | Simpler sequence, small drift risk | |

**User's choice:** Saved plan file.

---

## Secret Container Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Terraform creates all fresh empty containers | No ARN overrides; matches existing "Terraform creates empty, later phase populates" convention | ✓ |
| Point at pre-existing secrets | Only sensible if containers already exist | |

**User's choice:** Terraform creates all fresh empty containers.
**Notes:** Confirmed live via `aws secretsmanager describe-secret --secret-id edgartools-prod-edgar-identity` → `ResourceNotFoundException` before asking — consistent with "create fresh."

| Option | Description | Selected |
|--------|-------------|----------|
| Strictly empty shells — no `put-secret-value` in Phase 6 | MDM values are Phase 8 scope; edgar-identity flagged as a gap | |
| Phase 6 also populates the edgar-identity secret value | Not a credential — a User-Agent string with an email; needed for the active deploy to function | ✓ |

**User's choice:** Phase 6 also populates the edgar-identity secret value.
**Notes:** This is the one exception to the "containers only, no values" rule — scoped narrowly to `edgar-identity` only; the 4 MDM containers remain empty shells (Phase 8 / MDM-02 territory).

---

## Pipeline Notifications Opt-In

| Option | Description | Selected |
|--------|-------------|----------|
| Enable now, with operator email as subscriber | Live alerting from the first prod apply | ✓ |
| Leave off for this apply, add later | Revisit once an on-call owner is settled | |

**User's choice:** Enable now.
**Notes:** Subscriber email confirmed as `thepaulananth@gmail.com` (session account email) in a follow-up question rather than assumed.

---

## versions.tf Bug-Fix Ownership

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 6 fixes it directly (ISO-01 exception) | Same pattern as Phase 4's dashboard README rewrite | ✓ |
| Document only — operator fixes outside go-live commits | Separate, non-go-live commit | |

**User's choice:** Phase 6 fixes it directly.
**Notes:** It is a hard blocker for the apply this phase exists to run, so fixing it in-phase (rather than deferring to an out-of-band commit) was judged consistent with the existing Phase 4 precedent for scoped source-code exceptions.

---

## Claude's Discretion

- Exact corrected `required_version` constraint value in `versions.tf` — user did not specify the replacement string; planner/researcher should check Phase 2 evidence for the value that was "temporarily worked around via a reverted edit" (per launch gate matrix row 12) and use that as the fix.

## Deferred Ideas

- MDM secret value population (postgres_dsn, neo4j, api_keys, snowflake) — explicitly Phase 8 / MDM-02.
- Snowflake native-pull stack deploy — Phase 7.
- Bronze data reuse from dev — already has a documented procedure in the launch gate matrix (row 13); not re-discussed as a gray area since it wasn't actually open.
