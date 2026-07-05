# Phase 11 Evidence Audit

> **Non-secret deliverable.** This file contains no credential values, no raw AWS account IDs,
> no full ARNs, no Snowflake passwords, no DSN user credentials, no private-key material, and no
> generated deployment JSON bodies. Secret names (e.g., `edgartools-prod/mdm/postgres_dsn`) are
> cited as identifiers only; secret values are never included.

**Date:** 2026-06-25
**Plan:** 11-01
**Scope:** Phases 06-10 committed evidence files
**Purpose:** Reconcile all five NO-GO blocker themes against committed evidence before the
launch decision in Plan 11-02. Four blockers are PASS; one is CONDITIONAL (see Blocker 4).

---

## 1. Blocker Evidence Reconciliation

| Blocker | Requirement IDs | Committed Evidence File(s) | Key Matrix Rows | Status |
|---------|----------------|---------------------------|-----------------|--------|
| **Blocker 1** | LIVE-04, LIVE-05 | `phases/06-production-aws-infrastructure-and-application-deploy/06-VERIFICATION.md`<br>`phases/06-production-aws-infrastructure-and-application-deploy/06-02-SUMMARY.md` | AWS passive infra outputs; prod application manifest; AWS active application deploy; `edgar-identity` ARN mitigation; ECR cleanup mitigation | **PASS** |
| **Blocker 2** | MDM-02 | `phases/08-production-mdm-secrets-and-connectivity/evidence/mdm-prod-secrets-and-connectivity.md` | MDM Snowflake/Postgres secret container and connectivity | **PASS** |
| **Blocker 3** | SNOW-03, SNOW-04 | `phases/07-production-snowflake-native-pull-and-gold/evidence/native-pull.md`<br>`phases/07-production-snowflake-native-pull-and-gold/evidence/dbt-gold.md` | Snowflake native S3 pull stack; deployer direct grants; dbt compile/run/test; EDGARTOOLS_GOLD_STATUS freshness | **PASS** |
| **Blocker 4** | GRAPH-03, GRAPH-04 | `phases/09-production-hosted-graph-e2e/evidence/hosted-graph-local.md` (GRAPH-03)<br>`phases/09-production-hosted-graph-e2e/evidence/aws-mdm-e2e.md` (GRAPH-04) | Hosted graph `mdm sync-graph` + `mdm verify-graph`; AWS MDM E2E via `bronze_seed_silver_gold` | **CONDITIONAL** (see Open Items) |
| **Blocker 5** | DASH-04 | `phases/10-dashboard-uat/evidence/blocker5-dashboard-uat.md` | Dashboard operator inspection views | **PASS** |

### Blocker 1 Detail

10/10 verification truths satisfied. Re-verification performed after gap closure (commit `81e28c4`):
gap 1 was stale proof counts in a matrix row; gap 2 was an unredacted cluster ARN in a prior
evidence/aws.md draft (removed). Phase 6 produced 42 infrastructure resources, 22 state
machines, and 5 ECS task definitions. LIVE-04 and LIVE-05 both satisfied.

### Blocker 2 Detail

Both `edgartools-prod/mdm/postgres_dsn` and `edgartools-prod/mdm/snowflake` populated with
`AWSCURRENT` versions (2026-06-21). Commands `check-connectivity`, `migrate` (idempotent), and
`counts` all pass. Instance `EDGARTOOLS_PROD_MDM` in `READY` state. Credential rotation
documented over 6 rotations; no values printed. MDM-02 satisfied.

### Blocker 3 Detail

All 3 Terraform roots applied with zero destroys. `native_pull_ready = true`. 17 source tables
created. Stream-processor task state `started`. Service user `EDGARTOOLS_PROD_DEPLOYER` created;
credentials stored in `edgartools-prod/dbt/snowflake`. Six root-cause fixes documented (version
constraints, IAM policy namespacing, authenticator, STREAMLIT race, FINANCIAL_FACTS period-start
column migration). 16/16 dbt models built (15 dynamic tables + 1 status view), 47/47 dbt tests
pass. All 15 dynamic tables `scheduling_state = ACTIVE`. SNOW-03 and SNOW-04 satisfied.

### Blocker 4 Detail

**GRAPH-03 (local hosted graph): PASS.** Strict `mdm verify-graph --native-app-compute-pool
CPU_X64_XS` passed: 10 nodes, 0 edges, SQL parity ok, compute pool available, `GRAPH_INFO`,
`BFS`, and `WCC` checks pass. First-time `EDGARTOOLS_PROD.MDM` mirror load: 19 tables, 135 rows.

**GRAPH-04 (AWS MDM E2E): PASS at MaxConcurrency=2 only.**

