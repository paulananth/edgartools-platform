# 04 — Physically resequence build_stages() to the final phase order

Type: task
Status: resolved
Blocked by: 01, 02, 03

## Question

Apply Ticket 01's classification and Ticket 02's safety-verified ordering
to actually reorder the `add_stage` calls inside
`infra/scripts/install.sh`'s `build_stages()` function:

- Move each stage to its phase-correct position (stable partition:
  preserve original relative order within each phase).
- Add visible phase-boundary markers in the source (e.g. a comment header
  above each phase's first `add_stage` call) so the grouping reads clearly
  to a future maintainer, not just in test coverage.
- If Ticket 02 found dbt gold needs early-data to precede it as a genuine
  exception to the clean 4-phase order, encode that exception explicitly
  in a comment at the point it applies — don't let it look like an
  oversight.
- Run the full test suite plus
  `tests/architecture/test_install_wizard.py` specifically (updated by
  Ticket 03) green before considering this done.
- Do not touch or interfere with the live PRJEDJU/QJB05385 provisioning
  run (Task #159) — confirm with the user whether that run has reached a
  safe stopping point before merging this, per the open question in the
  map's Not yet specified section.

## Answer

Physically reordered `build_stages()` in `infra/scripts/install.sh` to
Ticket 01's decided order: provision{1,2,3,4,7,13} -> deploy{5,6,9,10,11,12}
-> early-data{8} -> late-data{14,15,16,17,18} (original stage numbers).
Confirmed a minimal, surgical diff -- only 2 stage blocks (native-pull
foundation + Postgres/graph prereqs, and seed-universe) actually needed to
move; every command body is byte-identical to before, only comments and
position changed.

- Added 4 phase-boundary comment headers in source, one before each
  phase's first stage.
- Fixed two stale cross-reference comments in the Neo4j install stage
  (a wrong stage-name callout, a wrong absolute "stage 13" reference --
  both already stale before this reorder, now pointing at the correct
  named stage instead of a number that would drift again on any future
  reorder) and added a note that its own position within provision is
  unpinned per Ticket 01.
- Rewrote the seed-universe stage's positioning-rationale comment to
  explain its new position (after the whole deploy phase, not immediately
  after native-pull foundation) and cite Ticket 02's safety findings
  directly, including the dbt-gold self-heal reasoning.
- Ticket 04's contingency clause (encode a dbt-gold exception if Ticket 02
  found one needed) was correctly not triggered -- Ticket 02 concluded no
  exception was needed, and seed-universe genuinely sits after the full
  deploy phase in the final diff, not moved earlier as a workaround.
- Removed the now-satisfied `@pytest.mark.xfail(strict=True)` marker (and
  the now-unused `import pytest`) from
  `test_stages_run_in_provision_deploy_early_data_late_data_order` --
  it now genuinely passes against the live `--plan` output.

Verified: `bash -n infra/scripts/install.sh` clean; full architecture test
file green (26 passed); full suite green (2172 passed, 4 skipped, 0
failures, 0 xfailed -- one more pass than Ticket 03's run since the
phase-order test flipped from xfail to a real pass). `/code-review`
(Standards + Spec axes, done directly after both review sub-agents hit an
API session limit) found zero findings on either axis -- command bodies
confirmed byte-identical via diff, final stage order confirmed to match
Ticket 01's decision exactly via the live passing test, no AWS/Snowflake
state touched (pure source diff), Task #159's paused run undisturbed.

The install-sh-provision-deploy-data map is now fully resolved -- no
tickets remain open.
