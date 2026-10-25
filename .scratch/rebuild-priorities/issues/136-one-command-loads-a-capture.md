# 136: One command loads a capture

Priority: 136. Map: [Rebuild priorities](../map.md). Opened 2026-10-25 12:32 ET.

Type: task. Status: done (Claude). PR #1168 merged 2026-10-25 13:22 ET.
Blocked by: none. Unblocks the last part of [120](120-switch-on-securities.md).

## Why

Operator, 2026-10-25: "take over from grok the complete the steps", then
"nothing should be named company-on all operation must be generic and should
not be tied to an entity", and "update skill to be generic and super user
friendly".

Found (2026-10-25 12:30 ET): Grok drove 120's load with three hand-written
scripts tied to one store and one source (`company-on-load.py`,
`-continue.py`, `-after-requests.py`). The data-operations skill already says
a missing common command "remains a blocker, not permission to invent
source-specific orchestration". Three things went wrong in them, and each
shows what the common command must do:

- It started the combine step before the answers were verified. A worker
  that finds a prerequisite unfinished leaves the unit `waiting` ("Lease or
  prerequisite contention; retry on resume"). That is "try again", not a
  failure: Bookkeeping lets a waiting unit be claimed again. The scripts
  stopped on it, and `bookkeeping resume` (which only resets the run's state)
  did not move it. The run (OpenFIGI CUSIP bundle 1) stopped at 546 of 551
  units, with nothing written to MDM.
- It turned the manifest root `file://...` into a folder literally named
  `file:` inside the checkout.
- It wrote its verification reports under `/tmp`, which is cleared on a
  restart, and a resumed run rechecks them.

## Design

`edgar-warehouse load --source <s> --target <t> --capture <folder>
--capture-run <id> --stores <environment folder>`:

1. The documents are the capture's receipts that match the target's first
   read step's `files` pattern (every receipt when it names none).
2. They are cut into bundles of the source's `max_artifacts`.
3. Each bundle is prepared (the Change Journal skips processed documents),
   submitted with `rules run`, and driven to `complete`. A bundle with an
   unfinished run for the same manifest drives that run rather than submitting
   another.
4. The driver takes the steps in declared order, with `--workers` worker
   processes on each step and one verifier. It retries a waiting unit and
   stops on a unit that failed its checks, or at `--minutes`.

The driver is one function that `rules test` and `load` share. GoF consult
(2026-10-25 12:31 ET): leave the structure; extract one function. `drive`
has not changed since #1091, but Grok's three copies of it show the
repetition. One helper also reads the manifest root URI.

## Checklist

- [x] GoF consult on `proving.py`'s driver (2026-10-25 12:31 ET): extract one function, no new pattern
- [x] The shared driver (`edgar_warehouse/rules/driving.py`): steps in order, `--workers` workers, one verifier, retries a waiting unit, stops on a failed unit or the deadline, finalizes; `rules test` uses it (2026-10-25 12:45 ET): `test_rules_driving.py`, the two `rules test` Postgres files 9 passed
- [x] `edgar-warehouse load` (`edgar_warehouse/rules/loading.py`): finishes an open run of the source and target first, documents by the first step's `files`, bundles by `max_artifacts`, prepare, submit, drive (2026-10-25 12:45 ET): `test_rules_loading.py`
- [x] The manifest root read as a URI in one place (`driving.manifest_root`), used by `rules test` and `load` (2026-10-25 12:45 ET)
- [x] Tests (2026-10-25 12:45 ET): 20 passed; making the driver stop on a busy unit fails the retry test, and treating every document as new fails the bundle test; testmon over unit, architecture, mdm 2,101 passed (4 min 19 s); skill and rules files' tests 549 passed
- [x] data-operations skill: **Load a capture** (the one command, a "you see, it means, do this" table, fitting the window, while it runs, what runs underneath); bookkeeping RUN.md points at it (2026-10-25 12:45 ET)
- [x] `company-on` removed from rules and skills (`rules/sources/openfigi/source.yaml` comment, `skills/security-master/SKILL.md`) (2026-10-25 12:45 ET): `rules check` ok, `rules mapdoc check` 0
- [x] Three-axis review (2026-10-25 12:55 ET). GoF: leave it (the driver is one function, no pattern earned). Standards and Spec, each fixed and tested:
  - [x] A step over 1,000 units could be judged done from a cut list: `bookkeeping status --step` counts one step exactly; the driver judges by it (`test_one_steps_status_counts_only_its_units...`, Postgres)
  - [x] A blocked run would be submitted again on rerun: `load` stops and names it (`test_a_blocked_run_stops_the_load...`)
  - [x] An open run was driven by the steps on disk: now by its frozen rules export's steps (`test_each_new_bundle...` asserts the frozen steps)
  - [x] N workers on a one-unit step, and back-to-back passes when nothing can be claimed: workers capped at units left, a 15 s pause after a pass that moved nothing (`test_steps_run_in_declared_order_with_workers_only_where_units_are_left`, `test_a_pass_that_moved_nothing_pauses_before_the_next`)
  - [x] A unit that failed before is tried again first, not refused (`test_a_unit_that_failed_before_is_tried_again_first`)
  - [x] The skill's table lacked the worker-failure and blocked-run messages; data-platform, change-journal and data-onboarding now point at `load`
  - Tests after the fixes: 22 driver and load tests; 390 skill, rules and architecture tests; 70 Postgres (3 min 33 s)
- [x] Found by CI on PR #1168: the installed bundle failed to import `edgar_warehouse.rules.loading`. The data-skill wheel lists its files, and `driving.py`/`loading.py` were not on the list. Added to `packages/data-skill/pyproject.toml`. Locally, 3 bundle tests passed (3 min 18 s), and CI's engine and skill adapter jobs passed
- [x] A run pinned to other worker code is left as it is and its documents load in a new run. Found on the first real load: Grok's open OpenFIGI run was pinned to an uncommitted worktree's code. Test `test_an_open_run_pinned_to_other_worker_code_is_left...`
- [x] PR #1168, CI green (9 checks on `f06d1c2f`), merged 2026-10-25 13:22 ET (`e44e5daa`)
- [x] The operator's working store moved to a generic name, `working` (2026-10-25 12:55 ET): backed up from `company-on` (its identity file named Grok's worktree while the container named the deleted `claude-company` worktree; the identity was set back to the labels' owner to take the backup) and restored as `working`, owned by the main checkout
- [ ] ~~120's load run with the one command, in `working`~~ moved to [120](120-switch-on-securities.md): the load is 120's last part; it started 2026-10-25 12:58 ET
- [x] Learning → skill (2026-10-25 13:23 ET): `data-operations` "Load a capture" (the one command, written in this ticket); `data-platform` Setup: a module the CLI imports goes on its wheel's file list, which the bundle tests check
