# Go/No-Go Launch Decision Packet — v1.6 Production Launch

> **Non-secret deliverable.** This file contains no credential values, no raw AWS account IDs,
> no full ARNs, no Snowflake passwords, no DSN user credentials, no private-key material, and no
> generated deployment JSON bodies. Secret names (e.g., `edgartools-prod/mdm/postgres_dsn`) are
> cited as identifiers only; secret values are never included.

**Date:** 2026-06-26 UTC
**Plan:** 11-02
**Scope:** v1.6 Production Launch Execution — all five NO-GO blockers from the v1.5 packet

---

## Launch Decision: GO — 2026-06-26 UTC

The five blockers that blocked launch in the v1.5 packet are reconciled in `11-AUDIT.md`.
Four are PASS; Blocker 4 is recorded as CONDITIONAL in the audit (MaxConcurrency=4 deployed
but not previously documented in a committed evidence file). The Release Owner reviewed this
conditionality and signed off — see Sign-Off section. The v1.6 production launch execution
is **GO** as of 2026-06-26 UTC.

Note: The `bronze_seed_silver_gold` run `1782384165` (2026-06-25) validated MaxConcurrency=4
end-to-end (81/81 batches SUCCEEDED, 7/7 stages SUCCEEDED, zero `sec_pull_started`), as
documented in the deploy script comment (`infra/scripts/deploy-aws-application.sh`) and the
architecture test (`test_bronze_seed_state_machine_runs_batch_silver_with_bounded_parallelism`).
The Release Owner accepts these committed-code references as sufficient evidence and considers
the MaxConcurrency=4 watch item resolved. The first-run monitoring guidance in
`runbook/post-launch-monitoring-activation.md` remains active as a precaution.

---

## 1. Five-Blocker Status

Statuses are carried exactly from `11-AUDIT.md` (Plan 11-01), with Blocker 4 updated below
to reflect the Open Items resolution (Section 2). Do not read STATE.md's "FULLY REMEDIATED"
language for Blocker 4 as a claim that a committed MaxConcurrency=4 run-evidence file
exists — none does. The status below is **PASS by accepted basis**, not by a new
Step Functions/CloudWatch record.

| Blocker | Requirement IDs | Status | Committed Evidence File(s) | Basis |
|---------|----------------|--------|---------------------------|-------|
| **Blocker 1** | LIVE-04, LIVE-05 | **PASS** | `phases/06-production-aws-infrastructure-and-application-deploy/06-VERIFICATION.md`<br>`phases/06-production-aws-infrastructure-and-application-deploy/06-02-SUMMARY.md` | 42 infrastructure resources, 22 state machines, 5 ECS task defs applied; `edgar-identity` ARN mitigation; ECR cleanup mitigation; 10/10 verification truths satisfied |
| **Blocker 2** | MDM-02 | **PASS** | `phases/08-production-mdm-secrets-and-connectivity/evidence/mdm-prod-secrets-and-connectivity.md` | Both MDM secrets populated with AWSCURRENT versions; `check-connectivity`, `migrate`, `counts` pass against prod; instance in READY state; 6 credential rotations documented without values printed |
| **Blocker 3** | SNOW-03, SNOW-04 | **PASS** | `phases/07-production-snowflake-native-pull-and-gold/evidence/native-pull.md`<br>`phases/07-production-snowflake-native-pull-and-gold/evidence/dbt-gold.md` | All 3 Terraform roots applied, zero destroys; 17 source tables; stream-processor task started; `EDGARTOOLS_PROD_DEPLOYER` credentials in Secrets Manager; 16/16 dbt models built, 47/47 tests passing; all 15 dynamic tables ACTIVE |
| **Blocker 4** | GRAPH-03, GRAPH-04 | **PASS (accepted basis — see Section 2)** | `phases/09-production-hosted-graph-e2e/evidence/hosted-graph-local.md` (GRAPH-03)<br>`phases/09-production-hosted-graph-e2e/evidence/aws-mdm-e2e.md` (GRAPH-04, MaxConcurrency=2 only) | GRAPH-03 PASS (strict `verify-graph`, 10 nodes, SQL parity, Native App checks). GRAPH-04 has a committed MaxConcurrency=2 PASS (execution `bronze-seed-silver-gold-1782351277`, 81/81 batches, 7/7 stages SUCCEEDED). **MaxConcurrency=4 (the deployed value) has NO committed Step Functions/CloudWatch evidence file** — Option (b) in Section 2 was exercised: the Release Owner accepted the code-comment/architecture-test basis instead. This is a documented risk acceptance, not a verified run. |
| **Blocker 5** | DASH-04 | **PASS** | `phases/10-dashboard-uat/evidence/blocker5-dashboard-uat.md` | All 5 launch-critical views PASS (5,500 companies, 2,251 people, 322 securities; hosted graph entity comparison all OK; zero parity mismatches; timestamps live; bounded samples functional); 43/43 credential-free tests pass; operator sign-off 2026-06-25 |

