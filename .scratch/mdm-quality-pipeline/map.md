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
- The MDM path does not yet publish per-check run evidence. Its existing
  provenance retains failures, but not a complete pass denominator. The
  `quality.counts` helper is not wired to a verified MDM receipt.
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
- [Decide MDM Quality Evidence and Bookkeeping Admission](issues/03-decide-mdm-quality-evidence-and-bookkeeping-admission.md): implemented a source-contract-driven, immutable unit receipt; admitted counts remain distinct from pipeline completion, and receipt v1 stays behind recovery qualification and an explicit switch.
- [Decide OpenMetadata Projection and Readback](issues/04-decide-openmetadata-projection-and-readback.md): reuses source-contract-generated test cases, maps incomplete admitted evidence to `Aborted`, and requires exact timestamped readback.

## Not yet specified

- Disposable recovery qualification for MDM receipt v1 and operator enablement.
  Until that evidence is recorded, leave `mdm.quality.evidence.v1` out of
  production targets and `MDM_QUALITY_EVIDENCE_V1` unset.

## Out of scope

- Installing or invoking DataKitchen TestGen as a separate production runner.
- Customizing the OpenMetadata UI or making OpenMetadata execute the checks.
- Provider acquisition, source activation, production rule changes, or enabling
  a new evidence format before the required decisions and qualification.
