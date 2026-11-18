# The loads have a priority, the runbook lists it, and the scheduler reads it

Status: open
Type: task

Operator, 2026-11-18: "Can you prioritize the loads in the run book and data operations should look at it".

## Findings

- The scheduler already started the ready step with the longest chain behind it, so the order existed only as arithmetic over
  measured times: nothing said it, nothing could override it, and the runbook did not list it.
- From the first full load's measured times, 8 steps have 100 minutes or more of chain behind them (13F filings and registration are
  short but hold the 214-minute IPO step behind them in their lane; company and GLEIF pairs hold GLEIF), 3 have 30 to 100, and the
  other 32 under 30.

## Parts

- [x] `rules/load-chain.yaml` gives each step a `priority` (1, 2 or 3; a step that says nothing is 3) with the rule in a comment, and
  `chain_steps` refuses any other value (2026-11-18 15:16 ET; `test_every_step_has_a_priority_of_one_two_or_three_and_the_chain_file_refuses_any_other`:
  `KeyError: 'priority'`, and `DID NOT RAISE ValueError` for `true`, `2.0` and `4`)
- [x] `ready()` starts the higher priority first, then the longest chain (2026-11-18 15:16 ET;
  `test_a_higher_priority_step_starts_before_one_with_a_longer_chain_behind_it`: `assert ['long'] == ['urgent']`)
- [x] The init runbook's "Load priority" lists each tier and why, and a test holds the table to the chain file
  (2026-11-18 15:16 ET; `test_the_runbook_names_exactly_the_steps_the_chain_file_gives_priority_one_and_two`:
  `KeyError: 'priority'` reading the chain file's tiers)
- [x] A step with no priority is three, no step waits on one of a lower priority than its follower, and `--list` and the scheduler's start note
  show the priority (2026-11-18 15:21 ET; `test_a_step_that_says_no_priority_is_three_and_starts_after_a_priority_two` and
  `test_no_step_waits_on_one_of_a_lower_priority_than_the_step_that_follows_it`, both passing: nothing in the old code contradicted them)
- [x] The data-operations skill says the scheduler starts steps in the chain file's priority order and names the runbook table
  (2026-11-18 15:16 ET; the skill sentence, read in the PR; the skill is 499 lines)
- [ ] Re-measure after the second hosted load finishes: the tiers came from the first load's times, and the lock and flapping fixes
  change the critical path
- [x] Learning → skill: data-operations (the `--auto` sentence) and the init runbook's "Load priority" (2026-11-18 15:16 ET; both read in the PR)
