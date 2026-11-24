# 07: skills that own one thing each, hand off on both sides and touch regularly

Status: open
Type: task

Operator, 2026-11-24: "Review all skills and make each skills ownership clean and clear and inputs and SIPOC clear understanding they all should
work together an have handshake and regular touch point especially monitoring and operations skills".

## 5 whys

1. Why did a load stall without the monitor, operations and database skills acting together? None of the three named the others (load-monitoring
   named only data-operations; production-support named neither monitoring skill; database-monitoring named neither load-monitoring nor
   production-support): 15 one-way mentions among the operations skills, measured by reading the skills' links.
2. Why? Each skill was written for its own task, and the hub (data-platform) lists the phase owners, not the monitoring ones.
3. Why does nothing catch it? No page says what each skill owns, takes in and gives out, and nothing tests that a hand-off is written on both sides.
4. Why did that cost time? A stall needed the operator to say which skill to look at (the runtime, the lane budget, the database).
5. Root cause: no single ownership contract, and no test of its handshakes.

## 7 wastes

| Waste | Where | Fix |
|---|---|---|
| Waiting | A stall waited for the operator to name the next skill | Each monitoring skill hands to the next by name |
| Motion | Finding the owner meant reading several skills | One table: owns, inputs, outputs, hands off to, receives from, touch point |
| Defects | Skills restated each other's procedures and drifted | One owner per decision; the others link |
| Others | None found | |

## Parts

- [x] Read every skill's description and link the operations group's mentions of one another: 15 one-way mentions found, 2026-11-24 14:42 ET
- [x] `skills/OWNERSHIP.md`: the contract table (29 skills), the SIPOC of a load, the regular touch points, the rules of the handshake, 2026-11-24 14:42 ET
- [x] Failing test first: `tests/unit/test_skill_ownership.py` fails on a one-sided hand-off (`load-monitoring receives from data-operations, which does not
  hand off to it`) and passes with both sides written; it also holds one row per skill and that the four operations and monitoring skills touch, 2026-11-24 14:42 ET
- [x] A Handshake section in each operations and monitoring skill (data-operations, load-monitoring, database-monitoring, production-support,
  pipeline-orchestration, bookkeeping, change-journal, access-audit, openmetadata-deploy), 2026-11-24 14:42 ET
- [ ] The other 20 skills' own Handshake sections: their rows exist; their `SKILL.md` text names the same hand-offs as the table
- [ ] Each owner reviews its row (the rows were written from each skill's description and the README, not from the owner's word)
- [ ] data-platform's decisions table (499 lines, at the limit) routes to the monitoring skills: move a section to a sibling file first
- [ ] Learning → skill: OWNERSHIP.md and the README say it; a new skill adds its row in the same pull request