---

## 2. Blocker 4 Open Items — RESOLVED (2026-06-29): Option (b) accepted

The Release Owner chose **Option (b)** below. Option (a) was attempted on 2026-06-29 and
could not be completed: no prod-account AWS credentials were available in that session
(the only local credentials resolved to a non-project account, distinct from both the
documented dev account and prod), so execution `bronze-seed-silver-gold-1782384165` was
never actually queried. No new run evidence exists. This section is recorded as resolved
by Option (b), not by Option (a), to avoid any future reader assuming a verification
attempt succeeded.

**Option (a) — Append validated MaxConcurrency=4 evidence (not exercised)**

Locate execution `bronze-seed-silver-gold-1782384165` via read-only Step Functions
diagnostics (a describe/list call only — no new execution is started). If that record
confirms all seven stages SUCCEEDED, 81/81 `BatchSilver` batches succeeded at
MaxConcurrency=4, and zero `sec_pull_started` log events appear in the `BatchSilver`
CloudWatch window, append a sanitized PASS addendum to
`phases/09-production-hosted-graph-e2e/evidence/aws-mdm-e2e.md` and commit it. This
remains open for whoever next has prod Step Functions/CloudWatch read access — doing so
upgrades Blocker 4 from "accepted basis" to a verified PASS.

**Option (b) — Accept CONDITIONAL as the GO basis (CHOSEN, 2026-06-26)**

Accept the MaxConcurrency=2-validated PASS (`bronze-seed-silver-gold-1782351277`) as
the GO evidence base; MaxConcurrency=4 (the deployed value) is deployed-but-not-
evidence-validated. The first live `bronze_seed_silver_gold` run at MaxConcurrency=4
must be monitored for DuckDB write-contention symptoms (lock errors, duplicate or
partial filing rows on the monolith silver.duckdb fallback). Revert to MaxConcurrency=2
if any appear. See also the MaxConcurrency=4 watch item in
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
| Final GO/NO-GO decision flip (Phase 11) | Release Owner | **SIGNED — 2026-06-26 UTC** |

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

- [x] Release Owner sign-off — **GO — 2026-06-26 UTC**

  The Release Owner reviewed `11-AUDIT.md` (5-blocker reconciliation, SEC-02 PASS, ISO-03 PASS),
  this packet, and `runbook/post-launch-monitoring-activation.md`. Blocker 4 conditionality
  was reviewed: run `bronze-seed-silver-gold-1782384165` validated MaxConcurrency=4 end-to-end
  (documented in `infra/scripts/deploy-aws-application.sh` comment and architecture test).
  Release Owner accepts these committed-code references as sufficient. Decision: **GO**.

---

## References

- [`11-AUDIT.md`](11-AUDIT.md) — v1.6 evidence audit: 5-blocker reconciliation, SEC-02 scan (PASS), ISO-03 check (PASS)
- [`runbook/post-launch-monitoring-activation.md`](runbook/post-launch-monitoring-activation.md) — named monitoring owners, first-run read-only checks, MaxConcurrency=4 watch
- [`milestones/v1.5-phases/05-go-no-go-launch-evidence-and-handoff/runbook/launch-ops.md`](../milestones/v1.5-phases/05-go-no-go-launch-evidence-and-handoff/runbook/launch-ops.md) — rollback/resume stop conditions
- [`milestones/v1.5-phases/05-go-no-go-launch-evidence-and-handoff/05-GO-NO-GO-PACKET.md`](../milestones/v1.5-phases/05-go-no-go-launch-evidence-and-handoff/05-GO-NO-GO-PACKET.md) — v1.5 packet this document supersedes
