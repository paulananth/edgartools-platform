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

## Parts

- [ ] Decide the state with the operator (recommendation: `abandoned`, set only by the loader, on a refusal that never clears)
- [ ] Tests first: a run whose work raises that refusal is closed and not driven again; a lost connection leaves it open to resume
- [ ] Build it (schema, transition, loader), then close the 292 open runs on the hosted store and check the lookups guard opens
- [ ] Skills: `bookkeeping` (the state) and `data-operations` (what a load does with it)
- [ ] Learning → skill: name the skill lines changed, or "none"
