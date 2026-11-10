# 202: Name Matching inside the GLEIF merge

Priority: 202. Map: [Rebuild priorities](../map.md). Opened 2026-11-09 11:25 ET (operator: "This should be part of the mastering process not a separate job functionality required but it is part of GLEIF load only").

Type: task. Status: open. Blocked by: none.

## Question

How does the Name Matching become a step of the GLEIF merge, with no separate job and no input to `sec.company`?

## Operator rulings

- The Name Matching is part of mastering, not a separate job.
- It is a GLEIF load concern only. The SEC company run no longer reads it.
- An earlier name binding stays when a later load makes the name shared (operator, 2026-11-10 06:13 ET: "2 agreed", on my recommendation). A data steward splits it; the shared name only stops new binds. The build plan below stands as written.

## What exists today

- A separate command, `edgar-warehouse mdm name-count`, builds a file over one whole SEC capture and one full GLEIF file.
- `sec.company` reads that file as a run file in every bundle (`name_count` step, `--file name_count=...`) and refuses a load whose file counted another capture.
- It is used only by the three GLEIF name rules (name with jurisdiction, with postal code, with city or postcode). A name rule may bind only a name whose SEC count and GLEIF count are each exactly one.

## Design to check

The GLEIF load already runs after the SEC Companies are mastered. At its merge:

- the GLEIF count comes from the GLEIF publication being loaded, counted once over the whole file;
- the SEC count comes from the SEC Companies already in the store, counted when the GLEIF merge starts.

**Trap:** `CONTEXT.md` forbids "a count over the records a Stage happens to hold". A GLEIF load in parts (the full file was split into three scopes during the local load) would count only each part. The GLEIF side must be counted over the whole publication, not over the scope or the bundle in hand.


## Build plan (written 2026-11-09 23:34 ET; assumes the recommended ruling: an earlier name binding stays when a later load makes the name shared, a steward splits it, and the shared name only stops new binds)

Measured blast radius (files that name `name_count`): 6 source files under `rules/sources/sec.company` (source, fields, combine and name-count yamls), `rules/mastering/engine-v1.yaml`, 8 engine and integration tests, `tests/mdm/test_bind_run_inputs.py`, `edgar_warehouse/mdm/{matching,cascade,catalog,execution,name_count,name_count_file,store,cli,commands}.py` and `mastering/merge.py`. One PR would be too large to review, so four, each green on its own:

1. **Count inside the merge, beside the file.** `_match_names` computes the SEC-side count from the stored SEC Companies and the GLEIF-side count from a per-publication count table (built once from the captured file, keyed by the publication's identity), and uses them instead of `provenance.matching.name_count`. Both counts are written on the bind decision (step 6 already records binds). Test: a name unique on both sides binds, a name shared on either side waits, a scoped load reads the whole-publication counts.
2. **Prove it agrees with the file** on the same data (counts only), then take the file's use out of the three GLEIF name rules.
3. **Take the `name_count` step, run file and `--file name_count` out of `sec.company`**, with the policy, approvals, Mapping Documents and the pinned digests that follow.
4. **Drop `mdm name-count`**, `name_count_file.py` and the older readers; update `CONTEXT.md` ("Name Matching") and the load sequence's step 4.

Until part 3 lands the SEC company load needs the file (ticket 201). Parts 1 to 3 are the go-live's prerequisite.

## Checklist

- [x] Name the whole-publication GLEIF count's source (2026-11-09 13:54 ET, design from the structural consult; no code run). The count per name is built once per GLEIF publication from the captured file and stored under the publication's identity. A scoped load reads the stored counts and never recounts, so a name shared outside its scope waits, and no scope re-reads the 927 MB zip (about 45 min each in the local loads). A delta publication stays refused. The SEC side is counted from the stored SEC Company records when the GLEIF merge starts, and the count used is recorded on each decision. A later SEC load can make a bound name stop being unique: proposed, leave it bound and record the count it used; a duplicate found later goes through mastering again (step 4). Needs the operator's word on that proposal before the code.
  Why now: the SEC holder record carries GLEIF facts in `provenance.matching.name_count` (`matching.py:56-60`), so the SEC load cannot run before the separate command has read the full GLEIF zip.
- [ ] Measure the SEC-side count from the stored SEC Company records against the file's count on the same data, and show they agree (counts only).
  - Finding so far, corrected (2026-11-09 14:26 ET; the earlier note here was wrong): `mastering_name_key` does not hold name counts. Per `mastering/merge.py` `name_keys`, its `name_count` role holds the LEI each record's precomputed pass found, its `cascade` role the cascade LEI, and its `exact` role the record's name id. So the store has no SEC-side count and no former names, which the file counts. Counts only: the file (2026-11-04) holds 43,245 names, 43,096 with one SEC filer and 149 shared; the store holds 38,365 name-key rows (`exact` 32,658, `cascade` 2,142, `name_count` 3,565). The SEC-side count needs a new derived table of current and former SEC names per CIK, built from the SEC Company records. Agreement with the file is not shown; the part stays open.
- [ ] Take the `name_count` step, the run file and the `--file name_count` input out of `sec.company`.
- [ ] Move the count into the GLEIF merge, with a test: a name unique on both sides binds, a name shared on either side waits, and a scoped load counts the whole file.
- [ ] Drop `edgar-warehouse mdm name-count` as a separate command once nothing uses it, and update `CONTEXT.md` ("Name Matching") and the load sequence's step 4.
- [ ] Learning → skill: name the skill line this ticket changed, or write "none".
