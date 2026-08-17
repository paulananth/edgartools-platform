# 03 — Rewire Gold's Single-Source Dimensional Models onto Silver

**What to build:** `company`, `filing_activity`, `filing_detail`,
`adviser_disclosures`, `adviser_offices`, `earnings_releases`,
`guidance_facts`, and `executive_records` read from dbt silver via `ref()`,
including whatever light joins and surrogate-key derivation each currently
performs in its Python builder (typically one source table, a hashed key
column, and — for `company` specifically — its existing left join onto the
MDM golden-record company entity, which stays exactly as-is).

**Blocked by:** 01, 02

**Status:** resolved — all 8 models rewired, macros/joins/key derivations
hand-verified live against prod Snowflake. `dbt run --full-refresh` is
deliberately **not** run yet — see the live blocker documented below, which
is a stronger reason than "no credentials" this time.

- [x] All 8 models source exclusively via `ref()` from dbt silver, using
      Ticket 01's key macro for any hash-derived key column (`filing_key`,
      `form_key`, `fact_key`, etc.)
- [~] The cutover validation standard passes for each table, including
      `company.sql`'s MDM entity enrichment join (`has_multi_match_mdm_entity`
      flag and all) producing identical output to today — every model's SQL
      was hand-rendered and run live against prod Snowflake (real
      verification, not just `dbt parse`), and two new dbt unit tests cover
      the trickiest derived logic with live-computed literals. What's
      *not* done: a Table-Specific Reconciliation digest comparison
      against real data, because `EDGARTOOLS_SILVER` is currently empty in
      prod (see below) — there is no "new" content yet to reconcile
      against the old path's real output.
- [ ] `dbt run --full-refresh` succeeds for each model against prod — not
      attempted. See "A live blocker found, not caused, by this ticket"
      below for why this is deliberate, not just a credentials gap.

## Answer

**All 8 models rewired.** Five source columns needed no hash macro at all —
`company_key` is always literally `cik` (an identity, never a hash, in
every one of the eight Python builders read for this ticket), and
`date_key`/`filing_date_key`/`period_end_date_key`/`fiscal_year_date_key`
are plain YYYYMMDD (or YYYYMMDD-shaped) integer arithmetic, not hashes —
factored into a new `date_key()` macro
(`infra/snowflake/dbt/edgartools_gold/macros/date_key.sql`) reused across
five of the eight models rather than repeating the arithmetic inline
everywhere. `surrogate_key()` (Ticket 01) is used for every genuinely
hash-derived column: `filing_key`/`fact_key` (`company.sql` needs none;
`filing_activity.sql`/`filing_detail.sql` both hash `accession_number`;
`executive_records.sql` hashes `accession_number, exec_name`;
`earnings_releases.sql` hashes `accession_number` for `fact_key` and the
*literal constant* `'8-K'` for `form_key`, since every row in that table is
by definition an 8-K), `form_key` (`hash(form)`, see the HASH(NULL) finding
below), `disclosure_category_key`/`geography_key` (new `normalized_text()`
macro, see below).

**`guidance_facts` needed no key derivation at all** — genuinely different
from the other seven. `edgar_warehouse.explore.guidance_facts.guidance_fact_key()`
computes `fact_key`/`company_key` once, in Python, at silver-write time,
and stores them as durable columns in `sec_guidance_fact`'s own DDL — not
recomputed by DuckDB SQL at gold-build time in the old architecture either.

