# 03 — Add the BookkeepingStore Methods Callers Need, and an Instantiation Convention

**Renarrowed during implementation (2026-08-29).** Originally scoped as
"rewrite cross-store joins and repoint every caller" — a full-repo recon
pass (before any code was written; see the caller inventory in
[Ticket 14](14-repoint-warehouse-orchestrator-bookkeeping-callers.md)'s own
body for the detail) found that scope was itself under-scoped the same way
the original Ticket 02 was: `warehouse_orchestrator.py` alone has 50+ call
sites across many independently-scoped functions, one caller
(`scripts/build_relationship_release_manifest.py`) needs a Postgres
dependency it's never had before, and at least 3 callers need
`BookkeepingStore` methods Ticket 02's 34-method surface doesn't provide.
Split into four, in dependency order:

- **This ticket (03)** — the two things every other sub-ticket needs before
  it can start: the 3 missing `BookkeepingStore` methods, and a settled
  instantiation convention for how application code (not tests) gets a
  store instance. No caller repointing here.
- [Ticket 13](13-rewrite-cross-store-join-sites.md) — rewrite the 4
  cross-store join sites (the original ticket's actual stated focus) plus
  `mdm/pipeline.py::run_companies`'s repoint (same file family, same
  fetch-then-Python-join pattern, needs this ticket's new
  `get_all_company_sync_states` method).
- [Ticket 14](14-repoint-warehouse-orchestrator-bookkeeping-callers.md) —
  repoint `warehouse_orchestrator.py`'s 50+ call sites, isolated on its own
  given the file's size and review risk, plus the `get_table_counts`
  merge-shape decision.
- [Ticket 15](15-repoint-remaining-bookkeeping-callers.md) — repoint every
  other caller: the genuinely-mechanical ones, the two that need new store
  methods plus raw-SQL rewrites, `migrate_silver_shards.py`'s own review,
  and `build_relationship_release_manifest.py`'s net-new Postgres
  dependency. Ops scripts (`scripts/ops/check-neo4j-e2e.py` and siblings)
  stay deferred to [Ticket 08](08-build-table-specific-reconciliation-tooling.md)
  per an earlier operator decision — not this ticket's scope.

**What to build:**

1. **Three new `BookkeepingStore` methods**, each replacing a raw-SQL query
   a real caller runs today that none of Ticket 02's 34 ported methods
   cover:
   - `get_all_company_sync_states(self) -> list[dict[str, Any]]` — every
     `sec_company_sync_state` row (at least `cik`, `tracking_status`), no
     filter. Mirrors `get_gold_manifest(run_id=None)`'s existing
     "no filter → return everything" shape, the closest precedent already
     in the store. Replaces: `mdm/pipeline.py::run_companies`'s
     `SELECT cik, tracking_status FROM sec_company_sync_state` (no WHERE),
     and both fallback branches in `mdm/cli.py::_seed_mdm_from_silver`
     (needs `cik → tracking_status`, defaulting missing entries to
     `'active'`, for potentially every CIK in `sec_company_ticker`) —
     landed here since it's shared by 3 callers, but *used* by
     [Ticket 13](13-rewrite-cross-store-join-sites.md), not this one.
   - `get_recent_successful_pipeline_runs(self, limit: int = 10) ->
     list[dict[str, Any]]` — `pipeline_run` rows with
     `status IN ('succeeded', 'ok')` and non-null `metrics_json`, ordered
     `completed_at DESC NULLS LAST, started_at DESC`, limited. Replaces
     `application/commands/validate_data_quality.py`'s
     `_latest_previous_table_counts` raw SQL — used by
     [Ticket 15](15-repoint-remaining-bookkeeping-callers.md).
   - `has_successful_parse_run(self, *, accession_number: str,
     parser_name: str, parser_version: str) -> bool` — a succeeded
     `sec_parse_run` row keyed by `(accession_number, parser_name,
     parser_version)`, not by `parse_run_id` (the existing `get_parse_run`'s
     only key). Replaces `infrastructure/silver_once.py`'s
     `has_successful_ownership_parse` raw SQL — used by
     [Ticket 15](15-repoint-remaining-bookkeeping-callers.md).

   Before finalizing, re-verify no other caller needs a 4th/5th method —
   the recon pass that found these three covered the original ticket's
   explicit target list plus a fresh whole-repo grep, but did not
   exhaustively trace every one of `warehouse_orchestrator.py`'s 50+ call
   sites' exact query shapes; a name match against Ticket 02's existing 34
   methods isn't a semantics guarantee.

