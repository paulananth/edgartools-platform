# Company mastering completion gate

Priority set by the user on 2026-09-19: prove genuinely multisource Company
mastering with SEC and GLEIF before starting other entity integrations. This
supersedes the earlier handoff sequence that moved from the SEC-only sample
to Person/ADV. Shared recovery work necessary for Company remains in scope.
This document is a delivery gate, not a claim of implementation.

## Local milestone

A governed Company can retain SEC and GLEIF records under one immutable
internal ID, select or display fields according to explicit source semantics,
explain disagreement, preserve dated accounting relationships, and replay or
reverse decisions without losing source evidence or falsely declaring delivery
complete. A Company need not have a CIK; GLEIF eligibility and approved cohort
scope determine which additional Companies may be created.

Loading SEC rows alone, loading GLEIF into a staging table, or adding an LEI
column does not satisfy this gate. Every master mutation must use the shared
Merge Stage, transactional journal and bounded recovery contract.

## Work and acceptance evidence

| Order | Required delivery | Evidence needed to close |
| --- | --- | --- |
| 1 | Repair PostgreSQL CI prerequisites and finish Company-relevant recovery | Mandatory PG16 tests run without prerequisite skips; audited deferred resolutions; bounded review checks and resumable large-component replay/reversal |
| 2 | Pin approved multisource inputs and concrete adapter contracts | SEC Company/ticker publication, complete GLEIF Level 1 baseline, coordinated relationship/reporting-exception baseline, and OpenCorporates mapping; source registry authority, exact bytes/hashes/counts, schema versions, publication ordering and explicit scope |
| 3 | Implement shared GLEIF capture and normalization | Stream bounded XML ZIP processing; retain complete source records and unsupported kinds; normalize eligible Company evidence; no direct master writes; every input has an accounted disposition |
| 4 | Establish governed Company-to-LEI bindings | Reviewed evidence ties SEC CIK and GLEIF LEI to one immutable Company; uniqueness and incompatible-kind/identifier guards; aliases and audited revalidation/unlink/reversal; no name-only or unqualified automatic rules |
| 5 | Implement Company field policies | Versioned type/field rules distinguish different concepts, retain comparable disagreement and select only approved fields; per-value source, assertion, rule and effective/observed-time provenance |
| 6 | Integrate Company relationships and lifecycle | Separate direct/ultimate accounting consolidation from ownership and reported from calculated parents; dated edges only between accepted Company endpoints; cycles, conflicting parents and invalid intervals rejected/reviewed; reporting exceptions preserved |
| 7 | Exercise updates and reconciliation | Daily 24-hour GLEIF delta, monthly complete reconciliation, gap recovery and independent family checkpoints; revalidate changed/retired/successor LEIs; no retirement from partial-delta absence |
| 8 | Prove Company outputs and recovery end to end locally | Real pinned SEC+GLEIF cohort plus fault fixtures; API exposes source evidence and field provenance; required local export/graph contracts verify the same generation; lost acknowledgements, reordered/duplicate records, corrections, retirement and publication failures preserve exact business results |

## Accepted source semantics to implement

Use the resolved GLEIF decisions rather than reopening the architecture:

- [First Company slice](../../../.scratch/gleif-company-augmentation/issues/16-select-first-delivery-slice.md):
  Level 1, relationship and reporting-exception evidence; OpenCorporates mapping
  as corroboration only. Revalidate the 308 previously adjudicated seed links
  against the selected baseline. Those research decisions are not independent
  matching-calibration truth or current production approval.
- [Field semantics](../../../.scratch/gleif-company-augmentation/issues/15-decide-attribute-survivorship-and-conflicts.md):
  project approved LEI/link status, legal form/jurisdiction, entity/registration
  status, registration dates/authority, managing LOU, validation source and
  creation date. Initially retain GLEIF names, addresses, legal events,
  expiration and successor LEIs as separate source evidence. SEC filing and
  financial authority is preserved. SEC incorporation and GLEIF legal
  jurisdiction are not blindly collapsed into one field.
- [Binding lifecycle](../../../.scratch/gleif-company-augmentation/issues/13-decide-accepted-link-publication-policy.md):
  retain decisions and source history when a link closes; successors require a
  new decision. The later Clean MDM Q16 rule still disables every unqualified
  automatic rule. Reviewed binding can prove this milestone without waiting
  for automatic matching calibration.

The three-company SEC bundle is a preparation smoke test. It does not establish
multisource coverage. Choose an approved cohort containing real linked records,
unmatched records, conflicting legal fields, parent/exception cases and source
changes; supplement unavailable failure cases with clearly labeled synthetic
fixtures. Pin the cohort before measuring acceptance.

Each required record/candidate needs a terminal governed disposition. Ambiguity
must not disappear by dropping rows or bypassing reviews. Deferred records
outside an approved publishing scope remain retained; required unresolved
records continue to block completeness until their audited resolution contract
permits closure.

## Delivery boundary

Do not start Person, Adviser, Fund, Security or other entity integration until
this local Company gate passes. Capture unsupported GLEIF kinds without coercing
them into Company. Company-to-Company consolidation is part of this milestone;
other endpoint consumers remain deferred.

The user-selected current target remains local PostgreSQL. Passing this gate
permits the next entity integration; it does not authorize or prove hosted
export/graph operation, Snowflake qualification, production activation or
cutover. Those retain their separate consumer and release acceptance gates,
including the 30-day legacy rollback window.
