# Trace every Company field and convert confirmed defects into data-quality checks

Type: task
Status: in progress
Blocked by: none

## Goal

Repeat the AAPL-style trace for every current mastered Company: start from its
authoritative MDM identity, inspect every configured source field and
downstream field, then follow typed relationships and cross-store references.
Record evidence-backed issues and convert defects that can be expressed by the
existing data-quality engine into checks. Propose a separate implementation
ticket for any required check primitive the engine does not support.

Use the local captured stores and pinned rules only. Do not request provider
data, change source or matching rules, modify catalog contents, activate a
pipeline, or inspect Gold as part of this audit. Report counts and masked or
invented examples, never names or identifiers from records.

## Checklist

- [x] Confirm the reference method and current check formats: AAPL is the control trace; Silver table specs declare `checks`; the data-quality skill lists supported checks; DataKitchen TestGen research is pinned at `docs/research/datakitchen-testgen-test-types-2026-11-02.md`, sourced from [`DataKitchen/dataops-testgen`](https://github.com/DataKitchen/dataops-testgen/tree/3606859cf8bb4f809d2b19acc51462420829c4ab/testgen/template/dbsetup_test_types) (reviewed 2026-11-08 07:22 ET).
- [ ] Pin a read-only snapshot and enumerate the full current Company population; record its generation, denominator, and the AAPL control population.
- [ ] Inventory every configured Company source field, MDM field, identifier, relationship type, and downstream table/field from source contracts, master rules, relationship rules, and Silver specs.
- [ ] Reproduce the AAPL trace against the pinned snapshot and confirm the field and relationship checklist catches its known downstream paths.
- [ ] Trace all Companies in deterministic batches through source-to-MDM identity, each MDM field, and each Company-linked downstream field; report coverage, missing links, conflicts, duplicates, stale references, and applicable denominators.
- [ ] Trace typed relationship paths separately, including `ISSUED_BY` from Security to Company; verify endpoint kind, direction, current MDM identity, time basis, and source evidence.
- [ ] Classify the current Silver `ISSUED_BY` / MDM relationship difference by checking ID history, generation, and producer contracts before calling it a defect.
- [ ] Classify Security listing FIGI-to-market/venue coverage: distinguish mapped MICs, valid no-MIC composites, unmapped exchanges, and missing or mismatched MICs using the pinned RDM crosswalk.
- [ ] Write an issue ledger with one row per evidenced failure pattern: checkable condition, observed count and denominator, affected table/field, impact, snapshot/rule version, source evidence, and confirmed or unconfirmed cause.
- [ ] Map each confirmed defect to a DataKitchen TestGen category and to a supported platform check (`identifier`, `in_set`, `one_value`, `not_after`, or `reason_if_empty`) where it fits; use baseline checks only when an approved business reference exists.
- [ ] Draft check definitions in the owning source contract or Silver table spec; measure them on the pinned records, include counts in comments, and prove each check with a planted invalid record before proposing activation.
- [ ] For cross-table or cross-store checks without a supported primitive, document the exact predicate and smallest required engine/configuration change as a separate issue; do not approximate it with a misleading field-only check.
- [ ] Report the completed Company coverage, confirmed defects, candidate findings still under investigation, check definitions and measurements, and deferred work. Do not create external tickets unless requested.
- [ ] Learning → skill: record any reusable trace or check-design rule in the relevant skill, or write `none` with the reason.

## Initial measured candidates

These are investigation leads from the shared local snapshot, not confirmed
defects. Resolve them in the checklist before adding checks:

| Candidate | Measurement | Why it is not yet a confirmed defect | First validation |
|---|---|---|---|
| Silver `ISSUED_BY` endpoints do not resolve to current MDM IDs | 42,383 Silver relationship rows; 0 endpoint IDs matched current MDM entities. Current MDM had 505 `ISSUED_BY` edges. | Silver rows may reference an earlier generation or use a different identity contract. | Match endpoints and relationship IDs against MDM history and inspect the Silver producer/spec generation contract. |
| Listing venue MIC coverage | 617,684 of 1,392,524 listing details carried a MIC in the observed snapshot. | Composite listings can legitimately have no venue MIC; crosswalk scope and vintage must be accounted for. | Classify each exchange code using the pinned `iso-10383-mic` crosswalk and compare only listings expected to resolve. |

The full Company count in the prior shared-store observation was 8,361. Recount
it on the pinned audit snapshot before using it as the final denominator.

## Data-quality design constraints

- Derive expected presence and relationships from configured contracts and
  business rules; do not assert that every optional Company field must be
  populated.
- Use DataKitchen TestGen categories as a vocabulary for completeness,
  validity, consistency, uniqueness, and referential checks. The existing
  pinned research is the reference; TestGen is not installed in the platform.
- Silver table checks belong in the owning Silver spec. Source/Master checks
  belong in their configured quality rules. Cross-store checks need an
  implementation path that can actually see both authoritative sides.
- A check with zero failures still requires a planted-record proof. A measured
  count alone does not authorize activation or a data repair.
