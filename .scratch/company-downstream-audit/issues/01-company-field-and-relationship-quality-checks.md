# Trace every mastered entity and convert confirmed defects into data-quality checks

Type: task
Status: in progress
Blocked by: none

## Goal

Repeat the AAPL-style trace for every populated MDM kind: start from each
entity's authoritative MDM identity, inspect every configured source field and
downstream field, then follow typed relationships and cross-store references.
Cover Companies, international entities, N-PORT fund structures, private
equity where the configured model represents it, and every other populated
entity kind. Establish from configuration whether private equity is a separate
kind, a Company classification, or another modeled structure; do not assume.
Record evidence-backed issues and convert defects that can be expressed by the
existing data-quality engine into checks. Propose a separate implementation
ticket for any required check primitive the engine does not support.

Use the local captured stores and pinned rules only. Do not request provider
data, change source or matching rules, modify catalog contents, activate a
pipeline, or inspect Gold as part of this audit. Report counts and masked or
invented examples, never names or identifiers from records.

## Checklist

- [x] Confirm the reference method and current check formats: AAPL is the control trace; Silver table specs declare `checks`; the data-quality skill lists supported checks; DataKitchen TestGen research is pinned at `docs/research/datakitchen-testgen-test-types-2026-11-02.md`, sourced from [`DataKitchen/dataops-testgen`](https://github.com/DataKitchen/dataops-testgen/tree/3606859cf8bb4f809d2b19acc51462420829c4ab/testgen/template/dbsetup_test_types) (reviewed 2026-11-08 07:22 ET).
- [x] Enumerate configured kinds and observed population counts in the local MDM snapshot. The legacy master store contains 10,698 Companies, 12,937 fund structures, 31,125 people, and 393,683 securities; the configured branch, government, international-organization, and venue kinds have no rows there. The governed store has 8,361 Companies, 12,937 fund structures, 31,097 people, and 383,441 securities, with max generation 2,619. The stores therefore cannot be combined into one denominator; finish pinning per-store generation and rule revisions before final comparison.
- [ ] Inventory every configured source field, MDM field, identifier, relationship type, and downstream table/field for each populated kind from source contracts, master rules, relationship rules, and Silver specs. Include Company fund profiles and international-jurisdiction subgroups; `private_equity` is not a configured kind, and private-offering forms alone do not establish private-equity identity.
- [ ] Reproduce the AAPL trace against the pinned snapshot and confirm the checklist catches its known Company paths; select a control entity for every other populated kind.
- [ ] Trace every entity in deterministic batches through source-to-MDM identity, each MDM field, and each linked downstream field; report coverage, missing links, conflicts, duplicates, stale references, and applicable per-kind denominators.
- [ ] Trace typed relationship paths for every populated kind, including `ISSUED_BY` from Security to its allowed issuer kinds; verify endpoint kind, direction, current MDM identity, time basis, and source evidence.
- [ ] Trace N-PORT registrants, funds, series, holdings, and securities to their mastered fund/security/company or other entity records; include private-equity structures where present and check actual configured representation. Current fund-structure masters are 12,937, all with the `fund` profile; 1,947 Company masters also carry `fund`. Silver `nport_holding` currently has zero rows, so holdings coverage is unmeasurable in this snapshot.
- [ ] Trace international entities and all non-US Company-like records through identifiers, source fields, relationships, and downstream references; report them separately from domestic Companies. The configured `international_organization` kind has zero observed masters; Company rules include a jurisdiction field, so determine the non-US Company denominator without exposing values.
- [ ] Compare Silver relationship IDs with both MDM stores, history, and the producer version that actually wrote each row. All 55,320 Silver relationship rows resolve to legacy `mastering_*` entity/relationship IDs; none resolve to current governed MDM IDs or scanned history. The checked-out code at `8fb535d` reads new Silver link IDs from governed MDM and no longer implements the relationship-table builder, but the local PostgreSQL server does not identify the worker code that produced existing data. Confirm the deployed producer and cutover contract before calling this a runtime defect or proposing repair.
- [ ] Classify Security listing FIGI-to-market/venue coverage: distinguish mapped MICs, valid no-MIC composites, unmapped exchanges, and missing or mismatched MICs using the pinned RDM crosswalk.
- [ ] Write an issue ledger with one row per evidenced failure pattern: checkable condition, observed count and denominator, affected table/field, impact, snapshot/rule version, source evidence, and confirmed or unconfirmed cause.
- [ ] Map each confirmed defect to a DataKitchen TestGen category and to a supported platform check (`identifier`, `in_set`, `one_value`, `not_after`, or `reason_if_empty`) where it fits; use baseline checks only when an approved business reference exists.
- [ ] Draft check definitions in the owning source contract or Silver table spec; measure them on the pinned records, include counts in comments, and prove each check with a planted invalid record before proposing activation.
- [ ] For cross-table or cross-store checks without a supported primitive, document the exact predicate and smallest required engine/configuration change as a separate issue; do not approximate it with a misleading field-only check.
- [ ] Report the completed Company coverage, confirmed defects, candidate findings still under investigation, check definitions and measurements, and deferred work. Do not create external tickets unless requested.
- [ ] Learning → skill: record any reusable trace or check-design rule in the relevant skill, or write `none` with the reason.

## Measured evidence and unresolved checks

These measurements come from the local read-only snapshot observed on
2026-11-08. They are not a globally consistent snapshot across stores; preserve
the stated store and table denominator with every conclusion.

| Finding | Measurement | Current assessment | Next validation |
|---|---|---|---|
| Silver relationship IDs use a different MDM namespace | 55,320 Silver relationship rows: 42,383 `ISSUED_BY` plus 12,937 `IS_SUBFUND_OF`; all endpoint and relationship IDs match legacy masters, none match current MDM or scanned current history. Current governed MDM has 505 `ISSUED_BY` and 12,937 `IS_SUBFUND_OF` edges. | Confirmed ID namespace disagreement, but the producing worker and cutover contract are not verified. The local database container stores PostgreSQL only. | Trace cutover generations, run receipts, and deployed worker version; then define a non-mutating referential check against the configured MDM authority and a separate repair/retirement decision. |
| Several Silver entity links use legacy IDs | Company fact: 5,134,979 rows, 21,294 null IDs, 320 distinct nonnull IDs (all resolve to legacy Company, none to governed Company). Company line item: 96,807 rows, 414 null, 309 distinct (legacy only). Company measure: 168,360 rows, 720 null, 309 distinct (legacy only). Insider position issuer: 14,331 rows, 709 null, 1,621 distinct (legacy only). Insider owner person: 5,743 rows, 781 null, 4,339 distinct (legacy only). | Observed namespace difference; producer version and transition contract have not been tied to these rows. Nulls may be allowed for unresolved source keys; stale nonnulls are not if governed MDM is the target for that run. | Trace per-table landing generation, worker version and configured source-to-MDM contract. Define separate completeness expectations for required vs optional links before adding checks. |
| Registration links use governed Company IDs | Registration offering: 732 rows, 241 null, 412 distinct nonnull IDs (all match governed Company). Registration statement line: 27,415 rows, 10,008 null, 340 distinct (all match governed Company). | Resolved IDs match current authority; nulls need business-condition analysis, not blanket completeness checks. | Identify which rows require a registrant master and measure only that denominator. |
| Custodian Company/person links have nulls | `adv_custody`: 3,022 rows; adviser Company IDs resolve to 1,493 distinct legacy Company IDs, custodian MDM ID is null for all rows. | Custodian may be an unmastered/optional third party; field meaning and modeled kinds must be confirmed. | Trace custody contract, target kind, and source semantics; do not assert completeness yet. |
| Owner Company link has high null rate | `insider_reporting_owner`: 5,743 rows; 5,711 Company link IDs null; person IDs and issuer IDs have separate coverage. | A reporting owner can be an individual; Company is likely conditional. Null count alone is not a defect. | Confirm owner type and conditional link contract; measure Company resolution only for business-entity owners. |
| N-PORT holding link coverage and load state | `nport_holding`: 0 rows. Two `sec.nport.security` Bookkeeping runs, created 2026-11-06 at 11:54 ET and 21:31 ET, remain `running`; both have `land_holding` pending. | Empty holdings do not establish a content defect: the observed load path has not completed. A downstream relationship step is also pending in one run. | Resolve the run state and confirm the deployed worker version before measuring N-PORT holding quality. Do not resume, cancel, or alter the runs as part of this read-only audit. |
| Company jurisdiction cross-source disagreement | Of 3,073 legacy Company records with a mapped SEC state-of-incorporation code and a nonempty GLEIF jurisdiction field, 134 differ under the configured place-comparison semantics. The count applies the pinned `sec-place-codes` mapping and comparison logic in `crates/source-contract/src/matching_values.rs`; the installed native extension could not execute that helper. | Candidate only: the two fields may conflict, or may reflect a source/time/entity association issue. The declared Company name-binding rules include place predicates; check their proving/activation state and record-level cause. | Trace these 134 cases against source assertions, field winners, Company identity evidence, and effective times. Do not classify all as defects before that review. |
| Listing venue MIC coverage | 617,684 of 1,392,524 listing details carried a MIC in the observed snapshot. | Composite listings can legitimately have no venue MIC; crosswalk scope and vintage must be accounted for. | Classify each exchange code using the pinned `iso-10383-mic` crosswalk and compare only listings expected to resolve. |

The legacy and governed MDM counts differ. Finish tracing the governed entities
by kind; do not use one store's counts as the denominator for another store's
fields or links.

### Legacy master field and identifier presence

Read-only streamed the 448,443 legacy master records on 2026-11-08. Counts are
nonempty values per field/identifier; they describe presence only, not whether
the value is correct or required. Do not turn low counts into failures without
the field's source and business contract.

| Kind and denominator | Nonempty MDM fields | Nonempty identifiers |
|---|---|---|
| Company (10,698) | `name` 10,698; `address` 10,517; `fiscal_year_end` 6,217; `gleif_entity_creation_date` 2,693; `gleif_entity_status` 3,258; `gleif_initial_registration` 3,258; `gleif_legal_form` 3,258; `gleif_managing_lou` 3,258; `gleif_registration_authority` 3,258; `gleif_registration_authority_entity_id` 3,141; `gleif_registration_status` 3,258; `gleif_validation_source` 3,258; `jurisdiction` 3,258; `sic` 6,414; `state_of_incorporation` 5,787 | `cik` 8,361; `crd` 2,337; `lei` 3,258 |
| Fund structure (12,937) | `name` 12,937 | `sec_series_id` 12,937; `lei` 12,867 |
| Person (31,125) | `legal_name` 31,125 | `cik` 31,125 |
| Security (393,683) | `asset_category` 389,114; `currency` 393,500; `derivative_category` 5,264; `investment_country` 392,902; `issuer_type` 390,300; `market_sector` 382,648; `name_of_issuer` 393,674; `restricted` 390,318; `security_type` 382,500; `security_type2` 380,488; `share_class` 1,449; `title_of_class` 393,510 | `cusip` 375,014; `figi` 382,649; `isin` 390,458; `loanx` 424; `sedol` 22,092; `ticker` 129,767 |

The 70 fund structures without a nonempty LEI exceed the two-record exception
count stated in the pinned proving-run rationale. The binding rules allow the
SEC series ID to identify a fund without an LEI, and the N-PORT combine rule
skips an LEI that is absent or not uniquely attributable. This is therefore a
reconciliation candidate, not a confirmed defect: identify the snapshot and
source-delivery difference from the proving run before deciding whether the
additional missing LEIs are expected.

## Coverage by entity family

| Family | Configured representation and observed population | Downstream evidence | Audit status |
|---|---|---|---|
| Companies | Separate `company` kind; SEC Company, GLEIF Level 1, IAPD ADV and N-PORT registrant inputs. Legacy MDM: 10,698; governed MDM: 8,361. Legacy Company has a nonempty jurisdiction field on 3,258 records. | Company facts, line items, measures, insider issuer/owner links, ADV custody and registration links. | Partial. Jurisdiction nonempty is not the non-US denominator; need classify with the pinned ISO reference and trace the full source/master field set. |
| N-PORT funds | `fund_structure` is the series-level master; Company can separately hold profile `fund`. Legacy/governed fund structures: 12,937; governed Company fund profiles: 1,947. | N-PORT security holding spec includes fund, registrant Company and security links, but Silver currently has 0 holdings. Silver relationship has 12,937 legacy `IS_SUBFUND_OF` rows; governed MDM has the same count of current edges. | Partial. Trace registrant/series inputs, file-date relationship basis and current ID alignment. Holdings are unmeasurable until a populated run exists. |
| Private equity | No `private_equity` kind or explicit PE classification exists in the inspected master-kind catalog. Company rules recognize a `private_offering` form as one input to Company classification; this describes a filing/form, not a private-equity entity. | No distinct PE downstream link is configured. N-PORT fund structures may include private-fund structures, but the current empty holdings table cannot establish that population. | Unresolved representation. Do not report private-offering Companies as private equity. Complete source and identifier trace for any evidence-backed PE cohort in configured Company/fund data. |
| International companies/entities | In legacy Company, 1,405 records have a SEC state-of-incorporation place classified `FOREIGN` or `CANADIAN`; among records without that field, 57 more have a non-US GLEIF jurisdiction under pinned place codes (1,462 total by this rule). GLEIF jurisdiction is nonempty on 3,258 records; 599 map to a non-US country. The configured `international_organization` kind has zero legacy masters. | Company links appear in the Silver tables above; governed/legacy endpoint mismatch differs by table. | Partial. This establishes a legacy non-US cohort for tracing, not field correctness. Trace its identities, source inputs, downstream links, and jurisdiction disagreements; confirm zero international-organization population in governed MDM. |
| People | Separate `person` kind; legacy MDM: 31,125; governed MDM: 31,097. Configured SEC submissions and beneficial-ownership reporting-owner paths. | Insider reporting owner has 5,743 rows; 4,339 distinct nonnull person IDs resolve to legacy Person, while 781 rows have no person ID. | Partial. Distinguish individuals/entities and required-person cases from optional/missing source keys; trace person fields and source identity end-to-end. |
| Securities | Separate `security` kind; legacy MDM: 393,683; governed MDM: 383,441. Security sources include 13F securities, N-PORT security and OpenFIGI. | Silver relationship has 42,383 legacy `ISSUED_BY` rows but governed MDM has 505 edges; N-PORT holdings are empty and configured 13F tables are absent from this Silver schema. Listing detail MIC count is 617,684/1,392,524. | Partial. Trace the allowed issuer kinds and source evidence; classify listing/venue exceptions against the pinned RDM crosswalk; resolve Silver table/run coverage. |

## Candidate check definitions

These are check contracts to measure and prove, not enabled checks. DataKitchen
TestGen classifies the first two as referential/consistency checks; the platform
Silver engine currently supports only `identifier`, `in_set`, `one_value`,
`not_after`, and `reason_if_empty`, so these predicates cannot be represented
truthfully as existing field-only checks.

1. **Silver MDM link matches configured authority**: for every registered link,
   resolve its `source_key` using the link's configured `source_code` and
   `kind`. When a current MDM identity exists, require the row's
   `mdm_id_column` to equal it; when no identity exists, require the MDM ID
   column to be null. Evaluate only the row's declared link contract; do not
   require every optional source key to resolve.
2. **Silver relationship endpoints and edge match current authority**: require
   each live relationship row's type, direction, source and target kinds, and
   endpoint IDs to match an authoritative MDM relationship, including its
   effective-time/file-date rule. Do not use a former MDM generation as a
   successful reference.
3. **Conditional Company/person link completeness**: once source rules identify
   which reporting-owner records are entities versus people, require the
   corresponding owner link and prohibit the opposite link only for those
   classified cases. This requires a conditional/cross-field check; present
   field checks do not express the predicate.

The smallest implementation issue is a governed cross-store Silver reference
check that uses the existing link contract and current MDM resolver, reports
failing row counts without exposing source values, and supports a planted
invalid-ID proof. Relationship checks additionally need an authoritative read
of current typed relationships. Do not add a runtime dependency on TestGen.

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
