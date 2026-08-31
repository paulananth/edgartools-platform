# 05 — Cut Over MDM's `ShardedSilverReader` to Snowflake

**What to build:** DuckDB Retirement's Ticket 02 decided this is a hard
cutover, no transition window: `ShardedSilverReader` (`edgar_warehouse/
silver_support/sharded_reader.py`) is replaced at all 6 call sites by a
Snowflake-backed implementation of the same minimal `SilverReader` Protocol
(`edgar_warehouse/mdm/resolvers/base.py:19`) — confirmed zero DuckDB-dialect
SQL in any MDM silver-read query, so this is a storage-target swap, not a
query rewrite.

Credential activation: reuse the existing shared `EDGARTOOLS_PROD_LOADER`
secret as a secondary role for MDM's reads, rather than provisioning a
dedicated reader role — the operator's explicit choice, knowingly
reintroducing some write-role read overlap (Ticket 02's answer).

"Resolution matches" for the new reader means Ticket 07's row-level digest
standard (wayfinder decision, not this ticket set's own Ticket 09 below) — same
match decision and confidence score per input row as the old DuckDB-backed
reader produced, not identical `entity_id` values (entity IDs are assigned
independently per resolver run and aren't expected to be byte-identical).

**Blocked by:** None — can start immediately.

**Status:** code complete (2026-08-31); one live-verification step still open

- [x] All 6 call sites of `ShardedSilverReader` now use the new
      Snowflake-backed `SilverReader` implementation. Scope discovery: much
      of the mechanism already existed (`SnowflakeSilverReader`,
      `MDM_SILVER_READ_TARGET` toggle, `verify-silver-parity`) from the
      earlier silver-snowflake-migration map's Ticket 12, as a transition
      window — this ticket's own "hard cutover, no transition window"
      decision meant finishing that into an unconditional swap, not
      building the reader from scratch. `_silver_reader()` (the gated call
      site) now always returns `SnowflakeSilverReader.connect()` regardless
      of `MDM_SILVER_READ_TARGET`/`MDM_SILVER_DUCKDB`/`WAREHOUSE_STORAGE_ROOT`.
      `_duckdb_silver_reader()` is kept, reachable only from
      `verify-silver-parity`/the new `verify-resolver-input-parity` (below),
      which need a live DuckDB reader to compare against. The remaining 4
      direct `ShardedSilverReader(...)` constructions were all inside
      `_seed_mdm_from_silver`'s two branches (local `--silver-path` file,
      `WAREHOUSE_STORAGE_ROOT` shard-0 hydration) plus
      `_seed_mdm_from_silver_ticker_fallback` — all four reached past
      `.fetch()` into `reader._conn` (DuckDB-only), so converting them
      required rewriting those two functions onto `.fetch()`/tuple
      construction, not just swapping the reader class. `--silver-path`
      itself is deleted outright (both the CLI flag and the parameter) —
      confirmed via `deploy-aws-application.sh` that no state machine ever
      passed it; the one live prod invocation (`mdm seed-universe
      --tracking-status ... --limit ...`, the `MdmSeedUniverse` state) never
      set it either, so retiring it changes no deployed behavior. Two other
      unguarded `_silver_reader()` call sites (`_handle_coverage_report`,
      `_handle_backfill_relationships`) previously tolerated `_silver_reader()
      is None`-as-"not configured" — since `SnowflakeSilverReader.connect()`
      never returns `None` (only raises), both were rewired to catch the
      connection exception instead, preserving their original graceful-
      degradation contract (skip the silver-dependent phase, don't crash the
      whole command) rather than silently turning a pre-existing tolerance
      into a new failure mode.
- [ ] MDM reads authenticate via `EDGARTOOLS_PROD_LOADER`'s secondary role
      (no new dedicated role provisioned) — **not literally true yet, and
      deliberately not silently marked done.** Live in
      `infra/snowflake/sql/bootstrap/12_silver_schema_and_mdm_reader.sql`:
      the mechanism this bullet describes already exists and already works
      (`EDGARTOOLS_PROD_MDM_SILVER_READER` granted as a secondary role, live-
      verified 2026-08-18), but the live grant target is `ACCOUNTADMIN`, not
      `EDGARTOOLS_PROD_LOADER` — the file's own comment records that the
      connecting credential's role drifted to `ACCOUNTADMIN` at some point,
      and the `GRANT ROLE EDGARTOOLS_PROD_MDM_SILVER_READER TO ROLE
      EDGARTOOLS_PROD_LOADER` line (105) needed to match this ticket's
      literal wording is present but commented out. Applying it is a live,
      additive, idempotent Snowflake mutation — left for an operator to run
      deliberately rather than applied unilaterally in this pass:
      `snow sql --connection edgartools-prod -q "GRANT ROLE
      EDGARTOOLS_PROD_MDM_SILVER_READER TO ROLE EDGARTOOLS_PROD_LOADER;"`
      (and, separately, deciding whether to also point
      `MDM_SNOWFLAKE_SECRET_JSON`'s `ROLE` field at `EDGARTOOLS_PROD_LOADER`
      to match — out of scope here, a credential-rotation decision).
- [x] Digest-based parity tooling built and unit-tested:
      `edgar_warehouse.mdm.silver_parity.verify_resolver_input_parity`
      compares whole-row `content_hash()` digests (reusing
      `resolvers.base.content_hash` verbatim, not a bespoke normalizing
      digest — deliberately catches Snowflake-Decimal-vs-DuckDB-int type
      drift as a real mismatch, the same failure mode MDM's own
      `_skip_if_unchanged` already depends on being stable) between DuckDB
      and Snowflake for each entity type's real resolver input table(s), on
      a bounded case-selected (lowest+highest keyed rows, deduplicated)
      sample per Ticket 07's cutover validation standard — sized larger for
      the ownership transaction tables per that standard's "at least one
      genuinely large table" requirement. Wired as `mdm
      verify-resolver-input-parity` (mirrors `verify-silver-parity`'s exact
      shape: build both readers, print JSON, exit 1 on any mismatch). Proven
      against 9 unit tests using `.fetch()`-based fakes (identical rows
      pass; content/missing-row mismatches are caught and the key reported;
      the Decimal-vs-int type-drift case explicitly proven NOT to be
      normalized away; large-table sample sizing; missing-table error
      degrades to a payload field, not a crash) — **not yet run against
      real prod data.** Per this map's own "Decide the Cutover Validation
      Standard" sign-off shape ("automated fail-closed assertion gates a
      required human approval, neither alone"): this command is that
      assertion, but running it against prod and having an operator approve
      the result is a deploy-time step, not something an autonomous
      implementation session should perform unattended against production
      credentials. Evidence command:
      `edgar-warehouse mdm verify-resolver-input-parity` (needs
      `MDM_SILVER_DUCKDB` and the usual `MDM_SNOWFLAKE_*`/`DBT_SNOWFLAKE_*`
      Snowflake env set).
- [x] `edgar_warehouse/silver_support/sharded_reader.py` is left in place,
      but MDM no longer references it at all post-cutover (confirmed via
      grep: zero `ShardedSilverReader` hits under `edgar_warehouse/mdm/`).
      Not deleted outright because it has one other, genuinely separate
      consumer — `silver_landing_company_backfill.py`, a one-time DuckDB→
      Snowflake-landing backfill script unrelated to MDM's read path — so
      deleting it here would break that script, not just remove an unused
      parallel path. [Ticket 12](12-duckdb-retirement-cleanup.md)'s final
      sweep is still the right place to decide that script's (and this
      module's) ultimate fate.
- [x] Full MDM test suite green: `tests/mdm/`, `tests/unit/test_sharding.py`,
      `tests/unit/test_snowflake_silver_reader.py`,
      `tests/unit/test_mdm_seed_universe_source.py`, and the new
      `tests/unit/test_resolver_input_parity.py` — 607 passed. Full repo
      suite: 2870 passed, 5 skipped, only the 8 pre-existing/unrelated
      Postgres-integration failures (real-Postgres schema drift against the
      local test DB, documented elsewhere in this repo's history) remain.
      mypy: zero new errors (5 pre-existing, unrelated, confirmed via a
      `git stash` diff against the same baseline).
