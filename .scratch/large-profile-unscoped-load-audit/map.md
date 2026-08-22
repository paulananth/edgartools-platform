# Large-profile unscoped-load audit

Labels: wayfinder:map

## Destination

Every command/state that runs on the `large` (warehouse, 2048/8192) or
`mdm-large` (MDM, 2048/8192) Fargate task profile has been checked for the
same structural OOM shape MANAGES_FUND had: an **unscoped full load of a
shared table/dataset before the code knows which subset it actually
needs** — and any genuine gap found has been fixed the same way
MANAGES_FUND and INSTITUTIONAL_HOLDS were: batch-scope the load, release
each batch's cache before the next, with a red-before-green regression
test proving the scoping is real. Reaching the end of this map means every
`large`/`mdm-large` consumer is either confirmed safe (with the evidence
that made it safe recorded) or fixed.

## Notes

- **This map carries execution** (user-confirmed, 2026-08-21) — like
  gold-build-memory-reliability, tickets here investigate *and* fix, not
  just decide. Use `/tdd` and `/code-review` per this repo's standard
  `/implement` flow; mirror the MANAGES_FUND fix
  (`edgar_warehouse/mdm/pipeline.py`'s `_derive_manages_fund`/
  `_derive_manages_fund_batch`, `GraphSyncEngine.prime_relationship_type`'s
  `source_entity_ids` scoping + `unprime_relationship_type`) and the
  INSTITUTIONAL_HOLDS follow-up as the established fix pattern when a gap
  is found.
- **Full survey, including warehouse-side `large` commands** (user-
  confirmed) even though several already have dedicated resolved incident
  maps — those maps fixed a *different* memory-failure shape (DuckDB/S3
  buffering, not unscoped SQLAlchemy ORM table hydration), so re-checking
  them for *this specific* shape is not re-litigating closed work.
- Standing preference from this session: real measurements against live
  prod data before concluding a step is safe or at-risk — row counts,
  table sizes, concentration — not estimates. See tonight's MANAGES_FUND/
  INSTITUTIONAL_HOLDS investigation for the method (`SELECT ... GROUP BY
  rel_type_name` against MDM Postgres, table-size checks against the
  canonical `silver.duckdb`).
