# 04 — Physically resequence build_stages() to the final phase order

Type: task
Status: open
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

<!-- filled on resolution -->
