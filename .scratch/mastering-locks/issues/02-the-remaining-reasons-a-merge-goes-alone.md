# The remaining reasons a merge goes alone

Status: open
Type: task

After ticket 01 a batch no longer merges alone for its size. A part still merges alone when it merges golden records, meets an
identifier another golden record of its kind holds, or joins or creates by exact name (the lock covers none of those).

## Parts

- [ ] Count each `Contended` reason on a load with the change (a counter on the store, reported by the worker), and the share of the
  exclusive hold each causes
- [ ] Count the parts that still exceed the cap (the cut counts raw identifier pairs, the claim counts new ones after normalization and
  includes LEIs bound by name, so the two can differ): a part that raises the cap's `Contended` after the cut is a sign they have drifted
- [ ] If the exact-name path dominates, claim name values the way identifier values are claimed (a lock a value, then read again),
  with a race test: two merges minting one name leave one golden record
- [ ] The scheduler reads "waiting on locks" as pressure and halves workers: check it still should, with the waits shorter
- [ ] Learning → skill: mdm-engineering and data-operations
