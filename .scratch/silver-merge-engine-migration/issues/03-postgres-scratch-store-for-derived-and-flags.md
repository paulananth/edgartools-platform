# 03 — Score accounting flags in memory; make `merge_accounting_flags`/`merge_financial_derived` landing-only

**Type:** task

**Status:** resolved (2026-09-13). Originally titled "Build the Postgres-backed scratch store
for merge_accounting_flags/merge_financial_derived" — superseded before any code was written,
see [Ticket 01](01-choose-replacement-engine-and-migration-order.md)'s third CORRECTION section
for the grilling that replaced it. File name kept so existing links resolve.

## Question

`backfill_accounting_flags` read `sec_financial_derived` back from local DuckDB and UPDATEd
`sec_accounting_flag` there — the one genuine in-process reader that kept these two tables'
local DuckDB writes alive. But every row it read had been produced moments earlier, in the
same `run_bootstrap_entity_facts` loop iteration, from a companyfacts payload that carries the
company's full filing history. Move the scoring in-process and the read-back disappears; the
two merge methods then become landing-only passthroughs, the same shape as Ticket 02.

## What was built

- `parsers/accounting_flags.py`: `backfill_accounting_flags(cik, silver)` replaced by a pure
  `score_accounting_flags(flag_rows, derived_rows) -> (scored_flag_rows, updated)`. It keeps
  the old read-back-and-UPDATE semantics: derived rows folded per
  (accession_number, fiscal_period, period_end) with first-seen fiscal_year/form_type and
  last-seen metrics (the old ON CONFLICT split); FY rows only, ordered by fiscal_year, with
  the prior-year chain advancing on every FY row; a None score never clobbers an earlier
  score for the same accession (the old COALESCE); `updated` counts only real matches
  (Ticket 42).
- `fundamentals_ingest.run_bootstrap_entity_facts`: per CIK, facts → derived (collected) →
  score → flags → marker. A scoring failure logs `accounting_flags_backfill_error` and still
  writes the unscored flags. `accounting_flags_updated` is a run metric now.
- `bootstrap_fundamentals.py`: the post-run backfill loop is gone.
- `silver_store.py`: `merge_financial_facts`/`merge_financial_derived`/`merge_accounting_flags`
  share `_record_landing_passthrough` (landing-only; old values_fn defaults applied; NOT NULL
  columns read from the live DDL and enforced by raising; facts/flags stamped with
  `ingested_at` + the Ticket 33 validity trio). `update_accounting_flag_scores`,
  `retire_financial_facts_not_in_snapshot`, `retire_accounting_flags_not_in_snapshot` and
  `_finalize_retirement` deleted. The DuckDB DDL for all three tables stays (schema migrations
  and `PROTECTED_TABLE_REGISTRY` still reference it; `merge_candidate_into_canonical`'s
  `silver_event_reducer` caller is untouched).
- `company_facts_silver_acceptance.py`: read-back "verification" and retire calls removed;
  a producer settles VERIFIED once its rows are recorded.

Behaviour changes, all agreed in grilling: a scored flag lands as one complete row per
accession instead of two (same collapsed result); a CIK the skip gate skips keeps its last
scores in silver; the company-facts retirement feature is gone until rebuilt against
Snowflake silver (fog on the map).

Tests: `tests/unit/test_accounting_flags_scoring.py`, `test_fundamentals_landing_passthrough.py`,
`test_entity_facts_scoring_wiring.py` (new); acceptance/command/migration/provenance/landing
tests rewritten for the new contract; `test_accounting_flags_update_masking.py` and
`test_financial_fact_retirement.py` deleted (their coverage moved into the new files).

**Not yet live-verified** — the "done" bar's production write needs a prod entity-facts run
after deploy; see the map.
