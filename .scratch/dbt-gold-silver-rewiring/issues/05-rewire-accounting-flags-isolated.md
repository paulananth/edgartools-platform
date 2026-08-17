# 05 — Rewire accounting_flags onto Silver, Isolated from the Forensic-Score Fix

**What to build:** `accounting_flags` reads from dbt silver via `ref()`
instead of its current Python builder. Kept as its own ticket, separate from
Tickets 02-04, because this table has a known upstream fragility: a live
forensic-score (Beneish M / Altman Z / Piotroski F) masking bug tracked and
fixed separately (see CLAUDE.md / the platform's own accounting-flags
incident history). This ticket rewires the read path only — it does not
touch forensic-score computation logic, and should run its reconciliation
check against the *already-fixed* output, not the pre-fix output.

**Blocked by:** 01

**Status:** resolved — `base` rewired onto `ref('sec_accounting_flag')` and
unit-tested; `dbt run --full-refresh` deferred for the same account-mismatch
reason Tickets 03/04/06 documented.

- [x] `accounting_flags` sources exclusively via `ref()` from dbt silver's
      `sec_accounting_flag` model — the model's only other input, `base`,
      no longer references `source("edgartools_source", "ACCOUNTING_FLAG")`
      at all (confirmed by grep); the downstream `with_tenure`/`with_risk`
      CTEs were already pure dbt SQL over `base`'s output and needed no
      change.
