# Current-Head Production Launch Readiness

## Destination

Produce a decision-complete validation plan for production operator readiness, bound to an immutable Release Candidate commit and exact warehouse/MDM image digests, with every hard gate, evidence artifact, owner, dependency, and GO condition specified.

## Notes

- Domain: AWS-first SEC EDGAR data platform spanning AWS workflows, Snowflake/dbt, MDM, hosted graph, read-only dashboard, monitoring, and recovery.
- **Map charter was planning-first**; relationship bulk-load **implementation and
  technical PASS evidence have already landed in prod** (2026-07-25 Ticket 20
  package, residual holds pipeline, Ticket 21/24 insider sample). Remaining open
  tickets define/close **operator GO** (rollback rehearsal, dashboard acceptance,
  full-chain gate language, evidence automation, GO packet) — not re-do bulk-load.
- Read `CONTEXT.md` and `docs/release-readiness/` before working a ticket.
- Production operator readiness is the boundary; public/customer-facing launch is separate.
- Full-chain success is mandatory. BatchSilver success cannot waive a downstream failure.
- GO fails closed. Missing direct evidence cannot become PASS through conditional or accepted-basis approval.
- AWS/Snowflake-only architecture, passive Terraform, secret-safe evidence, named approvals, and bounded stop conditions remain fixed constraints.
- **Numbering:** ADV private-fund task is **21**; insider-scoped EMPLOYED_BY is **24**
  (renumbered 2026-07-26 — dual-21 collision fixed).

## Decisions so far

<!-- Closed ticket decisions — one-line gist + link; detail lives in the ticket. -->

### Core readiness design

