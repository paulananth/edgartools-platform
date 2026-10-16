# Integration tests share their containers and fixtures

Priority: 98, tier 3. Map: [Rebuild priorities](../map.md).

Type: task (tests). Status: in review (PR open). Blocked by: none. Deferred from 88 (Simplify and speed up the tests), whose PR the operator asked to finish by deleting old and unused tests (2026-10-16).

## Question

The slowest integration test files each start their own PostgreSQL 16 and build the same fixtures again. Which of them can share one container and one set of fixtures per session, and how much CI time does it save, measured job by job before and after?

## Checklist

- [x] Measure: the ten slowest integration files and their setup time (CI job log, `--durations`): CI run of #1025, integration step 310 s over 48 files; the first test of each file (server, template, first test) sums to 141 s. The 35 MDM-store modules each started their own PostgreSQL 16 and migrated the template again; locally they took 175.8 s (2026-10-16 19:08 ET)
- [x] Share the container and fixtures where tests do not depend on an empty store; keep isolation where they do: the MDM store's `postgres` and `database` fixtures move to `tests/integration/conftest.py`, the server once per session; each test still gets its own database copied from the template. The bookkeeping `databases` fixture stays per module: its tests share one set of stores and may count what earlier tests left. Locally the 35 modules: 285 passed in 68.7 s (was 175.8 s); modules with their own server pass beside it (2026-10-16 19:08 ET)
- [ ] Job times before and after in the PR; nothing else changes
- [ ] PR, CI green, merge on the operator's word
- [ ] Learning → skill
