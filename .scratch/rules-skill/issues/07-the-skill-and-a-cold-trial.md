# The skill and a cold trial

Type: task
Status: open
Blocked by: 04, 05, 06

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

## Checklist (times ET)

- [ ] The skill, and a link script.
- [ ] Test: every command the skill names exists.
- [ ] Cold trial: a fresh agent onboards an unseen non-SEC source end to end,
  locally, with no engine edits.
- [ ] `CLAUDE.md` Quick Navigation entries.
- [ ] Three-axis `/code-review`, then PR and CI.
