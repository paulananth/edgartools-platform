# Data profiling program

## Destination

Any data set can be profiled, classified into master, reference, relationship, transaction and metadata parts, and onboarded into MDM, RDM or silver by agents, generically. The program ends when the recreation proof's DIFF.md is accepted by the operator.

## Notes

- Plan: [plan.md](plan.md) (approved 2026-10-04). Genericity rule: SEC, Company and Person are examples only.
- Phase A starts now; phase B starts after Codex's old-parser retirement goal is merged.
- Path ownership: AGENTS.md / CLAUDE.md "Path ownership: data profiling program". Run `scripts/dev/overlap_guard.sh` before every commit and push.
- Each ticket: own branch and worktree, GoF consult before code, three-axis review, CI green, merge on the operator's word, checklist stamped in ET.

## Tickets

| # | Ticket | Phase | Blocked by | Status |
|---|---|---|---|---|
| 00 | [Ownership and overlap guard](issues/00-ownership-and-overlap-guard.md) | A | — | done (#823) |
| 01 | [Research note: classify, profile, RDM, agent context](issues/01-research-note.md) | A | 00 | done (#824) |
| 01a | [Specs: RDM, agent context, silver table spec, findings schema](issues/01a-specs.md) | A | 01 | done (#825) |
| 01b | [data-profiling skill and trials A and B](issues/01b-data-profiling-skill-and-trials-a-and-b.md) | A | 01a | done (#831) |
| 01c | [data-quality skill](issues/01c-data-quality-skill.md) | A | 01b | done (#832) |
| 02 | [RDM database, publish, MDM pin, migrate reference YAML](issues/02-rdm-database.md) | B | 01a, Codex retirement merged | open |
| 03 | [MDM cross-reference table](issues/03-mdm-cross-reference-table.md) | A | 01a | done (#835) |
| 04 | [Relationship context view and onboarding](issues/04-relationship-context-view-and-onboarding.md) | A | 01a | done (#836) |
| 04b | [Relationship types: real names; parents with a basis; corporate actions](issues/04b-parent-relationship-types.md) | A | 04 | open: ruled 2026-10-07 |
| 05 | [Agent context views and command](issues/05-agent-context-views-and-command.md) | A (MDM) / B (RDM) | 03, 04 (02 for RDM) | MDM part done (#837); RDM and silver in phase B |
| 06 | [Silver writer (rules-skill ticket 05)](issues/06-silver-writer.md) | B | 01a, Codex retirement merged | open |
| 07 | [Readers and custom parsing steps per feed](issues/07-readers-per-feed.md) | B | 01b inventory, Codex retirement merged | open |
| 07b | [Name-based matching](issues/07b-name-based-matching.md) | A | 03, 04 | done (#838) |
| 07c | [Unstructured extraction](issues/07c-unstructured-extraction.md) | B | 07 | open |
| 08 | [Recreation proof](issues/08-recreation-proof.md) | B | all above | open |

## Decisions so far

- See plan.md, decisions 1–49 (operator, 2026-10-04).
