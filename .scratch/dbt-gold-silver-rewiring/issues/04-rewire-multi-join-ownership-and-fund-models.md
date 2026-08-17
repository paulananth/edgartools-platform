# 04 — Rewire Gold's Multi-Join Ownership and Fund Dimensional Models onto Silver

**What to build:** `ownership_activity`, `ownership_holdings`, and
`private_funds` — the three models whose current Python builders `UNION`
multiple silver tables and derive natural keys via text normalization (owner
CIK-or-name fallback, security-title normalization) — reimplemented as dbt
SQL sourcing directly from dbt silver's raw ownership/fund tables via
`ref()`. This is the real porting work in the batch: unlike Tickets 02/03,
there is no existing dbt SQL to lean on, and the natural-key derivation logic
currently lives only in Python (`_ownership_fact_source_rows`,
`_private_fund_natural_key` in `gold_models.py`) and has to be re-expressed
in SQL.

**Blocked by:** 01, 02, 03

**Status:** resolved — all 3 models rewired and hand/dbt-parse-verified; a
new environment finding (see "A harder blocker than Tickets 01-03 had"
below) means `dbt run --full-refresh` is deferred for a stronger reason
than a missing-credentials gap.

- [x] All 3 models source exclusively via `ref()` from dbt silver's
      `sec_ownership_non_derivative_txn`, `sec_ownership_derivative_txn`,
      `sec_ownership_reporting_owner`, `sec_adv_private_fund`, and
      `sec_adv_filing` models
