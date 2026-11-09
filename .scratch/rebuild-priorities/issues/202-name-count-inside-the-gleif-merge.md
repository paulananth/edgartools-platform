# 202: Name Count inside the GLEIF merge

Priority: 202. Map: [Rebuild priorities](../map.md). Opened 2026-11-09 11:25 ET (operator: "This should be part of the mastering process not a separate job functionality required but it is part of GLEIF load only").

Type: task. Status: open. Blocked by: none.

## Question

How does the Name Count become a step of the GLEIF merge, with no separate job and no input to `sec.company`?

## Operator rulings

- The Name Count is part of mastering, not a separate job.
- It is a GLEIF load concern only. The SEC company run no longer reads it.

## What exists today

- A separate command, `edgar-warehouse mdm name-count`, builds a file over one whole SEC capture and one full GLEIF file.
- `sec.company` reads that file as a run file in every bundle (`name_count` step, `--file name_count=...`) and refuses a load whose file counted another capture.
- It is used only by the three GLEIF name rules (name with jurisdiction, with postal code, with city or postcode). A name rule may bind only a name whose SEC count and GLEIF count are each exactly one.

## Design to check

The GLEIF load already runs after the SEC Companies are mastered. At its merge:

- the GLEIF count comes from the GLEIF publication being loaded, counted once over the whole file;
- the SEC count comes from the SEC Companies already in the store, counted when the GLEIF merge starts.

**Trap:** `CONTEXT.md` forbids "a count over the records a Stage happens to hold". A GLEIF load in parts (the full file was split into three scopes during the local load) would count only each part. The GLEIF side must be counted over the whole publication, not over the scope or the bundle in hand.

## Checklist

- [ ] Name the whole-publication GLEIF count's source: the captured file, read once by the GLEIF merge, and say how a scoped load still counts the whole file.
- [ ] Measure the SEC-side count from the stored SEC Company records against the file's count on the same data, and show they agree (counts only).
- [ ] Take the `name_count` step, the run file and the `--file name_count` input out of `sec.company`.
- [ ] Move the count into the GLEIF merge, with a test: a name unique on both sides binds, a name shared on either side waits, and a scoped load counts the whole file.
- [ ] Drop `edgar-warehouse mdm name-count` as a separate command once nothing uses it, and update `CONTEXT.md` ("Name Count") and the load sequence's step 4.
- [ ] Learning → skill: name the skill line this ticket changed, or write "none".
