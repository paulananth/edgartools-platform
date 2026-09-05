# 01 — Fix the `sec_financial_fact`/`sec_accounting_flag` retirement publish-conflict bug

Type: task
Status: open

**Prerequisite for Ticket 03** (entity-facts writes into these two tables;
shipping the refresh trigger without this fix would just make the standing
bug reachable more often).

## What to build

Don't touch `ingested_at`'s existing semantics (documented elsewhere as true
capture time; reinstatement already relies on it advancing correctly).
Instead:

1. Add a new column, `retirement_state_observed_at TIMESTAMP`, to
   `sec_financial_fact` and `sec_accounting_flag` via a new entry in
   `silver_store.py`'s `_schema_migrations()` (same pattern as migration
   010 — `ADD COLUMN IF NOT EXISTS ... DEFAULT NOW()`). Follow migration
   010's own hard-won lesson (CLAUDE.md's "Migration 010" 5-whys): test
   against a **populated** table fixture, not just empty, and set
   `requires_transaction=False` if this migration combines with another
   default-bearing `ADD COLUMN` on the same table in the same pass
   (DuckDB's row-rewrite-on-ADD-COLUMN-with-DEFAULT commit conflict).
2. Set this new column unconditionally to `now()` in BOTH places that
   touch `is_current`/`valid_to`:
   - `retire_financial_facts_not_in_snapshot`'s own `UPDATE`
     (`silver_store.py:4145-4153` and its `fact_keys`-scoped sibling
     branch) — currently only sets `is_current=FALSE, valid_to=?`.
   - The merge's `ON CONFLICT DO UPDATE` reinstatement branch
     (`silver_store.py:4069-4081`) — already sets `ingested_at=now()`, add
     this column alongside it for symmetry.
3. Add an optional field to `ProtectedTablePolicy` (`silver_protection.py:55-74`):
   `retirement_authority_column: str | None = None` plus
   `retirement_columns: frozenset[str] = frozenset()` (`{"valid_to",
   "is_current"}` for these two tables). Extend `_resolve_conflict`
   (`silver_protection.py:1131-1147`): if the primary `authority_column`
   ties **and** the only differing comparable columns are a subset of
   `retirement_columns`, fall back to comparing `retirement_authority_column`
   instead, picking whichever side is greater. Every other table's
   behavior is byte-for-byte unchanged (both new fields default to
   empty/`None`).
4. Register this for exactly `sec_financial_fact` and `sec_accounting_flag`
   in `PROTECTED_TABLE_REGISTRY` (`silver_protection.py:249-287`).

## Tests

- A populated-table migration test (mirroring
  `test_migration_010_adds_retirement_columns_to_populated_tables`).
- A `_resolve_conflict` unit test proving a genuine retirement (only
  `valid_to`/`is_current` differ) now resolves via the new column instead
  of aborting, while a genuine *value* conflict (e.g. `value`/`decimals`
  also differ) still correctly aborts as ambiguous.

## Acceptance

- [ ] A live `sec_financial_fact`/`sec_accounting_flag` retirement can
      publish to canonical silver without a `SemanticMergeConflictError`,
      verified against a real populated canonical copy (not just unit
      tests) — closes CLAUDE.md's open "Part B" gap in the "sec_financial_fact
      retirement publish-conflict" 5-whys entry.
- [ ] `/gof-refactor-reviewer` consulted before editing
      `silver_protection.py`/`silver_store.py` (repo hard rule).
- [ ] `/code-review` (Standards, Spec, GoF) run before this ticket's PR is
      considered ready.
