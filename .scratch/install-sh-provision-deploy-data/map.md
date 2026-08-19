# Map: install.sh — physical reorder into provision/deploy/data phases

Labels: wayfinder:map

## Destination

`infra/scripts/install.sh`'s `build_stages()` physically resequenced into
four ordered phases — **provision → deploy → early-data → late-data** —
with every one of the 18 existing stages moved to its phase-correct
position (a stable partition: original relative order preserved *within*
each phase, no shuffling beyond that) while every documented inter-stage
dependency continues to hold. `tests/architecture/test_install_wizard.py`
updated to match: the Neo4j install stage's placement check becomes a
relative-order assertion (precedes "Snowflake Postgres / graph
prerequisites"), not the current literal stage-index-1 assertion.

## Notes

- Domain: `infra/scripts/install.sh`'s 18-stage go-live wizard (see
  CLAUDE.md's "Snowflake DEV is DECOMMISSIONED" and "Phased Pipeline"
  sections for platform background) plus its coverage in
  `tests/architecture/test_install_wizard.py`.
- Consult `/grilling` and `/domain-modeling` for any stage-classification
  call that isn't clean.
- This effort's scope is ONLY stage ordering/grouping in `build_stages()`.
  Do not fold in an operational `--phase` CLI flag or a checkpoint/resume
  mechanism between phases — see Out of scope.
- Task #159 (this repo's task tracker, not the issue tracker) is driving a
  live go-live run against Snowflake account `PRJEDJU/QJB05385` using the
  **current, pre-reorder** stage order; stages 14-18 were still pending
  when this map was created. **Decision: paused.** The user chose to pause
  Task #159 rather than let it finish on the old order — do not resume
  stages 14-18 until Ticket 04 lands and install.sh reflects the new
  phase order.

## Decisions so far

- [01 — Classify all 18 install.sh stages into provision / deploy / early-data / late-data](issues/01-classify-stages-into-phases.md) — final order: provision{1,2,3,4,7,13} → deploy{5,6,9,10,11,12} → early-data{8} → late-data{14,15,16,17,18}; every phase bucket is already internally monotonic, so no within-phase reordering needed.
- [02 — Verify ordering-safety for every stage-pair whose relative order changes](issues/02-verify-ordering-safety.md) — no real dependency breaks anywhere; the flagged dbt-gold-vs-empty-source risk turned out to be pre-existing (not new) and already tolerated by the not_null-only test surface, dynamic-table self-heal, and Stage 15's fail-closed gold-verify-live gate. Clean 4-phase linear order stands as final, no exceptions needed.
- [03 — Update test_install_wizard.py for the final stage order](issues/03-update-architecture-tests.md) — Neo4j placement test rewritten to relative-order only; new strict-xfail test pins the full target order (TDD-red, goes green on Ticket 04); audit confirmed no other order-dependent assertion existed. Full suite green (2171 passed, 1 xfailed as expected).
- [04 — Physically resequence build_stages() to the final phase order](issues/04-implement-the-reorder.md) — install.sh reordered to Ticket 01's decision, minimal surgical diff (command bodies untouched), 4 phase-boundary comments added, 2 stale cross-references fixed, phase-order test now genuinely passes (xfail removed). Full suite green (2172 passed, 0 failures). Map fully resolved.

## Not yet specified

- Whether any stage beyond the ones already ticketed carries a similar
  hidden data-availability assumption to Stage 8's (Snowpipe existing /
  `mdm seed-universe` needing non-empty silver) that Ticket 02's
  investigation doesn't happen to catch on its first pass — re-open if so.

## Out of scope

- Operational phase-level CLI controls (e.g. `install.sh --phase
  provision`, checkpoint/resume between phases) — the "Phase scope"
  grilling question resolved this as organizational/physical reordering
  only, not new runtime behavior beyond stage sequencing itself.
