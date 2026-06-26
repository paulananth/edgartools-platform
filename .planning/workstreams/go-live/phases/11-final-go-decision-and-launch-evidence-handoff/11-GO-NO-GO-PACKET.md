# Go/No-Go Launch Decision Packet — v1.6 Production Launch

> **Non-secret deliverable.** This file contains no credential values, no raw AWS account IDs,
> no full ARNs, no Snowflake passwords, no DSN user credentials, no private-key material, and no
> generated deployment JSON bodies. Secret names (e.g., `edgartools-prod/mdm/postgres_dsn`) are
> cited as identifiers only; secret values are never included.

**Date:** 2026-06-26 UTC
**Plan:** 11-02
**Scope:** v1.6 Production Launch Execution — all five NO-GO blockers from the v1.5 packet

---

## Launch Decision: GO — pending Release Owner sign-off (see Sign-Off section)

The five blockers that blocked launch in the v1.5 packet are reconciled in `11-AUDIT.md`.
Four are PASS; one (Blocker 4) is CONDITIONAL. The Release Owner must review the Blocker 4
conditionality and the open items below before signing. The decision line above does **not**
constitute a GO until the Release Owner sign-off box in the Sign-Off section is checked.

**If Blocker 4 remains CONDITIONAL at time of sign-off, the appropriate decision is
"GO — Conditional"** (accepting the MaxConcurrency=4 unvalidated-in-evidence watch item
documented in the Blocker 4 Open Items section below). If the Release Owner closes the open
item first by appending validated MaxConcurrency=4 evidence, the appropriate decision is
an unconditional GO.

---

## 1. Five-Blocker Status

Statuses are carried exactly from `11-AUDIT.md` (Plan 11-01). Do not read STATE.md's
"FULLY REMEDIATED" language for Blocker 4 as evidence of a clean PASS — the audit
explicitly records it as CONDITIONAL because the deployed MaxConcurrency=4 value has no
committed end-to-end evidence.

| Blocker | Requirement IDs | Status | Committed Evidence File(s) | Basis |
|---------|----------------|--------|---------------------------|-------|
| **Blocker 1** | LIVE-04, LIVE-05 | **PASS** | `phases/06-production-aws-infrastructure-and-application-deploy/06-VERIFICATION.md`<br>`phases/06-production-aws-infrastructure-and-application-deploy/06-02-SUMMARY.md` | 42 infrastructure resources, 22 state machines, 5 ECS task defs applied; `edgar-identity` ARN mitigation; ECR cleanup mitigation; 10/10 verification truths satisfied |
| **Blocker 2** | MDM-02 | **PASS** | `phases/08-production-mdm-secrets-and-connectivity/evidence/mdm-prod-secrets-and-connectivity.md` | Both MDM secrets populated with AWSCURRENT versions; `check-connectivity`, `migrate`, `counts` pass against prod; instance in READY state; 6 credential rotations documented without values printed |
| **Blocker 3** | SNOW-03, SNOW-04 | **PASS** | `phases/07-production-snowflake-native-pull-and-gold/evidence/native-pull.md`<br>`phases/07-production-snowflake-native-pull-and-gold/evidence/dbt-gold.md` | All 3 Terraform roots applied, zero destroys; 17 source tables; stream-processor task started; `EDGARTOOLS_PROD_DEPLOYER` credentials in Secrets Manager; 16/16 dbt models built, 47/47 tests passing; all 15 dynamic tables ACTIVE |
| **Blocker 4** | GRAPH-03, GRAPH-04 | **CONDITIONAL** | `phases/09-production-hosted-graph-e2e/evidence/hosted-graph-local.md` (GRAPH-03)<br>`phases/09-production-hosted-graph-e2e/evidence/aws-mdm-e2e.md` (GRAPH-04) | GRAPH-03 PASS (strict `verify-graph`, 10 nodes, SQL parity, Native App checks). GRAPH-04 PASS at MaxConcurrency=2 only (execution `bronze-seed-silver-gold-1782351277`, 81/81 batches, 7/7 stages SUCCEEDED). **The deployed source sets MaxConcurrency=4 but that value has no committed end-to-end evidence.** See open items below. |
| **Blocker 5** | DASH-04 | **PASS** | `phases/10-dashboard-uat/evidence/blocker5-dashboard-uat.md` | All 5 launch-critical views PASS (5,500 companies, 2,251 people, 322 securities; hosted graph entity comparison all OK; zero parity mismatches; timestamps live; bounded samples functional); 43/43 credential-free tests pass; operator sign-off 2026-06-25 |

---

## 2. Blocker 4 Open Items

The Release Owner must choose one of two options before signing:

**Option (a) — Append validated MaxConcurrency=4 evidence (closes the open item; preferred)**

Locate execution `bronze-seed-silver-gold-1782384165` via read-only Step Functions
diagnostics (a describe/list call only — no new execution is started). If that record
confirms all seven stages SUCCEEDED, 81/81 `BatchSilver` batches succeeded at
MaxConcurrency=4, and zero `sec_pull_started` log events appear in the `BatchSilver`
CloudWatch window, append a sanitized PASS addendum to
`phases/09-production-hosted-graph-e2e/evidence/aws-mdm-e2e.md` and commit it.
Once committed, Blocker 4 upgrades from CONDITIONAL to PASS and the GO decision above
becomes unconditional.

**Option (b) — Accept CONDITIONAL as the GO basis**

Accept the MaxConcurrency=2-validated PASS (`bronze-seed-silver-gold-1782351277`) as
the GO evidence base and record in this packet's Sign-Off section that MaxConcurrency=4
is deployed-but-not-evidence-validated. The first live `bronze_seed_silver_gold` run at
MaxConcurrency=4 must be monitored for DuckDB write-contention symptoms (lock errors,
duplicate or partial filing rows on the monolith silver.duckdb fallback). Revert to
MaxConcurrency=2 if any appear. See also the MaxConcurrency=4 watch item in
`runbook/post-launch-monitoring-activation.md`.

