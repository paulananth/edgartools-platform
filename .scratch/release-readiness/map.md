# Current-Head Production Launch Readiness

## Destination

Produce a decision-complete validation plan for production operator readiness, bound to an immutable Release Candidate commit and exact warehouse/MDM image digests, with every hard gate, evidence artifact, owner, dependency, and GO condition specified.

## Notes

- Domain: AWS-first SEC EDGAR data platform spanning AWS workflows, Snowflake/dbt, MDM, hosted graph, read-only dashboard, monitoring, and recovery.
- Planning only by default. Actual deployment, production mutation, and release execution begin after this map reaches the destination.
- Read `CONTEXT.md` and `docs/release-readiness/initial-findings.md` before working a ticket.
- Production operator readiness is the boundary; public/customer-facing launch is separate.
- The Release Candidate is an immutable integration-branch commit plus exact warehouse and MDM image digests.
- Full-chain success is mandatory. BatchSilver success cannot waive a downstream failure.
- Table-level data integrity, complete in-scope hosted-graph population, release-bound dashboard approval, and a successful rollback rehearsal are hard GO gates.
- GO fails closed. Missing direct evidence cannot become PASS through conditional or accepted-basis approval.
- AWS/Snowflake-only architecture, passive Terraform, secret-safe evidence, named approvals, and bounded stop conditions are fixed constraints rather than decisions to reopen.

## Decisions so far

<!-- Closed ticket decisions are appended here as one-line context pointers. -->

- [Define the Release Evidence Manifest](issues/01-define-release-evidence-manifest.md) — Use an automatically generated, append-only, digest-bound Candidate Evidence Set with a composite watermark, 24-hour live-evidence window, structured human attestations, and signed Git Release Seal.
- [Explain the MdmExport Failure Boundary](issues/02-explain-mdm-export-failure-boundary.md) — The July 5 failure was a pre-export Snowflake entitlement rejection; current readiness remains unverified until a dedicated deployed-runtime, read-only preflight proves the rotated secret's canonical target and runnable warehouse.
- [Design the MaxConcurrency=4 Data Integrity Proof](issues/03-design-maxconcurrency4-data-integrity-proof.md) — Require one execution-bound artifact with table-specific reconciliation, guarded publication, zero refetch, exact shard coverage, and a deterministic 16-batch idempotency rerun; historical reconstruction cannot satisfy current GO.
- [Define the MdmExport Entitlement Preflight and Retry Policy](issues/10-define-mdm-export-entitlement-preflight-and-retry-policy.md) — Require a same-runtime, marker-bound, non-mutating export capability gate with secret-safe evidence, command-owned transient retry, fail-fast prerequisite errors, and fresh full-chain revalidation after operator correction.
- [Define Required Relationship Bulk-Load Completion Gate](issues/12-define-required-relationship-bulk-load-completion-gate.md) — Require a fail-closed accession ledger over proxy, Item 5.02, and 13F candidates, with verified artifacts, terminal parser outcomes, temporal/amendment semantics, no release caps, idempotent replay, and exact graph parity.
- [Define Adviser-Fund Source Contract](issues/13-define-adviser-fund-source-contract.md) — Use public SEC/IAPD historical Form ADV Part 1 bulk filing data plus the current compilation control, with CRD/PFID identity, latest-effective filing reconstruction, and exact `MANAGES_FUND` parity.
- [Define Parent-Company Source and Parser Contract](issues/14-define-parent-company-source-parser-contract.md) — Use complete SEC annual-filing attachment inventories and Exhibit 21/8 evidence; model disclosed subsidiary-to-registrant relationships without inferring an immediate legal-parent hierarchy.
- [Define Auditor Evidence Ingestion Contract](issues/15-define-auditor-evidence-ingestion-contract.md) — Use direct annual-filing iXBRL or bounded audit-report evidence as primary and PCAOB AuditorSearch/Form AP for canonical firm identity, amendments, and corroboration.

## Not yet specified

- The final Release Candidate commit and image digests, which cannot be named until integration stabilizes.

## Out of scope

- Public or customer-facing launch readiness; this effort ends at production operator readiness.
- Non-AWS deployment paths, registries, storage targets, workflow engines, or secret-management systems.
- Replacing passive Terraform with runtime commands, image rollout, schedules, or secret values.
- Executing the deployment or mutating production while charting this decision map.
## Decision: Relationship Eligibility at the Release Watermark

All eleven relationship types are required for initial GO. Optionality is recorded per candidate in a complete applicability ledger; it does not permit excluding a required type. Eligibility, coverage, graph publication, and per-type parity derive from one transaction-consistent snapshot at the Release Data Watermark. See `docs/release-readiness/relationship-eligibility-at-release-watermark.md`.
## Newly exposed relationship-data blockers

- [12 — Define Required Relationship Bulk-Load Completion Gate](issues/12-define-required-relationship-bulk-load-completion-gate.md)
- [16 — Implement Relationship Source Candidate Ledger](issues/16-implement-relationship-source-candidate-ledger.md)
- [17 — Implement Strict Relationship Artifact Bulk Load](issues/17-implement-strict-relationship-artifact-bulk-load.md)
- [18 — Implement Item 5.02 Employment Events](issues/18-implement-item-502-employment-events.md)
- [19 — Implement Effective 13F Filing Set](issues/19-implement-effective-13f-filing-set.md)
- [20 — Execute Required Relationship Production Bulk Load](issues/20-execute-required-relationship-production-bulk-load.md)
- [21 — Implement Authoritative Form ADV Private-Fund Ingestion](issues/21-implement-authoritative-form-adv-private-fund-ingestion.md)
- [22 — Implement SEC Subsidiary Exhibit Ingestion](issues/22-implement-sec-subsidiary-exhibit-ingestion.md)
- [23 — Implement Auditor-Report Evidence Ingestion](issues/23-implement-auditor-report-evidence-ingestion.md)
