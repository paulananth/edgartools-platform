# 166: Port what main lacks from the grok catalog branch

Priority: 166. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 06:53 ET (operator, 2026-11-02: "yes, review the grok diffs and port what main lacks").

Type: task. Status: resolved. Blocked by: none.

## Question

`grok/catalog-follow-up-20261030` held 2 commits never pushed (9 skill files changed). Which of their text does `main` lack?

## Parts

- [x] Read both diffs against main's skills (2026-11-02 06:53 ET)
- [x] Main already holds the rest, reworked: the data and catalog order, the three facts, the owner-skill list, the domain type and layer placement, the classifications and certification, the data product package, the Relations Graph (now in `skills/openmetadata/SKILL.md`) (2026-11-02 06:53 ET)
- [x] Left out as out of date: the shared glossary, "the plan emits no product", and the deleted `OPENMETADATA.md` reference (2026-11-02 06:53 ET)
- [x] Ported the one missing fact: the Multiple Domains rule lives in `entityRulesSettings` (`skills/openmetadata/SKILL.md`, genericity lint passes, 2026-11-02 06:53 ET)
- [x] Learning → skill: the line above
