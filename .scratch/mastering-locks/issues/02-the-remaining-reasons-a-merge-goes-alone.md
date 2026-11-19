# The remaining reasons a merge goes alone

Status: open
Type: task

After ticket 01 a batch no longer merges alone for its size. A part still merges alone when it merges golden records, meets an
identifier another golden record of its kind holds, or joins or creates by exact name (the lock covers none of those).

## Parts

- [x] Count each `Contended` reason: `merge_file` returns `alone` (parts that merged alone, by the reason) and the merge worker
  prints `{"mastering_merge_alone": {...}}` to stderr when its batches end (2026-11-18 22:27 ET;
  `test_a_part_that_merges_alone_is_counted_by_its_reason`: `KeyError: 'alone'` before the change; PostgreSQL adapter file: 39 passed,
  the same 5 pair-evidence tests fail with and without the change)
- [ ] Read the counts on a load with the change, and the share of the exclusive hold each reason causes (needs the stopped `fresh-v3`
  load restarted)
- [ ] Count the parts that still exceed the cap (the cut counts raw identifier pairs, the claim counts new ones after normalization and
  includes LEIs bound by name, so the two can differ): a part that raises the cap's `Contended` after the cut is a sign they have drifted; the counter above names it, so read it on the same load
- [ ] If the exact-name path dominates, claim name values the way identifier values are claimed (a lock a value, then read again),
  with a race test: two merges minting one name leave one golden record
- [ ] The scheduler reads "waiting on locks" as pressure and halves workers: check it still should, with the waits shorter
- [ ] Learning → skill: mdm-engineering and data-operations
