# 195: Observability, data quality and scheduled jobs, run by a skill

Priority: 195. Map: [Rebuild priorities](../map.md). Opened 2026-11-05 06:35 ET (operator, 2026-11-05: "need to build
observability and data quality also be able to schedule jobs using skills").

Type: task. Status: in progress. Blocked by: none (ticket 194 is resolved; the operator accepted the measured speed).

## Question

What does the platform show an operator while and after a load runs (progress, time per step, failures, data quality),
and how does a skill schedule a recurring load, so that no one reads database tables to find out?

## Operator ruling (2026-11-05, asked with a recommendation)

First piece: **load progress and timings**, built on the profile tool already merged. Data quality counts per load and
scheduling a recurring load follow.

## What exists

- `skills/data-operations/scripts/profile_load.py`: `progress` (units per step and state of the running runs, how long
  they have run), `steps` (time per step of a finished run), `sample` (what the database ran). Each is read-only and
  prints counts, times and statement shapes, never a value from the data.
- The `data-quality` and `pipeline-orchestration` skills exist; the OpenMetadata catalog belongs to Codex (ticket 181).
- `data-operations` covers recurring loads.

## Checklist

- [x] Decide the first piece: load progress and timings (operator, 2026-11-05).
- [x] `progress` view: units per step and state, share verified, run age; it also lists runs left `running` by a stopped load (11 on the local store). Test: `test_progress_groups_units_by_step_in_run_order_with_the_verified_share`; run on the local store, 2026-11-05 17:37 ET.
- [ ] Failures in a load: which unit failed, at which step, with the engine's own error class (the load log holds a path today).
- [ ] Which data quality checks run on every load and where their counts are shown (the `data-quality` skill).
- [ ] How a skill schedules a recurring load (the schedule, the permission to fetch, the end condition).
- [ ] Split into build tickets once decided.
- [x] Learning → skill: `data-operations` "Measure a slow load with `scripts/profile_load.py`" now names `progress`.