- [~] The owner natural-key fallback (CIK when present, else normalized name)
      and security-title normalization logic produce identical output to
      today's Python builder — checked line-by-line against the Python
      builder and covered by 3 new dbt unit tests with literal expected
      values computed live (not guessed), but "for every existing row" is
      not actually established: the unit tests are synthetic fixture rows
      (a handful of edge cases per model), not `dbt test` executed against
      real data, and `dbt test` itself has not been run (see "Verification
      performed, and its limit" below) — downgraded from `[x]` after the
      Spec-axis code review caught this checkbox overclaiming its own
      evidence.
- [~] The cutover validation standard passes at real scale — this batch
      supplies the map's required large-table case (ownership data is one of
      the platform's higher-volume tables). Not run: `EDGARTOOLS_PROD` does
      not exist in the account `edgartools-prod` currently resolves to (see
      below), so there is no real-scale data anywhere to reconcile against
      right now, independent of this ticket's own work.
- [ ] `dbt run --full-refresh` succeeds for each model against prod — not
      attempted; see below.

## Answer

**All 3 models rewired**, in
`infra/snowflake/dbt/edgartools_gold/models/gold/{ownership_activity,ownership_holdings,private_funds}.sql`,
sourcing via `ref()` from dbt silver instead of the
`source("edgartools_source", ...)` mirror. Ported directly from
`gold_models.py`'s `_build_fact_ownership_transaction`,
`_build_fact_ownership_holding_snapshot`, and `_build_fact_adv_private_fund`
— the three Python builders whose natural-key derivation only ever lived in
DuckDB SQL/Python, with no existing dbt SQL to lean on (unlike Tickets
02/03).

**`ownership_activity.sql`** (`fact_ownership_transaction`): `UNION ALL` of
`sec_ownership_non_derivative_txn`/`sec_ownership_derivative_txn`, each
joined to `sec_company_filing` (inner — a row with no filing match is
dropped, matching the original `JOIN`) and left-joined to
`sec_ownership_reporting_owner` on `(accession_number, owner_index)`.
`fact_key` = `surrogate_key(['accession_number', 'owner_index', 'txn_index',
"case when is_derivative then 'D' else 'N' end"])` — Ticket 01's multi-arg
form, not string concatenation; the original DuckDB code concatenated a
`'|'`-joined string before hashing, but Ticket 01 already decided key
values reset during cutover, so byte-identical reproduction isn't a
requirement and the multi-arg form matches every other model in this batch
(`adviser_disclosures.sql`'s `'disclosure'` discriminator, etc.). `party_key`
= `'cik:<owner_cik>'` when `owner_cik` is present, else `'name:<normalized
owner_name>'`, else NULL — the CIK-vs-name *prefix* distinguishes a
CIK-shaped natural key from a name that happens to look like one; this
is presence of `owner_cik`, not truthiness, matching
`_party_natural_key`'s `cik is not None` check exactly. `security_key` =
`'<company_key or 0>|<normalized security_title>'`, NULL when the title has
no real content. `ownership_txn_type_key` = hash of the transaction code
after trim/collapse-whitespace — **deliberately not run through
`normalized_text()`**: that macro lowercases, and transaction codes (`P`,
`S`, `A`, ...) are case-significant single letters in the original DuckDB
SQL (`NULLIF(trim(regexp_replace(...)), '')`, no `lower()`). Using
`normalized_text()` here would have silently lowercased every transaction
code — caught before writing the model, not by a reviewer.

**`ownership_holdings.sql`** (`fact_ownership_holding_snapshot`): same
`UNION ALL`/join shape, but collapses to one row per "holding group"
(`accession_number, owner_index, security, direct/indirect`), keeping only
the most recent transaction — `qualify row_number() over (partition by
accession_number, owner_index, security_nk, di_clean order by
coalesce(txn_index, 0) desc, case when is_derivative then 1 else 0 end
desc) = 1`, reproducing the Python builder's own tie-break exactly
(txn_index wins; a tie at the same txn_index prefers the derivative row).
A `where` pre-filter drops any candidate row with no real `security_title`
(after normalizing) or a NULL `shares_owned_after` — matching the Python
builder's own filter, **minus** its second condition (`CAST(shares_owned_after
AS VARCHAR) != ''`), which was DuckDB-specific defensiveness against a
string-typed column; confirmed live in
`infra/snowflake/sql/bootstrap/11_silver_landing_schema.sql` that
`shares_owned_after` is `NUMBER(28,8)` in the Snowflake landing zone (a
numeric column can never literally equal `''`), so dropping that second
condition changes nothing. Unlike `ownership_activity.sql`'s optional
`security_key`, `security_key` here is never NULL by construction — the
`where` filter already requires a real `security_title` before a row
reaches the final `select`.

**`private_funds.sql`** (`fact_adv_private_fund`): `sec_adv_private_fund`
left-joined to `sec_adv_filing` and `sec_company_filing` for cik/date
resolution — same `COALESCE(f.cik, c.cik)` / `COALESCE(c.filing_date,
f.effective_date)` shape as `adviser_disclosures.sql`/`adviser_offices.sql`
(Ticket 03). `private_fund_key` is the one genuinely new derivation in this
batch: a **4-field composite** natural key (`<company_key or
0>|<normalized fund_name>|<normalized fund_type>|<normalized
jurisdiction>`), NULL only when **all four** inputs are absent — not a
single-field NULL-if-empty guard like `disclosure_category_key`. Matches
`_private_fund_natural_key`'s `if not any((issuer is not None, name,
fund_type_value, jurisdiction_value))` check exactly: the `cik`/`issuer`
component is a presence check (`is not None`), so a private-fund row with a
resolved `cik` but no `fund_name`/`fund_type`/`jurisdiction` at all still
gets a real, non-NULL `private_fund_key` — pinned by unit test row 2 below.

**Verification performed, and its limit:**
- `dbt parse --no-partial-parse` (with dummy `DBT_SNOWFLAKE_*` env vars —
  parse resolves `ref()` targets and expands every macro without needing a
  live connection) succeeds cleanly on all three models plus the three new
  unit test files. Re-confirmed genuinely validating, not just "no syntax
  error," via Ticket 01's typo-and-revert method: temporarily changed
  `private_funds.sql`'s `ref('sec_adv_private_fund')` to a nonexistent
  name, confirmed `dbt parse` fails with "depends on a node named
  'sec_adv_private_fund_TYPO' which was not found," then reverted.
- Three new dbt unit tests
  (`_ownership_activity_unit_tests.yml`, `_ownership_holdings_unit_tests.yml`,
  `_private_funds_unit_tests.yml`) cover the join/coalesce/normalization/
  tie-break logic with literal `fact_key`/`party_key`/`security_key`/
  `ownership_txn_type_key`/`private_fund_key`/`date_key` values computed
  live (`HASH`/`BITAND`/`YEAR`/`MONTH`/`DAY` against a real Snowflake
  session — see below for which account), not guessed. Each test's edge
  cases: `ownership_activity` — CIK-present-wins-over-name, name-fallback,
  and a reporting-owner LEFT JOIN miss that nulls out `owner_index`/
  `owner_cik`/`owner_name` together (an existing behavior of the Python
  builder being faithfully reproduced, not a new gap — the original
  selects `o.owner_index`, not `t.owner_index`, so an unmatched owner row
  loses the txn's own owner_index too); `ownership_holdings` — the
  highest-txn_index-wins collapse, a same-txn_index derivative-vs-non-
  derivative tie-break, and two rows that must be dropped entirely by the
  pre-filter (whitespace-only `security_title`, NULL `shares_owned_after`)
  and therefore must NOT appear in `expect.rows` at all; `private_funds` —
  differing cik/date precedence across the two joined sides, a
  cik-present-but-no-text-fields row (non-NULL key), and an
  everything-absent row (NULL key, but `fact_key` still derives cleanly).

**A harder blocker than Tickets 01-03 had — found while trying to verify
row counts before writing unit-test fixtures:** `edgartools-prod` (and
`snowconn`) in this session's `~/.snowflake/connections.toml` currently
resolve to Snowflake organization/account `PRJEDJU`/`QJB05385` — **not**
the `XCPCLKF`/`KB19989` account this repo's other docs (CLAUDE.md, Tickets
01-03's own Answers, the 2026-07-27 "Dev Terraform/Snowflake go-live
blockers" 5-whys) describe as the platform's real, populated Snowflake
account. `SHOW DATABASES` on this connection returns only Snowflake's own
system databases (`SNOWFLAKE`, `SNOWFLAKE_SAMPLE_DATA`,
`SNOWFLAKE_LEARNING_DB`, a personal database, plus the `NEO4J_GRAPH_ANALYTICS`
native app) — no `EDGARTOOLS_PROD`. `SHOW ROLES LIKE 'EDGARTOOLS%'` returns
zero rows. This is consistent with a separate, in-flight effort (the
`snowflake-env-provisioning` wayfinder map) having repointed
`connections.toml` at a freshly-provisioned, not-yet-installed Snowflake
account — **not** a regression in this ticket's own work, and not
something this ticket should try to fix (provisioning that account is a
different workstream's job). Two consequences for this ticket specifically:
  1. The account-agnostic parts of verification (dbt parse's `ref()`
     resolution, and `HASH`/`BITAND`/`YEAR`/`MONTH`/`DAY`/`REGEXP_REPLACE`
     literal computation for the unit tests) are unaffected — those
     behave identically in any Snowflake account regardless of which
     database holds data, and were run for real against this account.
  2. Anything that needs real `EDGARTOOLS_SILVER`/`EDGARTOOLS_SOURCE` data
     (the Table-Specific Reconciliation digest comparison, `dbt
     test`/`dbt run --full-refresh` themselves) cannot be attempted at
     all right now — not "deferred pending credentials" as in Tickets
     01-03, but genuinely blocked on an account that doesn't have the
     schema, roles, or warehouse this repo's `profiles.yml` (`prod`
     target: role `EDGARTOOLS_PROD_LOADER`, warehouse
     `EDGARTOOLS_PROD_REFRESH_WH`) expects to exist.
- **Not run, and not attempted:** `dbt test`, `dbt run --full-refresh`.
  Whoever resolves the `snowflake-env-provisioning` map (or otherwise
  restores `edgartools-prod` to a populated account) should, in order:
  (1) confirm `EDGARTOOLS_SILVER`'s ownership tables
  (`sec_ownership_non_derivative_txn`, `sec_ownership_derivative_txn`,
  `sec_ownership_reporting_owner`) and `sec_adv_private_fund` are populated
  — do not trust a stale claim that they already are; re-verify live, the
  same lesson this repo's own INSTITUTIONAL_HOLDS/EMPLOYED_BY 5-whys
  documents, (2) run `dbt test --select ownership_activity
  ownership_holdings private_funds` to confirm the three new unit tests
  actually pass, (3) run `dbt run --full-refresh` for all three models,
  (4) extend `ticket02_gold_silver_cutover_reconciliation.sql` (or run an
  equivalent digest check) to cover these three tables at real scale —
  this batch is the map's designated large-table case and that check has
  not been performed for it yet, by either Ticket 03 (which also deferred
  its own extension of that script) or this ticket.
