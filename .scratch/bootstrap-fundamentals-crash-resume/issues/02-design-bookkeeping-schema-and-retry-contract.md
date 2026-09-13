# 02 — Design the BookkeepingStore schema and retry-read contract for the per-CIK marker

**Type:** grilling

**Status:** open

## Question

[Ticket 01](01-design-per-cik-durability-mechanism.md) decided the per-CIK
completion marker moves into `BookkeepingStore`/Postgres. This ticket
designs the concrete shape:

- **Schema:** does this reuse an existing table (`company_sync_state` has a
  per-CIK row already — does a new column/status value fit its existing
  semantics, or would that overload a field meant for something else?) or
  does it need a new dedicated table (e.g. keyed on
  `(cik, command, mode, run_id_or_window)`)? What columns does it need
  beyond "cik" + "done" — does it need to distinguish *which window/attempt*
  marked it, to avoid a stale marker from a different, unrelated run
  silently satisfying this run's check?
- **Write contract:** where exactly does the write happen relative to
  `db.mark_entity_facts_refreshed(int(cik))` — replacing it, alongside it
  (transitional dual-write), or does the local DuckDB marker get removed
  entirely once Postgres is authoritative?
- **Read/retry contract:** `_resolve_fundamentals_ciks`
  (`bootstrap_fundamentals.py:536`) currently resolves the CIK window
  purely from `--cik-list`/`bookkeeping.get_tracked_ciks()` +
  offset/limit — it has no concept of "already done this attempt." Where
  does the filter against the new marker get applied, and scoped to what
  (this exact `run_id`? this exact `{cik_offset, cik_limit}` window,
  regardless of run_id, since a Step Functions retry of the same Map item
  may mint a new run_id)?
- **Interaction with `has_companyfacts_at_version`:** is the new marker a
  separate concept from this existing one-time-per-parser-version skip
  check, or should they be unified? (Current read: separate — this marker
  answers "did *this task attempt* already do this CIK," the existing
  check answers "has this CIK ever gotten facts at the current parser
  version, across all time." Conflating them risks silently skipping a
  CIK a future, unrelated run genuinely needs to process.)

## Blocked by:

None — [Ticket 01](01-design-per-cik-durability-mechanism.md) is resolved.

## Answer

(not yet resolved)
