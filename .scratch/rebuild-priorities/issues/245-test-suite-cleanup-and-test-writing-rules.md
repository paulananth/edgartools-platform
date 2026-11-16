# 245: Test-suite cleanup and the test-writing rules

Type: task. Status: resolved. Blocked by: none.

## Why

Operator, 2026-11-16: an audit of the suite (tautological, structure-sensitive and mismatched-mock tests), then
"clean this all up and make this a rule to be followed when you are writing tests".

## Checklist

- [x] Delete the tests that read a shell or Terraform file and assert its text (`test_prod_deploy_safety.py`,
  `test_mdm_snowflake_postgres_cutover.py`) 2026-11-16 07:00 ET
- [x] Replace copied repo-content counts with the property they stood for (entity types, line items, measures, mapdoc classification) 2026-11-16 07:00 ET
- [x] `FakeSink` implements the whole `Sink` protocol (a path that starts calling `link_keys` or `set_ids` fails loudly) 2026-11-16 07:00 ET
- [x] The rule: `docs/agents/watching-and-testing.md` "Writing a test", with a pointer in CLAUDE.md 2026-11-16 07:00 ET
- [ ] ~~OpenMetadata `_Server` fake in `unit/test_rules_catalog.py`: one contract test against a recorded 2.0.2 response~~ deferred to Codex: OpenMetadata work is Codex's
- [x] Not changed, on a re-read of current main: `mdm/test_target_manifest.py` starts each body from the real rules file; the Streamlit, native-pull and routine-retirement tests the audit named are already gone from main
- [x] Learning → skill: none; the rule lives in `docs/agents/watching-and-testing.md` and CLAUDE.md
