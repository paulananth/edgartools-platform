# A moved step's done line counts the whole attempt

Status: resolved
Type: bug
Owner: claude (operator, 2026-11-27: "fix the company done miscount on its own branch")

The AWS load `aws-20261127`, from cleared stores, wrote `company done: Done: 5212 documents loaded, 71168 already loaded
before`. Every one of its 76,380 documents was this load's work: the Change Journal holds 76,230 `sec.company` entries,
all recorded by the step's own runs between 15:46 and 16:07 ET.

Why:
1. The line counts one process: the load's `Done:` line counts the documents its process found new.
2. The step had two processes: at 16:04 ET the controller moved it from 2 workers to 1, which ends the load and starts it
   again in the same attempt.
3. The second process found the first one's bundles loaded and called them "already loaded before".
4. The first process's output was gone: `run_deliveries` empties the step's log at every start, a move's included, so
   the done line read only the last process.

## Checklist

- [x] A moved load's log is kept as `<log>.attempt-<n>.move-<m>`, and the done line counts each bundle as its first report in the attempt says, ending `over K processes (moved)`: `test_a_moved_steps_done_line_counts_what_every_process_of_the_attempt_loaded` (a real process moved after its first bundle) fails on main with `a1 done: Done: 92 documents loaded, 512 already loaded before`; with the fix, 604 loaded, 0 before (2026-11-27 16:28 ET)
- [x] Unit cases: no move, a move, two deliveries, a process stopped before it named a bundle: `test_each_bundle_counts_as_its_first_report_in_the_attempt_says` (2026-11-27 16:28 ET)
- [x] The run to publish is found in a moved process's log too, when the last process ran none: `test_a_step_whose_last_process_loaded_nothing_publishes_the_run_its_moved_process_completed` (2026-11-27 16:28 ET)
- [x] Tests: load jobs and load monitoring, 281 passed (2026-11-27 16:28 ET)
- [x] `/code-review` (Standards, Spec, GoF), each on `reviewer`: fixed a comment naming the wrong log path and a test docstring telling the bug's history; the Spec axis found `step_run_id` never read a moved process's log (fixed above); GoF: leave it (2026-11-27 16:28 ET)
- [x] Learning → skill: HOSTED-LOADS, the move paragraph (where a moved load's log is kept; the done line counts the attempt) (2026-11-27 16:28 ET)