---

## 3. v1.6 Production Launch Sequence

All five phases below are complete. Each step's already-executed status is recorded in the
committed evidence files. Commands and procedures are not re-pasted here — refer to the v1.5
runbooks linked per step.

| Phase | Step | Status | Evidence File |
|-------|------|--------|---------------|
| Phase 6 | AWS passive infrastructure + active application deploy | **COMPLETE** | `phases/06-production-aws-infrastructure-and-application-deploy/06-VERIFICATION.md` |
| Phase 7 | Snowflake native-pull stack + dbt gold dynamic tables | **COMPLETE** | `phases/07-production-snowflake-native-pull-and-gold/evidence/native-pull.md`<br>`evidence/dbt-gold.md` |
| Phase 8 | MDM Secrets Manager population + connectivity + migration | **COMPLETE** | `phases/08-production-mdm-secrets-and-connectivity/evidence/mdm-prod-secrets-and-connectivity.md` |
| Phase 9 | Hosted graph E2E (local verify-graph + AWS MDM E2E) | **COMPLETE — CONDITIONAL** | `phases/09-production-hosted-graph-e2e/evidence/hosted-graph-local.md`<br>`evidence/aws-mdm-e2e.md` |
| Phase 10 | Dashboard UAT (all 5 launch-critical views) | **COMPLETE** | `phases/10-dashboard-uat/evidence/blocker5-dashboard-uat.md` |

**Runbook references (v1.5, not re-pasted):**
- AWS deploy procedure: `milestones/v1.5-phases/02-aws-and-snowflake-production-deployment-dry-run/runbook/aws-deploy.md`
- Snowflake native-pull procedure: `milestones/v1.5-phases/02-aws-and-snowflake-production-deployment-dry-run/runbook/snowflake-native-pull.md`
- dbt gold procedure: `milestones/v1.5-phases/02-aws-and-snowflake-production-deployment-dry-run/runbook/dbt-gold.md`
- MDM secrets procedure: `milestones/v1.5-phases/03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md`
- Rollback/resume: `milestones/v1.5-phases/05-go-no-go-launch-evidence-and-handoff/runbook/launch-ops.md`

No step in this sequence runs out of order relative to the sequence above, and no step
runs before its named owner's approval is recorded.

---

## 4. Required Approvals

| Sequence step | Required approver | Status |
|---------------|-------------------|--------|
| AWS infrastructure + application deploy (Phase 6) | AWS operator | **SIGNED** |
| Snowflake native-pull + dbt gold (Phase 7) | Snowflake operator | **SIGNED** |
| MDM secrets + connectivity + hosted graph E2E (Phases 8-9) | MDM operator | **SIGNED** |
| Dashboard UAT (Phase 10) | Dashboard reviewer | **SIGNED** |
| Final GO/NO-GO decision flip (Phase 11) | Release Owner | **PENDING** |

No sequence step ran before its named owner approved it. The Release Owner sign-off is the
final gate. The four operator/reviewer approvals above are recorded in the committed
evidence files for their respective phases.

---

## 5. Evidence and Audit Reference (SEC-02, ISO-03)

**Full blocker reconciliation, secret-safety scan, and AWS-only isolation check:**
`phases/11-final-go-decision-and-launch-evidence-handoff/11-AUDIT.md`

Key results from `11-AUDIT.md`:

- **SEC-02 (secret-safety scan):** 0 blocking matches across 26 files in phases 06-10.
  Patterns checked: credentialed Postgres DSN, AWS IAM access key (`AKIA`), private-key
  PEM headers, JWT bearer tokens. Status: **PASS**.

- **ISO-03 (AWS-only isolation):** 0 matches for prohibited non-AWS deployment paths,
  registries, workflow engines, or secret-management systems across phases 06-10.
  Status: **PASS**.

Phase-11 deliverables (this file, `11-AUDIT.md`, and `runbook/post-launch-monitoring-activation.md`)
must maintain the same non-secret standard: no raw AWS account IDs, no full ARNs, no
credential values, no generated deployment JSON bodies.

---

## 6. Sign-Off

- [ ] Release Owner sign-off — pending

When signing, record the UTC date and one of:

- `GO — [date UTC]` if Option (a) above has closed the Blocker 4 open item.
- `GO — Conditional — [date UTC] — accepting MaxConcurrency=4 unvalidated-in-evidence watch item (see Blocker 4 Open Items)` if signing under Option (b).

The packet never records an unconditional GO while `11-AUDIT.md` lists an unresolved
Blocker 4 open item, unless the Release Owner explicitly accepts the conditionality in
writing in the signature line above.

---

## References

- [`11-AUDIT.md`](11-AUDIT.md) — v1.6 evidence audit: 5-blocker reconciliation, SEC-02 scan (PASS), ISO-03 check (PASS)
- [`runbook/post-launch-monitoring-activation.md`](runbook/post-launch-monitoring-activation.md) — named monitoring owners, first-run read-only checks, MaxConcurrency=4 watch
- [`milestones/v1.5-phases/05-go-no-go-launch-evidence-and-handoff/runbook/launch-ops.md`](../milestones/v1.5-phases/05-go-no-go-launch-evidence-and-handoff/runbook/launch-ops.md) — rollback/resume stop conditions
- [`milestones/v1.5-phases/05-go-no-go-launch-evidence-and-handoff/05-GO-NO-GO-PACKET.md`](../milestones/v1.5-phases/05-go-no-go-launch-evidence-and-handoff/05-GO-NO-GO-PACKET.md) — v1.5 packet this document supersedes
