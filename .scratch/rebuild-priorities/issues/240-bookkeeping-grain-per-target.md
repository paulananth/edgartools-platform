# 240: Bookkeeping runs once a bundle or a load, and a source can turn it off

Type: task. Status: resolved (operator, 2026-11-17: consolidate and close; hosted parts to 238, the rest to 212). Blocked by: none. Builds on ticket 232 (which leases the destinations already make redundant),
ticket 239 (where a bundle's statements go) and the `local: true` target setting.

## Why

Operator, 2026-11-15: "Bookkeeping runs once per batch or load I should be able to turn on and off bookkeeping for a source
create ticket and adjust skills". Bookkeeping's job is to say which work of a run is in flight, who holds it and what is
verified, so a stopped run resumes. Its cost today is paid per unit: every unit of every step is claimed, leased, renewed,
checked and reported through a process and a database session.

## Evidence (ticket 239, persons, steady state over 17 to 30 local bundles)

- A persons bundle is 462 statements in 12 sessions; **Bookkeeping is 309 of them (67%)**, the Change Journal 82, MDM 63.
- What Bookkeeping's statements are: about 8 status reads a bundle (73 statements), 41 reads of work items (the claims), 37
  reads of the run row, 55 isolation switches, and the BEGIN and COMMIT around the rest. The merge itself is 13 ms a batch.
- On the hosted store a bundle is 48 s; the statements are about 20 s of it and the processes and sessions most of the rest.
- Ticket 232's audit: the destinations already protect most steps (the immutable artifact store, the kind lock, the silver
  table lock and key, the journal's unique key), so a lease on them is a second copy of a protection.
- Precedent: a target marked `local: true` runs its read and combine steps in the loader's process with no claim, lease or
  heartbeat; Bookkeeping starts at the first later step and its receipts are the proof.

## Design (to settle with the operator, one question at a time)

A target says how much Bookkeeping it uses, in its source file, one setting for the target:

| Grain | What Bookkeeping holds | Resumes at | Costs |
|---|---|---|---|
| `unit` (today) | every unit of every step: claim, lease, heartbeat, check, report | the unit | the most |
| `bundle` | one run for a bundle with one unit a step: the step claimed once, its units run inside the worker | the step of a bundle | a claim a step |
| `load` | one run for the load, one unit | the load; the Change Journal skips the files done | one claim |
| `off` (built as `grain: run`) | the run's start and completion only; the loader runs the steps itself (as `local: true` does for read and combine) | the file: the Change Journal skips what was processed | two writes a load |

What a coarser grain gives up, and what already stands in for it:

- **A lease's exclusion of a second writer of one unit.** The destinations protect themselves (ticket 232): the artifact store
  never overwrites, the kind lock serializes a merge, a silver table has its lock and key, the journal a unique key. No
  destination checks a lease proof: the guard that would (`bookkeeping_guard`, `destinations.guard`) has no caller, and ticket
  232 part 3 deletes it. So dropping the lease gives up only that one unit is not done twice, and the chain already refuses a
  second load of one source and target.
- **Per-unit retry and audit.** A rerun skips the files the Change Journal records (a file is recorded once its merge is
  verified), and every step is a deterministic function of its input.
- **Parallel workers on one step.** `off` and `load` run a step in the loader's process (it can still use its own threads).
- **Progress in `bookkeeping status`.** The load log reports each bundle; a target at `off` shows its run as running or complete, with no units.

Recommendation: `bundle` as the default for the sources loaded in bundles (persons, SEC company, ownership, OpenFIGI); `off`
for the silver-only sources and the one-document deliveries (one claim is the whole load); `unit` for GLEIF, whose merge
units are long and where a unit-level resume earns its cost.

## What `off` takes to build (read 2026-11-15, GLEIF first)

`rules/local.py` runs only `source.read` and `source.combine`, calling each worker's `execute(envelope, artifacts)` with a
synthetic envelope and keeping the receipt. GLEIF's target is read, prepare, merge, links, processed. What the rest needs:

- **Envelope.** Every worker reads `input`, `output`, `keys`, `checks`, `cursor`; the merge and journal workers also read
  `claim.run_id` (the journal event's run), and the report binding reads `claim.step/key/attempt` and `effect_key`. A local
  run supplies a run id of its own (the load's) and attempt 1.
- **Verify.** Prepare, merge, links and journal each have a second function that checks the candidate against the input
  (`envelope["candidate"]`). Bookkeeping calls it after `execute`; `off` calls it in the same process, one after the other,
  and stops the load on a failed check.
- **Expansion (the hard part).** Prepare's output is an expansion receipt; Bookkeeping turns its sealed children into the
  merge units (`generated_worklist`, at most 128 a parent, ordinals offset by the parent's). The runner does the same from
  the receipt, in order, and the merges run one after the other (the kind lock already serializes them).
- **Resume.** A stopped load runs again from the Change Journal: a batch recorded as merged is skipped (`_recorded`), and
  the artifact store never overwrites, so a repeated prepare writes the same object.
- **What is dropped.** The work units and their claim, lease, heartbeat and report rows.
- **What stays (operator, 2026-11-15: start and completion, for OpenMetadata).** One run row a load: opened as `running`
  when the load starts, closed as `complete` when it ends; a stopped load leaves it `running` with the failed step named,
  and the rerun closes the same row. That is all the catalog reads to publish a Pipeline status
  (`pipeline_status_from_bookkeeping`: the run id, its state, the submission's kind, name and target, and `failed_steps`),
  so the publisher needs no change. Open: the catalog's quality results are read per unit (`quality.aggregate`), so a
  target at `off` publishes a run status but no per-unit quality result until that has another source.
- **The setting.** `bookkeeping: {grain: off}` on the target, read by `rules/driving.py` (skip `rules run` and `drive`, call
  the local runner) and refused by `rules check` for any other value until each grain is built.
- **Proof.** Load one GLEIF capture slice at `unit` and at `off` into two disposable stores: the same records, masters and
  links (counts and a content hash), and statements a bundle by `count_statements.py`.

Not started: the runner, the setting and the proof are the next three checklist parts.

## Checklist

- [ ] ~~The operator's rulings on the table above: the default grain and the sources that turn it off (one question at a time, with a recommendation)~~ deferred to 212: the remaining work is one backlog, in one ticket
- [x] The setting on the source file's target: `grain: run` (`unit` is the default; not `off`, which YAML reads as false), validated in `config.validate`: `test_a_grain_is_unit_or_run_and_a_run_grain_target_is_not_also_local` (2026-11-15 19:01 ET). Not done: a line in the Mapping Documents' pipeline sheet
- [x] Tests, each failing on the code before ("Unknown target option"): a run at `run` grain holds no unit and completes (`test_a_target_at_grain_run_holds_its_start_and_completion_only`, PostgreSQL and MySQL); a failed check leaves it running and it is worked again; the loader works such a run by one command and an open one again (`test_rules_loading.py`) (2026-11-15 19:01 ET)
- [x] The run's start and completion are recorded and nothing between: on a disposable store Bookkeeping held 1 run row and no work item, lease, checkpoint or outbox row, against 1 run and 6 of each at `unit` (2026-11-15 19:01 ET)
- [x] The loader runs every step (`local.work_run`, `rules run --work-run-id`, called by `load`), generic for any target. Proof on one N-CEN registrant quarter at each grain, two disposable stores: every MDM and silver table holds the same number of rows (14 non-empty tables, 1,413 rows); the journal holds the same batch and file records and lacks only Bookkeeping's 6 per-unit events; a second load loads nothing; 3.6 s against 6.1 s (2026-11-15 19:01 ET). Not done: GLEIF itself, which is loading on the hosted store at `unit` now; its switch needs the operator's word, since a changed rules file is a new processing identity
- [ ] ~~`bundle` and `load` grains~~ deferred: `run` gives what the operator asked for (off, with start and completion); a grain between is built when a source needs one
- [ ] ~~Each grain measured as statements a bundle (`count_statements.py`) and hosted seconds, on the persons capture~~ deferred to 238: every hosted part is one run, in one ticket
- [x] `grain: run` on every target (operator, 2026-11-15: "Turn on grain run for all sources", "implement it for ever source"): 25 of 27 targets. The two kept at `unit` are the N-PORT security `mastering` target, whose combine step the second-batch target reads as verified units, and that second-batch target, whose loader would have to read another run. `test_every_target_is_at_grain_run_except_the_two_joined_by_a_read_of_verified_units` (2026-11-15 20:31 ET)
- [x] The grain is no part of the processing identity, so the switch loads no file again: `test_the_rules_version_holds_the_steps_not_how_they_are_written` failed for all 25 targets (`{'grain': 'run'}` was in the identity) until `changed_files.source_rules` left it out (2026-11-15 20:31 ET)
- [x] A `local` target at `run` grain keeps the manifest it was given: the company load stopped at its first bundle ("Manifest must declare exactly the configured steps") because its local steps still ran before the run started. `test_a_local_target_at_grain_run_keeps_the_manifest_it_was_given` failed with "the manifest is not read before the run starts" before the fix (2026-11-15 20:31 ET)
- [x] A step's units run several at once at `run` grain (operator, 2026-11-15: "nothing stops OpenFIGI and company facts running several workers"): each unit in its own worker process, `--workers` of them. Company facts, forced again on the disposable store: 14 min with four workers against 38 min with one. The chain gives OpenFIGI answers and company facts four workers. `test_a_steps_units_run_several_at_once_each_in_its_own_process_and_give_the_same_receipts` (2026-11-15 20:31 ET)
- [x] Every target loaded at `run` grain on a disposable store, from the real captures, each to "Done" with every document: company (150 bundles), persons (149 bundles, 76,231 documents in 17 min), ownership and its symbols and silver (5,356 documents each), the N-CEN registrant, fund and adviser quarters and one class quarter, N-PORT registrant, fund and security silver, the Form ADV custodians, mastering and silver loads, 13F securities, their silver and the 13F filings, company facts, registrations, GLEIF sub-fund pairs. OpenFIGI answers: 10 of its 16 bundles complete when the store was stopped (the long load of the chain). (2026-11-15 20:48 ET)
- [ ] ~~GLEIF mastering loaded at `run` grain on a disposable store~~ not done: the whole publication is hours on a laptop; its steps (read, prepare, merge, links, journal) are the steps the other mastering targets proved
- [x] The integration tests that drive real targets through the unit protocol hold them by the unit (`targets_held_by_the_unit` in `tests/integration/conftest.py`): 14 failed in CI with `{} == {'verified': 4}` and missing outputs, since a run at `run` grain has no unit to claim; the nine files pass with it (2026-11-15 20:48 ET)
- [ ] ~~The N-PORT security pair at `run` grain~~ deferred: it needs a run at `run` grain to keep its units' receipts where another run can read them, which is a record Bookkeeping does not hold at this grain
- [ ] ~~The hosted store loads at `run` grain from the next load on (the hosted GLEIF load now running was started at `unit`); nothing is loaded again for the switch~~ deferred to 238: every hosted part is one run, in one ticket
- [x] Skills, second pass (operator, 2026-11-15: "fix the skill too"): bookkeeping (write `grain: run` on every target, the two kinds that keep `unit`, the two-step proof), data-onboarding (the target line), data-operations runbook (`--workers` adds nothing at `run`; raise `--bundles`) (2026-11-15 20:31 ET)
- [x] Skills: bookkeeping ("Grain": the two grains, what `run` keeps and gives up, how to prove a change) (2026-11-15 19:01 ET); data-onboarding and data-operations already point to it
- [ ] ~~Learning → skill~~ deferred to 212: the remaining work is one backlog, in one ticket