**Not a pure passthrough, though — a real Spec-axis review finding, fixed
before commit:** my first draft claimed "swap `source()` for `ref()`,
nothing else," which was wrong. `_build_fact_guidance` (the Python builder
this replaces) applies `NULLIF(accession_number, '')` — silver's
`sec_guidance_fact` stores `''`, not `NULL`, for `firm_manual` rows (a
`NOT NULL DEFAULT ''` primary-key column in `silver_store.py`'s DDL), and
gold has always translated it back to the documented nullable column. My
rewrite dropped that translation, which would have surfaced
`accession_number = ''` instead of `NULL` for every `firm_manual` guidance
row — a real behavioral regression the "hand-render and run live" checks
never caught, because `EDGARTOOLS_SILVER` is empty right now so an
empty-vs-`''`-vs-`NULL` difference produced no visible signal either way.
Fixed by adding `NULLIF(accession_number, '')` back to the final `SELECT`,
confirmed live that `NULLIF('', '')` returns `NULL` while `NULLIF('0001',
'')` returns `'0001'`.

**`adviser_disclosures`/`adviser_offices` are the two genuinely new-logic
cases**, each joining `sec_adv_office`/`sec_adv_disclosure_event` to
`sec_adv_filing` and `sec_company_filing` (`COALESCE(f.cik, c.cik)` /
`COALESCE(c.filing_date, f.effective_date)`, exactly matching
`_build_fact_adv_office`/`_build_fact_adv_disclosure` in `gold_models.py`)
and normalizing free-text natural keys before hashing them. New
`normalized_text()` macro
(`infra/snowflake/dbt/edgartools_gold/macros/normalized_text.sql`) ports
`gold_models.py`'s `_normalized_text()` (collapse whitespace, trim, lower)
plus the "empty after normalizing means absent" check every call site
applied before hashing (`if normalized_category else None`), folded into
one `NULLIF(..., '')` so the macro itself returns NULL rather than `''`.
`geography_key` differs from `disclosure_category_key` in one respect:
`_geography_natural_key` only returns `None` when **both** `state` and
`country` are empty (not either), so `geography_key` hashes the pair of
normalized columns directly (`surrogate_key()`'s multi-arg form) rather
than a single normalized value, guarded by its own explicit
both-null-then-null `CASE`.

**A Standards-axis review finding, fixed before commit:** the macro's own
doc-comment originally claimed "callers wrap this directly in
`surrogate_key()` without a separate emptiness check" — false, and
self-contradicting against the very code three lines below it, which does
add an explicit `CASE WHEN normalized_category IS NULL THEN NULL ELSE
surrogate_key(...) END` guard at both call sites. The claim would have
been actively wrong to follow: per the `HASH(NULL)`-is-nonzero finding
below, skipping the guard and passing NULL straight into `surrogate_key()`
would silently hash a NULL into a bogus nonzero key instead of correctly
propagating "no natural key value." Corrected the doc-comment to state the
guard is required, not optional.

**A real bug caught and fixed before commit, not by a reviewer:**
`filing_activity.sql`/`filing_detail.sql`'s first draft used
`COALESCE(surrogate_key(['form']), 0)`, mirroring the original DuckDB code's
`COALESCE((hash(form) & mask)::BIGINT, 0)`. Confirmed live
(`snow sql --connection edgartools-prod`) that **Snowflake's `HASH(NULL)`
does not return `NULL`** — it returns a real, deterministic, nonzero value
(`8817975702393619368` for `HASH(NULL::VARCHAR)`) — unlike DuckDB's, which
the original code relied on propagating to `NULL` so `COALESCE` could
substitute `0`. The `COALESCE` was dead code in Snowflake: every null-form
row would have silently gotten a nonzero, arbitrary-looking `form_key`
instead of the intended `0` sentinel for "no form" — indistinguishable from
a real form's key to any downstream consumer, and a behavior change nobody
asked for. Fixed both models to `CASE WHEN form IS NULL THEN 0 ELSE
{{ surrogate_key(['form']) }} END`, which checks the real column instead of
relying on hash-null propagation, confirmed correct live.

**A live blocker found, not caused, by this ticket:** running the new
`ticket02_gold_silver_cutover_reconciliation.sql` script for real (I have
live `snow sql --connection edgartools-prod` access this session — see
below) revealed `EDGARTOOLS_SILVER.SEC_COMPANY`,
`EDGARTOOLS_SILVER.SEC_COMPANY_FILING`, and every other silver table these
eight models now `ref()` are **currently empty** in prod
(`EDGARTOOLS_SILVER_LANDING.SEC_COMPANY` is also 0 rows — the gap is
upstream of dbt, not in dbt). `SHOW TASKS LIKE 'LOAD_SILVER_LANDING_TASK'`
confirms the task's current `state` is `started` but its
`last_suspended_reason` is `SUSPENDED_DUE_TO_ERRORS` — this is the exact,
already-tracked `EDGARTOOLS_SILVER empty in prod` blocker this session's
own task list has open (task #147, with #155 actively verifying a fix).
**This is a load-bearing reason to not run `dbt run --full-refresh` right
now even independent of credentials**: doing so today would deploy
syntactically-correct dynamic tables that read real, empty data, silently
replacing the currently-working `EDGARTOOLS_SOURCE`-backed gold output with
empty tables — a self-inflicted production incident. `dbt run
--full-refresh` for these eight models should wait until #147/#155 confirm
`EDGARTOOLS_SILVER_LANDING` (and therefore `EDGARTOOLS_SILVER`) is actually
receiving rows again.

**Verification performed, and its limit — a stronger story than Tickets
01/02, because `snow sql --connection edgartools-prod` (a pre-configured
SnowCLI connection, distinct from dbt's own `DBT_SNOWFLAKE_*` credentials)
turned out to be available this session:**
- `dbt parse --no-partial-parse` succeeds cleanly on every edit, and was
  re-confirmed to genuinely validate `ref()` targets (Ticket 01's
  typo-and-revert method, reused here).
- Every one of the eight models' actual SQL body was hand-rendered (Jinja
  macro calls expanded to their literal SQL by hand, since dbt itself
  wouldn't render them without full dbt credentials) and run directly
  against live prod Snowflake — all eight executed with **zero errors**
  (only "no data," matching the confirmed-empty upstream). This is real
  confirmation that every join resolves, every type checks out, and
  `HASH`/`BITAND`/`YEAR`/`MONTH`/`DAY` all behave as expected in this
  account — not merely that the Jinja is syntactically valid.
- Two new dbt unit tests (`_adviser_disclosures_unit_tests.yml`,
  `_adviser_offices_unit_tests.yml`) cover the join/coalesce/normalization
  logic with literal `fact_key`/`disclosure_category_key`/`geography_key`/
  `date_key` values computed live, not guessed — including both edge cases
  (`sec_company_filing` match present vs. absent; category/geography
  present vs. entirely empty). `_filing_activity_unit_tests.yml` (Ticket
  01's pilot) was updated for the new `ref()` source and to prove
  `fact_key`/`filing_key` come out numerically equal, as they did before.
  Both new unit tests' `expect.rows` entries specify every output column
  explicitly (rather than relying on dbt's default-comparison behavior for
  omitted columns, which was never independently confirmed this session)
  to avoid a silent false-pass. `_filing_activity_unit_tests.yml` does
  **not** follow this fully — it's Ticket 01's original test, carried
  forward with only its `given.input` and added `filing_date` column
  changed, and still asserts only 3 of `filing_activity`'s 11 output
  columns (`accession_number`, `filing_key`, `fact_key`) per row, not all
  11. Not fixed here — a Spec-axis review finding this session chose not
  to act on, since widening Ticket 01's test is out of this ticket's own
  scope and the 3-column assertion is still correct as far as it goes.
- **Still not run:** `dbt test`/`dbt run --full-refresh` themselves — this
  session still has no `DBT_SNOWFLAKE_PASSWORD`/`DBT_SNOWFLAKE_ACCOUNT`,
  and per established practice those are not extracted or requested here,
  even though the separate `snow sql` connection happens to be available.
  Whoever has dbt prod credentials should, in order: (1) confirm
  `EDGARTOOLS_SILVER` is populated (resolve #147/#155 first, or this
  ticket's own concern above repeats), (2) run `dbt test --select
  filing_activity adviser_disclosures adviser_offices` to confirm the new
  unit tests actually pass (not just that their literals were computed
  correctly by hand), (3) run `dbt run --full-refresh` for all eight
  models, (4) re-run `ticket02_gold_silver_cutover_reconciliation.sql`
  (extend it to cover these eight tables, or run an equivalent check) to
  confirm real non-empty digests match on business-key content.

## Closing note (2026-08-17, added while implementing Ticket 04)

**Ticket 03 is closed as resolved with its one remaining checkbox
(`dbt run --full-refresh` against prod) still unchecked — do not check it
retroactively.** While implementing Ticket 04, `edgartools-prod` (and
`snowconn`) in this session's `~/.snowflake/connections.toml` were found to
resolve to Snowflake organization/account `PRJEDJU`/`QJB05385` — a
freshly-provisioned account with zero `EDGARTOOLS`-prefixed databases or
roles (`SHOW DATABASES` returns only Snowflake's own system databases;
`SHOW ROLES LIKE 'EDGARTOOLS%'` returns zero rows) — **not** the
`XCPCLKF`/`KB19989` account this ticket's own Answer above, and the rest of
this repo's docs, describe as the platform's real, populated Snowflake
account. This is a harder gap than the one this ticket originally
documented ("no dbt prod credentials in the implementing session"): even a
session *with* full `DBT_SNOWFLAKE_*` credentials cannot run `dbt run
--full-refresh` right now, because the target account has no
`EDGARTOOLS_SILVER` schema, no `EDGARTOOLS_PROD_LOADER` role, and no
`EDGARTOOLS_PROD_REFRESH_WH` warehouse for `profiles.yml`'s `prod` target
to resolve. This is not a regression caused by this ticket or Ticket 04 —
it's consistent with a separate, in-flight effort (the
`snowflake-env-provisioning` wayfinder map) having repointed
`connections.toml` at a not-yet-installed account. See Ticket 04's Answer
for the same finding recorded in more detail, including which parts of
verification remain account-agnostic (dbt parse, and literal
`HASH`/`BITAND`/date-arithmetic computation) and were still performed for
real against this new account. Whoever resolves the
`snowflake-env-provisioning` map (or otherwise restores `edgartools-prod`
to a populated account) should complete this ticket's deferred step-4 list
above before checking that last box.
