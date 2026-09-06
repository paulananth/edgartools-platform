# MDM relationship-derivation incremental filters

## Destination

Every `_derive_*` method in `MDMPipeline.derive_relationships()`
(`edgar_warehouse/mdm/pipeline.py`) reads its source table with a real
incremental/diff filter — only rows new or changed since that
relationship type's last successful derivation — instead of the current
full-source-table scan bounded only by how many new relationship rows to
write. Done when `mdm derive-relationships`/`mdm infer-relationships` can
be folded into a genuinely daily-scoped pipeline (e.g. the single MDM
machine's automatic tail, state-machine-consolidation map) without paying
a full-table-scan cost on every run.

## Notes

- Domain: `edgar_warehouse/mdm/pipeline.py`, `MDMPipeline.derive_relationships`
  and its 11 `_derive_*` methods.
- Discovered while grilling
  [state-machine-consolidation ticket 08](../state-machine-consolidation/issues/08-decide-fate-of-mdm-pipeline-machine-heads.md):
  the user asked whether `IS_INSIDER`/`HOLDS`/`COMPANY_HOLDS`/
  `INSTITUTIONAL_HOLDS` derivation should fold into the new single MDM
  machine's automatic tail (would then run on every `daily_incremental`/
  `load_history` execution). Investigation found the gap this map exists
  to close, and ticket 08 stayed with the conservative answer (leave all 4
  relationship types operator-triggered-only) specifically because of it —
  see that ticket's Answer once resolved for the full reasoning.
- Real per-type filtering shape, row counts, and available timestamp/
  versioning columns for all 11 types: see Ticket 01's resolution above
  and `research/01-incremental-filtering-status.md` — four genuinely
  distinct shapes exist, not the single presumed one this section
  originally described (now superseded, not restated here).
- Existing incremental/diff precedent elsewhere in the platform worth
  modeling this on: `sec_daily_index_checkpoint` (daily-index-driven
  discovery, CLAUDE.md's "SEC data idempotency" section) and the
  accession-union/digest carried through `daily-incremental`'s recurring
  window (CLAUDE.md's "Daily accession-expansion 5-whys"). Both use an
  explicit checkpoint/high-water-mark rather than re-scanning source state
  each run.

## Decisions so far

- [Confirm incremental-filtering status and data volume](issues/01-confirm-incremental-filtering-status-and-data-volume.md) — Read all 11 `_derive_*` methods directly rather than extrapolating from the 2 previously-confirmed ones. Found **four distinct filtering shapes, not the presumed one**: (1) growing-window bounded `_bounded_relationship_sql` LIMIT (5 of 11 types, fully or partially); (2) CIK/CRD-range batched full scan, count-bounded only across the whole batch loop (INSTITUTIONAL_HOLDS, and newly-found MANAGES_FUND); (3) fully unbounded MDM-Postgres scan with no SQL LIMIT at all, Python `break` only (IS_ENTITY_OF, IS_PERSON_OF, ISSUED_BY, plus fallback/prefetch paths inside MANAGES_FUND and HAS_PARENT_COMPANY) — these 4+ types don't read a silver table at all, previously unflagged; (4) an always-unbounded secondary sub-query hardcoded `remaining=None` inside EMPLOYED_BY. Also found live: HAS_PARENT_COMPANY's and AUDITED_BY's "bounded" primary paths currently process 0 rows in prod (empty source tables), so their real behavior today is their fallback branch. Full per-type row-count/timestamp-column inventory: `research/01-incremental-filtering-status.md`.
- [Investigate empty HAS_PARENT_COMPANY/AUDITED_BY source tables](issues/03-investigate-empty-has-parent-company-audited-by-source-tables.md) — **Real, close-to-shippable gap found for two of the three tables.** `sec_subsidiary_evidence`/`sec_auditor_report_evidence` (HAS_PARENT_COMPANY's and AUDITED_BY's primary sources) have real, tested parsers wired into `ingest-relationship-sources`' dispatch, but **no code anywhere ever produces a manifest entry of the required `kind`** — the only large-scale candidate-discovery pipeline that ever ran in prod (`relationship_bulk_load.py`, Ticket 20's 2026-07-25 technical PASS) covers only `thirteenf`/`proxy`/`item_502_8k`, zero subsidiary/auditor/PCAOB coverage. Confirmed independently by release-readiness Ticket 35 (zero `HAS_PARENT_COMPANY`/`AUDITED_BY` graph edges in any of 14 tracked generations, ever). The parser/write half is done; only a discovery/fetch step is missing. `sec_accounting_flag` (AUDITED_BY's fallback), by contrast, is a confirmed structural SEC-API limitation (companyfacts never surfaces the 4 auditor-DEI XBRL concepts, for any filer — verified twice independently) with its own already-open decision ticket (release-readiness Ticket 92), not a wiring gap. Full detail: `research/03-empty-source-tables-investigation.md`.

## Not yet specified

(none currently — both items graduated into Ticket 01 and Ticket 02 below)

## Out of scope

(none yet)