Execution: `bronze-seed-silver-gold-1782351277`
Start: 2026-06-24T21:34:39-04:00
Stop: 2026-06-25T00:20:32-04:00
Final status: `SUCCEEDED`

| Stage | Result |
|-------|--------|
| `SeedFromBronze` | `SUCCEEDED` (exited 21:36:14) |
| `BatchSilver` (Distributed Map, MaxConcurrency=2 at execution time) | `SUCCEEDED` 23:03:57; 81/81 batches succeeded, 0 failed |
| `MdmRun` | `SUCCEEDED` (exited 00:14:52) |
| `MdmBackfill` | `SUCCEEDED` (exited 00:16:08) |
| `MdmSync` | `SUCCEEDED` (exited 00:17:15) |
| `MdmVerify` | `SUCCEEDED` (exited 00:18:42) |
| `GoldRefresh` | `SUCCEEDED` (exited 00:20:32) |

Zero-SEC-call confirmation: CloudWatch logs for `/aws/ecs/edgartools-prod-warehouse` filtered for
`sec_pull_started` across the full `BatchSilver` window — zero matches.

**The mismatch:** The deployed source (`infra/scripts/deploy-aws-application.sh`) sets
`BatchSilver MaxConcurrency=4`. The committed evidence file (`aws-mdm-e2e.md`, "Open follow-up:
BatchSilver concurrency" section) explicitly states MaxConcurrency=4 is **"unvalidated — only 2
produced the PASS documented above."** The deploy script's own inline comment references run
`bronze-seed-silver-gold-1782384165` as validating MaxConcurrency=4, but that run ID does not
appear in any committed evidence file (confirmed: `grep -rn "1782384165"
.planning/workstreams/go-live/phases/` — sole match is `11-01-PLAN.md`, not any evidence file).

### Blocker 4 Open Items

Before the Plan 11-02 GO decision, the release owner must choose one of the following options:

**Option (a) — Append validated MaxConcurrency=4 evidence (preferred)**

Locate run `bronze-seed-silver-gold-1782384165` via read-only AWS Step Functions diagnostics
(no execution is started; this is a describe/list call only). If the execution record confirms:
- All seven stages `SUCCEEDED`
- 81/81 `BatchSilver` batches succeeded at `MaxConcurrency=4`
- Zero `sec_pull_started` log events across the `BatchSilver` window
- `MaxConcurrency` value at execution time (from the state machine definition in effect, not the
  current source) was 4

...then append a sanitized PASS addendum to
`phases/09-production-hosted-graph-e2e/evidence/aws-mdm-e2e.md` recording those results and
commit it. Once committed, Blocker 4 status upgrades from CONDITIONAL to PASS.

**Option (b) — Accept the CONDITIONAL as the GO basis**

If option (a) is operationally impractical, the release owner may accept the
MaxConcurrency=2-validated PASS (`bronze-seed-silver-gold-1782351277`) as the GO evidence base
and record in Plan 11-02 that MaxConcurrency=4 is deployed-but-not-yet-evidence-validated. The
next live `bronze_seed_silver_gold` run at MaxConcurrency=4 must then be monitored for
DuckDB write-contention symptoms (lock errors, duplicate or partial filing rows) before
MaxConcurrency=4 is treated as confirmed safe. The STATE.md monitoring note (2026-06-25) already
documents this obligation.

**Resolution (2026-06-29, recorded in `11-GO-NO-GO-PACKET.md` Section 2):** Option (b) was
chosen. An attempt at Option (a) on 2026-06-29 could not obtain prod AWS credentials, so
execution `bronze-seed-silver-gold-1782384165` was never queried — this audit's CONDITIONAL
finding above stands unchanged as the point-in-time record; the packet records Blocker 4 as
PASS by accepted basis, not by new run evidence.

### Blocker 5 Detail

All 5 launch-critical views PASS: MDM Overview (5,500 companies, 2,251 people, 322 securities),
Hosted Graph Overview (6 entity types, all Entity Comparison Status = OK), Mismatch Diagnostics
(zero mismatches in parity table), Manual Refresh Timestamps (both timestamps live; Refresh button
triggers live re-read), Bounded Samples (row limit selector functional; all tables bounded).
43/43 credential-free tests pass (DASH-03 security check PASS). Operator sign-off: 2026-06-25.
DASH-01, DASH-03, DASH-04 satisfied.

---

## 2. Secret-Safety Check (SEC-02)

**Scope:** All `.md` files in phases 06-10, excluding `*-PLAN.md` files. PLAN files describe
credential patterns in prose; excluding them prevents the scan from matching its own documentation
of those patterns.

**BLOCKING credential scan command (run from go-live workstream root):**

```
grep -rEin --include="*.md" --exclude="*-PLAN.md" \
  'postgresql://[A-Za-z0-9][^:@[:space:]]*:[^<@[:space:]]+@|AKIA[0-9A-Z]{16}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}' \
  phases/06-production-aws-infrastructure-and-application-deploy/ \
  phases/07-production-snowflake-native-pull-and-gold/ \
  phases/08-production-mdm-secrets-and-connectivity/ \
  phases/09-production-hosted-graph-e2e/ \
  phases/10-dashboard-uat/
```

**Result: 0 blocking matches across 26 files.**

Patterns targeted:
- Credentialed Postgres DSN (user:password@ with a non-placeholder password)
- AWS IAM access key (`AKIA` + 16 uppercase alphanumeric characters)
- Private key PEM header (RSA, EC, OPENSSH variants)
- JWT bearer token (three-part dot-separated base64url string)

**Files scanned by phase:**

| Phase | Files |
|-------|-------|
| 06 — AWS infrastructure | 6 |
| 07 — Snowflake native pull and gold | 7 |
| 08 — MDM secrets and connectivity | 4 |
| 09 — Hosted graph E2E | 5 |
| 10 — Dashboard UAT | 1 |
| **Total** | **26** |

**Informational (non-blocking):** A secondary scan for the project AWS account ID and ARN prefixes
found **17 occurrences** across the 26 files in phases 06-10. These are project-wide committed
conventions (per CLAUDE.md and REQUIREMENTS.md) used in resource identifiers and are not in
SEC-02's prohibited list (DSNs with live credentials, access keys, private-key headers, JWT
tokens). They appear only in phases 06-10 evidence, not in this phase-11 deliverable.

