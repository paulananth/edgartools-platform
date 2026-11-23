# The remaining reasons a merge goes alone

Status: resolved
Type: task

After ticket 01 a batch no longer merges alone for its size. A part still merges alone when it merges golden records, meets an
identifier another golden record of its kind holds, or joins or creates by exact name (the lock covers none of those).

## Parts

- [x] Count each `Contended` reason: `merge_file` returns `alone` (parts that merged alone, by the reason) and the merge worker
  prints `{"mastering_merge_alone": {...}}` to stderr when its batches end (2026-11-18 22:27 ET;
  `test_a_part_that_merges_alone_is_counted_by_its_reason`: `KeyError: 'alone'` before the change; PostgreSQL adapter file: 39 passed,
  the same 5 pair-evidence tests fail with and without the change)
- [x] Read the counts on a load with the change: the hosted load of 2026-11-23 (43 steps, every mastering step) wrote no `mastering_merge_alone` line in
  any step log, so no part merged alone and the exclusive hold had no share to read. Not proved by a positive control: the worker's stderr
  reaching the step log is shown for `build-lookups`, not for a merge worker process 2026-11-23 2026-11-23 13:58 ET
- [x] Count the parts that still exceed the cap: none, by the same absence (a part over the cap raises `Contended` and would be counted by its reason); the cap is itself the subject of `mastering-locks/03`'s deferred part 2. The part as written: (the cut counts raw identifier pairs, the claim counts new ones after normalization and
  includes LEIs bound by name, so the two can differ): a part that raises the cap's `Contended` after the cut is a sign they have drifted; the counter above names it, so read it on the same load
- [ ] ~~If the exact-name path dominates, claim name values~~ not needed: no part merged alone on the load, so no path dominates. The part as written: claim name values the way identifier values are claimed (a lock a value, then read again),
  with a race test: two merges minting one name leave one golden record
- [x] The scheduler reads "waiting on locks" as pressure and halves workers: it still should, unchanged. Lock waiters read 0 in every status of the load and lock waits were 1% of merge session time (`mastering-locks/03`), so the rule did not fire and costs nothing; it stays as the guard against a real queue (`db_level`: three waiters, or one waiting a minute) 2026-11-23 2026-11-23 13:58 ET. The part as written:
- [x] Learning → skill: `data-operations/HOSTED-LOADS.md` ("While a load runs": read the merge-alone counts from the step logs, and the lock waits by sampling) 2026-11-23 13:58 ET
