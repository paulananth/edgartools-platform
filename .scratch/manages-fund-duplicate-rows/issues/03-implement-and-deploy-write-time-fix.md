Type: task
Status: open
Blocked by: 02

## What to build

Implement Ticket 02's decided fix mechanism, per this repo's standing
discipline: `/gof-refactor-reviewer` before editing `pipeline.py`/`graph.py`
(hard rule), a regression test reproducing the live duplicate-insert shape
before the fix, full 3-axis `/code-review` before the PR is ready, deploy,
and live-verify no new duplicates accumulate on the next real
`daily_incremental`/`derive-relationships` run.

## Acceptance

- [ ] Fix implemented per Ticket 02's decided mechanism.
- [ ] Regression test reproduces the exact live failure shape and fails
      without the fix, passes with it.
- [ ] `/gof-refactor-reviewer` consulted before editing.
- [ ] `/code-review` (Standards, Spec, GoF) run before PR is ready.
- [ ] Deployed and live-verified: a fresh run does not add new duplicate
      active rows for any `relationship_id` it touches.
