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

## Not yet specified

- Whether MDM entity-*resolution* steps (`run_companies`/`run_securities`/
  `run_persons`/`run_advisers`/`run_funds` — distinct from relationship
  *derivation*, MANAGES_FUND's own subsystem) have any unscoped-full-load
  shape of their own. The mdm-run-throughput map already gave these a
  bulk-prefetch/bounded-round-trip treatment for a *speed* problem: not
  yet checked whether that same work incidentally also bounds memory, or
  whether a separate audit is needed. Ticket 01 below touches
  `MdmSecurities`/`MdmPersons` (which call these resolvers) — if it
  surfaces a resolution-side gap, that graduates into its own ticket then.
- Whether the same unscoped-load shape exists anywhere outside the MDM
  Postgres/relationship-derivation and warehouse bronze/silver/gold
  domains entirely (e.g. the Snowflake mirror/graph-sync writers in
  `edgar_warehouse/mdm/snowflake_graph.py`, `export.py`) — not sharp
  enough to ticket yet; may or may not be in scope depending on whether
  those run on `large`/`mdm-large` at all (not yet confirmed either way).

## Out of scope

- Re-deriving fixes already covered by another resolved map for a
  *different* memory-failure shape (gold-build-memory-reliability's
  `iter_gold_tables()` streaming fix, seed-universe-narrow-hydrate's
  streaming-hydrate fix, stage0-stage1-consolidation) — those stay
  authoritative for the DuckDB/S3-buffering shape; this map only adds a
  check for the *unscoped-ORM-hydration* shape on top, not a re-litigation.
