# 41 — Build the cross-stage watermark aggregator

**What to build:** A scheduled Postgres-side reconciler that watches each
stage's already-existing (or soon-to-exist, per Tickets 35/36/39/40)
completion evidence, writes one composite alignment row per
`cause_reference`, rolls those up into `business_date`-level completeness,
and feeds real values into the already-built `decision_contract.py`
(`evaluate_agent_grade`/`DecisionWatermark`) instead of today's
placeholder-ridden SQL sketch.

**Blocked by:** 09 — Decide the cross-stage coordinator and composite
watermark contract (this map); 35, 36, 39, 40 (each stage's own
completion-evidence mechanism must exist for the aggregator to read)

**Status:** ready-for-agent (2026-08-29: Tickets 35, 36, 39, and 40 are
resolved. Ticket 09 is resolved. This ticket is unblocked.)

- [ ] A new scheduled job (not event-triggered, per Ticket 09's Answer)
  reads, per `cause_reference`: silver's completion barrier (Ticket 35),
  MDM's publication-outbox lifecycle state (Ticket 36), gold's native
  refresh version (Ticket 39), and graph's generation status/parity
  (Ticket 40) — writing one composite row recording whether all four are
  aligned for that `cause_reference`.
- [ ] A separate daily rollup derives `business_date`-level
  `silver_completeness_ok`/`gold_run_id`/`graph_generation_id`/
  `graph_parity_ok` from every `cause_reference` touching that date, and
  calls `evaluate_agent_grade` with real (not placeholder) values.
- [ ] The two SQL gaps CLAUDE.md already documents in the existing
  Decision Contract sketch (`infra/snowflake/sql/decision_contract/` —
  the "MDM active-company universe" placeholder join, and
  `BUNDLE_AUDITOR`'s reference to `SEC_AUDITOR_REPORT_EVIDENCE` in the
  wrong schema) are fixed as part of wiring real data through this
  aggregator, not left as separate unowned gaps.
- [ ] A watchdog SLO (reusing `publication.py`'s 5-minute-warning/
  15-minute-hard-alert pattern) fires when a `cause_reference` stays
  unaligned past threshold, naming which specific stage is stuck.
- [ ] No new retry/DLQ/repair mechanism is built on the aggregator itself
  — a live test confirms a stuck `cause_reference` is repaired entirely
  through the stuck stage's own existing mechanism, then the aggregator
  picks up the resolved state on its next scheduled pass without any
  aggregator-specific intervention.

## Notes

Surfaced while resolving [09 — Decide the cross-stage coordinator and
composite watermark contract](09-decide-cross-stage-coordinator.md) — see
that ticket's Answer for the full design rationale, including why this is
an aggregator watching independently-publishing stages rather than an
orchestrator driving them.
