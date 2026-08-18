# 03 — Update test_install_wizard.py for the final stage order

Type: task
Status: resolved
Blocked by: 01, 02

## Question

With Ticket 01's classification and Ticket 02's safety-verified final
ordering settled, update `tests/architecture/test_install_wizard.py` so it
asserts the *new* correct behavior rather than merely not-yet-broken by
accident:

- Rewrite `test_neo4j_install_runs_early_and_before_the_grants_stage` to
  check relative order only (`install < grants`), dropping the literal
  `install == 1` assertion, per the "Neo4j placement" grilling decision
  (recorded in this map's Destination).
- Audit the rest of the file for any other assertion — positional or
  substring — that assumes the current stage order, even if it currently
  reads as a simple `"X" in out` membership check (as most of
  `test_plan_prints_preview_only_aws_ordered_commands` turned out to be on
  closer reading — confirmed NOT order-sensitive as written, but re-verify
  under the actual new stdout ordering in case any assertion was relying
  on incidental adjacency).
- Add or extend a test that pins the *new* phase order explicitly (e.g.
  asserting `--plan` output shows stages grouped/labeled in
  provision → deploy → early-data → late-data order), so a future edit to
  `build_stages()` can't silently drift the ordering again the way the old
  code had no test for the provision/deploy split at all.

## Answer

Implemented in `tests/architecture/test_install_wizard.py`:

- `test_neo4j_install_runs_early_and_before_the_grants_stage` renamed to
  `test_neo4j_install_precedes_the_grants_stage` and its literal
  `assert install == 1` dropped, keeping only `assert install < grants`,
  per Ticket 01's Neo4j-placement decision.
- Audited the rest of the file (grepped every `.index(`/`titles[` usage):
  confirmed this was the *only* positional/order assertion anywhere in the
  file. `test_plan_prints_preview_only_aws_ordered_commands`'s name is
  misleading but its body only does substring (`"X" in out`) membership
  checks, not order — confirmed not order-sensitive, needed no change.
- Added `test_stages_run_in_provision_deploy_early_data_late_data_order`,
  decorated `@pytest.mark.xfail(strict=True, reason=...)`, asserting
  `_plan_stage_titles(...) == PROVISION_DEPLOY_DATA_STAGE_ORDER` — the
  exact 18-title sequence Ticket 01 decided and Ticket 02 verified safe.
  This is a deliberate TDD-red test: it fails today (install.sh hasn't
  been reordered yet) and must go green — with the xfail marker removed —
  as part of Ticket 04. `strict=True` means if Ticket 04's reorder is
  wrong or incomplete, this test surfaces as a hard failure, not a silent
  no-op.
- `PROVISION_DEPLOY_DATA_STAGE_ORDER` and two extracted title constants
  (`NEO4J_INSTALL_STAGE_TITLE`, `GRANTS_STAGE_TITLE`, shared between both
  tests to avoid a 3-way literal-string duplication) live in the file's
  top-of-file constants block, matching local convention.

Verified: `tests/architecture/test_install_wizard.py` — 25 passed, 1
xfailed (expected). Full suite — 2171 passed, 4 skipped, 1 xfailed, 35
subtests passed, 0 failures. `/code-review` (Standards + Spec axes) found
zero hard violations and zero scope creep; two minor duplication/placement
smells were fixed inline before this Answer was written.

Ticket 04 is now unblocked.
