# Build durable identity candidate assessments

Type: task
Status: resolved
Owner: Codex
Blocked by: none (gate 08 accepted)

## Scope

Implement Company Q13 in the shared Merge Stage: retain every new source-binding
and published-ID consolidation proposal before master application. Keep the
existing field-only path, rollback preview and atomic journal/checkpoint/outbox.
No new matcher or automatic-rule qualification is implied by this foundation.

## Implementation and acceptance

- Add migration 028 without rewriting installed migrations. Assessments and
  transitions are append-only; restricted runtime has capability-only writes.
- Persist proposed evidence/identity/field/relationship effects and dependency
  snapshot separately from master commit. Retain hard-veto proposals too.
- Resume a retained ready assessment after interruption. Recompute projections
  and check affected-state dependencies under the existing transaction lock.
- Supersede stale assessments without affecting unrelated Company progress.
- Record application with the final master/journal/checkpoint/outbox transaction.
- Prove SQL coverage enforcement, preview rollback, immutable history, duplicate
  and lost-ack recovery, stale evidence and unrelated-generation behavior on
  disposable PostgreSQL 16 using the restricted application role.

## Design review

GoF review of `clean/merge.py`, `store.py`, identity replay and history found one
implementation commit (`e2807e52`), with no repeated variation warranting a GoF
refactor. Keep the existing coordinator; add plain assessment helpers and SQL
capabilities. The cost is one extra persisted phase for identity-changing work.

## Remaining Company milestone

GLEIF normalization/capture and pinned publications, candidate generation,
independent automatic-rule qualification, link suspension/replay, audited match
dispositions, full scoped Company rebuild and consumer recovery remain separate
work. This ticket must not claim completion of multisource Company mastering.

## Verification — 2026-09-20

665 broader checks passed (Clean MDM PostgreSQL, Company adapter, API and
architecture), with zero skips. The final assessment changes passed 9 targeted
PostgreSQL tests, zero skips; these counts overlap. Ruff and diff checks pass.
[Evidence](../company-assessment-acceptance.json) pins source and report hashes.
[Operation and recovery](../../../docs/specs/clean-mdm/candidate-assessments.md).
Persistent local and hosted databases were not changed.
