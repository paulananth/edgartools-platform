# Gold is built at init, and a mastering step's progress is read from MDM

Status: resolved
Type: task
Owner: claude (operator, 2026-11-27: "do the skill PR and clean up the worktrees", "dbt build must be part of init not part of load")

The seven-wastes review of `aws-20261127` (execution 3: 17:42:50 to 18:57:35 ET, succeeded) found two things a skill should say.

- Motion: counting `gleif`'s progress took four tries. The monitor login (`ops_reader`) holds `pg_monitor` and no SELECT on MDM, the
  tables are in schema `mdm`, and the engine logs a step's count only when its run ends. Read as the worker login, read-only, MDM held
  2,838,657 mastered and 589,820 deferred `gleif.level1.v1` records at the end, together the file's `record_count` of 3,428,477.
- The Gold build had no place in init: the initialize runbook has no Gold step after the mirror (8b), and tickets 01 here and 23 of
  hosted-mirroring plan `dbt build` after the load.

## 5 whys (the Gold build)

1. `dbt build` was planned after the load.
2. Gold acceptance was written as "the load, then Gold", and no runbook step owned the build.
3. Gold is views over the mirror, which carries each load's writes by change capture.
4. A view built once reads every later load; only a change of Gold's configuration needs a new build.
5. So the build belongs where the mirror is made, at init, and a load adds no Gold step.

## Checklist

- [x] HOSTED-LOADS "While a load runs": a mastering step's progress is read from MDM as the worker login (read in the diff) (2026-11-27 19:00 ET)
- [x] Initialize runbook step 8c: Gold is built once at init with `dbt build` as the Gold writer; a load adds no Gold step; `dbt test` reads the links after a load (read in the diff) (2026-11-27 19:00 ET)
- [x] data-modeling GOLD.md: the build is an init step, never a step of a load (read in the diff; the operator's words stay in this ticket, since skills hold no dates) (2026-11-27 19:00 ET)
- [x] Worktrees: ten merged or closed `claude/` worktrees removed with their local branches, none with changes (`git status --porcelain` empty each); `sg-text` kept while its launcher exits (2026-11-27 19:00 ET)
- [x] Learning → skill: data-operations HOSTED-LOADS (reading a mastering step's progress), data-modeling GOLD.md and the initialize runbook (Gold built at init) (2026-11-27 19:00 ET)
