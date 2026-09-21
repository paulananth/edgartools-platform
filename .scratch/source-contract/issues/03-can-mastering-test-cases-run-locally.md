# Can mastering test cases run on a laptop

Type: research
Status: claimed
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
