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

## Open frontier (hygiene 2026-07-26)

Unblocked open tickets (work through the map; claim before starting):

1. [Define the Rollback Rehearsal Contract](issues/05-define-rollback-rehearsal-contract.md) — grilling (now also the standing precondition ticket 06's stage 2 depends on)  
2. [Define Release-Bound Dashboard Acceptance](issues/07-define-release-bound-dashboard-acceptance.md) — prototype  
3. [Design the Release Evidence Automation](issues/09-design-release-evidence-automation.md) — prototype (cross-cutting per ticket 06; assembles the Candidate Evidence Set, not a numbered stage)  
4. [Define ERDP-05-04-Equivalent Promotion Criteria for the F1–F12 Coverage-Matrix Products](issues/25-define-erdp-f1-f12-promotion-checklist.md) — grilling, new 2026-07-27. Not yet worked (recorded as a go-live dependency only, per explicit instruction) — the older Gold/MDM ER products (identity, filings metadata, historical financials, ownership, 13F, graph neighborhood, executive pay, accounting scores, etc.) have no defined Partial→Covered promotion checklist, unlike the 4 new Explore products (`erdp-coverage-promotion`, DESTINATION REACHED 2026-07-27).  
5. [Define the Direct-Evidence GO Packet](issues/08-define-direct-evidence-go-packet.md) — grilling (blocked by 05, 07, 09, **25** — 06 resolved 2026-07-26)

## Hygiene log

- **2026-07-26:** Renumbered dual `21-insider-…` → **24**; cleared stale 06 blockers on 20–23; normalized Status headers on 13–15; refreshed Decisions so far for 16–24 + prod residual context.
- **2026-07-26:** Ticket 06 (Full-Chain Launch Gate) resolved via grilling — 9-stage ordered template, strict inheritance of ticket 04's no-exclusion rule (surfaces INSTITUTIONAL_HOLDS as a real blocker, not a design gap), new-execution-name-on-failure relying on existing per-stage idempotency. Removed from open frontier.
- **2026-07-26 (correction):** ticket 06's INSTITUTIONAL_HOLDS note initially blamed EDGE-11 (bulk fetch never selects 13F-HR) — **stale as of this session**. Live prod check: `SEC_THIRTEENF_HOLDING` already has 6.8M rows in Snowflake SOURCE. Real cause found via CloudWatch: `ShardedSilverReader._TABLES` (`edgar_warehouse/silver_support/sharded_reader.py`) never registered `sec_thirteenf_filing` (added same commit as the holding table, d20cad8), so the derive JOIN hits a DuckDB catalog error that the graceful missing-table skip swallows as a false "not loaded yet." Same gap silently drops `sec_employment_event` (EDGE-09 sibling). Fixed by adding both names to `_TABLES`; regression test added; no SEC refetch needed. Deploy + re-derive pending operator go.
- **2026-07-26 (gating contradiction resolved):** Ticket 20's Done-when had marked `INSTITUTIONAL_HOLDS` parity "non-blocking" for launch (Release Owner decision, 2026-07-19). This directly conflicted with Ticket 04 ("all eleven relationship types required") and Ticket 06, resolved later the same day, which explicitly named INSTITUTIONAL_HOLDS while confirming strict inheritance with **no exclusion valve**. Same Release Owner, later and more specific decision controls: struck the non-blocking clause in Ticket 20 (kept visible, not deleted) and marked it superseded — INSTITUTIONAL_HOLDS parity is now required on the same footing as the other ten types. The 2026-07-25 Ticket 20 PASS record is not retroactively invalid (accurate under that day's rules) but is not sufficient for GO under today's rules pending a new evidence record covering INSTITUTIONAL_HOLDS parity.
