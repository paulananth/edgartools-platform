# Can mastering test cases run on a laptop

Type: research
Status: resolved (2026-09-21)
Blocked by: none

## Question

Q3 requires each Source Contract to declare mastering test cases: given a
small declared set of existing identities, a fixture's records must bind,
create, or defer as expected. That means running `normalize` and the Merge
Stage locally, inside one command (check 8), with no network (check 4).

From the code and `docs/specs/clean-mdm/` (especially `local-operations.md`,
`merge-stage.md`, `evidence.md`), establish:

1. What the Merge Stage needs to run: store (Postgres only, or can it run on
   SQLite / an in-memory store?), migrations, a registered policy digest, a
   pinned source publication.
2. What existing tests already do this (`tests/` for `mdm/clean`): their
   fixtures, setup cost and runtime.
3. How a test could declare "existing identities" and seed them through
   supported paths only (no direct inserts that bypass the Merge Stage).
4. What outcome a test can assert on: bind to which identity, new identity,
   deferred with which reason, which fields survived.
5. The smallest local setup that meets checks 4 and 8, and its runtime.

## Answer

[research/03](../research/03-local-mastering-tests.md). **Yes, on a local
PostgreSQL 16 container, not without one**: the engine requires Postgres 16
and commits through PL/pgSQL, so SQLite or in-memory is out. Smallest setup:
one pre-pulled `postgres:16` on `127.0.0.1`, one database, two roles,
migrations 014, 023, 025-029, an active registry row, a registered policy,
and direct `MergeStage.apply()` calls, run offline
(`uv run --offline --frozen …`). Estimated 45-75 s for a 5-case mastering
suite (25-40 s with a pre-migrated template database, unmeasured).
**Existing identities** can only be seeded through a first
`MergeStage.apply()` batch — direct inserts are impossible by design.
**Limit**: automatic rules are refused (`store.py:160-161`), so today a
mastering case can assert a *declared* bind accepted or rejected, a new
identity, `binding_required`, a deferral and its reason, surviving fields
and quarantine — not "the engine bound this record to X". Engine-chosen
bindings become testable only when the Mastering Policy's automatic rules
can activate. The shared fixture's readiness wait is ~8 s
(`tests/integration/test_clean_mdm_postgres.py:65-73`), which failed 4 of 7
runs on Colima; the runner needs ≥30 s. Three Codex proposals: a longer
readiness wait, a named offline registry authority for tests, and a test
mode for automatic rules.
