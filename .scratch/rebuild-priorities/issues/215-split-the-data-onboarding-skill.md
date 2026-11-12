# 215: The `data-onboarding` skill is split behind pointers

Priority: 215, housekeeping. Map: [Rebuild priorities](../map.md). Opened 2026-11-11 19:31 ET (operator: "split the long skills one per PR"). Part of [214](214-skills-organized-one-index-one-link-script.md).

Type: task. Status: resolved (2026-11-11 19:31 ET).

## Checklist

- [x] (2026-11-11 19:31 ET) `skills/data-onboarding/SKILL.md` goes from 1032 to 488 lines. Whole sections move unchanged to `MAP.md`, `TARGETS.md`, `TEST.md`; each heading stays in `SKILL.md` with one line saying when to read the file, so links to those headings still land. Verified by the move script: no line lost
- [x] (2026-11-11 19:31 ET) Ticket-citation and genericity lints pass; every relative link in the skill resolves; the doctor's skill check (`bundle.unresolved`) returns nothing
- [x] (2026-11-11 19:31 ET) `tests/unit/test_rules_skill_commands.py` also reads `MAP.md` and `TEST.md`, so the `rules` commands that moved with them stay checked. Verified: 12 passed with the main checkout's environment
- [x] (2026-11-11 19:31 ET) Learning → skill: none here; the rule and its lint land with ticket 214's closing PR
