# 157: A ticket marked resolved has no open part

Priority: 157. Map: [Rebuild priorities](../map.md). Opened 2026-11-01 18:00 ET, from the ticket 156 retrospective
(operator, 2026-11-01: "start ticket 157 when 1269 merges").

Type: task. Status: resolved on merge of the PR below (Claude, branch `claude/t157-open-parts`). Blocked by: none.

## Question

A ticket merges in the same commit as its PR, so a "PR, CI green, merged" part can never be ticked before the merge and
stays open on `main`. Can the guard catch a ticket that merges marked resolved with a real open part, and the rule say that
the PR is no part of the ticket?

## Parts

- [x] A test states which open parts are found (resolved status only; ticked and deferred parts and other statuses pass; only tickets the branch changes): `tests/unit/test_open_parts.py`, 3 tests, red before the script (collection failed: no `open_parts.py`), green after (2026-11-01 18:00 ET)
- [x] `scripts/dev/open_parts.py`, run by `overlap_guard.sh` (2026-11-01 18:00 ET)
- [x] CLAUDE.md, "Path ownership": the guard also fails it; the PR is no ticket part (2026-11-01 18:00 ET)
- [x] Review fixes: a status on its own line counts, `resolved-pending` does not, checkboxes in a code fence are skipped, tickets are taken from the merge-base (test: `test_a_status_on_its_own_line_counts_and_a_checkbox_in_a_code_fence_does_not`; 2026-11-01 18:00 ET)
- [x] Learning → skill: CLAUDE.md, "Path ownership" (the part above)
