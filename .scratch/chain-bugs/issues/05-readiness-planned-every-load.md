# 05: readiness took over three minutes, most of it planning every load

Status: resolved
Type: bug

A readiness pass took 201 s, measured one check at a time. CAPTURES took 174 s of it (87%); the rest were doctor 10 s,
the database facts 6 s, logins 4 s, catalog 4 s, git 2 s and under a second each for the others.

## 5 whys

1. Why did readiness take over three minutes? CAPTURES took 174 s.
2. Why? It ran `load_chain.py --plan`: 43 `load --plan` commands in a row, each listing Bookkeeping's open runs and
   cutting its capture into bundles.
3. Why plan the loads? It counted a plan's "no plan" lines as a missing capture.
4. Why that proxy? The plan was the tool at hand, so it was reused.
5. Root cause: a question a look at each folder answers (does the capture hold its receipts file?) was answered by
   working out every load.

## 7 wastes

| Waste | Where | Fix |
|---|---|---|
| Over-processing | 43 plans to learn whether 43 folders hold a file | Each step's capture folder is checked for `receipts.jsonl` |
| Waiting | Every pass, and every pass again after a commit, waited three minutes | 0.03 s for the check; the pass is about half a minute |
| Others | None found | |

## Parts

- [x] Measured each check on the hosted store (201 s, CAPTURES 174 s), 2026-11-23 19:20 ET
- [x] Failing test, then fix: `test_a_step_has_a_capture_when_its_folder_holds_receipts_and_the_check_plans_no_load`
  failed with `Failed: a capture check runs no command`; passes, and the real captures give the same answer (0 missing) in 0.026 s, 2026-11-23 19:20 ET
- [x] Skills: `data-operations/HOSTED-LOADS.md` (a pass takes about half a minute; each check reads what it asks) and the
  init runbook's step 9; skill lints pass, 2026-11-23 19:20 ET
- [x] Learning → skill: the HOSTED-LOADS line above, 2026-11-23 19:20 ET
