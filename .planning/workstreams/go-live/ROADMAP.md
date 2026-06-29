# Roadmap: Go Live

workstream: go-live
status: complete
updated: 2026-06-29

---

## Milestones

- ✅ **v1.5 Go Live** — Production launch-readiness evidence and operator handoff across AWS deployment, Snowflake native pull/gold, MDM Snowflake Postgres, hosted graph verification, dashboard inspection, and secret-safe evidence. 5 phases, 12 plans, shipped 2026-06-19. Decision: **NO-GO — Conditional** (see `phases/05-go-no-go-launch-evidence-and-handoff/05-GO-NO-GO-PACKET.md`). Archive: [`milestones/v1.5-ROADMAP.md`](milestones/v1.5-ROADMAP.md).
- ✅ **v1.6 Production Launch Execution** — Executed the documented production sequence and flipped the v1.5 `NO-GO - Conditional` launch decision to `GO`. 6 phases, 13 plans, shipped 2026-06-26 (decision), documentation reconciled 2026-06-29. Decision: **GO — 2026-06-26 UTC** (see `phases/11-final-go-decision-and-launch-evidence-handoff/11-GO-NO-GO-PACKET.md`). All 5 blocker themes PASS; Blocker 4 PASS by accepted basis (Option b) — MaxConcurrency=4 itself has no committed AWS run evidence (see Phase 9 below and the packet's Section 2).

**No further phases are planned for this workstream.** This file previously listed Phases
7, 8, 9, and 11 as blocked/pending; that was stale (last updated 2026-06-19, mid-execution).
All phase content below is now historical record, corrected to match `STATE.md` and the
final packet as of 2026-06-29.

---

## Completed Milestone: v1.6 Production Launch Execution

**Goal:** Turn the v1.5 `NO-GO - Conditional` launch decision into `GO` by executing the
documented production sequence and capturing secret-safe production PASS evidence.

**Starting phase number:** Phase 6. v1.5 used Phases 1-5, and v1.5 evidence remains linked
from archived milestone files and the go/no-go packet.

### Phase 6: Production AWS Infrastructure And Application Deploy

**Goal:** AWS operator applies prod infrastructure, deploys active AWS application components,
and captures non-secret evidence for both passive outputs and active app manifest readiness.

**Requirements:** LIVE-04, LIVE-05

**Depends on:** v1.5 launch gate matrix, `runbook/aws-deploy.md`, approved image references,
and AWS operator approval.

**Plans:** 2/2 plans complete

- [x] **06-01:** Prod Terraform apply and passive infrastructure evidence capture.
- [x] **06-02:** Active AWS application deploy, `infra/aws-prod-application.json` presence/summary evidence, and launch gate matrix update.

**Success criteria:**

1. Prod Terraform apply completes or records a precise BLOCKED status with owner and remediation.
2. Required Terraform outputs are captured as non-secret evidence.
3. Production deploy script runs with explicit image references and no Terraform-owned runtime secret values.
4. `infra/aws-prod-application.json` is summarized without committing sensitive generated JSON.

### Phase 7: Production Snowflake Native Pull And Gold

**Goal:** Snowflake operator deploys the production native-pull stack and proves dbt gold
readiness through production-target run/test evidence.

**Requirements:** SNOW-03, SNOW-04

**Depends on:** Phase 6 AWS storage/export outputs, production Snowflake identifiers, and
Snowflake operator approval.

**Plans:** 2/2 plans complete — SNOW-03 and SNOW-04 PASS (after 07-01/07-02 documented the
initial BLOCKED state, a later session completed the Terraform applies and dbt run; see
`STATE.md` Blocker 3 and `evidence/native-pull.md` / `evidence/dbt-gold.md`)

- [x] **07-01:** Prod Snowflake native-pull preflight evidence; initial attempt BLOCKED (required local inputs absent), later resolved.
- [x] **07-02:** Prod dbt/gold dependency evidence — 16/16 dbt gold models built, 47/47 tests passing against production data.

**Success criteria:**

1. Storage integration, stage, source mirror tables, pipe, stream, procedures, and task are deployed or precisely blocked.
2. AWS access reconcile and Snowflake access checks produce non-secret evidence.
3. `dbt run --target prod` and `dbt test --target prod` pass or record actionable failure evidence.
4. `EDGARTOOLS_GOLD_STATUS` and freshness evidence are captured without sensitive values.

### Phase 8: Production MDM Secrets And Connectivity

**Goal:** MDM operator populates the required production secrets and proves the production
MDM database path before any hosted graph write path runs.

**Requirements:** MDM-02

**Depends on:** Phase 6 AWS secret containers, production Snowflake Postgres DSN, and MDM
operator approval.

**Plans:** 2/2 plans complete — MDM-02 PASS (PR #80; see `STATE.md` Blocker 2 and
`evidence/mdm-prod-secrets-and-connectivity.md`)

- [x] **08-01:** Populated prod `postgres_dsn` and `snowflake` secrets using the v1.5 runbook (AWSCURRENT versions confirmed).
- [x] **08-02:** Prod MDM connectivity, migration, and counts verification — `check-connectivity`/`migrate`/`counts` passed against prod.

**Success criteria:**

1. Both required production secret names are populated by an operator without printing values.
2. `check-connectivity`, `migrate`, and `counts` pass against the production MDM database URL.
3. Evidence records only secret names, command status, and sanitized counts.
4. Launch gate matrix rows for MDM secret/container readiness are updated.

### Phase 9: Production Hosted Graph E2E

**Goal:** MDM operator proves the production hosted graph path end to end through local
strict graph verification and AWS MDM E2E execution.

**Requirements:** GRAPH-03, GRAPH-04

**Depends on:** Phase 7 Snowflake/dbt readiness, Phase 8 MDM database readiness, production
Native App compute pool selector, and MDM operator approval.

**Plans:** 2/2 plan attempts executed; GRAPH-03 PASS, GRAPH-04 PASS by accepted basis
(see `STATE.md` Blocker 4 and `11-GO-NO-GO-PACKET.md` Section 2 — MaxConcurrency=2 has a
committed PASS via `bronze_seed_silver_gold` execution `bronze-seed-silver-gold-1782351277`;
MaxConcurrency=4, the deployed value, was never separately validated by a committed AWS
run-evidence file, and the Release Owner accepted that gap rather than blocking on it)

- [x] **09-01:** Bounded prod `mdm sync-graph` and strict prod `mdm verify-graph` — PASS with SQL parity, Native App checks.
- [x] **09-02:** Initial preflight blocked on missing `infra/aws-prod-application.json`; later resolved and a `bronze_seed_silver_gold` execution reached `ExecutionSucceeded` (81/81 BatchSilver batches, 7/7 stages, zero `sec_pull_started`) at MaxConcurrency=2.

**Success criteria:**

1. Production `mdm sync-graph` completes with explicit bounds and stop conditions.
2. Strict `mdm verify-graph` passes SQL parity, Native App grants, compute pool availability, `GRAPH_INFO`, `BFS`, and `WCC` checks.
3. AWS MDM E2E reaches all required stages through the Snowflake-hosted graph path.
4. Evidence proves no external `NEO4J_*` credentials are required.

### Phase 10: Production Dashboard UAT

**Goal:** Dashboard reviewer proves the read-only dashboard against production or
production-like configuration after the CLI/dbt/Native App gates are available.

**Requirements:** DASH-04

**Depends on:** Phases 7-9 and dashboard reviewer approval.

**Plans:** 1

- [x] **10-01:** Production or production-like dashboard UAT for all 5 launch-critical views. — PASS 2026-06-25; evidence at `phases/10-dashboard-uat/evidence/blocker5-dashboard-uat.md`

**Success criteria:**

1. Dashboard runs in read-only mode against production or production-like configuration.
2. Reviewer records pass/fail notes for MDM overview, hosted graph overview, mismatch diagnostics, manual refresh timestamps, and bounded samples.
3. UAT evidence contains no secrets, raw connector exceptions, stack traces, mutation controls, or unbounded exports.
4. Dashboard launch gate row flips to PASS only when all 5 views are inspected.

### Phase 11: Final GO Decision And Launch Evidence Handoff

**Goal:** Release owner audits all v1.6 evidence, verifies the secret-safety and AWS-only
contracts, flips the launch decision only if every blocker is PASS, and hands off monitoring.

**Requirements:** LIVE-06, OPS-03, SEC-02, ISO-03

**Depends on:** Phases 6-10 complete or explicitly blocked with owner decisions.

**Plans:** 2/2 plans complete — LIVE-06, OPS-03, SEC-02, ISO-03 all PASS/satisfied (see
`11-02-SUMMARY.md`). Documentation reconciled 2026-06-29 (see `11-GO-NO-GO-PACKET.md`
Section 2 and `11-AUDIT.md` resolution note) after Blocker 4's Open Items section was
found framed as a future decision when the Sign-Off had already happened.

- [x] **11-01:** Evidence audit, blocker matrix reconciliation (`11-AUDIT.md`) — SEC-02 PASS (0 blocking matches, 26 files), ISO-03 PASS (0 prohibited non-AWS paths).
- [x] **11-02:** Final go/no-go packet (`11-GO-NO-GO-PACKET.md`), Release Owner sign-off — **GO, 2026-06-26 UTC** — and post-launch monitoring activation (`runbook/post-launch-monitoring-activation.md`).

**Success criteria:**

1. All five NO-GO blocker themes are PASS before any GO decision is recorded.
2. Required approvers sign off in the documented sequence.
3. Evidence contains no DSNs, credential values, Terraform state, raw connector traces, raw Native App logs, or sensitive generated JSON.
4. No non-AWS deployment paths, registries, storage targets, workflow engines, or secret-management systems are introduced.
5. Post-launch monitoring owners know the first-run checks and escalation thresholds.

---

## Coverage

| Requirement | Phase | Status |
|-------------|-------|--------|
| LIVE-04 | Phase 6 | Complete |
| LIVE-05 | Phase 6 | Complete |
| SNOW-03 | Phase 7 | Complete |
| SNOW-04 | Phase 7 | Complete |
| MDM-02 | Phase 8 | Complete |
| GRAPH-03 | Phase 9 | Complete |
| GRAPH-04 | Phase 9 | Complete (accepted basis — MaxConcurrency=4 unverified) |
| DASH-04 | Phase 10 | Complete |
| LIVE-06 | Phase 11 | Complete |
| OPS-03 | Phase 11 | Complete |
| SEC-02 | Phase 11 | Complete |
| ISO-03 | Phase 11 | Complete |

**Coverage:** 12/12 v1.6 requirements mapped, 12/12 complete, 0 unmapped.

---

## Next Step

None required to launch — v1.6 is shipped and GO. One optional follow-up remains open
(not blocking): a prod-credentialed operator can query Step Functions/CloudWatch for
execution `bronze-seed-silver-gold-1782384165` to upgrade GRAPH-04 from "accepted basis"
to a fully verified PASS at MaxConcurrency=4 (Option (a) in `11-GO-NO-GO-PACKET.md`
Section 2). No further phases are planned in this workstream.
