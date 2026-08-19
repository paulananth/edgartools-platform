# Single Path Per Layer

Label: `wayfinder:map`

## Destination

A written, enforced platform rule that every layer transition in this
pipeline (bronze→silver, silver→MDM entity resolution, silver→MDM's
backfill sweep, silver→gold, MDM→graph, MDM→Snowflake mirror,
gold→dashboard) has exactly **one implementation of its real decision/work
logic** — multiple entry points (CLI commands, Step Functions) are fine when
they're documented, distinct operational modes that all delegate to that one
implementation, never separate reimplementations of the same job. Reaching
the end of this map means: every transition has been audited against the
rule, violations found are tracked (fixed later, by a separate /implement
effort — this map decides, it does not build), the rule itself is written
down in CLAUDE.md, and an enforcement mechanism is decided that would have
caught the shard-publish-fix-style silent divergence before it shipped.

## Notes

- **Motivating incident, do not re-derive**: this session's shard-publish
  fix (CLAUDE.md's "Shard-publish promotion-race 5-whys" entry). The
  monolith `silver.duckdb` publish path and the shard publish path silently
  diverged — the shard path never got the merge+retry treatment the
  monolith got in PR #222 — until three real prod failures forced parity.
  Nothing (test, lint, or doc) caught the divergence while it existed. This
  is the concrete "what happens without an enforced single-path rule"
  example driving this map.
- **Corrected finding, do not re-flag as a violation**: this session
  investigated whether `edgar_warehouse/mdm_entity_backfill.py`'s 500-row
  batched sweep and `edgar_warehouse/mdm/pipeline.py`'s resolvers
  (`run_companies`/`run_persons`/etc., called by `mdm run`) are duplicate
  implementations of entity resolution. They are **not** — the sweep is
  deliberately read-only against MDM (its own docstring: "never duplicates
  run_companies/run_persons/etc.'s own work"); it only copies an ID the
  resolvers already decided, it does no matching itself. Different jobs,
  not a violation.
- **Also corrected, do not re-investigate**: `run_companies`/`run_securities`/
  `run_persons` are not naive per-row loops today. The separate, already-
  closed [mdm-run-throughput](../mdm-run-throughput/map.md) map moved them
  to bounded 16-worker concurrency (PRs #376/#381, merged 2026-08-08/09,
  predates this map). `run_advisers`/`run_funds` were already bulk-batched
  before that. MDM resolver throughput is settled; this map is not about
  speed.
- **Real, still-open finding folded in as a ticket**: a fresh full `mdm run`
  (no `resume_ledger_run_id` reuse) re-resolves the entire company/security/
  person/adviser/fund universe from scratch every time, including rows
  already correctly resolved and unchanged since the last run. This is
  distinct from both concurrency (throughput per row, already fixed) and
  from "single path" (duplicate implementations) — it's an absent
  skip-if-unchanged fast path, the same shape as release-readiness
  ticket 79's fingerprint pattern, which this session also used for the
  shard-publish fix.
- Use `/gof-refactor-reviewer` before any ticket proposing to consolidate or
  refactor code across a layer transition, per this repo's standing
  CLAUDE.md instruction.
- Consult CLAUDE.md's existing 5-whys entries for prior divergence/
  duplication incidents before assuming a transition needs auditing —
  relevant precedents already recorded there: the shard-publish incident,
  the INSTITUTIONAL_HOLDS/EMPLOYED_BY `ShardedSilverReader._TABLES`
  registration gap, and the manifest-pipeline-ownership incident.
- Mode: decision-spec only (wayfinder default, not overridden). Tickets
  decide; a later, separate `/implement` effort builds.

## Decisions so far

- [Enumerate Every Layer Transition and Its Current Implementation(s)](issues/01-enumerate-layer-transitions.md) — audited all 7 transitions (bronze→silver, silver→MDM resolution, silver→MDM backfill sweep, silver→gold, MDM→graph, MDM→Snowflake mirror, gold→dashboard); **no single-path violations found**. The Python `gold_models.py`/dbt gold-models pair looked like a candidate at first glance but turned out to be two stages of one pipeline (Python builds a source-layer export, dbt builds the actual gold tables from it) — flagged only as a misleading-name issue, not a violation. The two Streamlit dashboards also looked suspicious (near-identical line count) but serve genuinely different purposes, confirmed via a function-name diff. The only real violation found across this whole investigation — shard-publish vs. monolith silver.duckdb publish — was already fixed earlier this session and is what motivated this map.
- **Documentation cleanup (2026-08-19, direct fix, not a ticket)**: while auditing, found CLAUDE.md's Quick Navigation, Key Large Files, architecture diagram, and Data Layer Definitions all pointed at three files (`runtime.py`, `silver.py`, `gold.py`) that have since become thin compatibility shims — the real implementations live in `application/warehouse_orchestrator.py`, `silver_store.py`, and `serving/gold_models.py` respectively, all significantly larger than the stale sizes recorded. Also fixed the stale "8 dynamic tables" gold-layer count (now 23) and added the missing `EDGARTOOLS_SILVER` layer to the architecture diagram (hedged as mid-migration, pointing at this map rather than asserting a cutover state). Fixed directly in CLAUDE.md rather than as a separate ticket, per explicit instruction.
- **Rename `gold_models.py` off its misleading name (2026-08-19, direct fix via `/improve-codebase-architecture`, not a ticket)**: renamed to `source_dimensional_export.py` plus its `gold_*` symbol family (`GOLD_AFFECTING_COMMANDS` → `SOURCE_EXPORT_COMMANDS`, `build_gold` → `build_source_export`, etc.) across ~21 real code/test files, in two commits (file rename, then symbol rename). Explicitly did **not** rename `runtime.py`/`silver.py`/`gold.py` themselves — `tests/architecture/test_runtime_shim.py` proves those three are a deliberate, tested, stable public import surface, not drift. A wider "gold"-flavored vocabulary in `warehouse_orchestrator.py`'s own gold-publish pipeline (`publish_gold`, `gold_build_started`, `bronze_seed_silver_gold` — a live Step Functions state-machine name) was found and deliberately left alone, flagged for a possible future pass rather than folded in.
- **Investigated the MDM → graph transition more deeply (2026-08-19, direct fix, not a ticket)**: confirmed Ticket 01's "no violation" finding holds under a fuller trace of the write path (`graph.py` preps Postgres, `snowflake_graph.py` executes Snowflake SQL — split by design, not duplicated), found two deliberately different read paths (Postgres mirror for speed, Snowflake for dashboard metrics) and a whole undocumented publication-lifecycle queue (`publication.py`). Wrote all of this into CLAUDE.md's "Graph storage" note, which previously only covered the write/verify path. Found and removed one genuinely dead file, `edgar_warehouse/serving/targets/neo4j.py` (unimported, superseded "publish to external Neo4j" placeholder).
- [Decide the Enforcement Mechanism for the Single-Path Rule](issues/02-decide-enforcement-mechanism.md) — architecture test extending the existing `test_runtime_shim.py` precedent, not a lint rule or general detector. Locks the one sibling pair that has already diverged in production (`_publish_silver_database_if_remote`/`_publish_shard_if_remote`) rather than trying to catch every possible future violation. Implemented: `tests/architecture/test_sibling_path_symmetry.py`.
- [Decide How Full `mdm run` Should Skip Already-Resolved, Unchanged Entities](issues/03-decide-mdm-run-skip-unchanged.md) — content hash over the exact fields `resolve_one` stages, stored on a new `mdm_source_ref.source_content_hash` column, `run_companies` only (adviser/fund/security/person left for a future ticket). While testing, found and fixed a real, pre-existing, unrelated bug: `survivorship.py`'s priority-tie-breaking had no recency signal, so a stale first-ever-staged value could permanently beat a genuinely newer one — fixed using the schema's already-present but never-read `loaded_at` column.

## Not yet specified

<!-- empty -- the gold_models.py naming-clarity issue was fixed directly in
     CLAUDE.md (2026-08-19) rather than ticketed; see Decisions so far. -->

## Out of scope

- **MDM resolver throughput/concurrency** (`run_companies`/`run_securities`/
  `run_persons` per-row vs. concurrent execution) — already resolved by the
  [mdm-run-throughput](../mdm-run-throughput/map.md) map (PRs #376/#381).
  A performance question, already fixed elsewhere, not a single-path
  violation.
- **`mdm_entity_backfill.py` vs. `pipeline.py` resolvers as "duplicate
  paths"** — investigated this session (see Notes above), confirmed not
  duplicates. Different jobs: cheap read-only ID-copy vs. real matching.
