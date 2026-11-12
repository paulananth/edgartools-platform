# 214: The skills are organized: one index, one link script, no ticket citations

Priority: 214, housekeeping. Map: [Rebuild priorities](../map.md). Opened 2026-11-11 19:22 ET (operator: "now review the skills and organize them too").

Type: task. Status: open.

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
- [ ] `security-master` (12) and `company-financials` (8): the remaining citations sit in sentences that say what is live and what waits for a switch-on, or point to evidence. Rewriting them needs a check of each against the rules as they are now
- [x] (2026-11-11 19:23 ET) `bookkeeping` (5 citations removed) and `openmetadata` taken over on the operator's word (2026-11-11 19:23 ET: "take over bookkeeping and openmetadata skill files tool"). The overlap guard stops on `skills/bookkeeping/SKILL.md`, held by the worktree of `codex/bookkeeping-openmetadata-20261105` (last commit 2026-11-05); the commit goes ahead under that word. `openmetadata` cites no ticket and needs no edit here; the lint now covers both
- [ ] `openmetadata/SKILL.md` is 851 lines: move its local-server and rebuild sections behind pointers after open PR #1684 merges, since that PR adds 248 lines to the same file
- [ ] Dates and run figures: about 200 dates remain in the skills, most inside an operator's quoted ruling. Decide whether the rule covers those
- [ ] `data-onboarding/SKILL.md` is 1,032 lines; five more are over 500. Move reference tables behind a pointer, one skill per PR
- [ ] Learning → skill: `skills/README.md`, "What a skill holds"
