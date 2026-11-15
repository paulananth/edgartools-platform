# 240: Bookkeeping runs once a bundle or a load, and a source can turn it off

Type: task. Status: open. Blocked by: none. Builds on ticket 232 (which leases the destinations already make redundant),
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
| `off` | nothing: the loader runs the steps itself (as `local: true` does for read and combine) | the file: the Change Journal skips what was processed | none |

What a coarser grain gives up, and what already stands in for it:

- **A lease's exclusion of a second writer of one unit.** The destinations protect themselves (ticket 232): the artifact store
  never overwrites, the kind lock serializes a merge, a silver table has its lock and key, the journal a unique key. No
  destination checks a lease proof: the guard that would (`bookkeeping_guard`, `destinations.guard`) has no caller, and ticket
  232 part 3 deletes it. So dropping the lease gives up only that one unit is not done twice, and the chain already refuses a
  second load of one source and target.
- **Per-unit retry and audit.** A rerun skips the files the Change Journal records (a file is recorded once its merge is
  verified), and every step is a deterministic function of its input.
- **Parallel workers on one step.** `off` and `load` run a step in the loader's process (it can still use its own threads).
- **Progress in `bookkeeping status`.** The load log reports each bundle; a target at `off` has no run to inspect.

Recommendation: `bundle` as the default for the sources loaded in bundles (persons, SEC company, ownership, OpenFIGI); `off`
for the silver-only sources and the one-document deliveries (one claim is the whole load); `unit` for GLEIF, whose merge
units are long and where a unit-level resume earns its cost.

## Checklist

- [ ] The operator's rulings on the table above: the default grain and the sources that turn it off (one question at a time, with a recommendation)
- [ ] The setting in the source file's target (`bookkeeping:`), validated by `rules check`, in the Mapping Documents' pipeline sheet (`rules mapdoc write`), and in `rules/shape.py`'s expansion
- [ ] Failing tests first: a target at `off` takes no claim, lease or report and a rerun skips what the Change Journal recorded; at `bundle` a step is one unit; at `load` one run
- [ ] `off` and `load`: the loader runs the steps (generalizing `local: true`); a stopped load resumes from the journal
- [ ] `bundle`: one unit a step, with its units run inside the worker
- [ ] Each grain measured as statements a bundle (`count_statements.py`) and hosted seconds, on the persons capture
- [ ] The grain chosen for each source, and the hosted loads of the changed sources run again, after the operator's word
- [ ] Skills: bookkeeping (the grain table and the rule), data-onboarding (the target setting), data-operations (resource sizing and the load runbook) as each grain is built
- [ ] Learning → skill
