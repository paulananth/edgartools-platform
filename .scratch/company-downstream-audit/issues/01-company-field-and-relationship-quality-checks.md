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
- [x] Enumerate configured kinds and the connected snapshot's population counts. Legacy `mastering_master` has 10,698 Companies, 12,937 fund structures, 31,125 people, and 393,683 securities; branch, government, international-organization, and venue have no legacy rows. The governed MDM tables on the current connection are empty, so governed-kind counts and generation cannot be confirmed here. Earlier governed counts (8,361 Companies, 12,937 fund structures, 31,097 people, 383,441 securities; max generation 2,619) are retained as prior observations only.
- [x] Inventory nonempty source assertion fields and identifiers for all 11 feeds represented in the legacy mastering snapshot, alongside the master-field presence inventory below. This is presence evidence only; it does not validate field semantics, requiredness, or full downstream coverage.
- [ ] Reproduce the AAPL trace against the pinned snapshot and confirm the checklist catches its known Company paths; select a control entity for every other populated kind.
- [ ] Trace every entity in deterministic batches through source-to-MDM identity, each MDM field, and each linked downstream field; report coverage, missing links, conflicts, duplicates, stale references, and applicable per-kind denominators.
- [ ] Trace typed relationship paths for every populated kind, including `ISSUED_BY` from Security to its allowed issuer kinds; verify endpoint kind, direction, current MDM identity, time basis, and source evidence. Source assertion inventory confirms 12,937 N-PORT `IS_SUBFUND_OF`, 245,130 N-PORT `ISSUED_BY`, 4,962 `BENEFICIAL_OWNER_OF`, and 14,886 `EMPLOYED_BY` relation assertions; repeated filing sightings must be reduced to the governed edge grain before comparing to Silver.
- [ ] Trace N-PORT registrants, funds, series, holdings, and securities to their mastered fund/security/company or other entity records; include private-equity structures where present and check actual configured representation. Legacy fund-structure masters: 12,937, all with the `fund` profile; 1,947 Company masters also carry `fund`. Silver `nport_holding` currently has zero rows, so holdings coverage is unmeasurable in this snapshot. All 12,937 Silver subfund links have `valid_from_basis=observed`; configured source rules use filing date provisionally while flagging that authoritative inception remains unknown.
- [ ] Trace international entities and all non-US Company-like records through identifiers, source fields, relationships, and downstream references; report them separately from domestic Companies. The configured `international_organization` kind has zero observed masters; Company rules include a jurisdiction field, so determine the non-US Company denominator without exposing values.
- [ ] Reproduce the earlier protocol-7 entity-link resolver comparison for every populated Silver link. Its prior row-level counts cannot be rerun while governed MDM tables are empty on the current shared connection; historic producer and safe refresh timing also remain unresolved.
- [ ] Map Silver relationship endpoints from legacy IDs to current MDM identities by configured source keys, then compare typed edges, direction, and effective dates. Silver has 55,320 rows; the governed relationship projection is empty in the current connection, while a prior snapshot reported 13,442. Confirm the loaded producer and identity transition before deciding whether to repair or retire any rows.
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

**Snapshot qualification:** a fresh connection to the designated shared
`local-test-server` during this audit found 448,443 legacy `mastering_master`
rows but zero rows in governed `mdm.master_entity`, `mdm.current_record`, and
`mdm.relationship_version`; these tables have no row-level security policy.
Therefore every governed-store count and resolver comparison below is an
earlier reported measurement that is not reproducible against this current
connection. Treat those rows as provisional leads, not confirmed current
defects, until the intended populated governed snapshot is identified.

