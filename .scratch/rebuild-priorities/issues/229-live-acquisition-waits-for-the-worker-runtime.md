# 229: Live acquisition waits for the worker runtime on AWS

Priority: 229. Map: [Rebuild priorities](../map.md). Opened 2026-11-12 06:02 ET (operator: "move the unfinished live pipelines line to a ticket").

Type: task. Status: open.

## The open item, moved from the `data-onboarding` skill

The skill's Examples held this line as "the one list" of unfinished live pipelines, and `refining-rules` pointed to it:

> live acquisition (`provider.capture`, qualified offline) waits for the worker runtime on AWS. A source's pipes switch on over captured files without it.

The rule in the second sentence stays in the skill where it already was: switching on a source's pipes and switching on live data are apart.

## Checklist

- [x] (2026-11-12 06:02 ET) The line is out of `skills/data-onboarding/SKILL.md`, and the pointer to it is out of `skills/refining-rules/SKILL.md`. Verified: no skill, guide or doc names "Unfinished live pipelines" any more (grep); ticket-citation and genericity lints pass; the `rules` command tests pass
- [ ] Live acquisition through `provider.capture` runs on the worker runtime on AWS (it is qualified offline today)
- [ ] Learning → skill
