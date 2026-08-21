# How do we detect an in-flight Identity Refresh Run for one-shot skip?

Type: grilling
Status: resolved
Blocked by: none

## Question

GSD IDEN-01: delete historical `warehouse/identity_refresh/` snapshots,
skipping any in-flight `run_id`. GSD Leak-seal D-07 already locked that the
**standing 7-day lifecycle** does not skip RUNNING maps. This ticket is only
the **one-shot VersionId reclaim** skip.

Identity language in `CONTEXT.md`: Identity Refresh Run, Identity Reference
Snapshot, Identity Refresh Batch Delta, Identity Refresh Reducer.

Decide the skip signal:

1. Any `run_id` directory whose objects are newer than N hours.
2. `run_id` present in a live Step Functions execution or ECS task command.
3. Presence of an Identity Refresh lease / `lease_result.json` under
   `warehouse/reference/identity_refresh_lease/` (that prefix is **not**
   under `warehouse/identity_refresh/`).
4. Skip nothing on the one-shot; rely on D-07’s 7-day hard expire only.

Name the exact keys or APIs the skip must read. Do not delete objects while
resolving this ticket.

## Answer

**Option 1.** Skip an Identity Refresh Run whose newest listed object
LastModified is younger than **24 hours** relative to reclaim `now` (age
≤ 24 hours is skipped). Group keys under
`warehouse/identity_refresh/runs/{run_id}/` by run directory; if that
group's newest LastModified is inside the window, skip every object in
that run. Unique current keys older than 24 hours stay reclaim-eligible.
The skip uses LastModified on listed versions, not `IsLatest` only.

Do not poll Step Functions or ECS (option 2). Do not read Identity Refresh
lease objects under `warehouse/reference/identity_refresh_lease/` (option
3). Standing identity lifecycle remains 7 days current and noncurrent on
the snapshot prefix only and still does not skip RUNNING maps (D-07).

Shipped in VersionId Reclaim `select_candidates` (`IDENTITY_SKIP_HOURS = 24`).
Covered by `test_skips_identity_run_dirs_newer_than_24_hours`.
