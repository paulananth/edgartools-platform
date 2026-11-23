# 04: a run that can never finish stays open

Status: open
Type: bug

Carried from ticket 03. A load at grain `run` (`company`) submits one Bookkeeping run a bundle. When the run's work raises,
`work_run` (`edgar_warehouse/rules/local.py`) never reaches `finalize`, so the run stays `running`. The rerun left 292 of
them (`expected_count` 0) on the hosted store.

## Why it costs

- Every later `company` load lists them as open runs to finish first and drives each again. Each was frozen with the
  facts that were refused, so each fails again and stays `running`: the same work on every load, for nothing.
- `mdm build-lookups` and `mdm clear-source` refuse while a mastering run is open, so they stay refused.

## What Bookkeeping has

The run states are `running`, `waiting`, `blocked` and `complete`. None fits a run that can never finish:

- `running` and `waiting` are open: the loader drives the run again.
- `blocked` under the rules as they are stops every later load of the source ("recover it before loading more").
- `complete` would record work that never happened.

## The design question

A terminal state for a run whose frozen inputs the store refuses (`abandoned`, say). It would not be open and would not
stop a load. Bookkeeping would keep it as evidence, and the Change Journal, which holds only verified work, would load
its documents again in a new run. The loader would set it when a run's work ends in a refusal the same inputs always
give. This changes the control schema and the `edgar_control` transitions, so it is the operator's decision.

## Decision

Operator, 2026-11-23 (recorded at 2026-11-23 18:40 ET): "yes, add abandoned and rerun the 10 steps". Approved: a run state `abandoned`
in Bookkeeping's control schema, set only when a run's work ends in a refusal its frozen inputs always give; the 292 open
runs closed with it; the 10 steps that did not run rerun under `fresh-v1`. Init applies it to a live store as a numbered
file after `schema.sql`; runs stay.

## Parts

- [x] Decide the state with the operator: `abandoned` (words above), 2026-11-23 18:40 ET
- [x] Tests first: `test_a_run_at_grain_run_refused_for_good_is_abandoned_and_never_worked_again` failed on both engines
  (`'running' == 'abandoned'`), passes on PostgreSQL and MySQL; a check failure still stays open (existing test), 2026-11-23 18:40 ET
- [x] Build it: `01-abandoned-run.sql` (PostgreSQL), `mysql-v1.sql`, `Bookkeeping.abandon`, `work_run`, the catalog shows it
  failed; init adds it to a populated store that holds `schema.sql` alone, its runs kept
  (`test_init_adds_the_abandoned_state_to_a_populated_store_that_holds_the_schema_alone`), 2026-11-23 18:40 ET
- [ ] Init the hosted Bookkeeping store, close the 292 open runs, check the plan lists none and the lookups guard opens
- [ ] Rerun the 10 steps under `fresh-v1` and report each one's Change Journal result
- [x] Skills: `bookkeeping/SKILL.md` (grain `run`: an abandoned run) and `data-operations/SKILL.md` (that run is abandoned), 2026-11-23 18:40 ET
- [x] Learning → skill: the two lines above, 2026-11-23 18:40 ET
