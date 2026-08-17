# Decide Gold's Python-Builder Retirement Mechanics

Type: grilling
Status: resolved
Blocked by: 07 (resolved)

## Question

The closed silver-snowflake-migration map's Ticket 03 already decided the
*target*: `gold_models.py`'s ~20 Python builders retire entirely in favor
of dbt gold `ref()`-ing dbt silver directly, which also retires
`EDGARTOOLS_SOURCE`'s current gold-mirror purpose and structurally moots
the `iter_gold_tables` OOM-mitigation concern (CLAUDE.md's "Gold-build
memory / daily_incremental OOM 5-whys" — the streaming-generator fix that
concern motivated becomes unnecessary if there's no longer a Python
builder pass over silver at all). Not yet decided: how the cutover from
Python-built gold to dbt-native gold actually happens.

Decide: are new dbt gold models built and validated against the existing
Python-builder output *before* `gold_models.py` is deleted (parallel-run),
or is this a hard swap once dbt silver models are trusted? Per the
validation standard from [Decide the Cutover Validation Standard](
07-decide-cutover-validation-standard.md), what does gold parity mean
concretely — same 8 dynamic tables, same row counts, same aggregation
values, over what data volume/time window? `validate_data_quality.py`'s
separate `build_gold()` call was already flagged by the closed map's
Ticket 03 as becoming "SQL assertions against live Snowflake gold" — does
that conversion happen as part of this ticket's scope or is it a
downstream implementation detail? Also confirm whether any current
consumer of `gold_models.py`'s Python output (beyond
`validate_data_quality.py`) exists and needs its own migration path.

## Deliverable

A decided cutover mechanism (parallel-run-then-swap vs. hard swap, and how
parity is proven per the shared validation standard) for retiring
`gold_models.py` in favor of dbt-native gold.

## Answer

**Grounding, checked before deciding:** dbt gold today is *not* actually
wired to dbt silver at all — 22 of 23 gold models still `source()` from
`EDGARTOOLS_SOURCE` (the Python-builder gold-mirror), not `ref()` from dbt
silver, despite `sources.yml` declaring an `edgartools_silver_landing`
source no model references. This is a bigger gap than "swap `source()` for
`ref()`": per-table complexity varies enormously — some models
(`financial_derived`, `adv_fund_count_reconciliation`) already have their
real business logic in dbt SQL layered atop a Python passthrough (near-
mechanical to finish); others (`ownership_activity`, `ownership_holdings`,
`private_funds`) `UNION` multiple silver tables and derive natural keys via
text normalization that today exists only in Python
(`_ownership_fact_source_rows`, `_private_fund_natural_key` in
`gold_models.py`) — real porting work, not substitution. A further
complication found only by reading every builder: `form_key`, `filing_key`,
`fact_key`, `party_key`, and `security_key` are derived from DuckDB's
proprietary `hash()` SQL function (one more, `private_fund_key`, from
Python `hashlib.sha256`) — neither has a drop-in Snowflake equivalent that
reproduces the same bit values, so **every** rewired hash-keyed table needs
a deliberate key-regeneration decision, not just a source swap. Five
builders (`sec_subsidiary_evidence`, `sec_auditor_report_evidence`,
`sec_employment_event`, `sec_adv_firm_roster`,
`sec_adv_private_fund`-passthrough) have no dbt gold model at all — nothing
downstream `ref()`s them — so they need a different mechanism (repoint their
export at Snowflake silver directly) than the 18 tables dbt gold does
consume. Real caller check: only `warehouse_orchestrator.py` (the
production write path) and `validate_data_quality.py` genuinely call
`iter_gold_tables()`/`build_gold()` — two other files (`edgar_warehouse/gold.py`,
`application/workflows/serving_publish.py`) re-export `build_gold` but have
zero importers anywhere in the repo, dead shims to delete alongside the
Python builders, not real consumers needing a migration path.

- **Hard swap, not parallel-run-then-swap** — but per-table, not
  all-at-once. Given the per-table complexity spread above, gating every
  table's cutover on every other table's readiness (a single big-bang
  parallel-run window) adds coordination cost without adding safety: each
  table's swap is independently verifiable against
  [Decide the Cutover Validation Standard](07-decide-cutover-validation-
  standard.md)'s digest-based reconciliation, so each table proves itself
  and cuts over on its own schedule. "Parallel-run" in the sense of keeping
  the old Python builder importable-but-unreferenced after a table's own
  cutover (not deleted until every table has moved) is the actual safety
  net — cheap rollback per table without a synchronized freeze window.
- **What "gold parity" means concretely, addressing the validation
  standard's open question for this consumer:** Table-Specific
  Reconciliation applied per-table, compared on **business-key content, not
  surrogate-key columns** — the hash-key portability gap above means a
  literal `filing_key`/`fact_key` diff would show 100% mismatch even on a
  byte-correct migration. A companion decision-only ticket,
  [Establish Snowflake-Native Surrogate Keys](../../dbt-gold-silver-
  rewiring/issues/01-establish-snowflake-native-surrogate-keys.md), settles
  the key-regeneration approach uniformly so this isn't re-litigated per
  table. Bounded case-selection includes at least one real-scale table
  (ownership data, the platform's higher-volume table) per the standard's
  own requirement.
- **`validate_data_quality.py`'s `build_gold()` → Snowflake-assertions
  conversion is in scope, done last** — folded into the final retirement
  ticket once every table has an independent non-DuckDB path, not a
  separate downstream effort.
- **Concrete cutover mechanics, sequenced as seven vertical-slice tickets**
  under `../dbt-gold-silver-rewiring/issues/` (a plain ticket breakdown, not
  a wayfinder map — this is implementation, and the duckdb-retirement map
  stays decision-spec only per its own Notes):
  (1) the surrogate-key macro, (2) near-mechanical passthrough models — 6
  tables, (3) single-source dimensional models — 8 tables, (4) multi-join
  ownership/fund models — 3 tables, the batch's required large-table
  parity case, (5) `accounting_flags` in isolation (known upstream
  forensic-score fragility, tracked separately), (6) the 5 orphan
  evidence-table exports repointed at Snowflake silver directly
  (independent of the dbt-facing batches), and (7) `gold_models.py`
  deletion plus the `validate_data_quality.py` conversion and the two dead
  re-export shims, blocked by everything above. Full per-model sizing and
  acceptance criteria live in that ticket set, not restated here.
