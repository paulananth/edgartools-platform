# GoF review of the Clean MDM change boundary

Reviewed with the available `gof-refactor-reviewer` skill against code and git
history at `b1babd8bbd0e04044fcacbbab822d480c97c01bc`.

**Overall:** existing adapter and matcher seams are reusable. A new pattern
framework would not solve the missing evidence and atomicity contracts.

## 1. Keep source variation behind the existing adapter/policy seam

`edgar_warehouse/acquisition/source_family_registry.py:1-75` documents repeated
growth from filing artifacts to submissions, facts, reference catalogs and
ADV datasets. The active registry loader in `registry_ledger.py:519` already
selects installed family policies. Reuse that seam for approved publication
and normalization contracts, without giving source adapters transaction or
master-write authority.

Cost today: a source-specific direct writer creates another identity,
survivorship and recovery path. The ADV bulk path at `mdm/adv_bulk.py:195,353`
already bypasses ordinary resolver behavior, so source onboarding cannot be
only another branch in the pipeline.

Fix: narrow Adapter / registry-selected Strategy, using functions or small
protocol implementations. Cost of fix: one indirection and potential fidelity
loss if the evidence interface drops source-specific semantics. Keep typed
extension evidence and reject unsupported schemas.

Safe sequence after the gate: characterize existing source normalization;
introduce the evidence contract unused; adapt one Company source; verify the
PostgreSQL transaction; then adapt remaining sources with their fixtures.

## 2. Put shared transaction ownership in one merge operation

`mdm/resolvers/base.py:95,171,196` centralizes some common writes, but
`mdm/adv_bulk.py:349,520` commits directly, stewardship commits its own changes,
and `mdm/pipeline.py:3116` enqueues publication after worker commits.

History shows current costs: `be111c14` added change-log diff checks,
`37c44e1d` batched source-ref checks, `c59aefc1` repaired that batching, and
`dacac18a` collapsed stage representatives. Bulk projection separately needed
`e6fc0626` to fix fund occurrence dedup and `23f13786` to repair growing reads.
One source fix currently does not establish the same behavior for all writers.

Fix: a narrow Merge Stage facade owning one caller-visible transaction,
with injected deterministic matching/field policy functions. Cost of fix:
the facade can grow into another pipeline monolith; keep capture, orchestration,
network publication and domain normalization outside it. This is primarily
transaction and data-contract work, not a Template Method class hierarchy.

Safe sequence: prove transaction/recovery invariants on real PostgreSQL;
route Company, Person, profiles and relationships in dependency order; route
stewardship and repair last only after reversal tests exist; then enforce that
no live writer bypasses the operation.

## Not recommending

- Observer for downstream writes: in-memory callbacks cannot replace durable
  publication intent or prove recovery after process death.
- Command/Memento as the primary reversal mechanism: restoring a pre-merge
  snapshot would discard later valid corrections. Retained assertions and
  evidence-bound compensating replay are the needed contract.
- A new matcher hierarchy: `mdm/match.py` already has a Protocol and injected
  matchers. Its conflict handling, optional fallback and threshold policy need
  specification; renaming classes adds no evidence.

## Independent PostgreSQL prerequisite fix

The existing integration fixture grew to include migration 017 in `cb76c508`
but omits 018 despite the current ORM requiring its HTTP validator columns.
The reproduced six baseline failures justify adding that migration and
preserving runtime migration order in privileged-rerun tests. Review verdict:
leave the fixture structure in place; no GoF pattern is justified for this
17-line setup repair. The existing real-PostgreSQL tests verify the fix.

## Shared-core recovery review, 2026-09-18

Reviewed the new core at `6aa55228` and legacy CLI history (`6faa4d31`,
`4dcd5507`). Keep the small command dispatch and publication protocols; no new
class hierarchy is warranted. The demonstrated costs were behavioral: bounded
retry starvation, unavailable reconciliation flags, stale success and use of
arrival-dependent prior projections. Fix these at their existing boundaries.
The added PostgreSQL tests reproduce and verify those paths. API composition
has remained stable since `c8562b73`; a separate versioned router can reuse it
without refactoring the legacy routers.
