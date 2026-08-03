# Add progress logging to the Daily Identity Refresh reducer

Type: task
Status: resolved

## Question

`reduce-identity-refresh` (`edgar_warehouse/application/commands/reduce_identity_refresh.py`,
calling `reduce_identity_refresh()` in
`edgar_warehouse/application/identity_refresh_publication.py:169-238`) emits **zero** log or
stdout output for its entire runtime — it only prints one JSON line at the very end
(`reduce_identity_refresh.py:39`), on success. On failure it prints one `stderr` line
(`:37`) with only the exception message, no attempt/stage context.

Found live while monitoring `daily-incremental-postdeploy-1785701660` (2026-08-02): its
`ReduceIdentityRefresh` ECS task ran for 17+ minutes with `describe-log-streams` reporting
`storedBytes: 0` the entire time. There was no way to distinguish "working normally" from
"hung" from outside the process — had to read the source to explain the silence at all.

The reducer's real work per attempt (`identity_refresh_publication.py:191-217`) is multi-stage
and each stage has a materially different cost profile: read+verify the canonical baseline
(~1GB) and every batch delta, then for each candidate — `shutil.copy2` a ~1GB local copy,
`ATTACH` both DBs, and run the protected-table upsert merge (`merge_candidate_into_canonical`,
`edgar_warehouse/silver_protection.py:414+`) — sequentially, once per batch, then stage+promote
the merged ~1GB result. A future run with more than 3 batches, or a `PromotionConflictError`
retry (up to `max_attempts`), has no visible way to tell which stage or which candidate it's
on, or whether progress is being made toward `max_attempts` being exhausted.

## Required work

- Add structured log events (matching this codebase's existing `event`-keyed JSON logging
  convention used elsewhere, e.g. `gold_table_started`/`gold_table_completed` in
  `edgar_warehouse/serving/gold_models.py`) at minimum for: attempt start (`attempt`,
  `max_attempts`), baseline read complete (size/etag), each candidate's merge start/complete
  (`batch_id`, `tables_merged`, elapsed), stage+promote start/complete, and
  `PromotionConflictError` retry (with the conflicting etag).
- Do not change the reducer's control flow, retry semantics, or return value — this is
  observability only.
- Confirm the new events are attributable to the `ReduceIdentityRefresh` step's own log stream
  (not confounded with `RunWarehouseTask`/`GoldRefresh`, per the attribution pattern already
  established in gold-build-memory-reliability's ticket 03).

## Done when

A live prod `ReduceIdentityRefresh` execution shows incremental log events in CloudWatch while
the task is still `RUNNING` (not only a single line at completion), and a focused test asserts
the reducer emits the named events in order for a multi-batch merge.

## Progress (2026-08-03)

Picked via `/wayfinder` "work through the map" (first open, unblocked, unclaimed ticket by
number across the whole issues directory — 42/49/51/52/54/61/63 were all already `claimed` by
an earlier session; 31/32/36/38 blocked by 42).

**Implemented**, on branch `claude/identity-refresh-reducer-progress-logging`:
`edgar_warehouse/application/identity_refresh_publication.py` gained a
`_emit_reducer_event(event, *, run_id, **fields)` helper (same `event`-keyed JSON-to-stderr
convention as `gold_models.py`'s `gold_table_started`/`gold_table_completed` and
[ticket 82](82-add-silver-merge-per-table-started-event.md)'s
`silver_table_merge_started`/`silver_table_merged`) and 8 call sites inside
`reduce_identity_refresh`, matching the ticket's required-work list exactly:

- `identity_refresh_attempt_started` (`attempt`, `max_attempts`)
- `identity_refresh_baseline_read_completed` (`canonical_exists`, `byte_size`, `etag`)
- `identity_refresh_candidate_merge_started`/`_completed` per candidate (`batch_id`,
  `candidate_index`, `candidate_count`, `tables_merged`, `elapsed_seconds`)
- `identity_refresh_stage_and_promote_started`/`_completed` (`byte_size`, `staged_path`,
  `result_etag`, `elapsed_seconds`)
- `identity_refresh_promotion_conflict` (`attempt`, `max_attempts`, `expected_etag`,
  `conflicting_etag` — read from `PromotionConflictError.actual_etag`)

Every event carries `run_id`. Control flow, retry semantics, and return value are byte-for-byte
unchanged — confirmed by all 8 pre-existing tests in `test_identity_refresh_publication.py`
passing unmodified. Attribution to the `ReduceIdentityRefresh` step's own log stream (not
confounded with `RunWarehouseTask`/`GoldRefresh`) is automatic: each is a distinct ECS task
launch with its own CloudWatch log stream, so no additional plumbing was needed beyond the
existing per-task stream separation this pipeline already has.

Two new tests in `tests/unit/test_identity_refresh_publication.py`:
`test_reducer_emits_progress_events_in_order_for_a_multi_batch_merge` (2-batch merge, captures
stderr via `capsys`, asserts the exact 8-event ordered sequence plus field-level assertions on
each) and `test_reducer_emits_promotion_conflict_event_with_conflicting_etag` (reuses the
existing conflict-then-retry fixture, asserts the conflict event fires with the actual
conflicting etag and that a full second attempt cycle follows). Full `tests/unit` +
`tests/application` + `tests/architecture` suite: 1265 passed (up from 1263), 4 skipped
(pre-existing), 1 pre-existing unrelated deselect, 35 subtests.

Not yet deployed — takes effect on the next warehouse image rebuild + deploy. The "Done when"
criterion of seeing this live in a real prod `ReduceIdentityRefresh` execution remains open
until that deploy happens and the schedule (still gated behind [ticket 49](49-implement-bounded-daily-identity-refresh-schedule.md))
or a manual run exercises it.
