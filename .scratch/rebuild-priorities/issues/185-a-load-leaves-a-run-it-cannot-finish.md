# 185: A load leaves a run it cannot finish and loads its documents again

Priority: 185. Map: [Rebuild priorities](../map.md). Opened 2026-11-03 16:00 ET (operator, 2026-11-03: "Rerun should just load three based on bookkeeping and change journal"), from the full sec.company load of ticket 177.

Type: task. Status: resolved. Blocked by: none.

## Found

The full sec.company load (150 bundles) finished 147 and stopped on 3 with transient database errors (a deadlock; a closed connection) and a source.read failure. Rerunning the same command finished two. The third, bundle 10, failed again: `Artifact hash mismatch` on an output file an earlier test run (same `--as-of`, so the same output folder) had left with other bytes. A retry cannot overwrite it, and `load` stopped before loading anything, because it drives every open run first and stops if one fails. I began moving the stale files aside by hand; the operator said the rerun should just load the remaining documents from Bookkeeping and the Change Journal.

## Parts

- [x] `load` names a run it cannot finish and goes on (2026-11-03 16:00 ET): the other open runs are still finished, the run stays in Bookkeeping as evidence, and its documents (the Change Journal holds only what was verified) load again in a new run. Failing before: `tests/unit/test_rules_loading.py::test_a_run_that_cannot_be_finished_is_left_named_and_its_documents_load_again` raised `1 of 2 did not finish` and loaded nothing. The recovery rule is bookkeeping RECOVERY.md's: a replacement needs a new run
- [x] The load runs with its own `--as-of` (the default, now), so a new run's output folder is its own: the cause of the collision was passing one fixed `--as-of` to every command of ticket 177's test runs
- [x] Learning → skill (2026-11-03 16:00 ET): `skills/data-operations/SKILL.md`, the row for `workers work ... failed with status 1`
- [x] The full sec.company load, checked (2026-11-03 16:08 ET): the three stopped bundles' runs finished (the two with transient errors on their first retry, bundle 10's after its stale outputs were moved aside by hand before this change, files kept in `~/.local/share/edgartools/local-tests/stale-20261103/`); the load then reran with the new code and its own `--as-of`: exit 0, 150 bundles, every document already loaded, one run left as it is (pinned to other worker code, from the first test run). MDM now holds 6,414 Company masters with 6,414 bindings, no identifier on two masters, and 69,886 submissions set aside as `classification_deferred` (not Companies: the Person source masters them); 6,414 equals the 6,414-Company cohort of the earlier proving runs. The change log counts 76,300 record changes against 76,230 documents: 70 more than the documents, from records the left-open first test run had already published; not investigated further
