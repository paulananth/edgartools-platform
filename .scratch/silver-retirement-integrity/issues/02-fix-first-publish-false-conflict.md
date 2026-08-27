# 02 — Fix sec_financial_fact's first-publish false conflict

Type: task

**What to build:** stop canonical silver's first publish after Ticket 33
(the validity-interval retirement columns) from false-conflicting on every
pre-existing `sec_financial_fact`/`sec_accounting_flag` row.

**Blocked by:** None — independent of Ticket 01, though found immediately
after it in the same verification run.

**Status:** resolved (Scenario A only — see Ticket 03 for the deliberately
unresolved Scenario B)

## Answer

Root cause, confirmed via a direct repro against the real
`merge_candidate_into_canonical`: when canonical learns about
`valid_from`/`valid_to`/`is_current` for the first time, the additive
schema-reconciliation step added them via a bare
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS {type}` with no default, leaving
every pre-existing canonical row `NULL` — while the candidate's own local
migration 010 had already backfilled real values. NULL-vs-real-value on a
comparable column reads as a genuine conflict, and this table's
`authority_column` (`ingested_at`) ties on every untouched row (neither
side touched it), so the tiebreak can't resolve it either. Result: 434,805
`SemanticMergeConflictError` rows, all flagged on
`['valid_from', 'is_current']`.

Fixed two ways:
1. The additive `ADD COLUMN` step now reuses the candidate's own declared
   `DEFAULT` (new `_column_defaults` helper reading
   `information_schema.columns.column_default`) instead of leaving the
   column `NULL` — fully fixes `is_current` (a constant `DEFAULT TRUE`).
2. `valid_from` (`DEFAULT NOW()`) needed a second, targeted fix on top:
   `NOW()` evaluates to a genuinely different literal each time it runs, so
   no shared default expression can make two independent backfills agree.
   `sec_financial_fact`'s and `sec_accounting_flag`'s registry entries now
   declare `provenance_columns=frozenset({"valid_from"})` — safe because
   `valid_from` is set once at first capture and never touched again by
   design (same guarantee that already makes `mdm_entity_id`'s existing
   exemption safe elsewhere in this registry).

Deliberately did **not** add `valid_to`/`is_current` to `provenance_columns`
— see Ticket 03 for why that would silently break retirement instead of
fixing anything.

3 new tests (`tests/unit/test_silver_financial_fact_retirement_provenance.py`):
the first-publish false-conflict regression (confirmed to fail before this
fix, pass after); a valid-from-only-difference case proving canonical's
original value wins, not the candidate's independently-backfilled one; and
a positive control proving a genuine retirement conflict still correctly
blocks publication (confirms `is_current`/`valid_to` were not accidentally
exempted too). Full repo suite green.

Full write-up: CLAUDE.md's "sec_financial_fact retirement publish-conflict
5-whys."

**Merged:** PR [#483](https://github.com/paulananth/edgartools-platform/pull/483).
