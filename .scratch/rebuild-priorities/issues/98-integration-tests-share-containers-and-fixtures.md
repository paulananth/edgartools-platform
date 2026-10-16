# Integration tests share their containers and fixtures

Priority: 98, tier 3. Map: [Rebuild priorities](../map.md).

Type: task (tests). Status: open, not started. Blocked by: none. Deferred from 88 (Simplify and speed up the tests), whose PR the operator asked to finish by deleting old and unused tests (2026-10-16).

## Question

The slowest integration test files each start their own PostgreSQL 16 and build the same fixtures again. Which of them can share one container and one set of fixtures per session, and how much CI time does it save, measured job by job before and after?

## Checklist

- [ ] Measure: the ten slowest integration files and their setup time (CI job log, `--durations`)
- [ ] Share the container and fixtures where tests do not depend on an empty store; keep isolation where they do
- [ ] Job times before and after in the PR; nothing else changes
- [ ] PR, CI green, merge on the operator's word
- [ ] Learning → skill
