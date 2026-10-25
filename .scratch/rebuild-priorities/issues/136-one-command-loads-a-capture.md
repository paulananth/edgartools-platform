# 136: One command loads a capture

Priority: 136. Map: [Rebuild priorities](../map.md). Opened 2026-10-25 12:32 ET.

Type: task. Status: in progress (Claude, branch `claude/generic-load-command`).
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
- [ ] Three-axis review, PR, CI green, merge
- [ ] The operator's working store moved to a generic name; 120's load run with the one command
- [ ] Learning → skill
