# After a store reset the catalog holds the previous load's statuses

Status: resolved
Type: task

Operator, 2026-11-18, after the hosted stores were reset and loaded again: "Do you need to update open metadata too", then
"Fix the skills update open metadata".

## Findings

- The catalog's pipelines, datasets and quality cases come from the rules files, so a store reset changes none of them. Its text had
  moved: `rules catalog check` read 21 differences (descriptions of the service and its per-source pipeline services);
  `rules catalog publish` then `check` read `confirmed`, no differences.
- The statuses the first load published stay in the catalog and say "Successful" for steps the empty stores no longer hold. The status
  command publishes a finished run; it has no reset, so the new load's statuses supersede them step by step.
- Neither the data-operations skill nor the init runbook said any of this, and the commit script's guard stopped a rules change
  silently (its cause was one line above its STOP) because the checkout had no Python with the engine's dependencies.

## Parts

- [x] The catalog was brought up to the rules after the reset: `publish` then `check` 2026-11-18 11:55 ET (live: 21 differences before, 0 after)
- [x] The skill says what the old statuses are and when to publish the catalog's text (2026-11-18 11:55 ET; the skill and the runbook's new step, read in the PR)
- [x] The init runbook gains the catalog step, with its done condition (2026-11-18 11:55 ET; read in the PR)
- [x] The guard's STOP message names TEST_PYTHON when the rules check could not run (2026-11-18 11:55 ET; read in the PR)
- [ ] ~~A fresh run's projection uses the previous run's measured times~~ deferred to ticket 04 (`04-a-fresh-runs-projection-uses-the-last-runs-times`): the first projection of a new run
  is the sum of the step bounds (hours past the deadline) until a step finishes
- [x] Learning → skill: data-operations ("Publish a step's status to the catalog") and the init runbook's step 8 (this ticket)
