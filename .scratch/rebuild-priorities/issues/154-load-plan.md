# 154: `load --plan` says what a load would do

Priority: 154. Map: [Rebuild priorities](../map.md). Opened 2026-11-01 17:43 ET, from the ticket 150 retrospective.

Type: task. Status: resolved on merge of the PR below (Claude, branch `claude/t154-load-plan`). Blocked by: none.

## Question

Ticket 150 said "the same command finishes its open runs first". That was false: all 14 open runs were pinned to old
worker code, so `load` left them and loaded every bundle again. It was found only after about an hour of measuring and
hand-running, and the status took eight database and container calls to piece together. Can `edgar-warehouse load`
answer, read-only and before any work, which open runs it would finish, which it would leave and why, and how many
documents and bundles it would load?

## Parts

- [x] A test states the plan for an invented source: finishable runs, runs left as they are with their reason, a blocked run, the documents and bundles, and that no run is prepared, submitted or driven: 3 tests in `tests/unit/test_rules_loading.py`, red before `plan` existed (2026-11-01 17:48 ET)
- [x] `load --plan` prints that plan and changes nothing: run read-only against `company-on`, it reports 0 finishable and 15 pinned runs, 7,714 documents in 16 bundles, exit 0 (2026-11-01 17:48 ET)
- [x] PR, CI green, merged: #1270 (the PR is the record; ticked 2026-11-04 04:42 ET)
- [x] `Learning → skill`: `data-operations`, "Load a capture": plan first with `--plan` (2026-11-01 17:48 ET)