- Full inventory of `large`/`mdm-large` consumers as of 2026-08-21 (source:
  `infra/scripts/deploy-aws-application.sh`'s `command_task_profile()` and
  every `wh_large_arn`/`mdm_large_arn` call site):
  - **`large`**: `bootstrap-full`, `targeted-resync`, `full-reconcile`,
    `gold-refresh`, `daily-incremental`, `bootstrap`, `bootstrap-next`,
    plus `load_history`-internal states: `ComputeWindows` (window
    planning), 3 per-window fundamentals fetches (entity-facts,
    per-filing, thirteenf-holdings), `ReleaseSecFetchLease`,
    `ReduceIdentityRefresh`, and 2 still-hardcoded `wh_large_arn`
    `SeedUniverse` call sites (lines ~3487, ~4129) that may predate ticket
    07's `command_task_profile('seed-universe') == "medium"` decision —
    worth confirming these are current/live definitions, not dead code,
    before treating them as a discrepancy.
  - **`mdm-large`**: all 7 steps of `residual_holds_graph` —
    `MdmSecurities` (`mdm run --entity-type security`), `MdmPersons`
    (`mdm run --entity-type person`), `MdmIsInsider`/`MdmHolds`/
    `MdmCompanyHolds`/`MdmInstitutionalHolds` (each a standalone `mdm
    derive-relationships --relationship-type X` call — confirms
    `residual_holds_graph` is a **live, production-reachable path** that
    directly exercises `INSTITUTIONAL_HOLDS` derivation, independent of
    `mdm run --entity-type all` — real validation that tonight's fix
    wasn't purely theoretical), and `mdm export`.
- Live row counts measured 2026-08-21 (context for tickets, not a
  substitute for each ticket's own re-check as data grows): MANAGES_FUND
  563,631 (fixed), INSTITUTIONAL_HOLDS 0 today but 6.8M-row source table
  (fixed pre-emptively), COMPANY_HOLDS 3,148, ISSUED_BY 2,985, IS_INSIDER
  902, HOLDS 395, EMPLOYED_BY 3 — all six orders of magnitude below
  MANAGES_FUND's outlier scale.

## Decisions so far

<!-- Closed ticket decisions — one-line gist + link; detail lives in the ticket. -->

- [Audit residual_holds_graph's mdm-large steps for the unscoped-load shape](issues/01-audit-residual-holds-graph-mdm-large-steps.md) — found and fixed the real gap: IS_INSIDER/HOLDS/COMPANY_HOLDS still primed unscoped (COMPANY_HOLDS grew ~10.6x in ~24h, live-measured), now self-priming with per-invocation scoped source_entity_ids; MdmSecurities/MdmPersons and both `mdm export` steps confirmed safe with evidence recorded; MdmInstitutionalHolds's call site confirmed consistent with the existing fix.
- [Audit bootstrap-full/targeted-resync/full-reconcile/bootstrap/daily-incremental/bootstrap-next for the unscoped-load shape](issues/02-audit-core-warehouse-commands-large-profile.md) — found and fixed the real gap: `mdm_entity_backfill.py`'s `_fetch_pending_rows` read each of 6 tables fully unbounded (`sec_adv_private_fund` alone is 1,579,876 rows, larger than MANAGES_FUND's own OOM trigger, live-measured), now keyset-paginated per table's real unique key (not uniformly CIK — `sec_adv_private_fund` has no CIK column); `_run_submissions_bronze_then_silver`/`ReleaseSecFetchLease`/`ReduceIdentityRefresh` confirmed safe or already fixed elsewhere; the addendum's hardcoded `SeedUniverse` state was initially mis-scoped as out-of-scope, corrected during Ticket 03's prep — see that ticket's answer.
- [Confirm gold-refresh's streaming fix is the complete story for the unscoped-load shape](issues/03-confirm-gold-refresh-streaming-fix-is-complete.md) — confirmed the streaming fix is genuinely complete (traced the live loop, no full-dict pass); real psutil-measured memory margins for `_build_fact_adv_private_fund`/`_build_sec_thirteenf_holding` show wide headroom, no fix needed; deleted a confirmed-dead `serving_publish.py` wrapper; corrected Ticket 02's `SeedUniverse` finding — routed `write_warehouse_mdm_gold_definition`'s hardcoded `wh_task_large_arn` through the already-decided `command_task_profile('seed-universe') == "medium"` lookup (task-profile-consolidation tickets 06/07), mirroring `write_load_history_definition`'s own already-fixed pattern.
- [Audit load_history's internal large-profile states for the unscoped-load shape](issues/04-audit-load-history-internal-large-states.md) — corrected this ticket's own original `persist_run_manifest` claim (that's `compute-identity-refresh-window`, a different command on `medium`, not `ComputeWindows`); `ComputeWindows`'s real hydrate cost confirmed already owned by `seed-universe-narrow-hydrate` (live-measured canonical: 1.59GiB); 3 fundamentals-fetch commands confirmed already fixed (ecs-cost-sizing ticket 20's `_merge_chunk_size()`); found and fixed the sibling gap to Ticket 02/03's — `write_silver_mdm_gold_definition`'s hardcoded `SeedUniverse` now also routes through `command_task_profile()`.
- [Audit snowflake_graph.py's sync-graph/verify-graph internals for the unscoped-load shape](issues/05-audit-snowflake-graph-sync-verify-internals.md) — a real coverage gap in the map's own inventory, found while closing out (Ticket 01's 7-step scope never named `mdm sync-graph`/`verify-graph` even though `sync-graph` runs on `mdm-large`). Confirmed clean bill of health: every data-volume-scaling operation pushes computation server-side into Snowflake SQL (aggregate counts, `HASH_AGG` exact-parity) and pulls back only tiny summaries or explicitly `LIMIT`-bounded samples (`sample_limit` defaults to 20) — architecturally the opposite of the audited shape by design.

## Not yet specified

None — both fog items above graduated and resolved: MDM entity-resolution
steps (`run_companies`/`run_securities`/`run_persons`) were checked by
Ticket 01 (`MdmSecurities`/`MdmPersons`, confirmed safe — DuckDB-native
reads, no unscoped Python-side hydration) and Ticket 05 checked the
Snowflake mirror/graph-sync writers (`snowflake_graph.py`, confirmed safe
— server-side aggregation only). `run_advisers`/`run_funds` were never
directly exercised by any ticket here (not reachable from
`residual_holds_graph`, per Ticket 01's Out-of-Scope) — if a future
effort wants that covered, it starts as a fresh map, not a resumption of
this one, since this map's destination is now reached.

## Status: complete (2026-08-22)

Every `large`/`mdm-large` consumer named in this map's own inventory
(Notes, above) has been checked against the MANAGES_FUND-shape risk: 4
genuine gaps found and fixed (IS_INSIDER/HOLDS/COMPANY_HOLDS priming,
`mdm_entity_backfill.py`'s unbounded reads, and 2 stale `SeedUniverse`
task-profile hardcodes), the rest confirmed safe with real, recorded
evidence (live row counts, live schema inspection, `psutil`-measured
memory margins). No changes deployed to production as part of this map —
each ticket's fix landed in the codebase (PR #443, branch
`claude/large-profile-unscoped-load-audit`); deployment is a separate,
explicit follow-up.

## Out of scope

- Re-deriving fixes already covered by another resolved map for a
  *different* memory-failure shape (gold-build-memory-reliability's
  `iter_gold_tables()` streaming fix, seed-universe-narrow-hydrate's
  streaming-hydrate fix, stage0-stage1-consolidation) — those stay
  authoritative for the DuckDB/S3-buffering shape; this map only adds a
  check for the *unscoped-ORM-hydration* shape on top, not a re-litigation.
