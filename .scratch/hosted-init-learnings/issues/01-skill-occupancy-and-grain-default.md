# Skill occupancy and grain: run as the load default

Status: claimed
Type: task

## Parts

- [x] Occupancy in change-journal Init: hosted instance extension schemas (`extension_base`, `extension_updater`) proceed; leftover business tables refuse with "Journal database must hold only the journal." Skill text, 2026-11-15 21:31 ET.
- [x] Grain: run as the load default in data-operations Load a capture ("no bookkeeping" = that grain; Bookkeeping still inits and writes the run row). Skill text, 2026-11-15 21:31 ET.
- [x] One-command owner URL form `env KEY=value command args` in data-operations Apply store DDL, with occupancy pointer. Skill text, 2026-11-15 21:31 ET.
- [ ] ~~Invert the bookkeeping grain table so an unnamed target is `run`~~ deferred to grain-on: `skills/bookkeeping/SKILL.md` is open on `claude/grain-run-all-sources`.
- [ ] ~~STORES.md / RUNBOOK / aws-snowflake hosted pointers~~ deferred: unique diffs on hosted-fresh (`STORES.md`, aws-snowflake) and grain-on (`RUNBOOK.md`).
- [ ] ~~Occupancy engine allowlist~~ deferred to journal-guard: `claude/journal-guard-platform-tables` already holds the code and test; this ticket is skill-only.
- [x] Genericity and guide-path tests on the skill edits. `uv run --no-project --with pytest -- pytest -q -p no:cacheprovider tests/unit/test_profiling_genericity.py tests/unit/test_guides_name_existing_paths.py` 119 passed, 2026-11-15 21:31 ET.
- [x] Publish the skill PR from `grok/hosted-skill-learnings`. https://github.com/paulananth/edgartools-platform/pull/1823 head 46afddf4, 2026-11-15 21:31 ET.
- [x] Trim `skills/data-operations/SKILL.md` below 500 lines (`test_every_skill_file_is_short_enough_to_read_whole` failed at 505). Keep occupancy pointer, `grain: run`, and load-chain lanes. 2026-11-15 21:49 ET
- [x] Learning → skill: change-journal Init (hosted occupancy); data-operations Load a capture (`grain: run` default) and Apply store DDL (`env KEY=value`, occupancy pointer). 2026-11-15 21:31 ET.

## Scope

Hosted initialize then load all sources hit two skill gaps: occupancy treated the instance's own extension schemas as leftover tables, and "load with no bookkeeping" is `grain: run` on the target, not a missing Bookkeeping init. Operator: fix the skill; do not change code; make grain: run the default.

Engine occupancy allowlist and grain-table inversion stay on the Claude trees that already hold them. This ticket writes the skill homes only.
