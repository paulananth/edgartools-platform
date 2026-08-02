# Add progress logging to the Daily Identity Refresh reducer

Type: task
Status: open

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
