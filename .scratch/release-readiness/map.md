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
- [Define the Full-Chain Launch Gate](issues/06-define-full-chain-launch-gate.md) — Reusable per-candidate template with 8 ordered gates (identity → rollback-readiness precondition → export preflight → BatchSilver integrity → relationship source completion → MDM/graph execution → relationship eligibility & parity, strict/no exclusions → dashboard acceptance); GO packet assembly is the downstream decision workflow, not a ninth gate. A failed attempt uses a new execution name; `full-chain-launch-pass.json` indexes the eight results. Currently cannot Pass: INSTITUTIONAL_HOLDS = 0 — **not** EDGE-11 (that's stale; source data has 6.8M rows) but a `ShardedSilverReader._TABLES` registration gap for `sec_thirteenf_filing`, fixed 2026-07-26, no exclusion valve until re-derived.
- [Define the Direct-Evidence GO Packet](issues/08-define-direct-evidence-go-packet.md) — The Candidate Evidence Set is the sole packet: append-only attempts, exactly eight indexed gates with explicit role attestations, a seal-anchored 24-hour window with standing rollback exception, an externally digest-bound authority registry, and fail-closed `not_ready` → `ready_for_owner` → verified sealed GO. F1-F12 product promotion is outside operator GO; implementation graduated to ticket 48.
- [Define the Rollback Rehearsal Contract](issues/05-define-rollback-rehearsal-contract.md) — Two-part standing (not per-candidate) proof, both attested by AWS Operator: (1) digest restoration proven by ordinary use of `deploy-aws-application.sh --image-ref` — no dedicated drill, no staleness/expiration concept, bound to a **1-hour RTO**; (2) BatchSilver concurrency restoration requires an actual live re-run exercising the old-task/new-task overlap during the rollback transition (not just a parameter check), proving ticket 11's contention-safe publication boundary holds — separate from the 1-hour bound, judged pass/fail not by a clock. Evidence at a fixed non-RC-scoped path (`docs/release-readiness/rollback-rehearsal.json`), regenerated only when the mechanism itself changes.
- [Execute the Rollback Rehearsal](issues/26-execute-rollback-rehearsal.md) — Both proofs executed live in prod 2026-07-29, **PASS**. Digest restore: 5m37s (within 1h RTO). BatchSilver overlap: two `bootstrap-batch` tasks on the two distinct digests from Proof 1, hydrated the same base silver version 0.7s apart, publish windows overlapped ~70s, neither write lost (2 distinct sequential canonical versions), CIK-scoped semantic digest byte-identical before/after. Evidence: `docs/release-readiness/rollback-rehearsal.json` + `rollback-rehearsal-batchsilver-overlap-evidence.json`.
- [Define ERDP-05-04-Equivalent Promotion Criteria for the F1–F12 Coverage-Matrix Products](issues/25-define-erdp-f1-f12-promotion-checklist.md) — Scoping decision only (2026-07-29): survey first (ticket 27), then graduate to 12 per-product satellite tickets (28–39), mirroring `erdp-coverage-promotion`'s ticket 01 → 03–06 shape. No product-specific criteria decided in this ticket itself.
- [Survey financial-services ER skill requirements per F1–F12 product](issues/27-survey-er-skill-requirements-per-f1-f12-product.md) — Read all 9 ER skills + `earnings-analysis`/`initiating-coverage`'s reference sub-files; findings in sibling file `issues/27-research-findings.md`. Grounding strength varies sharply: F1/F4 strong across nearly every skill; **F7 (13F/holders) and F8 (graph neighborhood) are the weakest** — most Partial cells have no supporting skill text; F11 (accounting forensic scores) has exactly one skill hit across all 9 skills, and it asks for two boolean flags, not a computed score; F5's GAAP-only platform surface only half-satisfies earnings-analysis's stated Adjusted+GAAP need; F9 (segment/geo revenue) is the most demanding, well-grounded requirement found (initiating-coverage Task 2); F12 conflates pure-SEC and market-priced metrics in the skills' own text, a boundary the platform enforces (ADR 0001) that the skills don't acknowledge. Unblocks tickets 28–39.
- [Root-cause the empty TICKER_REFERENCE pipeline](issues/40-root-cause-empty-ticker-reference-pipeline.md) — Two independent findings, not one: (1) `TICKER_REFERENCE` = 0 rows **is** a genuine, isolated export-wiring bug (gated to fire only on the one-time `seed-universe` command, never on the ongoing `daily-incremental`/`load_history`/`gold-refresh` paths); (2) the ~8-10% ticker-population figure on `MDM_COMPANY_ENTITY.ticker` and silver `sec_company_ticker` **is not a bug** — cross-referenced against SEC's own official `company_tickers.json` for the same 26,300-row active/tracked population, all three sources agree to within noise (9.8%/9.8%/9.8%), because the tracked universe is 88.9% `entity_type='other'` (insiders, advisers, broker-dealers, trusts — not equity issuers); `entity_type='operating'` alone matches SEC's ticker file at 72.9%. Silver `sec_company_ticker` (8,056 distinct CIKs, near-exact match to SEC's own 8,017) is the healthy root source; `MDM_COMPANY_ENTITY.ticker` is a derived copy of it, not an independent pipeline; the claimed third source `sec_tracked_universe` is a dead legacy table that never exists in real silver. Recommended fix (not implemented, research ticket): rewire `TICKER_REFERENCE` to read from silver `sec_company_ticker` and export on `gold-refresh`, not `seed-universe`. Unblocks ticket 28. **Addendum:** CUSIP cross-check (13F `INSTITUTIONAL_HOLDINGS`, name-matched) confirms the finding — 23,577 of 26,300 active CIKs have neither a ticker nor 13F evidence of being traded (correctly non-ticker); 149 have no ticker but DO match a 13F-held CUSIP by name — a 25-row spot-check found this is still mostly explained (gone-private, foreign-listed, structured debt, fund-trust wrappers, parent/subsidiary name-matching artifacts) but surfaces a small genuine set of real capture gaps (~5-6 of 25, e.g. NKGen Biotech, Soleno Therapeutics) worth spot-checking once the pipeline fix ships.
- [Investigate why daily_incremental reprocesses the full active universe](issues/43-investigate-daily-incremental-full-universe-scope.md) — SEC's daily-index has no JSON form (only `.idx`/`.xml`, confirmed live); narrowing `Stage0CompanyIdentity` from the full ~26,300-CIK universe down to a day's `impacted_ciks` (≈11% of the universe on a sample day) is architecturally possible and reuses only already-built code (the unscheduled `catch-up-daily-form-index` command plus `bootstrap-fundamentals`'s already-implemented `--cik-list` path), but trades away two specific coverage gaps (non-filing `submissions.json` drift; late daily-index republish after checkpointing) and `daily_incremental` has no schedule at all yet — graduated the actual narrow/no-narrow + cadence decision to ticket 45.
- [Decide whether/how to narrow daily_incremental's Stage 0 and set its actual schedule](issues/45-decide-narrow-daily-incremental-stage0-and-cadence.md) — Use a daily impacted-CIK refresh with forced seven-day index rechecks, a weekly full-universe backstop, one fail-closed cross-mode refresh slot, and explicit operator-managed Mon-Sat/Sun schedules; deploy disabled and enable only after bounded manual full-chain evidence and AWS Operator GO.
- [Research the SEC-listed company universe for bounded daily loads](issues/50-research-sec-company-universe-for-daily-load.md) — Live evidence found two independent runtime bounds: company identity must use the active operating-or-SEC-ticker union (~3.2K, not all ~26K entities), while daily artifacts must use the exact forced-index accession union and reset the shared client on `PoolTimeout`; ticker filtering the whole filing path would discard required filers.
- [Root-cause the excessive bounded Daily Identity Refresh runtime](issues/57-root-cause-bounded-daily-identity-runtime.md) — The bounded CIK universe works, but every serialized 500-CIK identity batch spends roughly 33 minutes merging and uploading the full 1.07 GB canonical DuckDB artifact; the next decision is a run-scoped, publication-safe aggregation boundary, and the six-hour schedule gate remains failed.
- [Decide a run-scoped publication boundary for Daily Identity Refresh](issues/58-decide-run-scoped-daily-identity-publication.md) — A dedicated run-bound reference snapshot plus immutable ordered CIK-batch deltas feed one fail-closed reducer and one ETag-guarded canonical promotion; batches/reducer recover independently under the identical run contract, and schedule activation still requires immutable-image full-chain evidence within six hours.
- [Research whether PostgreSQL is the right scalable operational Silver store](issues/62-research-operational-silver-postgres-fit.md) — Keep S3-backed DuckDB Silver plus the single reducer and add only a narrow durable operational ledger; PostgreSQL cannot fix the measured SEC/artifact retry bottleneck and must earn reconsideration through post-fix timing thresholds and a ≥2x end-to-end benchmark.
- [Root-cause Daily Artifact Retry Amplification](issues/59-root-cause-daily-artifact-retry-amplification.md) — The fixed-image daily worker correctly failed closed after completing 5,120/5,122 candidates, but generic ECS retry restarted the whole command because outcomes are telemetry rather than a durable worklist; decide the run-bound resume/disposition contract in ticket 60. The six-hour gate remains failed.
- [Decide a Durable Daily-Artifact Resume and Disposition Contract](issues/60-decide-durable-daily-artifact-resume-disposition.md) — Preserve the original immutable run manifest and append-only accession ledger. Completed work is final; only bounded transient failures or a candidate-bound immutable operator repair attestation may resume, and unresolved work remains fail-closed. Implementation/evidence is ticket 63.
- [Explain the 3,082-CIK to 148,524-artifact expansion](issues/53-research-daily-cik-to-artifact-expansion.md) — Daily staging preserved exact index accessions but passed only CIKs into a shared historical submissions helper: 1,132,927 distinct `filings.recent` accessions became 453,790 configured candidates and 148,524 after two limited lookbacks; pagination contributed zero, and ordinary `PoolTimeout` reset/retry was unreachable.
- [Root-cause orphaned 8-K bronze writes colliding with the immutable-object guard](issues/44-root-cause-earnings-8k-immutable-content-collision.md) — Fully root-caused with live-reproduced evidence: the 2026-07-19 timestamp is an S3-copy artifact from the documented `prodb→prod` cutover (`aws s3 sync`, not a fetch), carrying in byte-exact content captured by an old raw-HTTP fetch path removed by ticket 06 two days earlier; the current pipeline's edgartools `attachment.content` path `.strip()`s a trailing newline, producing content 1 byte shorter than the migrated original — reproduced live via sha256 diff of a raw SEC fetch, the existing bronze object, and a real `edgartools==5.30.0` fetch. Empirically Apple-specific (0/32 sampled non-Apple accessions have anything to collide with). Graduated into ticket 46 (repair decision) and ticket 47 (research: check for silent corruption of other objects during the 9-day pre-guard window).
- [Investigate whether the 2026-07-19–2026-07-28 window silently overwrote other migrated bronze objects](issues/47-investigate-silent-overwrite-window-prodb-migration.md) — No managed artifact-fetching workflow ran in the vulnerable interval and the retained Apple control-object history has no in-window successor; this is a strong execution-bound negative result, not a whole-bucket version-inventory proof.
- [Implement the Direct-Evidence GO Validation Contract](issues/48-implement-direct-evidence-go-validation-contract.md) — Schema-v2 manifests freeze an external authority registry and rollback mechanism, preserve evidence attempts, enforce the exact eight-gate/role/chronology predicate, and verify an authorized annotated Git Release Seal without manufacturing human approval.
- [Research the current-image Apple earnings-8-K content contract](issues/55-research-current-image-apple-earnings-content-contract.md) — Direct repository-owned SEC HTTP matched all 45 restored Apple bronze objects byte-for-byte; `attachment.content` is a transformed representation, not a newline-only variant. Ticket 56 implemented and production-validated the raw content-capture boundary: all 45 Apple Item-2.02 accessions have raw-object and primary-attachment registration, and a direct SEC-versus-bronze spot check is byte-exact. The remaining zero-row F5 outcome belongs to Ticket 42/Ticket 46, not to the capture boundary.
- [Filing / research text promotion criteria (F3)](issues/30-promotion-criteria-filing-research-text.md) — **Not promotable — no numbered checklist.** No `sec_filing_text` (or equivalent) table exists anywhere in Snowflake at all, not just undocumented — confirmed live. Only 1 of 9 skills (initiating-coverage Task 1) has a real prose-mining need, single-company/latest-10-K/no-history. Requires a dedicated automation ticket (bronze→silver→Snowflake export) before any checklist applies.
- [Ownership / Form 4 promotion criteria (F6)](issues/33-promotion-criteria-ownership-form4.md) — 5 numbered criteria. Real, previously-undiscovered coverage gap found live: `OWNERSHIP_ACTIVITY`/`OWNERSHIP_HOLDINGS` cover only **32 distinct companies** (pilot-scale, not the ~2,462-company operating universe) — the actual blocker, not documentation (the `insiders` Bundle section already exists). Kept separate from ticket 24's MDM-completeness gate.
- [13F / holders promotion criteria (F7)](issues/34-promotion-criteria-13f-holders.md) — 6 numbered criteria, built from the platform's own committed Bundle contract since this is the weakest ER-skill-grounded product of the 12. Underlying data is genuinely healthy (6.8M rows). Real open finding: the active graph generation has no relationship type literally named `INSTITUTIONAL_HOLDS` (only `HOLDS`/`COMPANY_HOLDS`) — flagged as an unresolved naming/sync question, not assumed either way.
- [Graph neighborhood promotion criteria (F8)](issues/35-promotion-criteria-graph-neighborhood.md) — 5 numbered criteria. Real, live-confirmed gap: `AUDITED_BY` and `HAS_PARENT_COMPANY` (2 of the matrix's 4 named relationship types) have never existed as an edge type in any of the graph's 14 generations, despite `audit_firm` nodes existing. Reframed scope: the Bundle already splits this into 4 independent named sections (insiders/employment/auditor/has_parent), not one unified traversal — only `auditor`/`has_parent` are this ticket's own scope.
- [Executive / management & pay promotion criteria (F10)](issues/37-promotion-criteria-executive-pay.md) — 5 numbered criteria. Healthiest of the still-open F1-F12 products: 13,457 rows, 893 companies (~36% of operating universe, plausible given DEF 14A isn't universal). One real live-found gap: `exec_role` only 43% populated despite `exec_name` being 100% — the actual gate, not coverage.
- [Pure-SEC subject features promotion criteria (F12)](issues/39-promotion-criteria-pure-sec-subject-features.md) — 5 numbered criteria. Inverse situation from F1-F3: design/Python semantics are the most mature of any F1-F12 product (ADR 0001 boundary explicit, unit-tested), but the Snowflake view itself was never deployed — `01_subject_feature_screen.sql` is an explicit "sketch," confirmed live via `SHOW TABLES` returning nothing. Most mechanical remaining fix of the still-blocked products: deploy the existing design, no data-capture question at all.
- [Root-cause the empty fundamentals gold pipeline](issues/41-root-cause-empty-fundamentals-pipeline.md) — **Different shape from ticket 40 — this is a bronze/silver capture gap, not an export-wiring bug.** Pulled live prod silver directly: `sec_financial_fact`/`sec_financial_derived` (F4) and `sec_accounting_flag` (F11) are 0 rows even in silver; `sec_earnings_release` (F5) has only 13 rows. Root cause: `load_history` — the only state machine ever wired to run `bootstrap-fundamentals --mode entity-facts/per-filing/thirteenf` — has **zero executions ever** in this account. F7 (13F, 6.8M rows, healthy) got its data from a separate, targeted manual bulk-load effort in a 4-day window (2026-07-21 to 07-24, matching CLAUDE.md's INSTITUTIONAL_HOLDS fix timeline), not from `load_history`. F4/F11's `entity-facts` mode has never produced a single row anywhere in this account's history — unverified whether it even works. Recommendation: smoke-test at small scale before any full-universe backfill; the backfill itself is a separate, substantial operator decision, same class as the `daily_incremental` first-run decision. Unblocks tickets 31/32/36/38 for a data-aware (not hypothetical) checklist pass once a real backfill lands.
- [Filings metadata promotion criteria (F2)](issues/29-promotion-criteria-filings-metadata.md) — 7 numbered criteria. Same real gate as ticket 28: `docs/subject-bundle-read.md` has zero filing-index section (verified live), so Filings metadata is **not promotable** regardless of gold data health. Coverage scoped to active `entity_type='operating'` (≥95% bar, live 98.7%), not the full tracked universe. Two adversarial findings: `dim_filing` (named in the matrix footnote) doesn't exist as a Snowflake object at all; only 2 of 9 skills (earnings-analysis, initiating-coverage) have an explicit textual need for filing metadata as such. Flags a real cross-ticket dependency to ticket 32 (F5): earnings-analysis's filing-date-must-match-release-quarter bar is an F2×F5 cross-check, not verifiable from either product alone.
- [Identity / ticker-CIK promotion criteria (F1)](issues/28-promotion-criteria-identity.md) — 9 numbered criteria. The real gate is criterion 1: a documented, working ticker read path doesn't exist today (`TICKER_REFERENCE` is 0 rows per ticket 40) — Identity is **not promotable** until that ships, independent of how well the underlying data scores. Coverage criterion scoped to the ticker-*eligible* subset (SEC `company_tickers.json` cross-check), bar ≥95%, not the full active/tracked universe. CIK is explicitly out of the ER-facing contract (no skill ever references it).
- [Design the Release Evidence Automation](issues/09-design-release-evidence-automation.md) — Implemented as working code (explicit `/implement` request): `edgar_warehouse/application/release_evidence.py` (pure, no network/live-system I/O, no wall-clock reads) + `edgar_warehouse/scripts/release_evidence_cli.py` (`init`/`add-gate`/`validate`). Schema, state-transition model, sanitization boundary, and validation report all per ticket 01's Answer. TDD throughout (137 focused tests, 93% statement coverage); successive post-handoff adversarial reviews closed fabricated-GO, tampering, malformed-type, chronology, lineage, symlink, and DSN-leakage gaps, ending in an independent APPROVE. GO remains fail-closed with `go_validation_not_implemented` until ticket 08 defines the complete gate and signer predicate.
- [Define Release-Bound Dashboard Acceptance](issues/07-define-release-bound-dashboard-acceptance.md) — `docs/release-readiness/dashboard-acceptance.json`, one entry per view keyed `<DASHBOARD>::<view_id>` across all 25 real views in the two Terraform-deployed Streamlit-in-Snowflake dashboards (`EDGARTOOLS_DASHBOARD`, `MDM_GRAPH_DASHBOARD`; the non-deployed `examples/dashboard/edgar_universe_dashboard.py` excluded), each with `status` + `watermark_checked` + three independent sub-checks (mutation surface, secret leakage, unbounded output). `READY` only if every view passes with a current watermark and all three sub-checks true; stale-watermark and thin-sample passes are distinct, explicit `NOT_READY` reasons, not silently accepted. Staleness is detected on watermark rebase, never auto-cleared. Attested by **Dashboard Reviewer** (ticket 01's existing named role). The original throwaway prototype was later user-directed into main as a hardened tracked reference after fail-open inventory/status review findings were fixed.

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
- Whether the 10,491-CIK submissions bronze capture phase inside `daily-incremental`'s `RunWarehouseTask` (currently ~64 min, live-observed) is dominated by rate-limit-bound real SEC fetches (not fixable) or unbatched per-CIK cache-hit-checking overhead (a possible sixth instance of this session's per-row pattern) — needs a live network_fetches/silver_skips breakdown before it's ticket-able. See [Why daily-incremental recomputes impacted CIKs separately from ComputeIdentityRefreshWindow](issues/73-why-daily-incremental-recomputes-impacted-ciks.md).

## Out of scope

- Public or customer-facing launch readiness; this effort ends at production operator readiness.
- Non-AWS deployment paths, registries, storage targets, workflow engines, or secret-management systems.
- Putting runtime commands, image rollout, schedules, or secret values into passive Terraform.
- Re-running Ticket 20 bulk-load from zero without a new operator decision (technical package already PASS).

## Open frontier (hygiene 2026-07-29v)

Unblocked open tickets (work through the map; claim before starting):

1. [Implement and Activate the Bounded Daily Identity Refresh Schedule](issues/49-implement-bounded-daily-identity-refresh-schedule.md) — **in progress, still open** (claimed 2026-07-30): "Refresh behavior" (bounded default path, `pipeline_run_lease` primitives) and the lease-wiring into the state machine's branching are both implemented and tested (`claude/daily-identity-refresh-go-live`, open as PR #316), and this session additionally closed `backstop_overdue` consumption (persisted on `pipeline_run_lease`, resolved into an `effective_mode` before every acquire, survives multiple consecutive deferrals) and EventBridge/Terraform schedule ownership (passive-Terraform file deleted; least-privilege scheduler IAM added to access Terraform; off-by-default `--configure-daily-incremental-schedule enable|disable` added to `deploy-aws-application.sh`). Explicitly NOT done: CloudWatch alerting, an actual prod `enable` run, and the full Phase 1/2 evidence-and-activation checkpoint — see the ticket's "Progress" section for the itemized remainder.
2. [Implement run-scoped Daily Identity Refresh publication](issues/61-implement-run-scoped-daily-identity-publication.md) — task (implements the resolved single-reducer, one-publication contract; schedule activation remains separately gated on immutable-image full-chain evidence)
3. [Implement durable Daily-Artifact resume and disposition](issues/63-implement-durable-daily-artifact-resume-disposition.md) — task (implements the accepted immutable manifest, outcome ledger, candidate-only resume, and operator repair-attestation contract)
4. [Add progress logging to the Daily Identity Refresh reducer](issues/64-add-identity-refresh-reducer-progress-logging.md) — task (the reducer emits zero log output for its entire runtime, confirmed live via a `RUNNING` ECS task with `storedBytes: 0` after 17+ minutes)
5. [Clean up orphaned staged-promotion blobs in S3 `silverstage/`](issues/65-clean-up-orphaned-staged-promotion-blobs.md) — task (`promote_staged` never deletes the staged object it just promoted and no bucket lifecycle rule exists; confirmed live: 46 objects, 49.3GB already orphaned under the old `_staging/` prefix in prod; prefix renamed `_staging/`→`silverstage/` 2026-08-02, go-forward only)
6. [Fix CLAUDE.md's stale Phased Pipeline concurrency documentation](issues/66-fix-stale-phased-pipeline-concurrency-docs.md) — task (`load_history` no longer has a `bootstrap-batch ×N` Map at all — live AWS shows 5 Distributed Maps all `MaxConcurrency=1`, fully sequential; the separate `bootstrap-batched` state machine that does have `MaxConcurrency=3` has zero prod executions ever; CLAUDE.md's "~15 min/100 companies" timing claim doesn't match the current architecture)

- [Fix authority-column false-positive conflicts in silver merge](issues/67-fix-authority-column-false-positive-conflicts.md) — resolved: `sec_company_filing`'s merge policy never excluded its own `authority_column` (`last_synced_at`) from the same-key conflict check, so every re-synced filing row registered as "different" forever even with zero real content change — measured live at 452,996-of-452,996 false-positive rows in one 500-CIK batch, ~753s of pointless single-row UPDATEs. Fixed generically (all 31 registry policies) via a `NOT EXISTS` anti-join scoped to comparable (non-key/provenance/authority) columns; validated end-to-end against real prod data (11.04s total, down from the ~753s extrapolation), full suite green.
- [Batch daily-index filing merge inserts instead of per-row autocommit](issues/68-batch-daily-index-filing-merge-inserts.md) — resolved: found while watching ticket 67's live verification run — `ComputeIdentityRefreshWindow` was still ~53s/file even though each SEC download itself took 100-250ms. `merge_daily_index_filings` ran one autocommitted `INSERT ... ON CONFLICT` per row (6,029 rows for one real daily-index file, confirmed live). Fixed via the same Arrow-staged bulk-upsert pattern `merge_filings`/`_merge_rows_bulk` already use elsewhere in `silver_store.py`; validated end-to-end against the real downloaded file (0.137s, down from 53s), full suite green. PR #331, merged.
- [Reuse a single boto3 S3 client instead of one per artifact write](issues/69-reuse-s3-client-in-artifact-fetch-loop.md) — resolved: found while watching the same execution's later `RunWarehouseTask` artifact-fetch stage — ~130-165ms of dead time per document beyond the 50-70ms SEC fetch itself. `StorageLocation.write_immutable_bytes`/`promote_staged` constructed a fresh `boto3.client("s3")` per call, discarding its connection pool and paying a cold TCP+TLS handshake every time. Measured live against the real prod bronze bucket: 184ms/call fresh vs. 52.6ms/call reused. Fixed via instance-level lazy client caching on the frozen `StorageLocation` dataclass; no concurrency added (advisor: DuckDB writes + the conditional-create guard make this the wrong pass for that). Full suite green.
- [Decide whether to exclude binary presentation artifacts from the default fetch policy](issues/70-decide-exclude-binary-artifacts-from-fetch-policy.md) — resolved via HITL exchange: exclude `.jpg`/`.jpeg`/`.png`/`.gif` exhibits by default (primary document always exempt), go-forward + retroactive cleanup requested. Implemented in `bronze_filing_artifacts.py`, tested, full suite green. Retroactive cleanup scoped separately as ticket 71 (investigation-first, no deletion yet).
- [Clean up already-captured binary attachments in S3 bronze](issues/71-cleanup-existing-binary-attachments-in-bronze.md) — open, task — needs object count/byte size, a safety check that nothing else references these `raw_object_id`s, and a deletion mechanism (dry-run first, matching this repo's other destructive-op conventions) before any prod S3 deletion runs.
- [Batch company_sync_state seeding instead of a per-CIK read+write loop](issues/72-batch-company-sync-state-seeding.md) — resolved: found while watching the tickets-67-70 deploy verification run — a silent ~2m20s gap between `company_tickers.json`/`company_tickers_exchange.json` fetches, from a per-CIK read+upsert loop over all 10,432 real tickers. Fifth instance of the same unbatched-per-row shape (67/68/69), but a fixed bounded cost per run, not volume-scaling — lower severity than those three. Fixed via `seed_company_sync_state_bulk`, six new DB-backed tests, full suite green.
- [Why daily-incremental recomputes impacted CIKs separately from ComputeIdentityRefreshWindow](issues/73-why-daily-incremental-recomputes-impacted-ciks.md) — resolved (research): genuinely different scopes, not wasteful duplication — `ComputeIdentityRefreshWindow` intersects with the narrow company-identity-eligible universe (1,194 CIKs), `daily-incremental`'s own handler intersects with the full active-tracked universe (10,491 CIKs, includes insiders/advisers/13F managers `ComputeIdentityRefreshWindow` correctly excludes). The one genuine duplication (re-fetching the same 7-day daily index twice) is cheap post-ticket-68 (~2.8s), not worth fixing. Left the real open question — whether the resulting 10,491-CIK submissions-capture phase itself is optimizable — in Not yet specified.
- [daily-incremental permanent terminal-repair block](issues/74-daily-incremental-permanent-terminal-repair-block.md) — open: the ticket70-verify run retried `RunWarehouseTask` 4x (~85 min each, ~5.7h total) and could never succeed — 2 accessions for CIK 2143673 permanently `terminal_repair_required`, root-caused live to a one-byte (trailing newline) mismatch between legacy pre-2026-07-31T16:58 (pre-ticket-56 byte-exact fix) bronze content and freshly re-fetched raw SEC bytes, not a real content change. Execution stopped and lease released manually. Open: how to repair these 2, whether other pre-fix objects will hit the same wall, and whether resume should gate on a cheap pre-check instead of redoing ~95 min of work before discovering an already-known block.

**All twelve F1-F12 promotion-criteria tickets (28-39) are now either resolved or explicitly
blocked** — the F1-F12 sub-workstream (tickets 25/27-41) is at its natural pause point pending
either a fundamentals-pipeline backfill decision (ticket 42) or later product work. Those
product tickets are not gates for Production Operator Readiness.

Blocked (do not claim):

- [Historical financials promotion criteria](issues/31-promotion-criteria-historical-financials.md) — blocked by 42 (re-blocked from 41, which is resolved but the real-world data gap persists; the product's entire gold layer is 0 rows in prod)
- [Earnings 8-K GAAP snapshot promotion criteria](issues/32-promotion-criteria-earnings-8k-gaap-snapshot.md) — blocked by 42 (re-blocked from 41; `EARNINGS_RELEASES` has 13 rows, essentially empty)
- [Segment / product-geo revenue promotion criteria](issues/36-promotion-criteria-segment-revenue.md) — blocked by 42 (re-blocked from 41; reads the same empty `SEC_FINANCIAL_FACT.segment`)
- [Accounting forensic scores promotion criteria](issues/38-promotion-criteria-accounting-forensic-scores.md) — blocked by 42 (re-blocked from 41; `ACCOUNTING_FLAGS` is 0 rows)

Claimed, in progress:

- [Decide and execute the fundamentals pipeline backfill (F4/F5/F9/F11)](issues/42-decide-execute-fundamentals-backfill.md) — stage 1 (single-CIK smoke test) executed live, mixed result, paused pending operator decision on two newly-found bugs (see hygiene (n))

## Hygiene log

- **2026-08-02 (aa):** Deployed ticket 67's fix to prod and started a fresh verification
  execution (`daily-incremental-ticket67-verify-1785709701`) to confirm it against real
  data. While watching it, found and fixed a second, independent bottleneck in the same
  spirit: `ComputeIdentityRefreshWindow` (the step *before* `ReduceIdentityRefresh`) was
  taking ~53s per daily-index file even though each SEC download itself completed in
  100-250ms — see
  [Batch daily-index filing merge inserts instead of per-row autocommit](issues/68-batch-daily-index-filing-merge-inserts.md).
  Not a caching gap (daily mode intentionally force-rechecks every lookback day by
  design); the cost was `merge_daily_index_filings`'s per-row autocommit loop, same
  structural shape as ticket 67 but in a different file/stage. PR #331 open, not yet
  merged/deployed. The verification execution itself was left running throughout —
  unaffected by this second fix, it's still on the pre-fix warehouse image for this
  particular step.
- **2026-08-02 (z):** Root-caused and fixed the `daily-incremental-postdeploy-1785701660`
  execution's 55+-minute `ReduceIdentityRefresh` stall — see
  [Fix authority-column false-positive conflicts in silver merge](issues/67-fix-authority-column-false-positive-conflicts.md).
  Not a network or infra issue (S3 gateway endpoint confirmed correctly attached to the task's
  route table, ruling out NAT bottleneck theories); a real data-merge defect in
  `silver_protection.py`, present since the file's earliest committed version, first triggered at
  scale by ticket 61's new reducer path. Reviewed via `/gof-refactor-reviewer` and `advisor`
  before implementation per explicit user request. Left the actual stalled execution running
  untouched (the code fix doesn't help it retroactively; aborting risks stranding
  `pipeline_run_lease`, per the advisor's operational note) — its outcome is orthogonal to this
  fix and will still supply real before-fix timing evidence once it completes.
- **2026-08-02 (y):** Filed
  [Fix CLAUDE.md's stale Phased Pipeline concurrency documentation](issues/66-fix-stale-phased-pipeline-concurrency-docs.md)
  after checking `load_history`'s deployed concurrency directly against AWS while answering an
  operator throughput question. Found the documented `bootstrap-batch ×N (MaxConcurrency=10)`
  shape no longer exists in the live `edgartools-prod-load-history` definition at all — it's
  now 5 Distributed Maps (`Stage0CompanyIdentity`, `Stage1Parallel/WindowedBootstrap`,
  `Stage1BEntityFacts`, `Stage1BPerFiling`, `Stage1BThirteenF`), every one `MaxConcurrency=1`
  by design (silver-promotion-consistency, same class of reason as the ticket-20 N-way race
  finding elsewhere in CLAUDE.md). The standalone `edgartools-prod-bootstrap-batched` state
  machine does have `MaxConcurrency=3` (matching the deploy script default CLAUDE.md's Key
  invariants section describes) but has never executed in prod. Added to the open frontier.
- **2026-08-02 (x):** Filed two new task tickets found live while monitoring the
  `daily-incremental-postdeploy-1785701660` evidence-gathering execution's
  `ReduceIdentityRefresh` step (ticket 61's reducer):
  [Add progress logging to the Daily Identity Refresh reducer](issues/64-add-identity-refresh-reducer-progress-logging.md)
  (the reducer — `identity_refresh_publication.py:169-238` — emits zero log output for its
  entire multi-stage, multi-GB-copy runtime; confirmed live via `describe-log-streams`
  reporting `storedBytes: 0` after 17+ minutes `RUNNING`) and
  [Clean up orphaned staged-promotion blobs in S3 `_staging/`](issues/65-clean-up-orphaned-staged-promotion-blobs.md)
  (`promote_staged` — `object_storage.py:322-389` — never deletes the ~1GB staged object it
  just promoted, and the bucket has no lifecycle rule; confirmed live: 46 objects, 49.3GB
  already orphaned in `s3://edgartools-prod-warehouse-690839588395/warehouse/_staging/`, and
  `get-bucket-lifecycle-configuration` returns `NoSuchLifecycleConfiguration`). Both added to
  the open frontier as unblocked, unclaimed tasks.
- **2026-08-02 (w):** Frontier review (no ticket resolved, one sibling map's ticket
  closed — see gold-build-memory-reliability). Confirmed all three frontier
  tickets (49, 61, 63) remain genuinely blocked on **immutable-image production
  evidence**, not on unresolved decisions — each has local implementation done
  and merged/committed, and each names the same missing step. Corrected two
  stale records found in passing: ticket 52's file claimed "no implementation
  has started" when PR #318 had already merged; ticket 51 had no Progress
  section at all despite PR #317 merging (its narrative was written into
  ticket 49 instead). Checked three previously "pending outcome" prod
  executions named in ticket files: `load-history-silver-only-20260801T235002Z`
  is **ABORTED**; `daily-incremental-ticket03-1785413694` is **FAILED** (not
  OOM — the pre-ticket-54 `ForceCheck` bug, now fixed); `bootstrap-ticket03-verify-1785426021`
  **SUCCEEDED** and supplied the exact discriminating signal
  gold-build-memory-reliability's ticket 03 needed — that ticket is now
  resolved. Confirmed live: ticket 61's ItemSelector corrective fix (parent
  execution name into distributed Map items) is present on `main`
  (`deploy-aws-application.sh:2738-2742`), so 61 is deploy-ready, not
  code-blocked. No new image has been built/deployed from current `main` since
  PR #326/#328/#329 merged — one build+deploy would unblock the evidence step
  shared by 49, 61, 63, and gold-build-memory-reliability's ticket 04.
  [Decide and execute the fundamentals pipeline backfill](issues/42-decide-execute-fundamentals-backfill.md)
  remains the one live ticket that's a genuine operator decision (split
  F4/F9 backfill now vs. hold for F5/F11), not evidence-gathering.
- **2026-07-29 (v):** Resolved
  [Decide whether/how to narrow daily_incremental's Stage 0 and set its actual schedule](issues/45-decide-narrow-daily-incremental-stage0-and-cadence.md)
  through HITL grilling. Operator chose an impacted-CIK Daily Identity Refresh
  with a forced trailing seven-day index recheck and a Sunday full-universe
  Identity Backstop Sweep, rather than accepting either evidenced coverage gap
  or retaining the 10h16m daily Stage 0. Slots run at 12:00 UTC (narrow
  Monday-Saturday, backstop Sunday) under one fail-closed lease; deferrals alert,
  and an overdue backstop takes the next free slot. Corrected a newly surfaced
  architecture contradiction: the disabled schedule currently modeled in
  passive prod Terraform must move to explicit, off-by-default application
  rollout controls while scheduler IAM remains in access Terraform. Schedules
  deploy disabled and require manual full-chain evidence (daily <=6h, backstop
  <=18h, scope/late-index/concurrency proof) plus explicit AWS Operator GO.
  Graduated implementation and live activation proof into
  [Implement and Activate the Bounded Daily Identity Refresh Schedule](issues/49-implement-bounded-daily-identity-refresh-schedule.md);
  no runtime or AWS mutation was performed.
- **2026-07-29 (u):** At the user's explicit request, reviewed and pulled
  `prototype/07-dashboard-acceptance` into a Codex-owned integration branch,
  superseding ticket 07's earlier throwaway-only instruction. The two-axis
  review found no hard repository-standard violation, but caught four spec
  defects before integration: an empty inventory could return `READY`,
  arbitrary status strings could evade all failure branches, reason-bearing
  strings violated the `READY`/`NOT_READY` schema enum, and Dashboard Reviewer
  authority was conventional rather than enforced. The integrated reference
  now validates the exact 25-view inventory and runtime enums, separates
  structured reason codes, enforces the attesting role, centralizes view/safety
  domain types and TUI recording logic, and has focused adversarial tests. It
  remains `.scratch/` reference code, not the production release validator.
- **2026-07-29 (t):** Ticket 08 resolved through one-at-a-time operator
  grilling after a two-axis standards/spec review. The Candidate Evidence Set
  is the only Direct-Evidence GO Packet; an unchanged immutable candidate may
  preserve multiple append-only attempts, but only one active attempt can
  satisfy the exact eight-gate and required-role matrix. Candidate-specific
  evidence is fresh relative to the verified Release Seal's fixed 24-hour
  window; standing rollback proof is the only clock-independent exception and
  remains valid only while its mechanism identity matches. Signer authority
  comes from an external digest-bound registry, the Release Owner acts only
  after automated `ready_for_owner` validation, and GO is effective only after
  the authorized signed annotated tag verifies against the exact finalized
  evidence commit. F1-F12 product promotion criteria remain outside Production
  Operator Readiness. Removed ticket 08 from the frontier and graduated the
  missing automation work to ticket 48; no implementation was performed.
- **2026-07-29 (s):** Ticket 09 (Design the Release Evidence Automation) implemented as real
  working code, per an explicit `/implement 09` request (overriding this ticket's `prototype`
  type default, which would otherwise mean a throwaway discussion artifact — the user asked for
  the real thing). Built `edgar_warehouse/application/release_evidence.py` (pure: no network/AWS/
  Snowflake I/O, no wall-clock reads — every timestamp is caller-supplied) and a thin CLI wrapper
  `edgar_warehouse/scripts/release_evidence_cli.py` (`init`/`add-gate`/`validate`), following this
  repo's existing `edgar_warehouse/scripts/*.py` convention. TDD throughout, then a two-axis
  `/code-review` against ticket 01's Answer as spec (parallel Standards + Spec sub-agents) found
  real issues on both axes, all fixed before commit: Standards — raw Python tracebacks on
  malformed input instead of the repo's established clean stderr+exit-code pattern; Spec — two
  schema fields missing (`addendum_references`, `release_owner_attestation`), no validation of
  `disposition`'s enum / attestation record shape / watermark sub-fields, and an
  operator-configurable freshness window that undercut ticket 01's fixed "24-hour Live-Evidence
  Window" invariant. Also fixed a genuine state-transition bug the spec reviewer caught: `init`
  originally refused ANY re-init unconditionally, when ticket 01 requires distinguishing a
  harmless idempotent re-init (identical inputs) from a genuine identity-mutation attempt (same
  commit+date, different image digest) — now the former succeeds quietly and the latter fails
  loudly instead of silently colliding. Final state after post-handoff hardening: 137 focused tests
  (114 pure-module, 17 CLI, 6
  dedicated architecture — the last statically + behaviorally proving the module can never
  manufacture a Gate Attestation or Release Seal disposition itself, per ticket 01's explicit
  requirement), with 93% statement coverage across the module and CLI. Repository-wide
  verification: 1519 passed / 4 skipped / 35 subtests passed, with
  3 pre-existing MDM test-double failures in `tests/mdm/test_cli_snowflake_graph.py` whose fix is
  outside the explicitly selected two-commit handoff scope. Removed from open frontier (resolved).
- **2026-07-29 (r):** Ticket 44's background research agent returned with a fully root-caused,
  live-reproduced answer (`44-research-findings.md`) — not a guess. The 2026-07-19 collision
  timestamp is an S3-copy artifact from the documented `prodb→prod` production cutover (`aws s3
  sync`, which doesn't preserve `LastModified`), not an original fetch; the migrated content was
  captured under an older raw-HTTP fetch path (removed 2026-07-17 by ticket 06's edgartools-only
  gateway consolidation) that preserved SEC's exact bytes, while the current pipeline's
  `attachment.content` path strips a trailing newline via edgartools' own
  `get_content_between_tags()` — reproduced directly (sha256 diff of a raw SEC curl fetch, the
  existing bronze object, and a real `edgartools==5.30.0` fetch: raw/bronze match exactly, current
  fetch is 1 byte shorter). Confirmed empirically Apple-specific via a live sample of 32 other
  non-Apple Item-2.02 accessions (0/32 have any pre-existing bronze to collide with) — this is not
  a whole-universe blocker for ticket 42's F5 backfill, just a scoped Apple-pilot repair. Also
  surfaced an adjacent, previously-unknown risk: between the 2026-07-19 migration and PR #298's
  2026-07-28 immutability guard, any re-fetch of migrated content through the post-ticket-06
  pipeline would have silently overwritten byte-exact originals with no audit trail — not checked
  whether this happened to anything beyond Apple (which was untouched in that window). Ticket 44
  resolved and removed from open frontier; graduated into ticket 46 (task: decide + execute the
  Apple repair) and ticket 47 (research: check for silent corruption elsewhere in that 9-day
  window), both added to the open frontier.
- **2026-07-29 (q):** Ticket 43 (Investigate why daily_incremental reprocesses the full active
  universe) formally resolved using the background research agent's findings
  (`43-research-findings.md`, landed earlier this session): narrowing Stage 0 is architecturally
  possible and would reuse only already-built/tested code (the unscheduled
  `catch-up-daily-form-index` command's index-only daily-index parse, plus
  `bootstrap-fundamentals --mode company-identity`'s already-implemented-but-unused `--cik-list`
  path), cutting per-run CIK volume by roughly an order of magnitude (2,925 of ~26,300 tracked
  CIKs filed anything on the one sample day checked) — but is a genuine operator trade-off, not a
  bug fix: it would trade away same-day coverage of two evidenced gaps (non-filing
  `submissions.json` metadata drift; a live-confirmed SEC daily-index republish ~37h after normal
  publish, invisible to the no-`--force` checkpoint cache). Also confirmed `daily_incremental` has
  no EventBridge schedule at all — "daily" is aspirational in the name only; the one execution to
  date was a manual `start-execution`. Removed from open frontier (resolved). Graduated the actual
  narrow/no-narrow-plus-cadence decision into new ticket **45** (grilling, HITL — the coverage-gap
  trade-off is the operator's call, not an engineering judgment call) and added it to the open
  frontier. Separately dispatched a background research agent for ticket 44 (immutable-object
  collision) to answer its three still-open questions (writer identity for the 2026-07-19 bronze
  objects, a real byte diff between the existing object and a fresh fetch, and whether the
  collision is Apple-specific or universe-wide) — not yet returned as of this hygiene entry.
- **2026-07-29 (p):** Fixed F5's root cause (ticket 42/hygiene (o)) and tested. Added
  `_is_item_202_candidate_form` to `warehouse_orchestrator.py`, OR'd into
  `_is_configured_parser_form`. Two existing tests had locked in the bug as intended behavior
  (a fixture literally named `earnings-8k` asserted as excluded in
  `test_submission_phase_order.py`; an item-2.02 fixture asserted excluded in
  `test_ownership_lookback.py`) — both updated to assert inclusion instead of adding
  contradictory new tests alongside stale ones. Added 7 direct unit tests for the new
  predicate. Full suite (`tests/unit`, `tests/application`, `tests/architecture`, `tests/mdm`):
  1386 passed, 4 skipped (pre-existing), 0 failed. Not yet live-verified against prod (would
  need an image rebuild + redeploy + re-run of the Apple smoke test) — flagged as the next step
  before treating F5 as genuinely resolved, consistent with this ticket's own standard that
  unit-tested-only code isn't proven.
- **2026-07-29 (o):** Root-caused F5's bronze capture gap fully (5-whys, ticket 42). The
  self-filed-vs-agent-filed correlation flagged in (n) was a false lead from a 3-row sample —
  a universe-wide query disproved it: 52,408 Item-2.02 (earnings) 8-Ks exist in prod silver,
  **0% have any `sec_filing_attachment` row**, vs. Item-5.02 (employment) 8-Ks at 20% (6,847/
  34,256) — a clean, total, item-type-scoped gap, not a filer-identity artifact. Real cause:
  `_is_configured_parser_form`/`_configured_parser_accessions`
  (`warehouse_orchestrator.py`) — the gate controlling which accessions get bronze attachments
  fetched at all — only admits 8-Ks via `_is_item_502_candidate_form`, whose regex matches
  Item 5.02 (or blank items) but has no corresponding Item-2.02 check. Built originally for the
  Required Relationship Bulk-Load scope (tickets 12-24: ownership/ADV/proxy/13F/Item-5.02
  employment events); when `bootstrap-fundamentals --mode per-filing` was added later for
  earnings, its docstring assumed Branch A already fetched "8-K earnings" attachments, but the
  selection gate was never updated to match that assumption. One-line, well-understood fix (add
  an Item-2.02 check mirroring the existing 5.02 regex) — not applied here, flagged as the next
  concrete step. Full 5-whys in ticket 42's Answer.
- **2026-07-29 (n):** Executed ticket 42's stage 1 (single-CIK smoke test) live against CIK
  320193 (Apple), real writes to prod's canonical silver via direct `aws ecs run-task`. Mixed
  result — **`entity-facts`→`sec_financial_fact`/`sec_financial_derived` (F4/F9) genuinely
  PASSED**: 24,195/282 rows written, revenue spot-checked exactly against Apple's real public
  10-K figures across 3 fiscal years. **Two real, previously-unknown bugs found, neither fixable
  by backfill scale:** (1) F11 (`sec_accounting_flag`) structurally can never populate via
  `entity-facts` mode — live-fetched Apple's actual companyfacts JSON and confirmed its `dei`
  section carries only 2 concepts total, never the 4 auditor-identity DEI tags
  (`AuditorFirmId`/`AuditorName`/`AuditorLocation`/`IcfrAuditorAttestationFlag`) the parser
  requires to build a base row — compounded by a masking bug in `backfill_accounting_flags`
  (an `UPDATE` against zero matching rows doesn't raise in DuckDB, so its `updated` counter
  claimed "129 flags updated" while writing zero actual rows). (2) F5 (`sec_earnings_release`)
  stayed 0 rows not from a parser defect but a bronze/silver capture gap: every one of Apple's
  real Item-2.02 earnings 8-Ks (self-filed, accession prefix `0000320193-...`) has **zero**
  `sec_filing_attachment` rows at all, while a same-CIK agent-filed 8-K (prefix
  `0001140361-...`) has full attachment metadata — a self-filed-vs-agent-filed asymmetry in
  attachment capture, not confirmed root cause, flagged for dedicated investigation. Paused
  stages 3/4 (sample batch, full-universe backfill) rather than run more CIKs through code known
  to reproduce these two bugs at scale. Full writeup in ticket 42's Answer. Reported back to
  operator for next-step decision (split F4/F9 backfill from F5/F11 fixes, or hold everything).
- **2026-07-29 (m):** Graduated ticket 41's deferred recommendation into a new task ticket,
  [42 — Decide and execute the fundamentals pipeline backfill](issues/42-decide-execute-fundamentals-backfill.md),
  claimed. Re-blocked tickets 31/32/36/38 from 41 (resolved, but a root-cause finding is not a
  completed backfill) onto 42. Grounded before grilling: `bootstrap-fundamentals` has 4 modes
  (`per-filing`, `entity-facts`, `thirteenf`, `company-identity`); `load_history`
  (`infra/scripts/deploy-aws-application.sh`) already sequences all four correctly after Branch
  A (bronze/silver), confirmed NOT in `GOLD_AFFECTING_COMMANDS` (needs a `gold-refresh` after);
  `entity-facts`/`per-filing`'s only test coverage
  (`tests/unit/test_edgartools_sec_gateway.py`, `tests/unit/test_silver_once.py`) mocks
  `fetch_companyfacts_json` — never run against real SEC data or executed live, matching
  ticket 41's "unverified" framing exactly.

- **2026-07-29 (l):** Resolved the six F1-F12 tickets unaffected by ticket 41's fundamentals
  finding: 30 (F3, filing text — not promotable, no Snowflake surface exists at all), 33 (F6,
  ownership — found a new, real coverage gap live: only 32 companies have any ownership data),
  34 (F7, 13F/holders — weakest ER-skill-grounded product, but data is healthy; found the active
  graph has no edge literally named `INSTITUTIONAL_HOLDS`), 35 (F8, graph neighborhood — found
  `AUDITED_BY`/`HAS_PARENT_COMPANY` have never existed as edge types in any of 14 graph
  generations), 37 (F10, executive pay — healthiest remaining product; found `exec_role` only
  43% populated despite `exec_name` at 100%), 39 (F12, subject features — most mature design of
  any F1-F12 product but the Snowflake view was never deployed, confirmed via live `SHOW TABLES`
  returning nothing). All 12 F1-F12 promotion-criteria tickets (28-39) are now resolved or
  explicitly blocked (31/32/36/38 on ticket 41) — the F1-F12 sub-workstream has reached its
  natural pause point. Live investigation for this batch pulled the graph generation/edge tables
  directly (`NEO4J_GRAPH_MIGRATION.MDM_GRAPH_EDGES`/`GRAPH_GENERATION`/`GRAPH_ACTIVE_POINTER`)
  rather than assuming the matrix footnote's relationship-type list was current.
- **2026-07-29 (k):** Ticket 41 resolved. Downloaded and queried the live prod silver DuckDB
  directly (994 MB) — confirmed the empty-table finding goes all the way to silver, not just a
  Snowflake export gap: `sec_financial_fact`/`sec_financial_derived` (F4) and
  `sec_accounting_flag` (F11) are 0 rows in silver too; `sec_earnings_release` (F5) has exactly
  13 rows in silver, matching gold exactly. Searched every Step Function's live definition for
  `bootstrap-fundamentals` — only `daily_incremental` (company-identity mode only) and
  `load_history` (all four modes) reference it at all. `aws stepfunctions list-executions` on
  `load_history` returned an empty list — **zero executions ever** in this account. Resolved the
  apparent contradiction (13F/F7 has 6.8M real rows despite this): checked
  `sec_thirteenf_holding`'s `ingested_at` timestamps — all 6,799,919 rows landed within a single
  4-day window (2026-07-21 to 07-24), matching CLAUDE.md's own documented INSTITUTIONAL_HOLDS
  fix timeline (dated 2026-07-26) — a separate, deliberate, targeted manual bulk-load effort,
  not `load_history` (confirmed never executed) or ordinary operation. The 13
  `sec_earnings_release` rows landed in that identical window — almost certainly an incidental
  side-effect of that same activity, not a deliberate earnings-release backfill.
  Recommendation: smoke-test `entity-facts`/`per-filing` modes at small scale (its true
  correctness is unverified by any evidence in this account) before considering a full-universe
  backfill, which is its own substantial operator decision — explicitly not attempted live in
  this ticket. Removed from open frontier (resolved); tickets 31/32/36/38 remain blocked on it
  pending an actual data-aware pass, not a hypothetical one.
- **2026-07-29 (j):** Paused the F1-F12 batch drafting (30-39) mid-grill on ticket 31 — a
  much bigger finding than anything so far. Three of twelve products (F4 Historical financials,
  F5 Earnings 8-K snapshot, F11 Accounting forensic scores) have essentially non-functional gold
  layers in prod (0/13/0 rows respectively), and F9 shares F4's root table. Operator chose to
  stop and investigate immediately rather than draft around it. Spun off ticket 41 (research,
  claimed) mirroring ticket 40's shape; re-blocked tickets 31/32/36/38 on it. Tickets 30/33/34/
  35/37/39 confirmed unaffected (spot-checked `EXECUTIVE_RECORDS`, the healthy F10 sibling in the
  same dimensional-gold family — 13,457 rows) and remain claimable.
- **2026-07-29 (i):** Ticket 29 (Filings metadata promotion criteria) resolved — 7 numbered
  criteria. Live-checked `EDGARTOOLS_GOLD.FILING_ACTIVITY`/`FILING_DETAIL` (2,713,414 rows each,
  100% accession-format valid, 100% CIK join integrity, all 4 named forms present at real
  volume: 8-K 203,094/10-Q 55,973/10-K 20,749/DEF 14A 17,687) and `docs/subject-bundle-read.md`
  directly (zero filing-index section — the only "accession" mention is unrelated internal
  provenance for the `insiders` section). Same shape as ticket 28: criterion 1 makes the missing
  documented read path the actual hard gate, independent of the (otherwise healthy) gold data.
  Coverage criterion (2) scoped to active `entity_type='operating'` at ≥95%, live 98.7% —
  explicit negative criterion (3) against ever gating on the full tracked universe. Found
  `dim_filing` (named in the coverage matrix's own footnote) doesn't exist as a Snowflake object
  — real surface is only the two near-duplicate `FILING_ACTIVITY`/`FILING_DETAIL` tables. Flagged
  (not resolved here) a genuine F2×F5 cross-ticket dependency for ticket 32 to own: earnings-
  analysis's stated hard bar that 10-Q/10-K filing date must match the earnings-release quarter.
  IS_XBRL explicitly marked not-required-for-promotion despite being named in the matrix footnote
  — no skill in ticket 27's survey asks for XBRL-flag-level data. Removed from open frontier
  (resolved).
- **2026-07-29 (h):** Added a CUSIP cross-check addendum to ticket 40, operator-directed.
  `MDM_SECURITY.cusip` turned out unpopulated (0/97 rows) — used `INSTITUTIONAL_HOLDINGS`
  instead (6.8M 13F rows, 41,225 distinct CUSIPs with issuer names; 13F only covers
  actively-held Section 13(f) securities, an independent signal from the ticker source itself).
  Built a normalized-name crosswalk against the 26,300 active CIKs: 23,577 (89.6%) have neither
  a ticker nor any 13F match — strongly reconfirms the original finding. 149 have no ticker but
  DO match a 13F-held CUSIP by name; a manual 25-row spot-check found this bucket is a genuine
  mixed bag, not a single explanation — real capture gaps (NKGen Biotech, Soleno Therapeutics,
  ~5-6 of 25), gone-private/acquired CIKs still on file (Dell's pre-2013 CIK, General Re,
  Yahoo), foreign-exchange-only listings (Kioxia, Tokyo Stock Exchange), debt-only/structured
  vehicles (Burlington Northern Santa Fe LLC, CLO note issuers), non-traded REITs, fund-trust
  wrappers with per-series tickers, and — a real limitation of the matching method itself, not
  a data gap — a few cases where a subsidiary/operating CIK's name matched its separately-traded
  parent's CUSIP (Charter Communications Holdings LLC vs. CHTR, GCM Grosvenor Holdings LLC vs.
  GCMG). Net effect: refines, does not overturn, ticket 40's conclusion and recommendation —
  added a follow-up smoke-test suggestion (confirm the sampled real gaps pick up a ticker once
  the export pipeline fix ships). Ticket 28 (Identity / ticker-CIK promotion criteria) resolved — 9 numbered
  criteria written against ticket 40's reconciled findings. Key shape decisions: criterion 1
  makes the missing documented read path the actual hard gate (data is healthy per ticket 40,
  but nothing ER-facing exposes it today — `TICKER_REFERENCE` is still 0 rows until ticket 40's
  fix ships), so Identity is explicitly **not promotable as-is** regardless of criteria 2-9;
  criterion 2 scopes coverage to the ticker-eligible subset (cross-checked against SEC's
  `company_tickers.json`) at a 95% bar, not the full active universe; criterion 3 is an explicit
  negative guard against ever re-adding a full-universe coverage bar; criterion 4 guards against
  `MDM_COMPANY_ENTITY`/silver `sec_company_ticker` silently diverging now that both are known to
  be the same underlying data via different paths. Explicitly not required: ticker history, CIK
  in any ER-facing output (per ticket 27, no skill ever references CIK), same-day freshness.
  Removed from open frontier (resolved).
- **2026-07-29 (f):** Ticket 40 (Root-cause the empty TICKER_REFERENCE pipeline) resolved.
  Two independent findings, not one, and it was important not to conflate them: (1)
  `TICKER_REFERENCE` = 0 rows **is** a genuine bug — re-confirmed live in prod, root cause is
  the `command_name == "seed-universe"` export gate (re-verified by reading
  `warehouse_orchestrator.py` lines 642-687/1404-1460 directly), which never fires under the
  documented Phased Pipeline's real operating commands (`daily-incremental`, `load_history`'s
  `bootstrap-batch`, `gold-refresh`). (2) The operator's stated hypothesis — that the ~8%
  ticker-population figure might just reflect a universe full of non-ticker filers rather than
  a capture bug — was checked against a real ground truth and **confirmed correct**: fetched
  SEC's own official `company_tickers.json` (8,017 unique CIKs total, the same source
  `edgartools` itself uses via `get_company_tickers()`), cross-referenced it against the
  live 26,300-row `tracking_status='active'` population from `EDGARTOOLS_GOLD.COMPANY`, and
  found 9.8% match — versus 9.8% on silver `sec_company_ticker` and 9.8% on
  `MDM_COMPANY_ENTITY.ticker` for the identical population. All three agree with SEC's own
  ground truth to within noise. Root cause of the low aggregate rate: the tracked/active
  universe is 88.9% `entity_type='other'` (sampled rows: broker-dealers, investment advisers,
  individual insiders, trusts, even a foreign sovereign issuer) — none of which SEC itself
  ticker-tags; `entity_type='operating'` alone matches SEC's file at 72.9%. Also resolved the
  ticket's "third source" question: downloaded and queried the live prod silver DuckDB
  directly (994 MB, `s3://edgartools-prod-warehouse-690839588395/warehouse/silver/sec/
  silver.duckdb`) and confirmed `sec_tracked_universe` (cited in `mdm/cli.py`'s
  `_seed_mdm_from_silver`) does not exist in real deployments — it's a dead legacy table
  (`ShardedSilverReader` comment "legacy table; best-effort"; a standing unit test asserts it's
  always 0) — the code always falls through to a `sec_company_ticker JOIN
  sec_company_sync_state` fallback, and `MDM_COMPANY_ENTITY.ticker` is itself fed from that
  same fallback (via `mdm/universe.py`'s `bulk_upsert_universe`), not an independent pipeline.
  So there are really two ticker sources, not three, and one of them (silver
  `sec_company_ticker`) is healthy. Recommendation (research only): make silver
  `sec_company_ticker` canonical and rewire `TICKER_REFERENCE`'s export onto `gold-refresh`
  instead of `seed-universe`. Removed from open frontier (resolved); ticket 28 unblocked
  (`Blocked by:` cleared, Progress section updated with the reconciled findings and a note to
  scope any coverage criterion to the ticker-*eligible* subset, not the full active universe).
- **2026-07-29 (e):** Started grilling ticket 28 (Identity / ticker-CIK promotion criteria).
  Before drafting any criteria, live-schema check found `EDGARTOOLS_GOLD.TICKER_REFERENCE` and
  its upstream `EDGARTOOLS_SOURCE.TICKER_REFERENCE` both 0 rows in prod — despite every one of
  the 9 ER skills (per ticket 27) using ticker/name as its primary input, making this the most
  load-bearing capability in the whole Identity product. Root-cause investigation (read-only)
  found the export is wired only into the one-time `seed-universe` command, scoped to
  newly-seeded CIKs only — `daily-incremental`, `load_history`'s `bootstrap-batch`, and
  `gold-refresh` never touch it. The only populated ticker data lives on
  `MDM_COMPANY_ENTITY.ticker` (~8% of companies), a completely different (MDM export) pipeline.
  Operator chose (via AskUserQuestion) to flag this as a blocker rather than guess which source
  is canonical. Spun off ticket 40 (research: root-cause the empty pipeline, unblocked) and
  re-blocked ticket 28 on it. Ticket 28 stays open/not-resolved, progress recorded on the ticket
  itself.
- **2026-07-29 (d):** Ticket 27 (Survey ER skill requirements per F1-F12 product) resolved —
  read all 9 `SKILL.md` files in full plus the most relevant `earnings-analysis`/
  `initiating-coverage` reference sub-files (the rest of those two skills' sub-files grepped,
  hits read in context). Findings written to sibling `issues/27-research-findings.md` (12
  sections, F1-F12, matching `erdp-coverage-promotion` ticket 01's structure). Key results:
  grounding strength varies sharply — F1/F4 strong across nearly every skill; F7 (13F/holders)
  and F8 (graph neighborhood) are the weakest, with most matrix Partial cells unsupported by any
  skill text once actually grepped; F11 (accounting forensic scores) has exactly one skill hit
  across all 9 skills + reference files, and it asks for two boolean flags, not a computed
  score; F5's GAAP-only platform surface only half-satisfies earnings-analysis's stated
  Adjusted+GAAP need; F9 (segment/geo revenue) is the single most demanding, well-grounded
  requirement found (initiating-coverage Task 2, matches the matrix's own "no curated mart"
  framing); F12 conflates pure-SEC and market-priced metrics in the skills' own text, a boundary
  the platform enforces (ADR 0001) that the skill text itself never acknowledges. No promotion
  checklists written (out of scope per ticket 27 — deferred to 28-39). Removed from open
  frontier (resolved); tickets 28-39 unblocked and added to frontier, two flagged with a pointer
  to weak-grounding findings (F7/F8/F11) for whoever claims them next.
- **2026-07-29 (c):** Ticket 25 (F1-F12 promotion checklist) resolved as a **scoping decision
  only** — grilled the scope question (survey-all-12-first vs. lighter single-ticket vs.
  subset-only); operator chose survey-first, mirroring `erdp-coverage-promotion`'s ticket 01 →
  03-06 shape. Graduated into ticket 27 (research: survey all 9 ER skills per F1-F12 product,
  unblocked) and twelve new per-product grilling tickets 28-39 (Identity, Filings metadata,
  Filing/research text, Historical financials, Earnings 8-K GAAP snapshot, Ownership/Form 4,
  13F/holders, Graph neighborhood, Segment/product-geo revenue, Executive/management pay,
  Accounting forensic scores, Pure-SEC subject features — all blocked by 27). Flagged two
  products (F3 filing text, F9 segment revenue) as likely needing a "not promotable without a
  prerequisite automation/mart build" finding rather than a normal checklist, per the coverage
  matrix's own notes. Removed from open frontier (resolved); ticket 27 added to frontier
  (unblocked); 28-39 added as explicitly blocked, not claimable yet.
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
