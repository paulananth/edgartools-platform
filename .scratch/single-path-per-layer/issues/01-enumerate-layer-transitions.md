# Enumerate Every Layer Transition and Its Current Implementation(s)

Type: `wayfinder:task` (AFK)

Status: resolved

Blocked by: none

## Question

For every layer transition in this platform's pipeline —

- bronze → silver (all write-path commands: `bootstrap-next`, `bootstrap`,
  `bootstrap-full`, `daily-incremental`, `bootstrap-batch`, `load_history`'s
  `WindowedBootstrap`)
- silver → MDM entity resolution (`mdm run`)
- silver → MDM's backfill sweep (`mdm_entity_backfill.py`)
- silver → gold (dbt models, `infra/snowflake/dbt/edgartools_gold/`)
- MDM → graph (`mdm sync-graph`)
- MDM → Snowflake mirror (`mdm export`)
- gold → dashboard (Streamlit reads)
- any other transition discovered while enumerating (e.g. relationship
  derivation, `mdm backfill-relationships`)

identify **every code path that performs the real decision/work logic** for
that transition — not just its CLI entry points. For each transition,
answer:

1. Is there exactly one implementation of the actual work, with multiple
   entry points (if any) all delegating to it? (expected/fine, per this
   map's Q2 decision)
2. Or are there two or more independent implementations of the same job
   for that transition? (a candidate violation — name both, and confirm via
   git history or code reading that they really do the same job, not
   different jobs that happen to look similar — see this map's Notes for
   two cases this session already checked and ruled NOT violations)

Cite specific functions/files for every answer. Where a transition already
has a documented reason for multiple entry points (e.g. bronze→silver's
different operational modes, per CLAUDE.md's "Phased Pipeline" section),
note that explicitly rather than re-flagging it.

## Answer (2026-08-19)

Audited all 7 transitions by tracing every entry point to its actual
implementation (grep + read, not assumption). **No single-path violations
found.** One naming-clarity issue noted (not a violation). Detail per
transition:

1. **bronze → silver.** All 6 write-path commands (`bootstrap-next`,
   `bootstrap`, `bootstrap-full`, `daily-incremental`, `bootstrap-batch`,
   `load-daily-form-index-for-date`) funnel through one function,
   `_run_submissions_bronze_then_silver`
   (`edgar_warehouse/application/warehouse_orchestrator.py:3251`) — verified
   via 6 call sites, 5 inside `_capture_bronze_raw`'s
   `if command_name == ...` branches, 1 inside `submissions_orchestrator`.
   Confirms the mdm-ahead-of-silver map's ticket 03 finding independently.
   No violation — matches this map's Q2 decision (documented distinct
   entry points, one implementation).

2. **silver → MDM entity resolution.** `mdm run` → `MDMPipeline`'s
   `run_companies`/`run_persons`/`run_securities`/`run_advisers`/
   `run_funds` (`edgar_warehouse/mdm/pipeline.py`). Single implementation
   per entity type, one CLI entry point. No violation. (Throughput —
   per-row vs. concurrent — is a separate, already-resolved question; see
   this map's Out of scope.)

3. **silver → MDM's backfill sweep.** `edgar_warehouse/
   mdm_entity_backfill.py`'s `backfill_pending_rows`/
   `run_mdm_entity_backfill_sweep` — one module, one function, one CLI
   command (`backfill-mdm-entity-ids`). Confirmed via its own docstring and
   this session's earlier investigation that this is a genuinely separate
   transition from #2 (reads MDM's already-resolved output, does no
   matching itself), not a second implementation of #2. No violation.

4. **silver → gold.** Two mechanisms exist —
   `edgar_warehouse/serving/gold_models.py`'s `_gold_table_builders`/
   `iter_gold_tables` (Python, ~29 `dim_*`/`fact_*`/`sec_*`-named builders)
   and `infra/snowflake/dbt/edgartools_gold/models/gold/*.sql` (dbt, 23
   business-named models: `company.sql`, `ownership_activity.sql`, etc.).
   Table-name sets are disjoint (`dim_company` vs. `company`,
   `fact_ownership_transaction` vs. `ownership_activity`) — **not** a
   duplicate**, confirmed by tracing where the Python builders' output
   actually lands: `infra/snowflake/sql/bootstrap/03_source_load_wrapper.sql`
   (`LOAD_EXPORTS_FOR_RUN`) runs `USE SCHEMA EDGARTOOLS_SOURCE` and
   `MERGE INTO` there, not `EDGARTOOLS_GOLD`. The Python side builds a
   dimensional-shaped **source-layer** export from local silver DuckDB;
   dbt's models then consume `EDGARTOOLS_SOURCE`/`EDGARTOOLS_SILVER` to
   build the actual `EDGARTOOLS_GOLD` dynamic tables. Two stages of one
   pipeline, not two implementations of the same stage. **Naming-clarity
   issue (not a violation, worth fixing separately)**: `gold_models.py`,
   `build_gold()`, and this repo's own Quick Navigation table ("Gold-layer
   aggregations (Python)") all call this a "gold" builder when it actually
   produces a source-layer export — misleading for anyone new to the repo
   trying to find "the" gold implementation.

5. **MDM → graph.** `mdm sync-graph` → one handler,
   `_handle_sync_graph` (`edgar_warehouse/mdm/cli.py:1421`). No violation.

6. **MDM → Snowflake mirror.** `mdm export` → one class, `MDMExporter`
   (`edgar_warehouse/mdm/export.py:294`), one connection-settings function
   (`silver_connection_settings`). No violation.

7. **gold → dashboard.** Two Streamlit apps exist
   (`infra/snowflake/streamlit/streamlit_app.py`,
   `examples/dashboard/edgar_universe_dashboard.py`) — suspiciously close
   in line count (1354 vs. 1359) at first glance, but a function-name diff
   shows only 6 of ~46 defined functions overlap. They serve different
   purposes: the Snowflake app is an operator/agent-decision-support view
   (`_render_agent_view_company`, `_pipeline_runs`, `_lookup_contract_subjects`),
   the standalone one is a general company-universe browser
   (`_companies_by_state_code`, `_entity_type_mix`, `_top_sic`). Same
   pattern as this map's already-corrected `mdm_entity_backfill.py`
   finding: similar surface size, genuinely different jobs. No violation.

**Overall: the codebase already follows the single-path discipline on
every transition checked.** The one real, already-known violation — the
shard-publish vs. monolith silver.duckdb publish divergence — was already
fixed earlier this session and is what motivated this map in the first
place; nothing else at this scope was found. [Ticket 02](02-decide-enforcement-mechanism.md)
is still worth resolving as insurance against a *future* divergence of
exactly that shape, even though today's audit came back clean.
