Labels: `wayfinder:map`

## Destination

A ready-to-implement design for executing Company, Person, and Security MDM
quality checks within their pipeline, retaining verified per-check outcomes in
Bookkeeping, and publishing genuine results to OpenMetadata with exact readback.
The map is complete when check scope, execution boundaries, the evidence and
recovery contract, and catalog projection are decided. It does not change
production rules or switch on new checks.

## Notes

- `mdm.quality.apply` already runs source `quality.yaml` checks during
  `mastering.merge` normalization, before a record is merged. `exception`,
  `withhold`, and `flag` have distinct behaviors; a quality exception does not
  stop the whole run.
- The MDM path now publishes per-check run evidence through immutable receipt v1, and Bookkeeping admits it by verified work unit. Parent reran the synthetic D5 disposable PG16 recovery scenario on current `origin/main` (`ba51a974`) from the updated ticket-25 worktree; it passed, qualifying recovery only, not production enablement.
- Use DataKitchen TestGen as a test-type reference, not as a second runtime.
  Keep the Company Financials silver recommendations distinct from Company,
  Person, and Security master rules. A master identifier-capacity constraint
  is not automatically a row-level quality test.
- The completed [Verified Per-Load Quality Evidence map](../openmetadata-quality-evidence/map.md)
  is the precedent for immutable receipts, Bookkeeping admission, exact result
  readback, and recovery qualification. This map covers the MDM execution path
  and its integration with that evidence flow.
- Consult `skills/data-quality/SKILL.md`, `skills/mdm-engineering/SKILL.md`,
  `skills/bookkeeping/RECOVERY.md`, and `skills/openmetadata/SKILL.md` while
  resolving the tickets. Apply the GoF review before MDM code changes.

## Decisions so far

- [Decide the MDM Quality Inventory and Scope](issues/01-decide-mdm-quality-inventory-and-scope.md): approved the current source-check inventory, evidence threshold, permitted grains, and unresolved-action policy; no additional evidence-backed check or new check kind is identified.
- [Decide MDM Check Execution Boundaries](issues/02-decide-mdm-check-execution-boundaries.md): retained current per-record checks in `mastering.merge`; bounded full-publication checks run pre-merge, and persisted-master checks run read-only after merges on a consistent snapshot.
- [Decide MDM Quality Evidence and Bookkeeping Admission](issues/03-decide-mdm-quality-evidence-and-bookkeeping-admission.md): implemented a source-contract-driven, immutable unit receipt; D5 synthetic disposable PG16 recovery qualification passed on current `origin/main` (`ba51a974`), while production target/switch enablement remains pending explicit operator authorization.
- [Decide OpenMetadata Projection and Readback](issues/04-decide-openmetadata-projection-and-readback.md): reuses source-contract-generated test cases, maps incomplete admitted evidence to `Aborted`, and requires exact timestamped readback.
- [Handle accepted policies without `kinds`](issues/05-policy-without-kinds.md): missing optional maps are empty across merge/readback, matching validation; PR #2025 keeps production quality evidence disabled.

## Recovery qualification and production enablement

- Parent reran D5 scenario `tests/integration/test_mdm_quality_evidence_postgres.py` on current `origin/main` (`ba51a974`) from the updated ticket-25 worktree: 1 passed in 4.77s on disposable PG16. Receipt-v1 recovery is qualified for this synthetic case only.
- CI run #45052107235 passed all 12 jobs for PR #2028 head `9649cc0`; the ticket-closeout commit creates a new head, so keep the PR draft until that head's CI passes. Production targets and `MDM_QUALITY_EVIDENCE_V1` stay off until explicit operator enablement; this test grants no production authorization.

## Out of scope

- Installing or invoking DataKitchen TestGen as a separate production runner.
- Customizing the OpenMetadata UI or making OpenMetadata execute the checks.
- Provider acquisition, source activation, production rule changes, or enabling
  a new evidence format before the required decisions and qualification.
