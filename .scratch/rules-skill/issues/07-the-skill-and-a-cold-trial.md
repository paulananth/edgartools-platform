# The skill, then Company trials

Type: task
Status: open
Blocked by: 01 merged (the trials need `rules/` on `main`)

## Outcome

`skills/rules/SKILL.md` plus `agents/openai.yaml`, linked into
`~/.agents/skills/rules`. It has three modes: init, migrate and add.

Add works on any source. It:
- identifies the source and confirms it, or asks for its name;
- profiles the files;
- researches the repo and the source's public docs (never `sec.gov`);
- proposes kinds, identifiers, fields and relationships;
- asks one plain question at a time, each with a recommendation;
- writes the files;
- previews, validates, asks for approval, activates and deploys, to MDM first
  and then to silver.

Skill first (operator, 2026-09-26, answered between 16:15 and 16:21 ET): "skill first, however must test skill on company entity for each source from scratch and fine tune and fix the skill, the incorporate all company data pipelines and test".

## Checklist (times ET)

- [ ] The skill, and a link script.
- [ ] Trials, one per source that feeds Company, each from scratch:
  - SEC submissions Company;
  - GLEIF Level 1, relationships and reporting exceptions.

  How each trial runs:
  - A fresh agent gets only the skill and a `git archive` export with the
    source's `rules/sources/<source>/` folder deleted, plus the tests that
    restate its values. It keeps the parsers.
  - Inputs are captured files only: the three local GLEIF zips, and a small
    sample of SEC submissions copied from bronze (Apple, Microsoft, Shell,
    ASML and a few dozen more). There are zero SEC requests.
  - It logs every question it asks. Answers give facts only, and each
    question is tagged "the skill should have inferred it" or "a real
    operator decision". An approval is never simulated.
  - It is scored against the proven files: digest-equal is best; otherwise
    diff the kind, identifiers, fields, ranks and relationships.
  - Every difference is a skill fix, never an edit to the answer. Rounds
    repeat until a round needs no fix.
- [ ] Build only the commands a trial round shows the skill needs (tickets
  02–06 as a menu).
- [ ] All Company data pipelines on the skill, tested.
- [ ] Test: every command the skill names exists.
- [ ] `CLAUDE.md` Quick Navigation entries for the skill.
- [ ] Three-axis `/code-review` of any code, then PR and CI.