| Finding | Measurement | Current assessment | Next validation |
|---|---|---|---|
| Silver relationship edge counts and endpoint identity | Silver: 42,383 `ISSUED_BY` plus 12,937 `IS_SUBFUND_OF` (55,320 total). An earlier governed-store read reported 505 and 12,937 respectively, with zero raw exact matches on relationship ID, type, and endpoints. | The earlier raw-ID comparison is not reproducible: governed relationship projection is empty in the current shared connection. The 41,878-row `ISSUED_BY` difference and endpoint mapping remain provisional. Silver subfund links are file-date-provisional (`valid_from_basis=observed`) as configured; authoritative inception remains flagged unknown. | Identify the populated governed snapshot, map endpoints through configured source keys, and compare type, direction, effective date, and assertion evidence. |
| Silver entity-link resolver comparisons | Earlier reported current-resolver deltas: Company fact 5,113,685, line item 96,393, measure 167,640, insider position issuer 13,622, owner Person 4,962 set IDs, owner Company 32, and insider issuer 5,199. Reported no-current-master/null rows were 21,294, 414, 720, 709, 781, 5,711, and 544. | These exact-resolver comparisons are not reproducible while governed projection is empty. Preserve them as unverified prior measurements, not confirmed current defects; historic producer and refresh timing also remain unknown. | Identify the populated governed snapshot, rerun each table against the protocol-7 resolver, then trace confirmed rows to landing generation and runtime. |
| Registration links | Earlier resolver read reported offerings: 491 matches, 1 resolvable null and 240 no-current-master null; statement lines: 17,407 matches, 3 resolvable null and 10,005 no-current-master null. | The four resolvable-but-null rows are candidates only until that populated resolver snapshot is reproduced. | Rerun against populated governed MDM, trace any confirmed rows to landing receipts, and prove the check with a planted null ID. |
| ADV adviser/custodian links | Earlier resolver read reported 3,022 set adviser IDs across 1,864 keys without current masters, and 3,022 null custodian IDs across 498 keys (106 BD-number, 118 LEI, 274 name-only). | The current governed source-record projection is empty, so the earlier no-pointer counts are not reproducible now. The completed ADV run targeted legacy `mastering`; this does not prove governed MDM received the records. | Verify the run target, then compare adviser and identifier-based custodian keys with populated current assertions, masters, and receipts. Keep name-only cases conditional. |
| Owner Company link has high null rate | `insider_reporting_owner`: 5,743 rows; 5,711 Company link IDs null; person IDs and issuer IDs have separate coverage. | A reporting owner can be an individual; Company is likely conditional. Null count alone is not a defect. | Confirm owner type and conditional link contract; measure Company resolution only for business-entity owners. |
| N-PORT holding link coverage and load state | `nport_holding`: 0 rows. Two `sec.nport.security` Bookkeeping runs, created 2026-11-06 at 11:54 ET and 21:31 ET, remain `running`; both have `land_holding` pending, and the later run also has `links` pending. | Empty holdings do not establish a content defect: the observed load path has not completed. | Resolve the run state and confirm the deployed worker version before measuring N-PORT holding quality. Do not resume, cancel, or alter the runs as part of this read-only audit. |
| Company jurisdiction cross-source disagreement | Of 3,073 legacy Company records with a mapped SEC state-of-incorporation code and a nonempty GLEIF jurisdiction field, 134 differ under the configured place-comparison semantics. The count applies the pinned `sec-place-codes` mapping and comparison logic in `crates/source-contract/src/matching_values.rs`; the installed native extension could not execute that helper. | Candidate only: the two fields may conflict, or may reflect a source/time/entity association issue. The declared Company name-binding rules include place predicates; check their proving/activation state and record-level cause. | Trace these 134 cases against source assertions, field winners, Company identity evidence, and effective times. Do not classify all as defects before that review. |
| Listing venue MIC coverage | 617,684 of 1,392,524 listing details carried a MIC in the observed snapshot. | Composite listings can legitimately have no venue MIC; crosswalk scope and vintage must be accounted for. | Classify each exchange code using the pinned `iso-10383-mic` crosswalk and compare only listings expected to resolve. |

### Source assertion trace across populated kinds

Read-only source assertions in legacy mastering were counted on 2026-11-08.
Counts below are distinct feed assertions and nonempty values, not entity
denominators. They establish source field presence, not correctness or
requiredness. This covers all 11 source feeds represented in the local
assertion store.

