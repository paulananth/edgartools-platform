---
phase: 07
plan: 03
subsystem: mdm-publication-queue
tags: [mdm, postgres, queue, observability, sla]
requires: [07-02]
provides: [publication-outbox, claim-lease-retry, freshness-slo, publication-cli]
affects: [07-04, 07-05, dashboard_readonly]
key-files:
  created:
    - edgar_warehouse/mdm/migrations/008_publication_queue.sql
    - edgar_warehouse/mdm/publication.py
    - tests/mdm/test_graph_publication_queue.py
  modified:
    - edgar_warehouse/mdm/database.py
    - edgar_warehouse/mdm/migrations/runtime.py
    - edgar_warehouse/mdm/cli.py
    - edgar_warehouse/mdm/dashboard_readonly.py
    - tests/mdm/test_runtime_ops.py
    - tests/mdm/test_dashboard_readonly.py
    - .planning/workstreams/fix-pipelines/REQUIREMENTS.md
key-decisions:
  - Claim uses an UPDATE...WHERE guard with synchronize_session=False rather than
    SELECT...FOR UPDATE SKIP LOCKED, since the queue mechanics must work identically
    against SQLite (unit tests) and Postgres (production); correctness relies on the
    database's row-level locking during UPDATE (rowcount==1 means this transaction won
    the race), not on SELECT-level locking semantics that SQLite doesn't support.
  - Retry never creates a new request row -- release_expired_claims resets the same row
    back to mdm_committed and increments retry_count, so an expired lease can never
    produce two competing generation attempts for one logical publication event.
  - Publication health degrades to status="unknown" (not an exception) when
    mdm_publication_request doesn't exist yet in a given environment, so a dashboard
    running against an unmigrated database doesn't lose its other metrics.
  - RSYNC-01 is only partially satisfied: the transactional queue makes MDM the sole
    staging/request authority (satisfying that half), but the "verified active
    generation" Snowflake pointer and MDM/Neo4j read-parity boundary don't exist yet --
    that's 07-04 (generation builder) and 07-05 (activation pointer) scope, not this
    plan's. Marked partial in REQUIREMENTS.md rather than overclaimed complete.
requirements-completed: [RSYNC-03]
requirements-partially-addressed: [RSYNC-01]
completed: 2026-07-14
---

# Phase 7 Plan 03: Transactional Publication Queue And Freshness SLO

## Results

- New `mdm_publication_request` table: `lifecycle_state` (`mdm_committed -> graph_pending ->
  graph_building -> graph_verified -> graph_active`, or `failed`), `committed_watermark`,
  claim/lease fields (`claimed_by`, `claimed_at`, `lease_expires_at`), `retry_count`,
  `last_error`, bounded-backfill metadata (`is_backfill`, `backfill_deadline`),
  `generation_id`, `source_summary` (JSON), `activated_at`.
- `edgar_warehouse/mdm/publication.py` (new module):
  - `request_publication(session, ...)` -- creates a request in the caller's own
    session/transaction; a rollback removes both the MDM change and the request
    (regression-tested with a real relationship-instance insert + rollback).
  - `claim_next_publication_request(session, *, owner, lease_seconds)` -- atomic
    UPDATE...WHERE claim; two concurrent claim attempts on the same request yield
    exactly one owner (regression-tested), the loser moves to the next candidate.
  - `release_expired_claims(session)` -- resets expired leases to `mdm_committed`,
    increments `retry_count`, never duplicates the row (row count stays 1 across an
    expire -> release -> reclaim cycle, regression-tested).
  - `advance_publication_lifecycle(session, request_id, new_state, ...)` -- validated
    state transitions, sets `activated_at` on `graph_active`.
  - `compute_publication_freshness(session)` -- `PublicationFreshnessStatus`: normal
    (<5min), warning (>=5min), hard_alert (>=15min OR an expired backfill deadline).
    Boundary-tested at 4:59/5:00/14:59/15:00.
- `mdm publication-claim --owner <name>`, `mdm publication-release-expired`,
  `mdm publication-status` CLI coordinator entry points.
- `dashboard_readonly.py`: `MdmDashboardMetrics.publication_health` (new field) surfaces
  `compute_publication_freshness` as the primary publication signal; existing
  `relationship_counts.pending_graph_sync_count`/`pending_sync_samples` remain untouched
  as secondary, per-row diagnostics per the plan's explicit instruction. New
  `warning`/`error`-severity `MdmMetricWarning` entries fire on freshness
  warning/hard-alert states (including the backfill-deadline-expired case).

## Deviations from Plan

**[Rule 1 - Bug, caught during Task 1] ORM bulk-UPDATE session-sync crash on naive/aware
datetimes.** The claim UPDATE's default `synchronize_session='evaluate'` re-checks the
WHERE clause in Python against already-loaded attributes, which raised
`TypeError: can't compare offset-naive and offset-aware datetimes` (SQLite round-trips
naive datetimes; `_utcnow()` is tz-aware). Fixed with
`.execution_options(synchronize_session=False)` -- correct here since the claimed row is
reloaded via `session.get()` after `expire_all()`, not relied on via in-memory sync.

**[Rule 3 - Scope] RSYNC-01 marked partial, not complete.** The plan's frontmatter lists
`requirements: [RSYNC-01, RSYNC-03]`, but 07-03's actual `<action>` items (outbox,
claim/lease, freshness) only build the queue/staging half of RSYNC-01's claim. The
"verified active generation" pointer and MDM/Neo4j parity boundary is explicitly 07-05's
scope per `07-CONTEXT.md`'s plan structure. Corrected in REQUIREMENTS.md rather than
repeating last plan's overclaim pattern (see `07-01-SUMMARY.md`'s correction note).

## Verification

```text
uv run pytest tests/mdm/test_graph_publication_queue.py -k 'transaction or claim or retry' -q
9 passed

uv run pytest tests/mdm/test_graph_publication_queue.py -q
22 passed

uv run pytest tests/mdm/test_graph_publication_queue.py tests/mdm/test_dashboard_readonly.py -q
40 passed

uv run pytest tests/ -q --ignore=tests/architecture/test_load_history_state_machine.py
662 passed
```

## Self-Check: PASSED

RSYNC-03 complete. RSYNC-01 partially addressed (staging authority only). Plan 07-04
(parallel generation builder, partition manifests, content-addressed reuse, independent
retries) may begin.