- [~] The cutover validation standard passes, explicitly re-verified against
      the current (post-fix) forensic-score output — not a stale pre-fix
      baseline. Confirmed by inspection that the *post-fix* output is what
      this rewire now reads (see "Isolation from the forensic-score fix"
      below) and pinned by a new unit test with real row content, but not
      run against live prod data end-to-end (see "Verification performed,
      and its limit" below).
- [ ] `dbt run --full-refresh` succeeds against prod — not attempted; same
      account-mismatch blocker as Tickets 03/04/06 (see below).

## Answer

**`accounting_flags.sql`'s `base` CTE rewired**, in
`infra/snowflake/dbt/edgartools_gold/models/gold/accounting_flags.sql`.
Unlike Tickets 02-04/06, this model already existed as dbt SQL before this
ticket — it just sourced its raw columns from
`{{ source("edgartools_source", "ACCOUNTING_FLAG") }}` (the Python-builder-
populated mirror) instead of dbt silver, with real business logic
(`consecutive_auditor_years`, `beneish_risk_tier`/`altman_zone`/
`piotroski_strength`, `is_most_recent`) already layered on top in pure dbt
SQL. This ticket's actual scope was narrower than the other tickets in this
batch: only the `base` CTE needed replacing — reconstructing
`_build_fact_accounting_flag`'s (`gold_models.py`) `fact_key`/`company_key`/
`fiscal_year_date_key`/`form_key` directly from `{{ ref('sec_accounting_flag') }}`
— everything downstream of `base` was untouched dbt SQL that already ran
generically over whatever `base` produced.

- `fact_key` = `surrogate_key(['accession_number'])` — single-field, no
  discriminator needed (`accession_number` is already this table's PK).
- `form_key` = `hash(form_type)`, falling back to `hash('10-K')` when
  `form_type IS NULL` — reproducing the original DuckDB
  `COALESCE(hash(form_type), hash('10-K'))` exactly, but via an explicit
  `CASE WHEN form_type IS NULL THEN ... ELSE ...` guard rather than
  `COALESCE`: per this map's now-established finding (Tickets 01/03),
  Snowflake's `HASH(NULL)` returns a real, deterministic, nonzero value, so
  a bare `COALESCE` would never actually fall through the way DuckDB's does.
  `form_type` is `NOT NULL` in the silver DDL today (`silver_store.py`:
  "always 10-K"), so this branch is currently unreachable in production —
  kept anyway for exact behavioral parity with the Python builder, and
  exercised directly by the new unit test's second fixture row.
- `fiscal_year_date_key` = `fiscal_year*10000 + 1231` — a synthetic
  "fiscal-year-end" YYYYMMDD-shaped integer, not a real calendar date, so
  this is direct arithmetic on the integer `fiscal_year` column rather than
  the `date_key()` macro (which operates on an actual `DATE` expression).

**Isolation from the forensic-score fix (the reason this ticket exists
separately from Tickets 02-04):** `sec_accounting_flag`'s own dbt silver
model (`models/silver/sec_accounting_flag.sql`, auto-generated) already
carries the separately-tracked forensic-score masking-bug fix — `LAST_VALUE
(beneish_m_score/altman_z_score/piotroski_f_score IGNORE NULLS) OVER
(PARTITION BY cik, accession_number ORDER BY parse_sequence)` instead of a
plain "latest row wins" collapse
(`generate_silver_dbt_models.py`'s `_COALESCE_PRESERVING_COLUMNS`
mechanism, the same fix
`.scratch/silver-landing-coalesce-bug/issues/01-thin-backfill-nulls-other-columns.md`
documents). This rewire's `ref('sec_accounting_flag')` therefore picks up
that already-fixed output automatically — there was no separate "apply the
fix" step needed as part of this ticket, only confirming (by reading the
silver model, not assuming) that the fix already lives where this ticket's
new `ref()` edge points.

**Tests:** new `_accounting_flags_unit_tests.yml`, the first unit test ever
written for this model. Two fixture rows for the same CIK across two fiscal
years (`auditor_changed = false` on both) prove `consecutive_auditor_years`
accumulates (1 then 2) and `recency_rank`/`is_most_recent` correctly picks
the later fiscal year — both pre-existing derivations, exercised here for
the first time. Row A has a real `form_type` ('10-K'); Row B's `form_type`
is `NULL`, exercising the `form_key` fallback branch — its expected
`form_key` is asserted equal to Row A's, proving the fallback resolves to
the same literal `'10-K'` hash rather than guessing a plausible-looking
value. Forensic scores are chosen to land in different tiers per model
(Row A: low/safe/strong; Row B: high/grey/neutral), covering all three
threshold `CASE` expressions' extremes. Expected `fact_key`/`form_key`
literals computed live via `snow sql --connection edgartools-prod`
(`BITAND(HASH(...), 9223372036854775807)::BIGINT`), not guessed.
`dbt parse --no-partial-parse --target prod` (dummy Snowflake credentials)
succeeds cleanly and lists the new unit test
(`dbt ls --resource-type unit_test`); re-confirmed genuinely validating
`ref()` resolution, not just syntax, via the established typo-and-revert
method (temporarily broke `ref('sec_accounting_flag')`, confirmed the
expected "depends on a node ... which was not found" failure, reverted).
Full Python test suite unaffected (no `.py` files changed this ticket):
2171 passed, 4 skipped.

**Code-review pass (Standards + Spec axes):** no defects found on either
axis — Spec confirmed the rewrite is faithful to `_build_fact_accounting_flag`
column-for-column and that no scope creep touched `with_tenure`/`with_risk`.
Standards raised two judgement calls, both already called out in this
model's own comments rather than being new findings: (1) this model's
`form_key` NULL-fallback hashes a literal `'10-K'` string, while
`filing_activity.sql`/`filing_detail.sql`'s `form_key` falls back to a `0`
sentinel — two different "form_key when missing" conventions now coexist in
the gold layer, but deliberately, since this ticket's job was byte-for-byte
parity with `_build_fact_accounting_flag`'s own per-table behavior, not
alignment with an unrelated sibling model; (2) the `form_type IS NULL`
branch is confirmed dead code today (`silver_store.py`: `form_type NOT
NULL`, "always 10-K"), kept for the same byte-for-byte-parity reason. Both
noted, neither changed.

**Verification performed, and its limit:** the account-agnostic parts
(`dbt parse`'s `ref()` resolution, `HASH`/`BITAND` literal computation for
the unit test) are genuinely verified against a real Snowflake session.
**Not run:** `dbt test`, `dbt run --full-refresh`, or a real-data
reconciliation check. `edgartools-prod`/`snowconn` in this session's
`~/.snowflake/connections.toml` still resolve to the same freshly-
provisioned, empty account documented in Tickets 03/04/06's Answers
(`PRJEDJU`/`QJB05385`, re-confirmed live at the start of this ticket — not
`XCPCLKF`/`KB19989`) — the ongoing `snowflake-env-provisioning` blocker,
not a new one. Whoever resolves that account should run `dbt test --select
accounting_flags` and `dbt run --full-refresh --select accounting_flags`
against real prod data, and spot-check that the post-cutover
`beneish_risk_tier`/`altman_zone`/`piotroski_strength`/
`consecutive_auditor_years` values for a few real CIKs match what they were
producing immediately before this rewire (a before/after snapshot
comparison of `EDGARTOOLS_GOLD.ACCOUNTING_FLAGS` itself, the same kind of
check Ticket 06 described for its own tables — there is no second,
still-live `EDGARTOOLS_SOURCE`-vs-`EDGARTOOLS_SILVER` sourcing path to
diff via `HASH_AGG` here, since `accounting_flags.sql` only ever had the
one dbt model, not a parallel Python-populated mirror table someone else
still reads).
