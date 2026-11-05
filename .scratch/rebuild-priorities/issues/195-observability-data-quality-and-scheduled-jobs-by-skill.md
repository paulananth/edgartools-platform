# 195: Observability, data quality and scheduled jobs, run by a skill

Priority: 195. Map: [Rebuild priorities](../map.md). Opened 2026-11-05 06:35 ET (operator, 2026-11-05: "need to build
observability and data quality also be able to schedule jobs using skills").

Type: grilling. Status: open. Blocked by: 194 (the timings say what to watch).

## Question

What does the platform show an operator while and after a load runs (progress, time per step, failures, data quality),
and how does a skill schedule a recurring load, so that no one reads database tables to find out?

## What exists (read, not built here)

- Timings today come from reading Bookkeeping and the database by hand (ticket 194 did this for every source).
- The `data-quality` and `pipeline-orchestration` skills exist; the OpenMetadata catalog belongs to Codex (ticket 181).
- `data-operations` covers recurring loads.

## Checklist

- [ ] Decide what an operator must see during a load: progress per step, time per step, failures, the slow statement.
- [ ] Decide which data quality checks run on every load and where their counts are shown (the `data-quality` skill).
- [ ] Decide how a skill schedules a recurring load (the schedule, the permission to fetch, the end condition).
- [ ] Split into build tickets once decided. Do not build before the ticket 194 fix, which sets what is worth watching.
- [ ] Learning → skill: name the skill line changed, or "none".