- [Define the Release Evidence Manifest](issues/01-define-release-evidence-manifest.md) — Append-only, digest-bound Candidate Evidence Set with composite watermark, 24h live-evidence window, structured attestations, signed Git Release Seal.
- [Explain the MdmExport Failure Boundary](issues/02-explain-mdm-export-failure-boundary.md) — July 5 failure was pre-export entitlement rejection; needs same-runtime preflight of rotated secret + warehouse.
- [Design the MaxConcurrency=4 Data Integrity Proof](issues/03-design-maxconcurrency4-data-integrity-proof.md) — Execution-bound table reconciliation, guarded publication, zero refetch, exact shard coverage, 16-batch idempotency rerun.
- [Define Relationship Eligibility at the Release Watermark](issues/04-define-relationship-eligibility-at-release-watermark.md) — All eleven relationship types required for initial GO; applicability ledger per candidate; one watermark snapshot for eligibility/coverage/graph/parity.
- [Define the MdmExport Entitlement Preflight and Retry Policy](issues/10-define-mdm-export-entitlement-preflight-and-retry-policy.md) — Same-runtime non-mutating export capability gate; command-owned transient retry; full-chain revalidation after operator fix.
- [Define the BatchSilver Contention-Safe Publication Boundary](issues/11-define-batchsilver-contention-safe-publication-boundary.md) — Semantic rehydrate-and-merge + atomic S3 conditional write; conflicts rerun full batch.
- [Define the Full-Chain Launch Gate](issues/06-define-full-chain-launch-gate.md) — Reusable per-candidate template, 9 ordered stages (identity → rollback-readiness precondition → export preflight → BatchSilver integrity → relationship source completion → MDM/graph execution → relationship eligibility & parity, strict/no exclusions → dashboard acceptance → GO packet); new execution name on any failure; `full-chain-launch-pass.json` evidence. Currently cannot Pass: INSTITUTIONAL_HOLDS = 0 — **not** EDGE-11 (that's stale; source data has 6.8M rows) but a `ShardedSilverReader._TABLES` registration gap for `sec_thirteenf_filing`, fixed 2026-07-26, no exclusion valve until re-derived.
- [Define the Rollback Rehearsal Contract](issues/05-define-rollback-rehearsal-contract.md) — Two-part standing (not per-candidate) proof, both attested by AWS Operator: (1) digest restoration proven by ordinary use of `deploy-aws-application.sh --image-ref` — no dedicated drill, no staleness/expiration concept, bound to a **1-hour RTO**; (2) BatchSilver concurrency restoration requires an actual live re-run exercising the old-task/new-task overlap during the rollback transition (not just a parameter check), proving ticket 11's contention-safe publication boundary holds — separate from the 1-hour bound, judged pass/fail not by a clock. Evidence at a fixed non-RC-scoped path (`docs/release-readiness/rollback-rehearsal.json`), regenerated only when the mechanism itself changes.
- [Execute the Rollback Rehearsal](issues/26-execute-rollback-rehearsal.md) — Both proofs executed live in prod 2026-07-29, **PASS**. Digest restore: 5m37s (within 1h RTO). BatchSilver overlap: two `bootstrap-batch` tasks on the two distinct digests from Proof 1, hydrated the same base silver version 0.7s apart, publish windows overlapped ~70s, neither write lost (2 distinct sequential canonical versions), CIK-scoped semantic digest byte-identical before/after. Evidence: `docs/release-readiness/rollback-rehearsal.json` + `rollback-rehearsal-batchsilver-overlap-evidence.json`.
- [Define Release-Bound Dashboard Acceptance](issues/07-define-release-bound-dashboard-acceptance.md) — `docs/release-readiness/dashboard-acceptance.json`, one entry per view keyed `<DASHBOARD>::<view_id>` across all 25 real views in the two Terraform-deployed Streamlit-in-Snowflake dashboards (`EDGARTOOLS_DASHBOARD`, `MDM_GRAPH_DASHBOARD`; the non-deployed `examples/dashboard/edgar_universe_dashboard.py` excluded), each with `status` + `watermark_checked` + three independent sub-checks (mutation surface, secret leakage, unbounded output). `READY` only if every view passes with a current watermark and all three sub-checks true; stale-watermark and thin-sample passes are distinct, explicit `NOT_READY` reasons, not silently accepted. Staleness is detected on watermark rebase, never auto-cleared. Attested by **Dashboard Reviewer** (ticket 01's existing named role). Validated via a logic prototype (`prototype/07-dashboard-acceptance` branch, not merged).

### Relationship contracts (research)

- [Define Required Relationship Bulk-Load Completion Gate](issues/12-define-required-relationship-bulk-load-completion-gate.md) — Fail-closed accession ledger over proxy, Item 5.02, 13F; terminal parser outcomes; exact graph parity.
- [Define Adviser-Fund Source Contract](issues/13-define-adviser-fund-source-contract.md) — SEC/IAPD ADV Part 1 bulk + compilation control; CRD/PFID; `MANAGES_FUND` parity.
- [Define Parent-Company Source and Parser Contract](issues/14-define-parent-company-source-parser-contract.md) — Exhibit 21/8 inventory; disclosed subsidiary→registrant without inventing legal parent hierarchy.
- [Define Auditor Evidence Ingestion Contract](issues/15-define-auditor-evidence-ingestion-contract.md) — Annual-filing iXBRL/audit-report primary; PCAOB Form AP for firm identity.

### Relationship implementation (execution complete — technical)

- [Implement Relationship Source Candidate Ledger](issues/16-implement-relationship-source-candidate-ledger.md) — Ledger built and used by strict freezes.
- [Implement Strict Relationship Artifact Bulk Load](issues/17-implement-strict-relationship-artifact-bulk-load.md) — Strict SM/path for relationship artifacts.
- [Implement Item 5.02 Employment Events](issues/18-implement-item-502-employment-events.md) — Employment-event silver + bulk-load path.
- [Implement Effective 13F Filing Set](issues/19-implement-effective-13f-filing-set.md) — Effective-set / window semantics for 13F.
- [Execute Required Relationship Production Bulk Load](issues/20-execute-required-relationship-production-bulk-load.md) — **Technical PASS 2026-07-25** (Ticket 20 strict endpoint seal) under the rules in force that day; **2026-07-26: INSTITUTIONAL_HOLDS reclassified non-blocking→required**, superseded by Ticket 06's strict-inheritance decision — PASS not sufficient for GO until a new dated evidence record shows INSTITUTIONAL_HOLDS parity too. **Production GO not self-declared**.
- [Implement Authoritative Form ADV Private-Fund Ingestion](issues/21-implement-authoritative-form-adv-private-fund-ingestion.md) — ADV bulk pipeline landed (PR #238 family); further ADV *plan* work lives under `.scratch/adv-pipeline/`.
- [Implement SEC Subsidiary Exhibit Ingestion](issues/22-implement-sec-subsidiary-exhibit-ingestion.md) — Subsidiary evidence path for HAS_PARENT_COMPANY.
- [Implement Auditor-Report Evidence Ingestion](issues/23-implement-auditor-report-evidence-ingestion.md) — Auditor evidence path for AUDITED_BY.
- [Insider-scoped EMPLOYED_BY completeness](issues/24-insider-scoped-employed-by-completeness.md) — Doctrine + SM + 10-CIK IS_INSIDER verify **146/146**; full-universe GO remains operator/GO-packet.

### Prod residuals (outside original ticket list, for GO context)

- Residual holds graph pipeline (`residual_holds_graph`, PR #265/#266) — security / HOLDS / INSTITUTIONAL_HOLDS fill path; candidate generation not auto-activate.
- Gold SOURCE load gap fixed (missing evidence tables + EARNINGS_CALENDAR map, PR #267) — `GOLD.COMPANY` repopulated after native-pull failure.

## Not yet specified

- Final Release Candidate commit and warehouse/MDM image digests for GO seal.
- Whether residual holds candidate generation must be **activated** before GO, or GO binds the Ticket 20 activated generation plus enumerated residual gaps.
- Soak criteria for any post-GO dashboard automation.

## Out of scope

- Public or customer-facing launch readiness; this effort ends at production operator readiness.
- Non-AWS deployment paths, registries, storage targets, workflow engines, or secret-management systems.
- Replacing passive Terraform with runtime commands, image rollout, schedules, or secret values.
- Re-running Ticket 20 bulk-load from zero without a new operator decision (technical package already PASS).

## Open frontier (hygiene 2026-07-29b)

Unblocked open tickets (work through the map; claim before starting):

1. [Design the Release Evidence Automation](issues/09-design-release-evidence-automation.md) — prototype (cross-cutting per ticket 06; assembles the Candidate Evidence Set, not a numbered stage)  
2. [Define ERDP-05-04-Equivalent Promotion Criteria for the F1–F12 Coverage-Matrix Products](issues/25-define-erdp-f1-f12-promotion-checklist.md) — grilling, new 2026-07-27. Not yet worked (recorded as a go-live dependency only, per explicit instruction) — the older Gold/MDM ER products (identity, filings metadata, historical financials, ownership, 13F, graph neighborhood, executive pay, accounting scores, etc.) have no defined Partial→Covered promotion checklist, unlike the 4 new Explore products (`erdp-coverage-promotion`, DESTINATION REACHED 2026-07-27).  
3. [Define the Direct-Evidence GO Packet](issues/08-define-direct-evidence-go-packet.md) — grilling (blocked by 09, **25** — 01, 05, 06, **07** resolved)

## Hygiene log

- **2026-07-29 (b):** Ticket 07 (Define Release-Bound Dashboard Acceptance) resolved via a
  logic prototype — inventoried all 25 real, Terraform-deployed views across the two prod
  Streamlit-in-Snowflake dashboards (`EDGARTOOLS_DASHBOARD`, `MDM_GRAPH_DASHBOARD`; excluded
  the non-deployed `examples/dashboard/edgar_universe_dashboard.py`), designed a per-view
  acceptance schema (`docs/release-readiness/dashboard-acceptance.json`) with three independent
  sub-checks (mutation surface, secret leakage, unbounded output) plus watermark tracking, and
  drove it through stale-watermark and thin-sample edge cases by hand before locking the shape.
  User confirmed schema shape, staleness-detected-not-auto-cleared behavior, and the
  view-inventory boundary; separately confirmed the attesting role as **Dashboard Reviewer**
  (ticket 01's existing named role, no new role introduced). Prototype captured on throwaway
  branch `prototype/07-dashboard-acceptance` (commit `78013d8`), not merged. Removed from open
  frontier; unblocks ticket 08 (Direct-Evidence GO Packet) alongside tickets 01/05/06.
- **2026-07-29:** Ticket 26 (Execute the Rollback Rehearsal) resolved — both proofs executed
  live in prod and PASS. Digest restore 5m37s (1h RTO). BatchSilver overlap: two `bootstrap-batch`
  ECS tasks launched directly (not via a full-universe Step Functions Map) on the two digests
  from the digest-restore proof, same CIK (Apple, 320193), hydrated the same base silver
  version 0.7s apart, publish windows overlapped ~70s, no lost update (2 distinct sequential
  canonical versions), CIK-scoped semantic reconciliation byte-identical before/after across 6
  tables. Evidence: `docs/release-readiness/rollback-rehearsal.json` +
  `rollback-rehearsal-batchsilver-overlap-evidence.json`. Removed from open frontier.
- **2026-07-28:** Ticket 05 (Rollback Rehearsal Contract) resolved via grilling — two-part
  standing proof (ordinary-use digest restoration within a 1h RTO, no staleness concept; a live
  BatchSilver re-run proving no silver clobbering during the rollback-transition overlap,
  separate from that bound), AWS-Operator-attested, evidence at a fixed non-RC-scoped path.
  Surfaced new task ticket **26** (Execute the Rollback Rehearsal) to actually perform the proof
  and produce the evidence file — removed from open frontier, replaced by 26.
- **2026-07-26:** Renumbered dual `21-insider-…` → **24**; cleared stale 06 blockers on 20–23; normalized Status headers on 13–15; refreshed Decisions so far for 16–24 + prod residual context.
- **2026-07-26:** Ticket 06 (Full-Chain Launch Gate) resolved via grilling — 9-stage ordered template, strict inheritance of ticket 04's no-exclusion rule (surfaces INSTITUTIONAL_HOLDS as a real blocker, not a design gap), new-execution-name-on-failure relying on existing per-stage idempotency. Removed from open frontier.
- **2026-07-26 (correction):** ticket 06's INSTITUTIONAL_HOLDS note initially blamed EDGE-11 (bulk fetch never selects 13F-HR) — **stale as of this session**. Live prod check: `SEC_THIRTEENF_HOLDING` already has 6.8M rows in Snowflake SOURCE. Real cause found via CloudWatch: `ShardedSilverReader._TABLES` (`edgar_warehouse/silver_support/sharded_reader.py`) never registered `sec_thirteenf_filing` (added same commit as the holding table, d20cad8), so the derive JOIN hits a DuckDB catalog error that the graceful missing-table skip swallows as a false "not loaded yet." Same gap silently drops `sec_employment_event` (EDGE-09 sibling). Fixed by adding both names to `_TABLES`; regression test added; no SEC refetch needed. Deploy + re-derive pending operator go.
- **2026-07-26 (gating contradiction resolved):** Ticket 20's Done-when had marked `INSTITUTIONAL_HOLDS` parity "non-blocking" for launch (Release Owner decision, 2026-07-19). This directly conflicted with Ticket 04 ("all eleven relationship types required") and Ticket 06, resolved later the same day, which explicitly named INSTITUTIONAL_HOLDS while confirming strict inheritance with **no exclusion valve**. Same Release Owner, later and more specific decision controls: struck the non-blocking clause in Ticket 20 (kept visible, not deleted) and marked it superseded — INSTITUTIONAL_HOLDS parity is now required on the same footing as the other ten types. The 2026-07-25 Ticket 20 PASS record is not retroactively invalid (accurate under that day's rules) but is not sufficient for GO under today's rules pending a new evidence record covering INSTITUTIONAL_HOLDS parity.
