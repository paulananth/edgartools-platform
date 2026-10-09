# Company preparation cutover review

Base: main `67e24723265ad8e9ff2a8cf2e383543c385ee2a5`.
Spec: operator goal and this workstream's TICKET.md. Local qualification only.

## Standards

Independent review found no remaining scoped design blocker. Existing worker
functions and the staging adapter are appropriate; GoF review found no evidence
that an additional class hierarchy would improve this change. Bronze lookup
semantics reside in Rules. Complete receipts are validated before a verified,
bounded Company reading selects inline reference keys; seed proof is retained
and excluded from combination inputs.

Projected Parquet inputs retain explicit 100,000 distinct-row / 32 MiB framing
bounds. Actual captured qualification does not establish compatibility for every
possible 64 MiB legacy input.

## Spec

Independent review found no remaining scoped implementation blocker after
fixing whole-census/reference bounds. It independently ran the greater-than-
10,000-receipt regression: 1 passed in 3.19 seconds. The test compares all
original bundle bytes and checks retry, proof replay, and refusal of a malformed
unrelated receipt. Earlier review independently verified late foreign-run
refusal behind duplicate rows.

The active CLI uses configured reading/combination. Preparation-only runtime
collectors and census attachment are removed; the historical implementation
exists only as a test oracle. The independently active census caller remains.

## Closure gates

Final captured code pins, installed CLI/replay with restricted-role PostgreSQL
16 qualification, and the complete CI gate must pass before closure. Their
results and completion times are recorded in TICKET.md.

## Refusal correction review

Full engine CI identified malformed `read: null` being accessed by Parquet
dispatch before native validation. The guarded dispatch and optional input-bound
check preserve native SourceRejected. Independent Spec review found no blocker
and reran all four facade/worker, bound-absent/bound-present cases: 4 passed in
1.20 seconds. The complete 51-case stream/worker/caller gate passed36.54s.
Captured proof was refreshed after this worker edit.
