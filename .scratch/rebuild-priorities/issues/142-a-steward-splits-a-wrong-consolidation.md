# 142: A steward splits a wrong consolidation

Priority: 142. Map: [Rebuild priorities](../map.md). Opened 2026-10-27 20:36 ET.

Type: task. Status: resolved.
Blocked by: none. Comes from [138](138-one-security-mastering-by-cross-reference.md)'s
follow-up line (operator, 2026-10-25, a wrong automatic consolidation: "Steward
splits + exclusion": a steward splits it, both ids return, a Match Exclusion
stops the same records merging again; the Identifier Contract's tolerance still
switches matching off).

## Question

How does a steward record the split of a consolidation a matching rule made, and
what does the operator see before and after it?

## What is known

- The engine already accepts it. A `reverse` decision naming a `merge` restores
  both masters on replay, and a reversed merge counts as a Match Exclusion: a
  later record reaching the pair goes to review as `excluded_consolidation` and
  proposes nothing (138 part A2a,
  `test_an_excluded_pair_goes_to_review_and_nothing_is_proposed`;
  `test_reversed_merge_ignores_unused_survivor_and_dependency_metadata`).
- No operator command writes that decision: `edgar-warehouse mdm` has no
  steward command, and the agent context shows a merge but cannot record its
  reversal.

## Parts

- [x] Decide the command's shape (2026-11-03 15:50 ET; operator, 2026-11-03: "Accept recommendations"): the merge is named by its decision id (the id the agent context shows); the stewardship login runs it with `--by` and `--reason` required and recorded; it previews unless `--confirm`; a split is never undone silently
- [x] Built through the Merge Stage on PostgreSQL and MySQL (2026-11-03 15:50 ET): `edgar-warehouse mdm steward split --merge <id> --by <name> --reason <words> [--confirm]` (`mdm/clean/steward.py`, one batch of its own consumer); `tests/storage_adapters/test_steward_split.py` on both engines: a preview writes nothing, the confirmed split returns both masters, a second split and an unknown merge are refused. Failing before: no command (`mdm steward` did not parse). The next delivery of the same records going to review was proven by the engine tests of ticket 138 (`test_an_excluded_pair_goes_to_review_and_nothing_is_proposed`)
- [x] The agent context shows a split and its exclusion (2026-11-03 15:50 ET): `context` lists `splits` on each restored master (the merge, the partner master, who, why, when, excluded) — checked on both engines in the same scenario
- [x] Tests (2026-11-03 15:50 ET): tests/mdm, tests/unit, tests/architecture (2476); the master-read scenarios on PostgreSQL and MySQL (8 each) pass with the context change
- [x] Learning → skill (2026-11-03 15:50 ET): `skills/mdm-engineering/SKILL.md` — a wrong consolidation is split by a steward command, and a reversal is found by the merge it names
