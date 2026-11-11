# 213: The agent guides hold each rule once

Priority: 213, housekeeping. Map: [Rebuild priorities](../map.md). Opened 2026-11-11 18:48 ET (operator: "review current repo claude.md and agents.md and organize").

Type: task. Status: resolved (2026-11-11 18:48 ET).

## What was found

- **AGENTS.md had drifted back into a copy.** Its "How to work in this repo (every runtime)" section repeated over twenty of CLAUDE.md's rules, and three had drifted: it still said to stop for an approval (CLAUDE.md: do not ask, operator 2026-10-17), it lacked the `merge_on_green.sh` rule, and it lacked the fix-PR rule.
- **Three every-runtime rules lived only in AGENTS.md**, which no Claude session loads: build generic, integer widths and number types. CLAUDE.md reached the integer rule by a link.
- **CLAUDE.md scattered one meaning across sections.** "Say the time of a step over ten minutes" appeared three times, the affected-tests rule twice, the branch rules in two sections, and two skill pointers sat under "What belongs in this file".
- **One AGENTS.md rule was stale:** the ownership parser's `edgartools` imports. No file under `edgar_warehouse/` imports `edgar`, and `edgartools` is not a dependency.

## Checklist

- [x] (2026-11-11 18:48 ET) CLAUDE.md regrouped, every rule kept: pointers in one "Skills and guides" list; branch rules together under "Parallel work"; the guard and `commit_push.sh` under "Path ownership"; "How to work" split into Tests, Merging, Long steps and runs, Commits, Talking, Code and stores, Debugging; "Shared local data" split into Loads, The shared server, Writing to it. Verified by reading the diff rule by rule
- [x] (2026-11-11 18:48 ET) Build generic and the number types (integer widths merged in) moved from AGENTS.md to CLAUDE.md, "Code and stores"; `skills/mdm-engineering/SKILL.md` now cites CLAUDE.md for build generic
- [x] (2026-11-11 18:48 ET) AGENTS.md cut from 226 to 61 lines: the copied section, the scope paragraph and the copied GoF lines replaced by the pointer to CLAUDE.md; kept the handoff rule, tooling, the GoF additions, data notes, safety rules and reference pages
- [x] (2026-11-11 18:48 ET) Moved, not dropped: the deploy validation commands and the Snowflake status query to `docs/agents/snowflake.md`. Already held elsewhere, so removed from AGENTS.md: the testmon and docs-only recipes (`docs/agents/watching-and-testing.md`), the "same calendar day" timezone and provisioning rules (`skills/aws-snowflake-operations/SKILL.md`)
- [x] (2026-11-11 18:48 ET) Dropped: the stale `edgartools` import rule, and the two local `pytest` folder commands (the CI workflow shows them)
- [x] (2026-11-11 18:48 ET) Decision under the standing rule (operator, 2026-10-17: "auto merge and not ask for approval"): Codex and Grok now follow CLAUDE.md's wording on approvals, since the section was headed "every runtime" and AGENTS.md's wording was the older copy. This is the one change of behaviour in the ticket
- [x] (2026-11-11 18:48 ET) Guide-path and genericity lints pass (`tests/unit/test_guides_name_existing_paths.py`, `tests/unit/test_profiling_genericity.py`)
- [x] (2026-11-11 18:48 ET) Learning → skill: `CLAUDE.md`, "What belongs in this file": every shared rule lives in CLAUDE.md once, and AGENTS.md's opening names CLAUDE.md as the one that rules where they differ