| Entity family / source feed | Assertions | Nonempty source fields (count each) | Nonempty identifiers (count each) |
|---|---:|---|---|
| Company — SEC Company | 6,414 | `address`, `description`, `fiscal_year_end`, `name`, `sic`, `state_of_incorporation` (6,414) | `cik` (6,414) |
| Company — GLEIF Level 1 | 3,716 | `address`, `gleif_entity_creation_date`, `gleif_entity_status`, `gleif_initial_registration`, `gleif_legal_form`, `gleif_managing_lou`, `gleif_registration_authority`, `gleif_registration_authority_entity_id`, `gleif_registration_status`, `gleif_validation_source`, `jurisdiction`, `name` (3,716) | `lei` (3,716) |
| Company — IAPD ADV filings | 2,938 | `address`, `name` (2,938) | `crd` (2,938) |
| Company — N-PORT registrant | 5,841 | `address`, `name` (5,841) | `cik` (5,841) |
| Fund structure — N-PORT fund | 25,874 | `name` (25,874) | `sec_series_id` (25,874); `lei` (25,734) |
| Person — SEC submissions | 31,097 | `legal_name` (31,097) | `cik` (31,097) |
| Person — SEC ownership reporting owner | 4,962 | `legal_name` (4,962) | `cik` (4,962) |
| Security — OpenFIGI | 733,538 | `market_sector`, `name_of_issuer`, `security_type`, `security_type2` (733,538) | `figi` (733,538); `cusip` (353,491); `isin` (380,047); `ticker` (243,729) |
| Security — N-PORT security | 428,262 | `asset_category`, `currency`, `derivative_category`, `investment_country`, `issuer_type`, `name_of_issuer`, `restricted`, `share_class`, `title_of_class` (428,262) | `cusip` (391,953); `isin` (425,310); `sedol` (23,533); `loanx` (440) |
| Security — SEC ownership security v1/v2 | 5,671 | none | none |

The N-PORT fund feed contains two assertions per 12,937 series in this
snapshot. Its 140 assertions without LEI correspond to 70 fund masters without
LEI, above the two-record exception in the pinned proving rationale. This is a
reconciliation candidate: series ID remains the configured identifying key,
and the proving snapshot/source delivery must be matched before treating it as
a defect. The 5,671 SEC ownership-security assertions have no nonempty fields
or identifiers; their cross-reference and consumer path still needs tracing.

### Governed snapshot availability

A fresh connection to the designated shared `local-test-server` on 2026-11-08
found 448,443 rows in legacy `mastering_master`, but zero in governed
`mdm.master_entity`, `mdm.current_record`, and `mdm.relationship_version`.
These tables have no row-level security policy. Governed counts and resolver
comparisons recorded in the earlier table are therefore not reproducible
against this current connection; treat them as unverified prior observations,
not confirmed current defects, until the intended populated governed snapshot
is identified.

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

### Earlier reported governed MDM source-record coverage (not reproducible)

An earlier read reported 794,456 pointers, grouped by source code and kind,
with no pointers for `sec.ownership.reporting_owner.v1`, `iapd.adv.filings.v1`,
or `iapd.adv.custodians.v1`. The current governed projection is empty, so these
counts and no-pointer findings cannot be reproduced. The legacy source
assertions above independently confirm those feeds have assertions; they do
not prove that the current governed MDM received or indexed them.

### Bookkeeping load status relevant to coverage

At the audit snapshot, Company fact landing had 119 verified items and 28
pending; line-item and measure derivation each had one verified and four
pending. Registration landing had 76 verified offerings, with 355 pending and
111 waiting; statement-line landing had 76 verified, 464 pending and two
waiting. Twenty-one owner and twenty-one position landing items were verified.
The ADV source run was complete. The two N-PORT security runs remain running
with holding land pending as described above. These states explain why empty
or partial Silver tables cannot be treated as complete quality populations.

## Coverage by entity family

