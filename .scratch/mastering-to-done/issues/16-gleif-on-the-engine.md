# GLEIF on the engine

Type: task (code)
Status: open
Blocked by: 15

## Question

Move GLEIF Level 1, relationships and reporting exceptions from `gleif_source.py` onto the engine, configured in `rules/sources/gleif/`.

- **Prove equivalence first.** On the pinned Golden Copy capture and Codex's fixtures, the engine must give the same assertions, assertion IDs, deferrals and refusals as today's reader.
- **Then retire the Python reader**, except for any declared custom step.
- The source version changes, so it needs a test run and the operator's approval.