**Phase 11 deliverables check:** Per the stricter v1.5 packet banner, phase-11 deliverables must
not contain raw AWS account IDs or full ARNs. Verified: `11-AUDIT.md` (this file) contains no
raw account IDs and no full ARNs. Secret names cited (e.g., `edgartools-prod/mdm/postgres_dsn`,
`edgartools-prod/mdm/snowflake`) are identifiers only; secret values are absent. Downstream
phase-11 outputs (`11-GO-NO-GO-PACKET.md`, runbooks) must maintain the same standard.

**Status: PASS** — 0 blocking matches; phase-11 deliverable is free of prohibited credential
values and raw account IDs.

---

## 3. AWS-Only Isolation Check (ISO-03)

**Scope:** All `.md` files in phases 06-10 excluding `*-PLAN.md` files. Scoped to the
`phases/06-10` directories specifically (not the full repository) to exclude `CLAUDE.md` and
`REQUIREMENTS.md`, which reference non-AWS services in prohibition and deprecation prose.

**Grep command (run from go-live workstream root):**

```
grep -rEin --include="*.md" --exclude="*-PLAN.md" \
  'non-AWS|gcloud|google cloud|\bgcp\b|dockerhub|docker\.io|quay\.io|kubernetes|\bk8s\b|\bhelm\b|hashicorp vault|doppler|1password' \
  phases/06-production-aws-infrastructure-and-application-deploy/ \
  phases/07-production-snowflake-native-pull-and-gold/ \
  phases/08-production-mdm-secrets-and-connectivity/ \
  phases/09-production-hosted-graph-e2e/ \
  phases/10-dashboard-uat/
```

**Per-term results (26 files scanned):**

| Term | Matches |
|------|---------|
| `non-AWS` | 0 |
| `gcloud` | 0 |
| `google cloud` | 0 |
| `\bgcp\b` | 0 |
| `dockerhub` | 0 |
| `docker.io` | 0 |
| `quay.io` | 0 |
| `kubernetes` | 0 |
| `\bk8s\b` | 0 |
| `\bhelm\b` | 0 |
| `hashicorp vault` | 0 |
| `doppler` | 0 |
| `1password` | 0 |
| **Total** | **0** |

**Neo4j note:** Neo4j appears in Phase 9 evidence (`aws-mdm-e2e.md`) as a deprecated runtime
whose legacy ECS secrets-injection wiring caused the initial `mdm_migrate` failure and was
subsequently removed from the MDM task-definition template. This reference documents the removal
of a non-AWS dependency, not introduction of one. Neo4j is not in the ISO-03 prohibited term
list (which targets newly-introduced non-AWS cloud registries, storage targets, workflow engines,
and secret-management systems). No Neo4j runtime dependency remains in the deployed architecture
per Phase 9 evidence.

**Status: PASS** — zero introduced non-AWS deployment paths, registries, storage targets,
workflow engines, or secret-management systems across phases 06-10.