2. **An instantiation convention for application code.** `edgar_warehouse/
   bookkeeping/database.py` (Ticket 02) exposes only `get_engine`/
   `get_session` primitives, no shared factory — deliberately, matching
   `edgar_warehouse/mdm/database.py`'s own convention. MDM's own precedent
   for how *application* code (not tests) gets a session is a tiny,
   module-local, one-line helper repeated per consuming module
   (`edgar_warehouse/mdm/cli.py:582-584`: `def _session() -> Session: return
   get_session(get_engine())`) — not a shared cross-module utility. Adopt
   the identical pattern here: a `_bookkeeping_store()`-style one-liner
   defined once per consuming module, not a new shared factory added to
   `edgar_warehouse/bookkeeping/`. **Resolved as:** the convention is now
   documented directly in `bookkeeping/database.py`'s own module docstring
   (the durable, discoverable home for it — not just this ticket file), so
   [Ticket 13](13-rewrite-cross-store-join-sites.md)/[14](
   14-repoint-warehouse-orchestrator-bookkeeping-callers.md)/[15](
   15-repoint-remaining-bookkeeping-callers.md) find it there rather than
   each independently re-deciding it.

**Blocked by:** [Ticket 02](02-move-bookkeeping-tables-to-snowflake-postgres.md)

**Status:** resolved

- [x] `get_all_company_sync_states`, `get_recent_successful_pipeline_runs`,
      and `has_successful_parse_run` exist on `BookkeepingStore`
      (`edgar_warehouse/bookkeeping/store.py`), each with tests proving it
      matches the exact raw-SQL query shape it replaces (ordering,
      filtering, default-value behavior) — 14 new tests in
      `tests/bookkeeping/test_store.py`, including two (`NULLS LAST`
      ordering, `started_at DESC` tiebreak) that construct their fixture
      state via direct session manipulation since `complete_pipeline_run`
      always sets `completed_at`/`metrics_json` together and can't produce
      those edge cases through the store's own write API
- [x] Final re-check found no other caller needing a 4th/5th new method: a
      repo-wide grep for `.fetch(...)` calls with raw SQL against all 11
      bookkeeping table names, plus a targeted check of
      `warehouse_orchestrator.py`'s 50+ call sites for any raw SQL

**Known, accepted gap (three-axis code review, Standards axis):** the
`NULLS LAST` ordering test (`test_null_completed_at_sorts_last`) runs only
against SQLite (the whole `tests/bookkeeping/` suite's only backend today,
per [Ticket 02](02-move-bookkeeping-tables-to-snowflake-postgres.md)'s own
accepted testing scope) — SQLite emulates `NULLS LAST` via a `CASE`
expression, while Postgres supports it natively, so this test proves the
emulation path, not the real dialect's SQL. Consistent with every other
`BookkeepingStore` method (none have Postgres integration coverage yet,
unlike MDM's `tests/integration/test_source_registry_postgres.py`) — not a
new gap this ticket introduces, and not fixed here since building
Postgres integration testing for the whole store is out of this ticket's
scope. Worth a follow-up before [Ticket 04](
04-provision-live-bookkeeping-postgres.md)'s live cutover actually depends
on this ordering behaving correctly against real Postgres.
      (none found — confirmed all method-call-based, as the original recon
      pass suspected but didn't verify), turned up only the 3 already-known
      sites this ticket's 3 new methods cover
- [x] The `_bookkeeping_store()` instantiation convention is documented in
      `edgar_warehouse/bookkeeping/database.py`'s module docstring (the
      durable home for it, not just this ticket file) so downstream
      tickets apply it uniformly rather than each inventing their own shape
- [x] Full test suite green
