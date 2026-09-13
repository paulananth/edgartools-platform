# 02 — Design the BookkeepingStore schema and retry-read contract for the per-CIK marker

**Type:** task (downgraded from `grilling` 2026-09-13 — see correction below)

**Status:** resolved (2026-09-13)

**CORRECTION (2026-09-13):** this was briefly moved to a new `silver-merge-engine-migration`
map on the premise that it was "the same DuckDB-to-Postgres move" as the bulk merge engine.
That premise was wrong on two counts: (1) this marker is a crash-resume/idempotency concern,
not a merge/dedup-compute concern, so it doesn't share the bulk engine's Postgres-vs-DuckDB
question at all; (2) **this exact problem is already solved and live in this codebase** —
the [pipeline-resumability map](../../pipeline-resumability/map.md)'s
[Ticket 02](../../pipeline-resumability/issues/02-design-resume-from-stage-mechanism.md)
already designed a "resume ledger" pattern (frozen candidate snapshot + batched/per-item
outcome flushes, stored as S3 objects, not a database table at all), with **three existing
implementations**: `edgar_warehouse/mdm/company_resume.py` (MDM's `run_companies`, batched
flushes — ~62,190 companies made per-item markers unacceptable, ~62K S3 objects/run),
`edgar_warehouse/application/daily_artifact_resume.py` (per-item), and
`batch_silver_resume.py` (per-batch). Moved back here (reverting the merge-engine-migration
move), downgraded from a design question to a task: apply this existing pattern directly.

## Answer

No new schema. Reuse the existing resume-ledger pattern. Given `entity-facts` mode's typical
CIK-window size (a single Step Functions Map item, not MDM's full ~62,190-company universe),
a **per-item marker** (mirroring `daily_artifact_resume.py`'s granularity, not
`company_resume.py`'s batched one) is the right granularity — object count per window stays
small. Concretely: freeze the resolved CIK window as a snapshot once per `run_id` (mirrors
`company_resume.py.write_snapshot`), write one outcome marker per successfully-processed CIK
(mirrors `daily_artifact_resume.py`'s per-item shape), and on any retry under the same
`run_id`, filter the frozen snapshot against already-flushed outcomes before the loop starts —
never re-derive the candidate set live. Implementation is [Ticket 03](03-wire-entity-facts-mode-to-durable-marker.md).

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