| Family | Configured representation and observed population | Downstream evidence | Audit status |
|---|---|---|---|
| Companies | Separate `company` kind; SEC Company, GLEIF Level 1, IAPD ADV and N-PORT registrant inputs. Legacy MDM: 10,698; current governed count unavailable. Legacy Company has a nonempty jurisdiction field on 3,258 records; pinned-place mapping yields a 1,462 non-US cohort. | Company facts, line items, measures, insider issuer/owner links, ADV custody and registration links. | Partial. Source and master presence are measured; non-US source/master identity, downstream and 134 jurisdiction-candidate traces remain unfinished. |
| N-PORT funds | `fund_structure` is the series-level master; Company can separately hold profile `fund`. Legacy fund structures: 12,937; legacy Company fund profiles: 1,947. | N-PORT security holding spec includes fund, registrant Company and security links, but Silver currently has 0 holdings. Silver has 12,937 `IS_SUBFUND_OF` rows with file-date-provisional starts. | Partial. Registrant/series and file-date semantics are configured and measured; holdings cannot be traced until a populated run finishes; cross-store identity remains open. |
| Private equity | No `private_equity` kind or explicit PE classification exists in inspected rules. Company rules use `private_offering` as a filing/form signal, not entity classification. Fund structure assertions expose name, series ID and optional LEI only. | No distinct PE downstream link is configured. Empty N-PORT holdings prevent portfolio-level evidence in this snapshot. | Representation is unclassified. Do not infer PE status from a private-offering filing or fund name; a confirmed PE cohort/definition is needed before a PE-specific check can be measured. |
| International companies/entities | Legacy Company: 1,405 with SEC place mapped `FOREIGN`/`CANADIAN`; 57 more with no SEC place but non-US GLEIF jurisdiction; 1,462 total under this rule. Of 3,258 nonempty GLEIF jurisdictions, 599 map non-US. Legacy `international_organization` has zero masters; current governed count unavailable. | Company downstream tables are listed above; current governed endpoint comparison cannot be repeated. | Partial. Non-US denominator is measured in legacy MDM, but source identity/downstream trace and the 134 jurisdiction candidates remain open. |
| People | Separate `person` kind; legacy MDM: 31,125; current governed count unavailable. Sources are SEC submissions and beneficial-ownership reporting-owner assertions. | `insider_reporting_owner` has 5,743 rows; 4,339 distinct nonnull Person links resolve to legacy Person, 781 rows have no Person link. | Partial. Conditional owner type and full entity-to-downstream trace remain open; null count is not itself a defect. |
| Securities | Separate `security` kind; legacy MDM: 393,683; current governed count unavailable. Sources include 13F, N-PORT security and OpenFIGI. | Silver has 42,383 `ISSUED_BY` relationships, 0 N-PORT holdings, and no configured 13F Silver tables in the observed schema. Listing MIC coverage is 617,684/1,392,524. | Partial. Issuer endpoints, listing/venue exceptions and incomplete run/table coverage remain to trace. |
| Other configured kinds | `branch`, `government`, `international_organization`, and `venue` are configured. Legacy MDM has zero masters for these kinds; governed counts unavailable because its projection is empty. Company classification rules can defer probable government candidates; venue is a listing lookup target, not a populated entity kind in this snapshot. | No Silver rows establish downstream use of those absent masters. | Not traceable as populated entity families in the connected snapshot. Verify candidate/deferred records and source onboarding separately; do not convert absence into a quality failure. |

## Candidate check definitions

These are check contracts to measure and prove, not enabled checks. DataKitchen
TestGen classifies the first two as referential/consistency checks; the platform
Silver engine currently supports only `identifier`, `in_set`, `one_value`,
`not_after`, and `reason_if_empty`, so these predicates cannot be represented
truthfully as existing field-only checks.

### Existing quality checks and gaps by entity family

| Family | Existing configured checks | Measured gap or next check |
|---|---|---|
| Company, including international Company records | SEC name presence, registered-agent/placeholder-address handling, pinned SEC place-code validity; GLEIF name and address checks; ADV name presence; N-PORT registrant provisional registration-start flag. | Reconcile SEC incorporation place with GLEIF jurisdiction for the 134-record candidate cohort after source/effective-time tracing. Use a cross-source consistency check only after the cause is resolved; the observed field-presence counts are not completeness targets. |
| N-PORT fund structure | Series ID and LEI format/cardinality rules; `subfund_start_is_authoritative` flags when the start is provisional. | Reconcile 70 masters without LEI against the two-record proving exception. Keep the SEC series ID as sufficient identity when LEI is absent or nonunique. A check must distinguish an allowed missing LEI from an unapproved exception. |
| Private equity | No PE kind, explicit PE classification, or PE-specific quality contract. | Do not infer PE from `private_offering` or from fund names. Define how PE is identified in approved Company/fund inputs before writing a cohort or check. |
| Person | SEC submissions and ownership owner name-presence and letter-pattern checks; CIK identifier contract. | Trace owner classification to the conditional Person/Company links. A null Company link is not a defect for an individual; this needs a conditional cross-field/reference check. |
| Security | N-PORT issuer-placeholder and filed share-class checks; 13F share-class check; CUSIP/ISIN identifier checks. | Trace `ISSUED_BY` endpoints to configured issuer kinds and evidence. Classify listing MICs using exchange code plus the pinned MIC reference; absence is not failure for composite listings. |
| Branch, government, international organization, venue | No populated master family in the legacy snapshot; no downstream quality denominator. | Do not emit zero-failure checks over empty populations. Inspect deferred government candidates and venue lookup behavior after an authoritative populated governed snapshot is available. |

These configurations already cover source-level completeness, validity, and
some consistency conditions. The measured cross-store identity and typed-edge
predicates are referential checks in DataKitchen TestGen terms, but require a
governed Silver check primitive; they cannot be truthfully approximated by a
field-only check. No candidate was added or activated without a pinned
population and planted-invalid proof.

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
