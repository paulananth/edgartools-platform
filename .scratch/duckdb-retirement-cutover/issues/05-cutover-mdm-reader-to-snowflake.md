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
- [x] MDM reads authenticate via `EDGARTOOLS_PROD_LOADER`'s secondary role
      (no new dedicated role provisioned). **2026-09-01, closed in two
      passes:** first ran the additive GRANT this bullet already specified
      (`GRANT ROLE EDGARTOOLS_PROD_MDM_SILVER_READER TO ROLE
      EDGARTOOLS_PROD_LOADER`), confirmed live — but that alone didn't
      close the bullet, since the secret's `MDM_SNOWFLAKE_ROLE` field was
      still `ACCOUNTADMIN`. Before flipping it (explicit user go-ahead),
      checked the actual risk the ticket flagged rather than assuming it
      away: `SHOW GRANTS TO ROLE EDGARTOOLS_PROD_LOADER` found a real,
      confirmed gap — only bare `SELECT` on `EDGARTOOLS_GOLD.
      MDM_COMPANY_ENTITY`, **zero** grants on `MDM_ADVISER`/`MDM_PERSON`/
      `MDM_SECURITY`/`MDM_FUND` (the other 4 tables `mdm export`'s default
      writer `MERGE`s into) — confirmed via `describe-state-machine` that
      `daily_incremental`'s `MdmExport` state has no `Catch`, so this gap
      would have failed the whole pipeline on the next export, not
      degraded gracefully like `MdmVerify` does. Granted the missing
      `INSERT`/`UPDATE`/`DELETE` on all 5 tables (additive, matches this
      repo's established grant pattern) *before* rotating, then rotated
      `MDM_SNOWFLAKE_ROLE` → `EDGARTOOLS_PROD_LOADER` (every other secret
      field preserved byte-for-byte, piped directly between
      `get-secret-value`/`put-secret-value`, never printed). Verified live
      with a real no-op `MERGE` smoke test against all 5 export tables
      under the new role (`CURRENT_ROLE()` confirmed `EDGARTOOLS_PROD_LOADER`,
      zero rows written) before letting anything depend on it.
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
      degrades to a payload field, not a crash) — **run against real prod
      data 2026-09-01 (below); still `[ ]`, does not pass, and the gate
      itself had a scope-confusion defect on top of a real, larger
      finding.** **2026-09-01, second pass: fixed the gate's own defect.**
      `RowParityResult` gained a `missing_keys` field, distinct from
      `mismatched_keys` — the loop in `verify_resolver_input_parity` now
      routes "row absent on the other side" into `missing_keys` and
      reserves `mismatched_keys` for "row present on both sides but content
      genuinely differs" (previously both were folded into one list, which
      is why the live prod run below reported a misleading 100% mismatch
      rate). `matches`/`passed` still fail on either category — a coverage
      gap is not silently waved through, only correctly labeled — so this
      fix does not, by itself, flip the gate to passing against current
      prod data; it only makes the failure it reports honest. Two new tests
      lock in the fix: a payload-shape test asserting
      `missing_keys_total`/`missing_keys_sample` are separate JSON fields
      from `mismatched_keys_total`/`mismatched_keys_sample`, and a
      dedicated "scope divergence alone does not masquerade as content
      corruption" test proving a sample where every genuinely-overlapping
      row is byte-identical reports zero content mismatches (only
      missingness) rather than the old blanket conflation. The pre-existing
      `test_row_missing_on_one_side_is_a_mismatch` test was updated in
      place (renamed, same coverage) to assert the row lands in
      `missing_keys`, not `mismatched_keys` — preserving its original
      intent (a missing row still fails the check) while fixing what it
      actually verified. 11/11 parity tests pass; full `tests/mdm/` suite
      (609 tests) and this file's test still pass unchanged. Not re-run
      against live prod in this pass — the fix changes only how the
      failure is labeled, and this session's earlier live run already
      recorded the real, correctly-interpreted picture by hand (isolating
      genuinely-overlapping rows directly); a fresh live run would just
      reproduce the same failure with better labels, not new information,
      so it's deferred to the natural re-run this ticket already has
      pending (after Ticket 15's backfill closes the coverage gap).
      Per this map's own "Decide the Cutover Validation
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

**2026-09-01: `verify-resolver-input-parity` and `verify-silver-parity` run
live against real prod data — both fail, and the underlying finding is
serious enough to flag prominently rather than bury in a checklist.**

Setup: downloaded the current canonical `warehouse/silver/sec/silver.duckdb`
(1.7 GiB, read-only `aws s3 cp`, no staging/promotion) to local scratch,
pointed `MDM_SILVER_DUCKDB` at it directly (deliberately did **not** set
`WAREHOUSE_STORAGE_ROOT`, to avoid `_duckdb_silver_reader()`'s remote-mode
branch picking up the stale, Ticket-06-orphaned `shard-manifest.json`/
`shard-*.duckdb` objects still sitting in S3, last written 2026-08-20 —
using those instead of the current monolith would have silently compared
against 11-day-stale data). Connected to Snowflake as `ANANP11` (who
already independently holds `EDGARTOOLS_PROD_MDM_SILVER_READER`, so this
predates and doesn't depend on the GRANT above).

`mdm verify-resolver-input-parity`: exit 1, every entity type
(company/adviser/fund/person/security) reported 100% mismatch on every
sampled key. **That 100% figure is partly a defect in the gate itself, not
purely a data finding**: `_sample_keys` draws its lowest/highest-N sample
from *each reader independently*, then `_fetch_row_by_key` looks the other
side's keys up on the opposite reader — under any universe-scope
divergence (see below), a DuckDB-sampled key that doesn't exist at all in
Snowflake returns `None`, and `None != real row` is counted as a content
mismatch. The gate conflates "row absent" with "row differs" and cannot
report a clean pass under scope divergence even if every truly-overlapping
row is byte-identical. Confirmed directly: DuckDB's lowest `sec_company`
CIKs (1750, 1800, 1961...) don't exist in Snowflake at all (Snowflake's
lowest is 2488) — so most of the sample never had a chance to compare
content in the first place.

Isolating genuinely overlapping rows (same key present on both sides) tells
a clearer story:
- `sec_company` CIK 2488 and CIK 2152204 (both present on both sides): the
  **only** field-level differences are `first_sync_run_id`,
  `last_sync_run_id`, `last_synced_at` — populated in DuckDB, `NULL` on
  every Snowflake row checked. These are bookkeeping/provenance columns,
  not core business content (name/address/etc. matched) — a real, but
  narrow, systematic gap in what the landing export carries for this
  table, not evidence of resolution-relevant business-data corruption.
- `sec_ownership_non_derivative_txn` (the `security` entity type's large
  table): **no overlapping key found at all** in a 2000-row sample from
  each side's tail. Row counts explain why: DuckDB has 78,096 rows,
  Snowflake has **36**.

`mdm verify-silver-parity` (the sibling row-count-only check, all 31
`PARITY_TABLES`) makes the scope of the gap unambiguous — it is not
confined to one table:

| table | duckdb | snowflake | coverage |
|---|---:|---:|---:|
| sec_company_ticker | 21,360 | 20,846 | 97.6% |
| sec_company_submission_file | 3,950 | 927 | 23.5% |
| sec_company_filing | 6,398,260 | 1,121,332 | 17.5% |
| sec_employment_event | 7,379 | 1,529 | 20.7% |
| sec_company | 52,778 | 7,625 | 14.4% |
| sec_company_address | 105,556 | 15,250 | 14.4% |
| sec_company_former_name | 12,689 | 1,749 | 13.8% |
| sec_filing_attachment | 420,010 | 5,068 | 1.2% |
| sec_ownership_reporting_owner | 58,715 | 44 | 0.1% |
| sec_adv_filing | 58,599 | 0 | 0.0% |
| sec_adv_firm_roster | 23,622 | 0 | 0.0% |
| sec_adv_private_fund | 394,969 | 0 | 0.0% |
| sec_earnings_release | 918 | 0 | 0.0% |
| sec_executive_record | 14,755 | 0 | 0.0% |
| sec_financial_derived | 5,056 | 0 | 0.0% |
| sec_financial_fact | 434,805 | 0 | 0.0% |
| sec_ownership_derivative_txn | 2,969 | 1 | 0.0% |
| sec_ownership_non_derivative_txn | 78,096 | 36 | 0.0% |
| sec_raw_object | 355,792 | 107 | 0.0% |
| sec_thirteenf_filing | 14,364 | 0 | 0.0% |
| sec_thirteenf_holding | 6,799,919 | 0 | 0.0% |
| (11 more tables) | 0 | 0 | n/a (both empty) |

Only company/ticker-family tables have meaningful coverage. Every ADV,
13F, ownership-transaction, financial-fact, and executive-record table is
at or near 0%. Not checked in this pass (deliberately, per the "don't fix
anything" boundary below): whether this is legitimate tracked-universe
export scoping (`edgar_warehouse/serving/silver_landing_export.py` has no
CIK-filtering logic itself — it's a row-recording hook for whatever the
write path already writes — so this looks less like deliberate scoping and
more like the landing/dbt-collapse pipeline genuinely not having caught up
for most tables) versus a real ingestion gap.

**Why this matters beyond this ticket's own checklist**: this ticket's own
"hard cutover, no transition window" already made MDM's production
resolvers read *exclusively* from `EDGARTOOLS_SILVER` (Snowflake) as of
commit `4c5de1aa`, merged and live. If ADV/13F/ownership-transaction tables
are genuinely near-empty in the table MDM now reads exclusively, then
production MDM entity/relationship resolution for everything besides basic
company identity has likely been resolving against a near-empty source
since that cutover shipped — not a hypothetical, a live state.

**Deliberately not investigated or fixed in this pass** (per explicit
scope discipline, not an oversight): whether 0% is a genuine ingestion gap
versus intentional scoping; the `_sample_keys`/`_fetch_row_by_key`
absent-vs-differs conflation in the parity gate itself; and any actual
data/pipeline remediation. All three are real, but none belongs inside
"cut over the reader class" — they're a data-completeness/architecture
question the user needs to weigh in on, most likely as its own ticket. The
checklist bullet above stays `[ ]`: the gate ran, it failed, and — even
setting the gate's own absent-vs-differs defect aside — the underlying
`verify-silver-parity` row-count comparison independently confirms real,
severe non-parity that no interpretation of "expected type drift" can
explain away.
