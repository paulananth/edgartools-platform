# 214: The skills are organized: one index, one link script, no ticket citations

Priority: 214, housekeeping. Map: [Rebuild priorities](../map.md). Opened 2026-11-11 19:22 ET (operator: "now review the skills and organize them too").

Type: task. Status: resolved (2026-11-12 06:13 ET).

## What the review found (21 skills, about 23,800 lines)

- **No map of the skills.** Twenty-one folders, and only each skill's own description said when to open it.
- **Thirteen copies of one link script**, the same but for the skill's name, and eight skills had none, so they could not be linked for an agent at all.
- **147 ticket citations in 19 files**, against the standing rule that a skill holds the rule and the method only (operator, 2026-11-05).
- **One stale pointer:** `mdm-engineering` sent readers to `AGENTS.md`, "Tests and CI", which ticket 213 removed.
- **Little copied text:** 9 lines of 80 characters or more appear in two or more skills. No merge of skills is needed.
- **Held by another runtime, so not edited:** `skills/bookkeeping/SKILL.md`, `skills/bookkeeping/OBSERVABILITY.md` and the `openmetadata` skill.

## Checklist

- [x] (2026-11-11 19:22 ET) `skills/README.md`: every skill in one table, grouped by the task it serves, with what a skill holds. Verified by `test_every_skill_is_in_the_index`, which failed when one row was removed
- [x] (2026-11-11 19:22 ET) `skills/link.sh [--home directory] [skill ...]` replaces the thirteen copies and links any of the 21. Verified against temporary home folders: all 21 linked, a second run changes nothing, an existing path is refused (exit 1) with nothing linked, an unknown skill exits 2
- [x] (2026-11-11 19:22 ET) 122 ticket citations removed from 17 files, each sentence keeping its rule. Verified by `tests/unit/test_skills_cite_no_ticket.py`, which failed on the old `mdm-engineering` text (20 citations found, none allowed)
- [x] (2026-11-11 19:22 ET) The lint counts the 25 citations that remain, file by file, so a new one fails and a removed one lowers the count (20 after the bookkeeping part below)
- [x] (2026-11-11 19:22 ET) `mdm-engineering` points to `CLAUDE.md`, "Tests"; `change-journal`'s spec names the one link script; `CLAUDE.md` points to the skills index
- [x] (2026-11-11 19:22 ET) Lints pass: ticket citations, genericity and guide paths (99 passed); every relative link in a skill resolves
- [x] (2026-11-12 06:13 ET) `security-master` (12) and `company-financials` (8): the last citations are gone and the lint allows none: [228](228-rulings-skills-hold-no-ticket-date-or-run-count.md), PR #1699
- [x] (2026-11-11 19:23 ET) `bookkeeping` (5 citations removed) and `openmetadata` taken over on the operator's word (2026-11-11 19:23 ET: "take over bookkeeping and openmetadata skill files tool"). The overlap guard stops on `skills/bookkeeping/SKILL.md`, held by the worktree of `codex/bookkeeping-openmetadata-20261105` (last commit 2026-11-05); the commit goes ahead under that word. `openmetadata` cites no ticket and needs no edit here; the lint now covers both
- [x] (2026-11-12 06:13 ET) `openmetadata/SKILL.md` split after PR #1684 merged, 942 to 479 lines: [221](221-split-the-openmetadata-skill.md), PR #1692
- [x] (2026-11-12 06:13 ET) Dates and run figures removed from every skill (operator, 2026-11-12 06:13 ET: "remove the dates and run figures from the skills too also make skills focused on the task or the function it is created for"): tickets 222 to 228 and 230, PRs #1693 to #1699 and #1705; the profiling scripts' eight ruling dates in this PR. Three dates stay and are counted by the lint: two folder names in a path, one example of a refused value
- [x] (2026-11-12 06:13 ET) The seven skills over 500 lines are split, one per PR: tickets 215 to 221, PRs #1686 to #1692. The longest `SKILL.md` is now 491 lines
- [x] (2026-11-12 06:13 ET) Focus: every section of every skill was read against the purpose its description states. Nothing needed to move between skills; what was off a skill's function was history, removed in the PRs above, and two backlogs, now tickets [227](227-aws-snowflake-operations-holds-rules-not-history.md) and [229](229-live-acquisition-waits-for-the-worker-runtime.md), both open
- [x] (2026-11-12 06:13 ET) Lints that keep it so, in `tests/unit/test_skills_cite_no_ticket.py`: no ticket citation, only the three counted dates, every `SKILL.md` under 500 lines. Each failed when its rule was broken once (a date added; 450 lines added) and passes restored. `scripts/dev/move_skill_section.py` is the committed tool for the next split
- [x] (2026-11-12 06:13 ET) Learning → skill: `skills/README.md`, "What a skill holds": no ticket, pull request, date or run figure; a limit is a rule; `SKILL.md` under 500 lines, sections moved whole behind a pointer
