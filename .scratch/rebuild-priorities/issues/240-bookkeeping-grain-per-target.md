# 240: Bookkeeping runs once a bundle or a load, and a source can turn it off

Type: task. Status: open (operator, 2026-11-15: "Run with no bookkeeping", then "Yes" to GLEIF first; then "i need be able to turn of bookkeeping for a source but must record start and completion alone to support open metadata"). Blocked by: none. Builds on ticket 232 (which leases the destinations already make redundant),
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
| `off` | the run's start and completion only; the loader runs the steps itself (as `local: true` does for read and combine) | the file: the Change Journal skips what was processed | two writes a load |

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

- [ ] The operator's rulings on the table above: the default grain and the sources that turn it off (one question at a time, with a recommendation)
- [ ] The setting in the source file's target (`bookkeeping:`), validated by `rules check`, in the Mapping Documents' pipeline sheet (`rules mapdoc write`), and in `rules/shape.py`'s expansion
- [ ] Failing tests first: a target at `off` takes no claim, lease or report and a rerun skips what the Change Journal recorded; at `bundle` a step is one unit; at `load` one run
- [ ] `off` records the run's start and completion in Bookkeeping, and nothing between; test: the catalog's Pipeline status is built from that row alone (Pending while running, Successful when complete)
- [ ] `off` and `load`: the loader runs the steps (generalizing `local: true`); a stopped load resumes from the journal. GLEIF first (operator, 2026-11-15); the build is described above, not started
- [ ] `bundle`: one unit a step, with its units run inside the worker
- [ ] Each grain measured as statements a bundle (`count_statements.py`) and hosted seconds, on the persons capture
- [ ] The grain chosen for each source, and the hosted loads of the changed sources run again, after the operator's word
- [ ] Skills: bookkeeping (the grain table and the rule), data-onboarding (the target setting), data-operations (resource sizing and the load runbook) as each grain is built
- [ ] Learning → skill
