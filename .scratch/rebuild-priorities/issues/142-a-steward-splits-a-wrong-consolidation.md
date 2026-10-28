# 142: A steward splits a wrong consolidation

Priority: 142. Map: [Rebuild priorities](../map.md). Opened 2026-10-27 20:36 ET.

Type: task. Status: open, not started.
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

- [ ] Decide the command's shape (what names the merge, who may run it, what it
  prints) with the operator
- [ ] Build it through the Merge Stage on PostgreSQL and MySQL, with a test that
  a split restores both masters, their listings and links, and that the next
  delivery of the same records goes to review
- [ ] The agent context shows a split and its exclusion
- [ ] Tests, three-axis review, PR, CI green, merge
- [ ] Learning → skill
