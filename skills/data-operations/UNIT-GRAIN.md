# By the unit

Read this only for a target that does not say `grain: run` (a target another target reads as verified units,
and the target that reads it), or for a run started by the unit. Every other load is in [SKILL.md](SKILL.md).

By the unit, Bookkeeping holds every unit of every step: a claim, a lease, a heartbeat, a check and a report.

## When it stops

| You see | It means | Do this |
| --- | --- | --- |
| `workers work <operation> ... failed with status 1; its message is in <log>` | A worker could not finish a unit. | Read that log (`load-errors.log` in the stores folder), fix the cause, and run the same command again. The unit is tried again first. A transient database error (a deadlock, a closed connection) clears on that retry. A retry that fails the same way ("Artifact hash mismatch": an earlier run left a different file at the output path) cannot be resumed: `load` names that run, leaves it as it is and loads its documents again in a new run from the Change Journal. Give each load its own `--as-of` (the default is now), because the output folder is named by it and a reused one collides with an earlier run's files. |
| `step <s>: unit <u> failed (<error>)` | A unit failed and is still failing. | Run `bookkeeping status <run> --step <s>` to see its error, fix the cause, and run the same command again. |

A unit left `waiting` with `Lease or prerequisite contention; retry on
resume` is not a failure: a worker found its prerequisites or leases busy.
`load` claims it again on the next pass, and waits a few seconds when a pass
moved nothing (a lease from a stopped worker has not expired yet).
(`bookkeeping resume` resets only the run's state, not such a unit.)

An open run is driven by the steps it was frozen with, so a later rules
version never changes a run already under way. Two kinds of run are reported
and left as they are, and their documents load again in a new run (the Change
Journal never recorded them): a blocked run frozen under a retired rules
version, and an open run pinned to other worker code, which no later checkout
can finish ("Pinned worker runtime changed; start a new run").

## While it runs

- **Finish open runs with `load`, never by hand.** `load` finishes what is
  open and runs the later steps. Driving `workers work`
  yourself skips the later steps, and a bare `--reports`
  path (it needs a `file://` address) marks the unit `waiting`.
- **Leave worker code alone** (`edgar_warehouse/workers/*`). A run pins its
  worker runtime and stops on a change ("Pinned worker runtime changed;
  start a new run"). Change code between loads.
- **Size the lease to the slowest claim, not to the work.** A step that
  reads another run's output rechecks that run on every claim and report,
  which can outlast the default 120 s lease ("Stale lease"). The target sets
  `lease_seconds` and `heartbeat_seconds`.
- **A target that reads another target's runs** (`{run: {source, target,
  step}}`, [Bookkeeping SPEC](../bookkeeping/SPEC.md)) loads after that
  target. The comments in `rules/source-sequence.yaml` give the order.

## Quality results in the catalog

For a completed run whose frozen steps requested version-2 silver quality evidence,
`edgar-warehouse rules catalog publish --bookkeeping-run <run-id>` sends only
verified per-unit outcomes with stable run, step and opaque unit references,
then requires exact timestamped OpenMetadata readback. Use
`edgar-warehouse rules catalog check --bookkeeping-run <run-id>` for a
read-only confirmation later. An incomplete run remains unknown and cannot
publish. The publish reconciles the whole catalog plan, not only the quality
results: run it from a checkout at current `origin/main`, or it removes
catalog objects the current rules describe. The quality results themselves
are keyed by timestamp and survive that reconcile. Keep `SILVER_QUALITY_EVIDENCE_V2` unset until
[Enable a new receipt format](../bookkeeping/RECOVERY.md#enable-a-new-receipt-format)
is met. Catalog
entries describe the load and its checks; OpenMetadata does not run or resume
the pipeline.

## Underneath `load`

`load` runs the same steps you can run by hand when diagnosing: `mdm
prepare-capture`, `rules run`, `workers work <operation> <run>` (several in
parallel; a lease keeps two off the same unit), and
`bookkeeping finalize <run>` ([Bookkeeping run](../bookkeeping/RUN.md)).
