# 33 — Add validity-interval retirement to financial facts

**What to build:** Decide and implement how `sec_financial_fact` (and any
sibling company-facts-scoped table that needs it) represents a fact that a
fresh, complete company-facts snapshot no longer contains — so that
retirement ("Changed, unchanged, reinterpreted, replayed, **and retired**
facts produce deterministic verified outcomes," Ticket 22 bullet 4) is a real,
tested outcome kind, not an unimplemented one.

**Blocked by:** None — the decision is standalone, though it should read
Ticket 22's Answer first for the constraint it already ran into.

**Status:** resolved

- [x] Decide whether `sec_financial_fact` (and `sec_accounting_flag`, if it
  needs the same treatment) gains a `valid_from`/`valid_to`/`is_current`-style
  column, matching `.scratch/change-propagation/spec.md`'s "`RETIRE` closes
  the current validity interval with the causing source revision and scope
  proof. It never physically deletes history" rule — confirmed live that no
  such column exists today (`silver_store.py` ~line 599).
- [x] Decide the comparison basis: a fact is "retired" when a CIK's fresh,
  COMPLETE company-facts snapshot's membership set (accession_number,
  concept, fiscal_period, segment, period_end, period_start) no longer
  contains a key that a prior complete snapshot's membership set did —
  `company_facts_silver_acceptance.py`'s `_member_digest`/`scope_reference`
  recording (Ticket 22) already computes the per-snapshot membership set this
  comparison would need; it just doesn't act on it today.
- [x] Decide whether this is a per-CIK full-scope comparison (compare this
  snapshot's whole membership set against the immediately prior one for the
  same CIK) or something narrower.
- [x] Implement the write path (a new merge/retire method on `SilverDatabase`,
  analogous to `stage_submission`'s scope-retire DELETEs but respecting the
  "never physically deletes" rule via the new interval column instead of a
  real DELETE) and wire it into `company_facts_silver_acceptance.py`'s
  `_finalize_company_facts_candidate`.
- [x] Regression test: a second complete snapshot missing a fact key the
  first snapshot had produces a deterministic, verified "retired" outcome for
  that key, and the row's history remains queryable (not deleted).

## Answer

Both `sec_financial_fact` and `sec_accounting_flag` gained
`valid_from`/`valid_to`/`is_current` (`silver_store.py`, schema migration
`010_company_facts_retirement_columns`) — `sec_accounting_flag` included
because it's the family's other required producer (Ticket 22), and leaving
only one of the two asymmetric was judged worse than treating both.
Comparison basis: per-CIK full-scope, keyed off the table's own
`is_current=TRUE` rows as the "prior snapshot" proxy — nothing else ever
mutates `is_current`, and nothing reaches Silver unless CAPTURED with a
complete payload (Ticket 22's existing negative gate), so this is always
exactly the prior complete snapshot's membership set with no separate
history store needed. Retirement is a validity-interval `UPDATE`
(`is_current=FALSE`, `valid_to=NOW()`), never a `DELETE`. Reinstatement (a
retired key reappearing in a later snapshot) is handled by
`merge_financial_facts`/`merge_accounting_flags`'s own `ON CONFLICT` branch,
not the retire call. Both new `SilverDatabase` methods
(`retire_financial_facts_not_in_snapshot`/`retire_accounting_flags_not_in_snapshot`)
are wired into `_finalize_company_facts_candidate`, gated behind the
existing read-back `verified` check so a FAILED write never retires
anything against an unconfirmed membership set.

**Two real bugs found and fixed along the way, not just the ticket's own
ask:**
1. The two existing schema-migration functions that recreate
   `sec_financial_fact` via `_backup_and_recreate_table`
   (`_migrate_financial_period_end_pk`, `_migrate_financial_fact_period_start_pk`)
   broke once `valid_from`/`is_current` became `NOT NULL` — that helper's
   `missing_values` fallback inserts a literal `NULL` for any column absent
   from a pre-migration backup table, violating the new constraint.
   Reproduced live via the existing `test_silver_store_schema_migration.py`
   suite before fixing both call sites' `missing_values` dicts.
2. `merge_financial_facts`/`merge_accounting_flags` originally used
   `@track_landing_rows`, which forwards the caller's raw row dicts
   unmodified to the Snowflake landing-zone export buffer — those dicts
   never carry `is_current`/`valid_to`/`valid_from`, so every *ordinary*
   (non-retiring) write would have landed with `is_current=NULL` forever in
   Snowflake-native silver, for any fact never retired. Fixed by removing
   the decorator and manually enriching each landing-tracked row
   (`is_current=True`/`valid_to=None` deterministically; `valid_from=<write
   time>` as a deliberate last-write-wins simplification for the
   landing/dbt collapse only — DuckDB's own `valid_from` stays genuinely
   first-insert-wins, since neither merge method's `ON CONFLICT` clause
   touches it). This is a real, documented semantic drift between the two
   stores (flagged by `/code-review`'s Spec pass) — worth a follow-up
   ticket if a consumer ever needs precise first-seen timing from the
   Snowflake side; not blocking, since DuckDB remains canonical today.

DDL/dbt regenerated and applied: `infra/snowflake/sql/bootstrap/11_silver_landing_schema.sql`
(via `infra/scripts/generate_silver_landing_ddl.py`, spliced in manually to
preserve the file's hand-maintained header — the generator's own header text
has drifted from what's committed, a pre-existing, unrelated gap not fixed
here) and `infra/snowflake/dbt/edgartools_gold/models/silver/sec_financial_fact.sql`/
`sec_accounting_flag.sql` (via `infra/scripts/generate_silver_dbt_models.py`,
confirmed byte-identical to the generator's real output). Neither has been
applied to prod yet — this ticket's work is code + committed schema
artifacts only, matching the phased-deploy pattern of prior tickets in this
map.

`/code-review` (Standards + Spec axes) found zero hard violations and zero
missing/wrong requirements; two judgement-call smells accepted and fixed
(deduped the two retire methods' shared landing-export tail into
`_finalize_retirement`), one accepted as-is (`fact_keys` as a raw 6-tuple
rather than a named type — Primitive Obsession, judged not worth a new type
for a single-producer key shape).

Full repo suite green: 2628 passed, 4 skipped (same baseline as this
session's other tickets).
