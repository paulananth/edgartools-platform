# 03: a rerun under a new run label processed `company` again, and the Stage refused it

Status: resolved
Type: bug

A rerun of all 43 steps on the hosted store, to check the Change Journal, ran under a new run label so it would start
a fresh state file. 33 steps were skipped as already loaded, each in 5 to 10 s. `company` was not: 145 of its 150
bundles had every document fresh, and both attempts failed with `ValueError: Source native revision has contradictory
publications`, 146 times each. The 10 steps behind it never ran, and 292 Bookkeeping runs were left open.

## 5 whys

1. Why did `company` fail? Its records changed under the same revision, and the Stage refuses that.
2. Why did they change? Each record carries its capture run (`capture_run`, `catalog_run`), and both were new values.
3. Why new? `rules/load-chain.yaml` wrote them as `{run}-company` and `{run}-catalog`: the chain's run label.
4. Why did the Change Journal not skip the files? A run fact is part of the processing identity
   (`target_manifest.py`, `fact:<name>`), so a new label is new processing. Measured on bundle 3 (512 documents):
   0 fresh with the facts at `fresh-v1`, 512 fresh with only the facts at the new label.
5. Why was the label an input at all? The chain used one name for two things: the state file of a chain run, and the
   capture runs of the store's records. The second must not move when the first does.

## 7 wastes

| Waste | Where it showed | Fix |
|---|---|---|
| Defects | A new run label changed `company`'s records | The capture runs are the chain file's `capture_label`; facts are written as values; `RUN` names the state and logs only |
| Over-processing | `--plan --only company` planned all 43 steps (about 20 minutes) | `--plan` honours `--only` and `--lane` |
| Motion | The plan dropped the open runs it would finish; the refusal named no cause | The plan prints the open runs to finish and those left; the refusal names the cause and both remedies; the chain's stop note names the error and its count |
| Waiting, Over-production | A second attempt repeated a refusal the same inputs always give: about 18 minutes and 146 more open runs | That refusal stops the step at its first attempt |
| Inventory | 292 runs left `running`, re-driven by every later `company` load, and they hold the lookups guard shut | Ticket 04 |

## Parts

- [x] Root cause measured: the facts alone change the processing identity (bundle 3: 0 against 512 fresh), 2026-11-23 18:22 ET
- [x] Failing test, then fix: the run label is no input of a load (`test_the_run_label_is_no_input_of_a_load` failed with
  `--capture-run another-label-company` against `one-label-company`), 2026-11-23 18:22 ET
- [x] Failing test, then fix: `--plan --only` plans only that step and prints the open runs
  (`test_a_plan_of_one_step_or_lane_plans_only_it_and_names_the_open_runs` failed: 42 more steps planned), 2026-11-23 18:22 ET
- [x] Failing test, then fix: a contradictory publication stops at the first attempt and the note names its cause
  (`test_a_retry_is_pointless_...` failed: `retry_is_pointless()` took no errors), 2026-11-23 18:22 ET
- [x] Failing test, then fix: the refusal names its cause and both remedies (Rust
  `a_contradictory_publication_names_its_cause_and_both_remedies` failed on `an input changed`), 2026-11-23 18:22 ET
- [ ] ~~Close the 292 open runs~~ deferred to ticket 04: Bookkeeping has no state for a run that can never finish
- [x] Skills: `data-operations/HOSTED-LOADS.md` (a run label names the state and logs, never an input; plan one step) and
  `data-operations/SKILL.md` (a refusal the same inputs always give stops at once), 2026-11-23 18:22 ET
- [x] Learning → skill: the two `data-operations` lines above, 2026-11-23 18:22 ET
