# 155: A stamp later than the clock fails the guard

Priority: 155. Map: [Rebuild priorities](../map.md). Opened 2026-11-01 17:41 ET, from the ticket 150 retrospective.

Type: task. Status: resolved on merge of the PR below (Claude, branch `claude/t155-future-stamps`). Blocked by: none.

## Question

CLAUDE.md says "Read the clock before every stamp", and the rule held in memory too. In one session three ET stamps were
guessed, each later than the clock (17:00 for 16:22, 17:36 for 17:25, 17:30 for 17:24). Can the guard every agent runs
before a commit catch a stamp that is later than now?

## Parts

- [x] A test states which stamps are later than a fixed "now" (and ignores earlier ones, other time zones and invalid dates): `tests/unit/test_future_stamps.py`, 4 tests incl. a temporary git repository; red before the script, green after (2026-11-01 17:43 ET)
- [x] `scripts/dev/future_stamps.py` checks the stamps a branch adds under `.scratch/`, and `overlap_guard.sh` runs it: the guard exits 1 on a planted 2099 stamp in a tracked and an untracked file and 0 clean, unpiped (2026-11-01 17:43 ET)
- [x] PR, CI green, merged: #1269 (the PR is the record; ticked 2026-11-04 04:42 ET)
- [x] `Learning → skill`: CLAUDE.md, "Path ownership": the guard also fails an ET stamp later than the clock (2026-11-01 17:43 ET)
