# 08: openfigi-answers stopped a forced load: a duplicate review row, and a manifest folder shared by attempts

Status: open
Type: bug

Operator, 2026-11-24: "Find rca" of the `openfigi-answers` stop (a missing manifest file, `FileNotFoundError`, under the forced run's own bundle folder).

## Evidence

- The step ran three attempts (28, 9 and 8 minutes) and stopped. In each, the same 10 of 16 bundles did not finish (`001 004 005 007 008 009 012 013 014 015`)
  and the same 6 completed (`002 003 006 010 011 016`).
- Each of the 10 failed in `mastering_merge` with `psycopg2.errors.CardinalityViolation: ON CONFLICT DO UPDATE command cannot affect
  row a second time`, raised by `Store.open_reviews` (`mastering/store.py`) called from `merge._merge` for the records that wait: the
  review key is `(subject, reason)`, one row per waiting record is proposed, and two waiting records of one subject in one batch proposed it twice.
- Bookkeeping holds three runs for each bundle number (one per attempt), all with the same manifest path (the forced time and the bundle
  number name the folder, and the forced time is kept across attempts on purpose). The 10 failed bundles' runs stayed `running`; the 6 completed in each attempt.
- `loading.bundle` deletes the whole bundle folder once its own run verifies complete. A run an earlier attempt left open for that bundle (here the run
  from attempt 1 for bundle 016, created 14:43 ET, state `running`) then has no manifest: the next attempt's "finish the open runs" reads it and raises
  `FileNotFoundError`, and the step's classifier calls a missing file a failure a retry cannot change.
- Nine runs from the first forced load (before the manifest folder was mounted) have no manifest either and are tried again, and fail, at every attempt start.

## 5 whys

1. Why did the step stop? Its third attempt ended with a `FileNotFoundError` the classifier treats as final, and 10 bundles had not finished.
2. Why 10 bundles? A batch that holds two waiting records of one subject cannot open its reviews (one command, one row per key).
3. Why only in a forced load? A forced load processes every document again, so a bundle can hold both records of a subject that an ordinary load meets
   one delivery at a time. (Not yet measured: which subjects, and why their records wait instead of binding.)
4. Why did a missing file show? Attempts of one step share one manifest folder, and a completed run deletes it under an older open run.
5. Root cause: a per-row write that the database refuses on duplicates (the engine never made the batch one row per key), and a folder that is the
   attempt's neighbour's too.

## 7 wastes

| Waste | Where | Fix |
|---|---|---|
| Defects | A batch with two rows of one key stopped 10 of 16 bundles three times | One row per `(subject, reason)` in `open_reviews` |
| Waiting | Three attempts of 28, 9 and 8 minutes failed the same way | Fix the cause; a failure that repeats identically is named at the second attempt |
| Over-processing | Nine unfinishable runs are tried at every attempt start | Leave a run whose manifest is gone, once, and say so |
| Others | None found | |

## Parts

- [x] Evidence read: the traceback, the review key, Bookkeeping's runs per bundle, the folder's contents, the code that deletes it, 2026-11-24 15:35 ET
- [x] Failing test: `test_two_waiting_records_of_one_subject_open_one_review_in_one_command` failed first (the command carried the subject twice); `open_reviews`
  now keeps one row per subject, the last assertion winning, 2026-11-24 15:35 ET
- [ ] Measure which subjects repeat in a bundle and why their records wait under a forced load (read-only, on the stores)
- [ ] A bundle folder no attempt shares: name it by the attempt, or delete only the manifest of the run that completed
- [ ] A missing manifest is a run that cannot be finished, said once, never a reason to stop the step
- [ ] Run `openfigi-answers` again (forced) and read its bundle lines
- [ ] Learning → skill: data-operations says a forced load repeats a step's attempts in one folder
