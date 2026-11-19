# The scheduler moved single-bundle steps ten times

Status: open
Type: bug

On the first hosted load after the reset, the scheduler moved `gleif` ten times and `nport-security-silver` five times (workers 8, 4, 2, 1,
2, 4, 8, 10 as the machine's load changed). Each move stops the step and starts it again, and a one-document step starts over: neither
finished in two hours, against 2 h 13 min and 1 h 30 min uninterrupted in the previous load.

## Parts

- [x] Root cause: `auto` resized any settled step, and a move abandons the bundles in flight; for a single bundle that is the whole attempt. 2026-11-19 13:33 ET
- [x] Fix: only a step whose log names more than one bundle is moved (`movable`); `tests/unit/test_load_chain.py::test_a_step_with_one_bundle_or_none_named_yet_is_never_moved` failed with the check removed; the four existing move tests now name a many-bundle log. 2026-11-19 13:33 ET
- [x] The live load: the scheduler was stopped (the two steps kept running) and a watcher runs `adv-custodians-06`, `adv-custodians-03` and `--finish` after them. 2026-11-19 13:33 ET
- [x] The operator asked that resizing be intelligent and avoid the seven wastes: a move is made only at a bundle boundary, with thirty minutes left, after measured gain from the last raise, and shedding only after four pressed cycles (`worth_moving`, `raise_pays`); the tests for each fail with the check removed. 2026-11-19 13:38 ET
- [ ] Merge the PR when CI is green
- [x] Learning → skill: data-operations `HOSTED-LOADS.md` ("A step of one bundle is never moved"). 2026-11-19 13:33 ET
