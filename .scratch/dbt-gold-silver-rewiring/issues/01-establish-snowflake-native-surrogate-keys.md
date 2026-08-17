# 01 — Establish Snowflake-Native Surrogate Keys for Gold's Hash-Keyed Dimensions

**What to build:** A single, uniformly-applied key-generation pattern (dbt
macro or equivalent) for every gold model whose surrogate key is currently
derived from DuckDB's `hash()` SQL function or Python's `hashlib.sha256` —
neither of which has a drop-in Snowflake equivalent that reproduces the same
bit values. Every later ticket in this batch (02-05) calls this one macro
instead of re-deriving a key strategy per table. Also decides and documents
whether existing key values are preserved or intentionally reset during
cutover, and who downstream (dashboard queries, MDM export joins, any
external consumer) currently depends on today's literal key values.

**Blocked by:** None — can start immediately

**Status:** resolved — design/decision complete; two criteria below are
code-complete but not yet live-verified (no dbt prod credentials in the
implementing session — see "Verification performed, and its limit" below).
Whoever has dbt prod credentials should run the two commands listed there
before treating this as fully closed.

- [x] A macro exists that deterministically derives a BIGINT surrogate key
      from one or more natural-key columns, usable identically across every
      affected model (`form_key`, `filing_key`, `fact_key`, `party_key`,
      `security_key`, `private_fund_key`, and any other hash-derived key)
- [x] Decision recorded on whether key values change during cutover, with an
      inventory of every known consumer of today's key values
- [~] The macro has a dbt unit test (or equivalent) against a representative
      natural key, confirming deterministic output — the test file exists
      and its expected literals were independently confirmed against live
      Snowflake, but `dbt test` itself has not been run (no session
      credentials); "confirming" isn't true until that runs and passes
- [~] Applied end-to-end on one pilot column (e.g. `filing_activity`'s
      `filing_key`) to prove the pattern before Tickets 02-05 apply it
      broadly — the model change is written and `dbt parse`/`dbt compile`
      succeed, but `dbt run --select filing_activity --full-refresh` has
      not been executed against prod, so the dynamic table has not actually
      redeployed with the new key yet

## Answer

**Macro:** `surrogate_key(field_list)` in
`infra/snowflake/dbt/edgartools_gold/macros/surrogate_key.sql`:

```sql
bitand(hash({{ field_list | join(', ') }}), 9223372036854775807)::bigint
```

Callers pass a Jinja list of one or more column/expression strings, e.g.
`{{ surrogate_key(['accession_number']) }}` or
`{{ surrogate_key(['accession_number', 'exec_name']) }}`, mirroring both
shapes already in use today (`hash(accession_number)` and
`hash(accession_number, exec_name)`). Note: Snowflake has no `&` bitwise-AND
operator (confirmed live — `Unknown function "&"`); the mask must use
`BITAND(...)`, not the `&` operator DuckDB/Postgres use.

**Key values change during cutover — not preserved.** Today's two
derivations (DuckDB's internal `hash()` and Python's
`hashlib.sha256(...)[:8]`-based `_det_key()`) are each a different,
undocumented-or-truncated algorithm with no byte-identical Snowflake
equivalent, so reproducing either exactly is not possible without
reimplementing DuckDB's private hash function or paying SHA2-based
complexity for no benefit. The macro standardizes on Snowflake's native
`HASH()` instead, masked to the same positive 63-bit range
(`0x7FFFFFFFFFFFFFFF`) every existing key already uses, so the BIGINT value
*range* is unchanged even though the literal values are new.

**Consumer inventory (repo-wide search for `filing_key`/`fact_key`/
`party_key`/`security_key`/`private_fund_key`/`form_key`):** no external,
persistent consumer of today's literal key values was found.
- The standalone dashboard (`examples/dashboard/edgar_universe_dashboard.py`)
  only does `count(distinct private_fund_key)` — a within-query
  cardinality count, indifferent to which literal values a dynamic-table
  refresh assigns.
- The Streamlit-in-Snowflake dashboard and MDM export/pipeline code
  (`edgar_warehouse/mdm/*.py`) reference none of these column names at all.
- No doc or script persists a key value outside a single query/refresh
  cycle. Every gold table is a dynamic table rebuilt in lockstep, so a
  hard reset at cutover is safe: nothing joins today's key value against a
  *different* refresh's key value.

**Unit test:** `models/gold/_filing_activity_unit_tests.yml`
(`filing_activity_filing_key_is_deterministic_per_accession`) — two rows
sharing one `accession_number` (differing on every other column) assert an
identical `filing_key`; a third row with a different `accession_number`
asserts a different `filing_key`. Expected literal values were computed
live against prod Snowflake (`BITAND(HASH('0001111111-26-000001'),
9223372036854775807)::BIGINT` = `5518306488236362277`, etc.) — not guessed,
since Snowflake's `HASH()` has no reference implementation to compute
offline against.

**Pilot application:** `models/gold/filing_activity.sql`'s `filing_key`
column now derives via `{{ surrogate_key(['accession_number']) }}` instead
of passing the value through from the Python-builder-exported source row.
The model's `FROM` clause is deliberately untouched (still
`source("edgartools_source", "FILING_ACTIVITY")`) — rewiring the source
itself onto Snowflake silver is Tickets 02/03's scope, not this one; this
pilot only proves the macro's SQL is valid and deployable inside a real
dynamic-table model.

**Verification performed, and its limit:** `dbt parse` succeeds cleanly
against the full project (54 models, 57 sources, 553 macros, 25 unit tests
— the new test counted). `dbt compile --select filing_activity` gets past
parsing and reaches the live-connection step (fails only on placeholder
credentials, confirming no compile-time error in the macro, model, or test
YAML). The macro's core SQL expression and both unit-test literal values
were independently confirmed by running them directly against real prod
Snowflake via the already-configured `snow sql --connection edgartools-prod`
connection. **Not yet run:** `dbt run --select filing_activity
--full-refresh` against prod (per this repo's own documented gotcha,
`dbt run` is a silent no-op on an unchanged dynamic-table config, so
`--full-refresh` is required to actually deploy this) — this session has no
`DBT_SNOWFLAKE_PASSWORD`/`DBT_SNOWFLAKE_ACCOUNT` credentials available, and
per established practice in this repo those are not something to extract or
request through this session. Whoever has dbt prod credentials should run
`dbt test --select filing_activity` then `dbt run --select filing_activity
--full-refresh` to complete the pilot's live deployment before Tickets
02-05 begin applying the macro broadly.
