# 13 — Rewrite the 4 Cross-Store Join Sites

**Split from the original Ticket 03 during implementation (2026-08-29)** —
see [Ticket 03](03-rewrite-cross-store-joins-and-repoint-callers.md)'s own
split note for the full context. This is that ticket's original, actual
focus: 4 call sites run a single SQL statement joining a real SEC-content
table against `sec_company_sync_state` in one query. Once that table lives
in a separate Postgres instance, none of these can execute as written —
cross-database SQL joins don't work that way.

1. `edgar_warehouse/mdm/coverage.py:44-52` (`compute_coverage`) —
   `SELECT COUNT(DISTINCT c.cik) FROM sec_company c JOIN
   sec_company_sync_state s ON s.cik = c.cik WHERE s.tracking_status =
   'active'`, run through `silver_reader.fetch(sql)`. Already takes
   `session: Session` (the MDM Postgres session) as a param — add a
   `bookkeeping: BookkeepingStore` param the same way. No new store method
   needed: `get_tracked_ciks("active")` (Ticket 02) already covers the
   "active" CIK set. Rewrite as a set intersection (distinct CIKs present
   in both `sec_company` and the active-tracked set) via two fetch/count
   calls plus a Python set operation, not a fabricated SQL join string.
   Caller (`mdm/cli.py:1061`, `_handle_coverage_report`) needs to
   construct/pass the `BookkeepingStore` alongside the existing
   `reader`/`session`.
2. & 3. `edgar_warehouse/mdm/cli.py:1451` and `:1492`
   (`_seed_mdm_from_silver`, used by both `seed-universe` and
   `seed-from-silver`) — two near-identical fallback queries:
   `sec_company_ticker t LEFT JOIN sec_company_sync_state s ON s.cik =
   t.cik`, run via `reader._conn.execute(query, params)` directly against a
   `ShardedSilverReader` (bypasses `.fetch()` entirely, reaching into the
   private `_conn` attribute). **Not a rare edge case**: this fallback
   fires whenever the primary `sec_tracked_universe` query fails, and that
   table is documented as a "legacy table; best-effort" in
   `silver_support/sharded_reader.py:88`'s own comment — likely the
   commonly-exercised path in practice, not a rare degrade. Keep the
   primary `sec_tracked_universe` query and its `try/except` exactly as-is
   (touches no bookkeeping table). Rewrite the `except Exception:` fallback
   to: fetch `SELECT t.cik, t.ticker AS current_ticker, t.exchange FROM
   sec_company_ticker t` via `reader._conn.execute(...)` (DuckDB side only,
   unchanged), separately fetch every `(cik, tracking_status)` pair via
   [Ticket 03](03-rewrite-cross-store-joins-and-repoint-callers.md)'s new
   `bookkeeping.get_all_company_sync_states()`, join in Python
   (`tracking_by_cik = {row["cik"]: row["tracking_status"] for row in
   bookkeeping_rows}`, defaulting missing CIKs to `"active"` via
   `.get(cik, "active")`), then apply `tracking_status_filter` as a
   Python-side filter afterward. `_seed_mdm_from_silver` doesn't currently
   take a `bookkeeping` param — add one, threaded from both its callers
   (grep `_seed_mdm_from_silver(` for the exact handler names before
   editing).
4. `edgar_warehouse/silver_store.py`'s own `get_company_identity_ciks`
   (currently ~line 3802) — `SELECT DISTINCT sync.cik FROM
   sec_company_sync_state AS sync LEFT JOIN sec_company AS company ON
   company.cik = sync.cik WHERE (LOWER(TRIM(COALESCE(company.entity_type,
   ''))) = 'operating' OR EXISTS (SELECT 1 FROM sec_company_ticker AS
   ticker WHERE ticker.cik = sync.cik AND ticker.source_name =
   'company_tickers')) {status_clause} ORDER BY sync.cik`. Deliberately
   **not** built in the new store at all (Ticket 02's own exclusion note) —
   its whole replacement shape is designed here: 1) `tracked_ciks =
   bookkeeping.get_tracked_ciks(tracking_status_filter)` (already covers
   the filter entirely, no new store method needed); 2) if empty, return
   `[]` immediately (avoid an empty-`IN ()` clause); 3) query DuckDB for
   eligibility over just that CIK set (`entity_type` from `sec_company`,
   ticker existence from `sec_company_ticker WHERE source_name =
   'company_tickers'`, both `WHERE cik IN (...)`); 4) join in Python
   (`eligible = {cik for cik in tracked_ciks if entity_type_by_cik.get(cik)
   == 'operating' or cik in ticker_cik_set}`), return `sorted(eligible)`.
   Requires adding a `bookkeeping: BookkeepingStore` param to this
   `SilverDatabase` method — re-verify no caller outside `silver_store.py`
   itself exists before changing the signature (a first pass found none).

**Also repoint, same file family and pattern (the template these 4 rewrites
follow):** `edgar_warehouse/mdm/pipeline.py:440` (`run_companies`) already
does the correct thing architecturally — `SELECT cik, tracking_status FROM
sec_company_sync_state` fetched separately via `self.silver.fetch(...)`,
already joined against `sec_company` rows in Python (mirrors the existing
`ticker_by_cik = _first_per_key(...)` pattern a few lines above it). It
isn't a broken cross-store join to rewrite — it's the shape sites 1-4 above
are being rewritten *into*. It just needs its `self.silver.fetch(...)` call
repointed at [Ticket 03](03-rewrite-cross-store-joins-and-repoint-callers.md)'s
new `bookkeeping.get_all_company_sync_states()` instead of DuckDB.

**Important correction to how this was first read (from the original
ticket):** `pipeline.py`'s existing `try`/`except` around its fetch, with
its comment about `MDM_SILVER_READ_TARGET=snowflake` degrading
`tracking_by_cik` to empty, is **not** a working solution to copy — it's a
documented silent correctness-loss path (every company resolves with
`tracking = None`). This degrade path is not live in prod today:
`MDM_SILVER_READ_TARGET` defaults to `"duckdb"` (`mdm/cli.py:698`), and
flipping it to `snowflake` is explicitly gated behind a not-yet-passed
correctness gate elsewhere in that file. But repointing this call makes the
*same* failure mode live under the default `duckdb` target too, not just
the not-yet-flipped `snowflake` one — `sec_company_sync_state` is leaving
DuckDB's connection entirely, regardless of which target MDM reads from.
Do not preserve or extend the silent-`None`-degrade pattern for this site;
a real fetch from the new store either succeeds or raises — treat a
`BookkeepingStore` failure as a real failure, not a silent empty-dict
fallback.

**Blocked by:** [Ticket 03](03-rewrite-cross-store-joins-and-repoint-callers.md)
(needs `get_all_company_sync_states`)

**Status:** blocked

- [ ] All 4 cross-store join sites plus `mdm/pipeline.py::run_companies`
      are rewritten to a two-step fetch-then-Python-join, each with a test
      proving it produces the same result as the original single-SQL join
      (or, for `run_companies`, the same result as the original DuckDB
      fetch) against a fixture with real overlapping and non-overlapping
      CIKs
- [ ] The silent-`None`-degrade pattern in `mdm/pipeline.py` is removed for
      `sec_company_sync_state` specifically (confirm no other table's
      degrade path in this file is accidentally touched)
- [ ] Every caller of `get_company_identity_ciks` and `compute_coverage` is
      updated to pass a `BookkeepingStore` instance, using the
      `_bookkeeping_store()` convention [Ticket 03](
      03-rewrite-cross-store-joins-and-repoint-callers.md) settled
- [ ] Full test suite green
