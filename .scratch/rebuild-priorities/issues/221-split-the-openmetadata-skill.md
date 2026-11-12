# 221: The `openmetadata` skill is split behind pointers

Priority: 221, housekeeping. Map: [Rebuild priorities](../map.md). Opened 2026-11-11 19:32 ET (operator: "split the long skills one per PR"). Part of [214](214-skills-organized-one-index-one-link-script.md).

Type: task. Status: resolved (2026-11-11 19:32 ET).

## Checklist

- [x] (2026-11-11 19:32 ET) `skills/openmetadata/SKILL.md` goes from 942 to 479 lines. Whole sections move unchanged to `CONTEXT-CENTER.md`, `LOCAL-SERVER.md`, `READBACK.md`; each heading stays in `SKILL.md` with one line saying when to read the file, so links to those headings still land. Verified by the move script: no line lost
- [x] (2026-11-11 19:32 ET) Ticket-citation and genericity lints pass; every relative link in the skill resolves; the doctor's skill check (`bundle.unresolved`) returns nothing
- [x] (2026-11-11 19:32 ET) Edited on the operator's word (2026-11-11: "take over bookkeeping and openmetadata skill files"), after PR #1684 merged
- [x] (2026-11-11 19:32 ET) Learning → skill: none here; the rule and its lint land with ticket 214's closing PR
