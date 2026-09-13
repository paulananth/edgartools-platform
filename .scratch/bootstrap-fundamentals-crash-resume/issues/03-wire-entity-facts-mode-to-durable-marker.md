# 03 — Wire `entity-facts` mode's per-CIK loop to the durable marker

**Type:** task

**Status:** open — reverted back here (2026-09-13) after a brief, mistaken move to
`silver-merge-engine-migration`; see [Ticket 02](02-design-bookkeeping-schema-and-retry-contract.md)'s
correction note. Implements the existing resume-ledger pattern
(`edgar_warehouse/mdm/company_resume.py`/`daily_artifact_resume.py` precedent), per-item
granularity, no new BookkeepingStore schema.

## Question

Implement [Ticket 02](02-design-bookkeeping-schema-and-retry-contract.md)'s
design against `run_bootstrap_entity_facts` (`fundamentals_ingest.py:407`)
and `_resolve_fundamentals_ciks` (`bootstrap_fundamentals.py:536`):

- Write the durable marker per Ticket 02's write contract, at the same
  point `db.mark_entity_facts_refreshed(int(cik))` already fires (last
  statement for that CIK — preserve this ordering guarantee exactly).
- Filter the resolved CIK window against already-marked CIKs before the
  loop starts, per Ticket 02's read/retry contract.
- Regression test: simulate a crash after N of M CIKs (raise mid-loop),
  restart the loop, assert only the remaining M-N CIKs are processed and
  no network fetch happens for the first N.
- Full regression test: the exact live shape observed 2026-09-12 (3
  consecutive OOM-equivalent crashes) resumes correctly and completes
  within roughly one window's worth of work, not 3x it.

## Blocked by: 02

## Answer

(not yet resolved)
