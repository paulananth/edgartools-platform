# 03 — Decide sec_financial_fact/sec_accounting_flag retirement conflict-resolution policy

Type: grilling

**Blocked by:** None — independent of Tickets 01/02, though found while
resolving Ticket 02 in the same session.

**Status:** open

## Question

How should `merge_candidate_into_canonical` resolve a **genuine** retirement
conflict on `sec_financial_fact`/`sec_accounting_flag` — a candidate that
has retired a row (`is_current=FALSE`, `valid_to` set, via
`retire_financial_facts_not_in_snapshot`/`retire_accounting_flags_not_in_snapshot`)
that canonical still shows as current?

Confirmed via a direct repro (not theorized): this **currently always**
raises `SemanticMergeConflictError` and blocks the whole publish, and — as
far as this investigation found — has done so for every retirement since
Ticket 33 shipped. Root cause: the retirement `UPDATE` deliberately never
touches `ingested_at` (this table's `authority_column` — it represents true
capture time, not last-touched), so `ingested_at` always ties between
candidate and canonical on a retirement-only change, and
`_resolve_conflict`'s tie-breaking logic returns `None` (ambiguous) on an
exact tie. Ticket 02's fix (Scenario A) does not touch this — it only fixed
the one-time NULL-default artifact on canonical's *first* publish after
Ticket 33; a real retirement conflict is a structurally different, standing
gap, reproduced independently.

Candidate resolution policies (none chosen — this is the actual decision):

- **Bump `ingested_at` (or a new column) on retirement**, so the existing
  authority-column mechanism naturally resolves it. Changes `ingested_at`'s
  semantic meaning ("true capture time") wherever else it's read — needs a
  check for other consumers before this is safe.
- **A dedicated `valid_to`/`is_current` resolver**, mirroring the existing
  narrow `mdm_entity_id`-regression-guard precedent already in
  `silver_protection.py` (a candidate win on a genuinely differing business
  column must not drag `mdm_entity_id` backward — a named, scoped special
  case inside conflict resolution, not a blanket exemption). E.g.: if the
  *only* differing columns are `valid_to`/`is_current`, and candidate's
  `valid_to` is non-NULL where canonical's is NULL (or vice versa with a
  later timestamp), pick a side deterministically instead of raising.
- Something else — surfacing the tradeoff space here, not prescribing an
  answer.

## Why this matters

Until resolved, Ticket 33's entire validity-interval retirement feature —
the actual point of that ticket — cannot reach canonical silver at all.
Every retirement computed locally during capture is silently unable to
publish; the merge either raises (blocking the whole command) or, if this
ticket is resolved wrong, could silently regress/drop real retirement state.
