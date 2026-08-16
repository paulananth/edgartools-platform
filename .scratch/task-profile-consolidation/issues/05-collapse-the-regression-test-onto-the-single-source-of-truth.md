# 05 — Collapse the regression test onto the single source of truth

**What to build:** `tests/architecture/test_gold_affecting_commands_task_sizing.py`
currently has to reverse-engineer three independent mechanisms (its own
docstring documents this as the reason it exists — `GOLD_AFFECTING_COMMANDS`
membership could previously resolve task memory through
`workflow_profile()`'s case statement, `write_warehouse_mdm_gold_definition`'s
hardcoded params, or `bootstrap-next`'s special case, with no link between
them). With ticket 04 done, rewrite the test to assert against the single
ticket 01 mapping directly — every `GOLD_AFFECTING_COMMANDS` member resolves
to at least the required profile via the one shared lookup, full stop.

**Blocked by:** 04

**Status:** ready-for-agent

- [ ] `test_gold_affecting_commands_task_sizing.py` asserts against the
      shared ticket 01 mapping, not three separately reverse-engineered
      mechanisms
- [ ] The test's own docstring/comments no longer describe a three-path
      problem — they describe the single dispatch point
- [ ] Full test suite green
