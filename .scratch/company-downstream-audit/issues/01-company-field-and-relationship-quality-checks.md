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

- [x] Confirm the reference method and current check formats: the operator-selected Company is the control trace; Silver table specs declare `checks`; the data-quality skill lists supported checks; DataKitchen TestGen research is pinned at `docs/research/datakitchen-testgen-test-types-2026-11-02.md`, sourced from [`DataKitchen/dataops-testgen`](https://github.com/DataKitchen/dataops-testgen/tree/3606859cf8bb4f809d2b19acc51462420829c4ab/testgen/template/dbsetup_test_types) (reviewed 2026-11-08 07:22 ET).
- [x] Enumerate configured kinds and the connected snapshot's population counts. Legacy `mastering_master` has 10,698 Companies, 12,937 fund structures, 31,125 people, and 393,683 securities; branch, government, international-organization, and venue have no legacy rows. The governed MDM tables on the current connection are empty, so governed-kind counts and generation cannot be confirmed here. Earlier governed counts (8,361 Companies, 12,937 fund structures, 31,097 people, 383,441 securities; max generation 2,619) are retained as prior observations only.
- [x] Inventory nonempty source assertion fields and identifiers for all 11 feeds represented in the legacy mastering snapshot, alongside the master-field presence inventory below. This is presence evidence only; it does not validate field semantics, requiredness, or full downstream coverage.
- [x] Reproduce the operator-selected Company control trace in legacy MDM/Silver and select controls for the other populated kinds. The Company control resolves to one Company with one SEC Company and one GLEIF assertion, 15 populated MDM field names, two identifier namespaces, 25,135 fact rows, 437 line-item rows, 760 measure rows, 10 issuer-position rows, three insider issuer rows, and 57 `ISSUED_BY` edges targeting the Company. One control each was traced for fund structure, Person, and Security; their details and limits follow below. Governed identity remains unavailable in this snapshot.
- [ ] Trace every entity in deterministic batches through source-to-MDM identity, each MDM field, and each linked downstream field; report coverage, missing links, conflicts, duplicates, stale references, and applicable per-kind denominators.
- [ ] Trace typed relationship paths for every populated kind, including `ISSUED_BY` from Security to its allowed issuer kinds; verify endpoint kind, direction, current MDM identity, time basis, and source evidence. Source assertions include 48 GLEIF `SUCCESSOR_ENTITY`, 3,017 ADV `CUSTODIAN`, 12,937 N-PORT `IS_SUBFUND_OF`, 245,130 N-PORT `ISSUED_BY`, 4,962 `BENEFICIAL_OWNER_OF`, and 14,886 `EMPLOYED_BY` declarations; repeated filing sightings must be reduced to governed edge grain before comparing to Silver.
- [x] Compare legacy N-PORT `ISSUED_BY` declarations to Silver by exact endpoint pair (read-only 2026-11-08 11:42 ET). The 245,130 declarations reduce to 225,221 distinct Security/issuer-source pairs; 43,601 target a retained GLEIF assertion. Silver has 42,383 pairs, all backed by the source pair set, with zero Silver-only pairs. Of 1,218 source-only pairs, 1,214 lack a mastered GLEIF target; one has neither endpoint mastered; one has a Company issuer master but no Security master; and two have both Security and Company masters but no Silver edge. All 1,421 declarations behind these source-only pairs have a nonempty start. These two are omission candidates; one current N-PORT run still has its `links` step pending, so a final publication gap is not yet established.
- [x] Compare N-PORT `IS_SUBFUND_OF` endpoints and both endpoint kinds/profiles to Silver (read-only 2026-11-08 11:57 ET). All 12,937 distinct legacy source pairs resolve to a `fund_structure` with the `fund` profile and a `company` with the `fund` profile. Exact Silver endpoint comparison has 12,937 overlaps, zero mastered source pairs absent from Silver, and zero Silver pairs without a mastered source pair. All Silver starts are nonempty and `valid_from_basis=observed`; the source has no authoritative start, so the configured file-date fallback remains provisional.
- [x] Compare ownership relationship endpoints to their designated owner Silver table (read-only 2026-11-08 11:57 ET). `BENEFICIAL_OWNER_OF` and `EMPLOYED_BY` each produce the same 4,139 distinct mastered Person/issuer Company pairs; both sets exactly match the nonnull Person/issuer endpoints in `insider_reporting_owner`, with zero source-only or Silver-only pairs. The Silver table does not preserve relationship type/capacity as a distinct edge, so typed capacity and period behavior still require current governed MDM evidence; the governed relationship projection is empty in this snapshot.
- [x] Assess source endpoint assignment for GLEIF successor and ADV custodian links (read-only 2026-11-08 12:03 ET). None of 48 `SUCCESSOR_ENTITY` declarations has an assigned source Company master; all 48 source subjects are in open `binding_required` review, and 26 target subjects resolve to a legacy Company. All 3,017 ADV `CUSTODIAN` declarations have a source Company master, but the target custodian feed has no retained legacy source assertions or assigned masters. These are source/target coverage limits, not confirmed broken edges; the current governed projection is empty.
- [x] Determine whether private equity has a separate representation in the active MDM/Silver path. The eight-kind catalog has no PE kind; `fund` is a profile on Company/fund structure. Active IAPD ADV rules master adviser filings and custodians, not private-fund records. Retained ADV schemas still describe private-fund details and PE roster indicators, but the read-only local Silver snapshot has no private-fund table (3,022 custody rows; zero N-PORT holdings). This establishes no current PE quality denominator; it does not establish defects in any PE records. Verified against current config/schema and local Silver on 2026-11-08 10:25 ET.
- [ ] Finish tracing N-PORT registrants, funds, series, holdings, and securities to their mastered fund/security/company or other entity records. Keep N-PORT series distinct from ADV private funds. Legacy fund-structure masters: 12,937, all with the `fund` profile; 1,947 Company masters also carry `fund`. The 12,937 `IS_SUBFUND_OF` source endpoint pairs exactly match Silver. Silver `nport_holding` currently has zero rows, so holdings coverage is unmeasurable in this snapshot. All subfund starts are `observed` file-date fallbacks; authoritative inception remains unknown.
- [x] Measure every legacy Security listing MIC against pinned MIC version 1 and the configured 246-code OpenFIGI exchange crosswalk. Of 1,392,524 listing rows, 617,684 have a MIC; all are valid reference codes and match the configured exchange mapping, with zero invalid, mismatch, or missing-MIC rows for mapped exchanges. The remaining 774,840 have no MIC: 414,643 have an unmapped exchange plus a composite FIGI, 42,639 have an unmapped exchange and no composite FIGI, and 317,558 have neither exchange nor composite FIGI. Full read-only pass over all 393,683 Security masters completed 2026-11-08 10:54 ET; the last three categories still need business/source classification.
- [x] Trace the entire legacy non-US Company cohort through source assertions, identifiers, field presence, and Silver references. Pinned SEC place mapping identifies 1,405 records; 57 additional records without an SEC place have a non-US GLEIF jurisdiction under the approved country mapping (1,462 total). This is a legacy/Silver trace; current governed identity remains unverified. The configured `international_organization` kind has no legacy masters.
- [x] Compare every Silver MDM pointer directly with the complete legacy master-ID set. Read-only full-table grouping covered all 16 configured link columns on 2026-11-08 10:29 ET: every populated Company-fact/line-item/measure, insider, ADV-adviser, and relationship endpoint ID matched a legacy master; `adv_custody.custodian_mdm_id` was null on all 3,022 rows; registration pointers (491 offering rows and 17,407 statement-line rows) did not match any legacy master ID; all three N-PORT holding links had zero rows. Those registration IDs belong to an unverified MDM identity generation because governed master tables are empty on this connection; the comparison is membership evidence, not proof that they are stale or wrong.
- [x] Trace the one observed Security ticker over the configured three-master forward claim through actual Form 4 records and issuer declarations. Two Form 4 assertions carrying it are both in open `conflicting_identifiers` review, as the configured `on_several: review` rule requires; neither silently auto-binds. The same four Security masters have three `ISSUED_BY` declarations targeting two GLEIF source subjects, neither present in retained GLEIF source assertions, and no Silver issuer edge. The ticker case is handled by review, not a confirmed quality defect; the missing GLEIF targets remain a source-coverage candidate. Verified from read-only current legacy MDM/source/Silver data on 2026-11-08 10:47 ET.
- [x] Verify the SEC–GLEIF jurisdiction binding rule's current approval state and proof (policy and `rules/merge/pending-proofs.yaml`, 2026-11-08 11:00 ET). `sec-gleif-name-jurisdiction` is active for Company with a 300/300 measured proof (95% one-sided lower bound 0.991062) and zero violations in 257 adversarial cases. This establishes the rule is approved and enabled; it does not establish when the legacy records were last processed or explain the 134 field disagreements.
- [x] Trace the 134 jurisdiction candidates against their accepted legacy masters, field winners, and retained assertion presence (pinned place mapping plus configured `places_agree` logic, read-only 2026-11-08 11:08 ET). All 134 are accepted Company masters; each field winner is from its expected source, and both SEC Company and GLEIF Level 1 assertions are retained for every candidate. This rules out missing source assertions as the explanation, but not stale/effective-time or identity-history causes.
- [x] Break down SEC Company classification deferrals by configured rule step and distinct source-record locator (read-only 2026-11-08 11:10 ET). All 69,816 blocking events map to distinct locators. Step 11 leaves 67,166 unclassified with no probable kind; step 1 adds 1,062 without a probable kind; step 7 adds 73 without a probable kind. The other 1,515 are explicitly held as probable Company (599), Person (658), fund structure (226), or government (32). This measures the configured hold-back population without treating every deferral as a defect.
- [x] Re-measure row-local configured Company Silver checks on the full current stored population (read-only 2026-11-08 11:19 ET). All 5,134,979 `company_fact` rows (3,113,260 with both period dates), 96,807 `company_line_item` rows (46,971 with both period dates), and 168,360 `company_measure` rows were checked. `period_start_not_after_end`, `empty_value_has_reason`, and `window_years_known` each have zero failing rows; all three tables have zero persisted `quality` tags. `one_value` checks remain unmeasured here because they are scoped to an individual delivery, not the combined historical table.
- [x] Reconcile the 70 N-PORT fund structures without a master LEI to their retained assertions (read-only 2026-11-08 11:24 ET). All 70 have a `sec_series_id` in the master and source assertion; none of their retained N-PORT fund assertions claims an LEI. The configured series-ID rule can identify them without a LEI, so the 70 are not defects and are not comparable to the two proving-run exceptions that lacked identity evidence.
- [x] Reconcile missing Person links on insider reporting owners to classification holds using the exact filing-owner key across MDM and Silver (read-only 2026-11-08 11:27 ET). All 781 Person-null owner rows match 781 distinct source records: 331 `classification_deferred` and 450 `classification_entity_undetermined`. Of those, 32 already link to a Company (14 deferred, 18 undetermined); 749 have neither an owner Person nor Company link (317 deferred, 432 undetermined). The key sets match exactly, with no unmatched rows.
- [x] Verify whether those unresolved owner rows are allowed to land (read-only config review, 2026-11-08 11:28 ET). `sec.ownership.reporting_owner.v1` explicitly treats both classification reasons as nonblocking, and Bookkeeping lands owner rows after merge. The 749 without either link are expected to remain unresolved while classification is held; do not flag them as broken links without a later classification decision.
- [ ] Reproduce the earlier protocol-7 entity-link resolver comparison for every populated Silver link. Its prior row-level counts cannot be rerun while governed MDM tables are empty on the current shared connection; historic producer and safe refresh timing also remain unresolved.
- [ ] Map Silver relationship endpoints from legacy IDs to current MDM identities by configured source keys, then compare typed edges, direction, and effective dates. Silver has 55,320 rows; the governed relationship projection is empty in the current connection, while a prior snapshot reported 13,442. Confirm the loaded producer and identity transition before deciding whether to repair or retire any rows.
- [ ] Finish classifying Security listing venue coverage. Confirm the 414,643 no-MIC composite rows are valid composite listings; classify the 42,639 rows with an unmapped exchange and no composite FIGI against the pinned RDM MIC crosswalk; establish whether the 317,558 rows with neither exchange nor composite venue detail are expected for this source. Do not classify them as failures merely because MIC is absent.
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
| Silver relationship edge counts and endpoint identity | Legacy N-PORT source: 245,130 `ISSUED_BY` declarations, 225,221 distinct Security/issuer-source pairs; 43,601 have a retained GLEIF assertion. Silver: 42,383 pairs. Exact comparison has 42,383 overlap, 1,218 source-only, zero Silver-only; 1,214 source-only pairs lack a mastered GLEIF target, one lacks both masters, one lacks a Security master, and two have both masters but no Silver edge. One current N-PORT run still has `links` pending. For `IS_SUBFUND_OF`, all 12,937 distinct fund-structure/Company pairs resolve to endpoints with the `fund` profile and exactly match Silver; zero source-only or Silver-only pairs. Every Silver subfund start is `observed` (file-date provisional). | N-PORT subfund endpoint coverage matches the legacy source pair set. Two fully mastered `ISSUED_BY` pairs remain possible omissions until the pending stage completes. These comparisons use legacy IDs only; the governed MDM relationship projection is empty, so current governed identity/effective-time evidence is unavailable. | Reconcile the two fully mastered issuer pairs after the pending stage completes; then repeat both comparisons on the populated governed MDM generation and verify evidence and temporal semantics. |
| Other configured relationship types and consumers | Legacy source assertions declare 48 `SUCCESSOR_ENTITY`, 3,017 `CUSTODIAN`, 4,962 `BENEFICIAL_OWNER_OF`, and 14,886 `EMPLOYED_BY`. None of the 48 successor declarations has a source Company master; all 48 source subjects are in open `binding_required` review, while 26 target subjects resolve to a legacy Company. All 3,017 custodian declarations have a mastered adviser, but the custodian source feed has no retained legacy assertions or masters; Silver `adv_custody` has 3,022 rows with null custodian MDM IDs. Both ownership types reduce to the same 4,139 distinct mastered Person/issuer Company pairs; each exact set matches nonnull owner/issuer endpoints in `insider_reporting_owner`, with zero source-only or Silver-only pairs. The owner Silver contract does not retain typed relationship capacity as a separate edge. | Successor and custodian results are source/target coverage limits, not confirmed broken links. Ownership endpoint pairs reach Silver, but typed capacity/period behavior is not verified by this endpoint-only comparison. The governed MDM projection is empty; custody's five-row difference is not a valid comparison until filing/row grain is reconciled. | Reconcile the 48 successor source reviews through the normal binding decision path; reconcile custodian feed registration/landing. Confirm ownership typed-edge and time evidence in a populated governed snapshot; reconcile ADV custody at its documented filing/row grain and verify the producer generation. |
| Silver entity-link resolver comparisons | Earlier reported current-resolver deltas: Company fact 5,113,685, line item 96,393, measure 167,640, insider position issuer 13,622, owner Person 4,962 set IDs, owner Company 32, and insider issuer 5,199. Reported no-current-master/null rows were 21,294, 414, 720, 709, 781, 5,711, and 544. | These exact-resolver comparisons are not reproducible while governed projection is empty. Preserve them as unverified prior measurements, not confirmed current defects; historic producer and refresh timing also remain unknown. | Identify the populated governed snapshot, rerun each table against the protocol-7 resolver, then trace confirmed rows to landing generation and runtime. |
| Registration links | Earlier resolver read reported offerings: 491 matches, 1 resolvable null and 240 no-current-master null; statement lines: 17,407 matches, 3 resolvable null and 10,005 no-current-master null. | The four resolvable-but-null rows are candidates only until that populated resolver snapshot is reproduced. | Rerun against populated governed MDM, trace any confirmed rows to landing receipts, and prove the check with a planted null ID. |
| ADV adviser/custodian links | Earlier resolver read reported 3,022 set adviser IDs across 1,864 keys without current masters, and 3,022 null custodian IDs across 498 keys (106 BD-number, 118 LEI, 274 name-only). | The current governed source-record projection is empty, so the earlier no-pointer counts are not reproducible now. The completed ADV run targeted legacy `mastering`; this does not prove governed MDM received the records. | Verify the run target, then compare adviser and identifier-based custodian keys with populated current assertions, masters, and receipts. Keep name-only cases conditional. |
| Insider reporting-owner identity links | `insider_reporting_owner`: 5,743 rows; 4,962 Person links, 32 Company links, 749 with neither, and no row with both. All 781 Person-null rows match the 781 retained source records deferred (331) or undetermined (450) by exact filing-owner key; the 32 Company links split across those queues (14 and 18), leaving 749 unlinked (317 and 432). Both classification reasons are explicitly nonblocking in the source contract, and the Bookkeeping flow lands owner rows after merge. | This is not a pointer mismatch: all owner-link gaps align exactly with unresolved classification. A null Company link is expected for known People; the 749 neither-linked rows are permitted unresolved cases, not proven invalid entities. | Keep them out of link-failure checks while classification remains unresolved. If later classified as a Person or Company, require the corresponding link and validate its current MDM identity. |
| N-PORT holding link coverage and load state | `nport_holding`: 0 rows. Read-only check at 2026-11-08 12:00 ET: two `sec.nport.security` Bookkeeping runs, created 2026-11-06 at 11:54 ET and 21:31 ET, remain `running`. Both have `land_holding` pending. The older run has `merge` waiting and `processed` pending; the later run also has `links`, `merge`, and `issuer_reduce` pending, with holding steps waiting. | Empty holdings do not establish a content defect: the observed load path has not completed. | Resolve the run state and confirm the deployed worker version before measuring N-PORT holding quality. Do not resume, cancel, or alter the runs as part of this read-only audit. |
| Company jurisdiction cross-source disagreement | Of 3,073 legacy Company records with a valid mapped SEC state-of-incorporation code and nonempty GLEIF jurisdiction, 134 disagree under the complete configured `places_agree` semantics, including U.S. territory aliases and country/subdivision compatibility. Reproduced with the pinned `sec-place-codes` canonical mapping and read-only aggregation over the full legacy Company population. All 134 are accepted Company masters; both expected source assertions are retained and each field winner is from its expected source. `sec-gleif-name-jurisdiction` is active with a 300/300 proof (95% one-sided lower bound 0.991062) and 0 violations across 257 adversarial cases. | Confirmed cross-source field disagreement, but not yet a confirmed data defect: the fields are deliberately source-owned separately, and the remaining cause may involve identity history, effective time, or processing under an earlier rule. The measured rule proof supports matching on its proof cohort; it does not attest every field pair. | Trace the exact assertions' effective times, bound/decision history, and producing rule version. Decide whether each disagreement represents an entity mismatch or a source-level quality issue before defining an enabled check. |
| Company Silver row-local checks | Full current stored-population evaluation: `company_fact` 5,134,979 rows, with 3,113,260 eligible period pairs; `company_line_item` 96,807 rows, with 46,971 eligible period pairs; `company_measure` 168,360 rows. The configured row-local checks `period_start_not_after_end`, `empty_value_has_reason`, and `window_years_known` each have zero failures. All three tables have zero persisted row-level `quality` tags. | The measured current rows satisfy these three checks; no row-level defect was found on these predicates. This is direct SQL evaluation against the current Silver snapshot, not proof that a Bookkeeping load report recorded the same counts. | Recover the per-delivery report evidence for the four `company_fact` `one_value` checks; their semantics are delivery-scoped and cannot be safely re-evaluated over the combined historical table. |
| Listing venue MIC coverage | Read-only full-population scan of all 1,392,524 legacy Security listing details against the 2,313 valid entries in pinned `iso-10383-mic` version 1 and 246 configured OpenFIGI exchange mappings: 617,684 rows have a MIC, every one is valid, all 617,684 match the configured exchange-to-MIC mapping, with zero invalid MICs, zero mapped-exchange mismatches, and zero missing MICs when the exchange is mapped. The 774,840 without MIC comprise 414,643 unmapped-exchange rows with a composite FIGI, 42,639 unmapped-exchange rows without a composite FIGI, and 317,558 rows with neither exchange nor composite FIGI. | Every present MIC passes the pinned reference and mapping. The mapped path has no observed omission. The remaining groups are not yet fully classified: composites may validly have no MIC, while an unmapped exchange or absent venue detail needs source/business interpretation. | Validate composite rows as no-MIC listings, classify the 42,639 unmapped-exchange rows using the local reference and source mapping, and decide the expected treatment of the 317,558 rows with no exchange/composite evidence. |
| Security ticker fan-out and review behavior | Of 129,394 distinct legacy ticker values, 366 appear on more than one Security; one value appears on four, above the configured `ticker.forward: 3` claim. The four masters have three CUSIPs, four ISINs, 69 FIGIs, four distinct issuer-name values, and four security-type values. Two Form 4 source assertions carry the over-limit ticker; both are open `conflicting_identifiers` reviews. The four Securities declare three `ISSUED_BY` links to two GLEIF source subjects, neither retained in the current GLEIF assertion set; none has a Silver `ISSUED_BY` edge. | The configured Form 4 rule sends a reused ticker reaching several Securities to review, and both observed records follow that path. The ticker case is not an auto-binding defect. The issuer edges cannot be confirmed because the required target source records are absent; do not invent endpoints or count these as missing Silver edges until source coverage is reconciled. | Trace the two absent GLEIF targets through retained capture receipts and the relevant load window. Check additional over-limit ticker cases only when they can be aggregated without exposing ticker values; preserve the existing review outcome. |

### Legacy identity, deferral, and review queues

These are counts of rows in the legacy MDM deferral and review tables at the
same snapshot. A queue row is not necessarily a distinct entity or a defect;
it shows where classification, identifier, or binding work was retained.

| Source family | Retained queue evidence | Assessment |
|---|---|---|
| Company | 69,816 blocking SEC Company `classification_deferred` records; all 69,816 have distinct retained source-record locators. Configured steps classify 599 as probable Company, 658 probable Person, 226 probable fund structure, and 32 probable government; 68,301 have no probable kind (step 11: 67,166; step 1: 1,062; step 7: 73). | Most of this snapshot's held records reach the rule's no-match/fall-through path. This is a measured classification-coverage gap, not proof that the hold is wrong: source records still need business review before any new kind or rule is defined. |
| International Company / GLEIF | 39 nonblocking `unsupported_identity_kind` deferrals; 1,891 `binding_required` review rows, 458 still open. | Review and classification outcomes need a controlled disposition. The connected governed projection is empty, so no current governed endpoint comparison is possible. |
| N-PORT fund | 14 blocking `invalid_lei_checksum` deferrals. | Existing identifier validation is catching invalid LEIs. Reconcile the retained source assertions and correct or disposition them through the normal workflow. |
| N-PORT Security | 2,428 `invalid_cusip_checksum` deferrals and one `invalid_cusip`; 6 open `conflicting_identifiers` reviews. | Invalid CUSIPs are kept out of matching by the configured dataset contract; conflicting identifier cases remain explicit review work. |
| Person / ownership owner | SEC submissions have 11,096 `classification_deferred` and 34,038 `classification_entity_undetermined` events. Ownership owner has 331 deferred and 450 undetermined records, exactly matching all 781 Silver rows without a Person link by filing-owner key. | SEC submissions counts remain event counts, not unique people. For ownership owners, 32 of the 781 also have a Company link; 749 have neither. This is unresolved classification coverage, not evidence of a stale or broken pointer. |
| Security ownership references | 15 and 83 `missing_record_identity` deferrals from ownership security v1/v2; 8 and 101 open `conflicting_identifiers` reviews respectively. | Trace the missing identity and conflict groups against their source contract and the Security lookup path; do not treat the empty `fields`/`identifiers` sections as an error by themselves. |
| OpenFIGI | 37,681 nonblocking `not_found_by_openfigi` deferrals. | Not found may be an allowed lookup outcome; no completeness failure is asserted without an approved request/response coverage denominator. |

### Source assertion trace across populated kinds

Read-only source assertions in legacy mastering were counted on 2026-11-08.
Counts below are distinct feed assertions and nonempty values, not entity
denominators. They establish source field presence, not correctness or
requiredness. This covers all 11 source feeds represented in the local
assertion store.

Joining each retained source assertion to its legacy `entity_id` and the
legacy master table gives this assignment coverage. A linked master means the
legacy store assigned the assertion; it does not certify the assigned identity
against the current governed authority.

| Kind | Source feed | Assertions | Distinct linked legacy masters | Assertion rows without a linked master |
|---|---|---:|---:|---:|
| Company | SEC Company | 6,414 | 6,414 | 0 |
| Company | GLEIF Level 1 | 3,716 | 3,258 | 458 |
| Company | IAPD ADV filings | 2,938 | 2,337 | 0 |
| Company | N-PORT registrant | 5,841 | 1,947 | 0 |
| Fund structure | N-PORT fund | 25,874 | 12,937 | 0 |
| Person | SEC submissions | 31,097 | 31,097 | 0 |
| Person | SEC ownership reporting owner | 4,962 | 4,339 | 0 |
| Security | OpenFIGI | 733,538 | 382,649 | 0 |
| Security | N-PORT security | 428,262 | 393,510 | 6 |
| Security | SEC ownership security v1 | 398 | 335 | 63 |
| Security | SEC ownership security v2 | 5,273 | 1,508 | 826 |

No retained legacy assertion rows were present for `iapd.adv.custodians.v1` or
`sec.thirteenf.securities.v1`, despite related Silver contract/table paths.
That is a snapshot coverage gap to trace through captures and Bookkeeping; it
does not prove the providers have no records. The ownership-security rows with
no legacy master and the six N-PORT-security rows should be reviewed alongside
the matching deferred reasons below.

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
LEI. Read-only source-to-master tracing confirmed that all 70 have a series ID
and none of their retained source assertions claims an LEI. The configured
series-ID rule identifies them without a LEI; the two proving-run exceptions
refer to records without identity evidence and are not a missing-LEI
threshold. This is an allowed source state, not a defect. The 5,671 SEC
ownership-security assertions have no nonempty fields or identifiers; their
cross-reference and consumer path still needs tracing.

### Representative legacy control traces

Controls are selected for trace shape, not as a statistical sample. No master
values or identifiers are recorded here.

| Control family | Legacy source-to-master trace | Silver/downstream trace |
|---|---|---|
| Company control | One Company; one SEC Company assertion and one GLEIF Level 1 assertion; 15 populated field names and two identifier namespaces. | 25,135 Company-fact rows, 437 line-item rows, 760 measure rows, 10 issuer-position rows and three insider issuer rows link to it; 57 `ISSUED_BY` edges target it. No ADV or registration link rows in this control. |
| International Company cohort | 1,462 legacy Companies: 1,405 classified by mapped SEC place and 57 with no SEC place but a mapped non-US GLEIF jurisdiction. All 1,462 have SEC Company assertions and CIK; 601 have GLEIF assertions and LEI. Nonempty fields include `state_of_incorporation` 1,405, `jurisdiction` 601, `address`, `name`, and `sic` 1,462 each; GLEIF status/legal fields occur on 601 each. | 269,277 Company-fact rows across 29 Companies; 5,704 line-item rows and 9,920 measure rows across 25 each; 1,480 issuer-position rows across 195 Companies; 588 insider issuer rows across 213; five owner-Company rows across three; and 2,030 `ISSUED_BY` edges target the cohort. No observed ADV custody or registration links target this cohort; the relevant tables are partial, so this is not a completeness failure. |
| Fund structure | One master with two N-PORT fund assertions, `name`, `sec_series_id` and LEI namespaces, and one `IS_SUBFUND_OF` assertion. | One legacy Silver `IS_SUBFUND_OF` edge; zero `nport_holding` rows. Its start is observed at the filing date and remains flagged as provisional. |
| Person | One Person linked to one SEC submissions assertion and one SEC ownership reporting-owner assertion; its source assertions declare one `BENEFICIAL_OWNER_OF` and three `EMPLOYED_BY` links. | One `insider_reporting_owner.person_mdm_id` row links to it, but no Silver relationship rows touch it. This is a candidate relationship-coverage gap pending producer and endpoint reconciliation. |
| Security | One Security with two OpenFIGI assertions and one N-PORT Security assertion; one `ISSUED_BY` declaration. | One Silver `ISSUED_BY` edge starts at it; zero `nport_holding` rows. |

These single-record controls verify that the trace follows source assertions,
master fields/identifiers, typed relationship declarations, and downstream
references for each populated legacy kind. They do not replace the unresolved
full-population producer and current-governed comparison.

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

The 70 fund structures without a nonempty LEI all retain a SEC series ID, and
their source assertions carry no LEI claim. The configured binding rule makes
the series ID sufficient for identity; the LEI is optional and only joins when
the source claim is unique. The proving-run count of two records without
identity evidence is not an LEI-completeness threshold. No missing-LEI defect
is observed in this cohort.

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

### Complete Silver pointer membership against legacy MDM IDs

Read-only full-table grouping on 2026-11-08 compared every nonnull populated
Silver MDM pointer with all 448,443 IDs in legacy `public.mastering_master`. It read link
columns, counted membership, and emitted no entity values or IDs. A match proves
only that the pointer exists in that legacy master snapshot; it does not prove
that the source key, entity kind, or relationship evidence is correct.

| Silver pointer | Rows | Null pointer rows | Rows pointing to legacy master IDs | Distinct matching legacy IDs | Nonnull IDs absent from legacy masters |
|---|---:|---:|---:|---:|---:|
| `adv_custody.adviser_mdm_id` | 3,022 | 0 | 3,022 | 1,493 | 0 |
| `adv_custody.custodian_mdm_id` | 3,022 | 3,022 | 0 | 0 | 0 |
| `company_fact.company_mdm_id` | 5,134,979 | 21,294 | 5,113,685 | 320 | 0 |
| `company_line_item.company_mdm_id` | 96,807 | 414 | 96,393 | 309 | 0 |
| `company_measure.company_mdm_id` | 168,360 | 720 | 167,640 | 309 | 0 |
| `insider_position.issuer_mdm_id` | 14,331 | 709 | 13,622 | 1,621 | 0 |
| `insider_reporting_owner.person_mdm_id` | 5,743 | 781 | 4,962 | 4,339 | 0 |
| `insider_reporting_owner.company_mdm_id` | 5,743 | 5,711 | 32 | 22 | 0 |
| `insider_reporting_owner.issuer_mdm_id` | 5,743 | 544 | 5,199 | 1,664 | 0 |
| `nport_holding.fund_mdm_id` | 0 | 0 | 0 | 0 | 0 |
| `nport_holding.registrant_mdm_id` | 0 | 0 | 0 | 0 | 0 |
| `nport_holding.security_mdm_id` | 0 | 0 | 0 | 0 | 0 |
| `registration_offering.registrant_mdm_id` | 732 | 241 | 0 | 0 | 491 |
| `registration_statement_line.registrant_mdm_id` | 27,415 | 10,008 | 0 | 0 | 17,407 |
| `relationship.source_master_id` | 55,320 | 0 | 55,320 | 55,320 | 0 |
| `relationship.target_master_id` | 55,320 | 0 | 55,320 | 4,125 | 0 |

The 3,022 missing custodian pointers align with the absence of retained legacy
assertions for `iapd.adv.custodians.v1`; the configured custody table expects a
Company MDM link, but no current source assertion/master population is available
to resolve it. This is a source-to-master coverage candidate, not a null check
that can be enabled without reconciling the intended capture and pipeline.
Registration is the opposite case: its populated pointers are from an identity
set absent from the legacy master table. Since the governed projection is empty,
these may be valid pointers from a different MDM generation. Do not flag them as
orphans until the producing generation and authoritative resolver are identified.

## Coverage by entity family

| Family | Configured representation and observed population | Downstream evidence | Audit status |
|---|---|---|---|
| Companies | Separate `company` kind; SEC Company, GLEIF Level 1, IAPD ADV and N-PORT registrant inputs. Legacy MDM: 10,698; current governed count unavailable. Legacy Company has a nonempty jurisdiction field on 3,258 records; pinned-place mapping yields a 1,462 non-US cohort. SEC Company classification has 69,816 distinct blocking hold-back source records, 68,301 without a probable kind. | Company facts, line items, measures, insider issuer/owner links, ADV custody and registration links. | Partial. Source and master presence are measured; non-US downstream, classification dispositions, and cause of the 134 accepted SEC/GLEIF field disagreements remain unfinished. |
| N-PORT funds | `fund_structure` is the series-level master; Company can separately hold profile `fund`. Legacy fund structures: 12,937; legacy Company fund profiles: 1,947. | N-PORT security holding spec includes fund, registrant Company and security links, but Silver currently has 0 holdings. Silver has 12,937 `IS_SUBFUND_OF` rows with file-date-provisional starts. | Partial. Registrant/series and file-date semantics are configured and measured; holdings cannot be traced until a populated run finishes; cross-store identity remains open. |
| Private equity and ADV private funds | Current MDM catalog has eight kinds; no PE kind. `fund` is a profile available on Company and `fund_structure`; N-PORT fund records create `fund_structure` masters keyed by SEC series ID. Current `iapd.adv` mastering rules cover adviser filing and custodian records, not private-fund records. The pinned relationship catalog defines `INVESTMENT_ADVISER_TO` for an adviser-profile entity to a fund-profile entity, but active source rules do not emit it. Older/parallel ADV schema/docs retain private-fund detail and firm-roster PE indicators (`fund_type`, `any_pe_funds`, `pe_fund_count`); legacy docs name the relationship `MANAGES_FUND`, so that historical terminology needs reconciliation before reuse. | Current local Silver snapshot read on 2026-11-08 contains 3,022 `adv_custody` rows and 0 `nport_holding` rows; it has no `adv_private_fund` table. Historical `sec_adv_private_fund` schema is not evidence that the active configured pipeline populated or masters PE funds. | No current PE cohort or denominator can be audited. Treat this as an active source-to-relationship-to-consumer coverage gap to reconcile across source capture, Bookkeeping, and intended consumer. Do not infer PE from a `private_offering` filing or fund name, and do not convert the lack of a configured PE population into a record-level failure. |
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
| N-PORT fund structure | Series ID and LEI format/cardinality rules; `subfund_start_is_authoritative` flags when the start is provisional. | The 70 masters without LEI all have a series ID and no source LEI claim; this is allowed by the configured rule. Do not make LEI mandatory. Holdings remain unavailable in the observed snapshot. |
| Private equity and ADV private funds | No PE kind or PE-specific quality contract in the current MDM/source rules. Current MDM has N-PORT `fund_structure` records and `fund` profiles; retained ADV schemas describe private-fund detail and PE roster indicators but do not connect those records to the active `iapd.adv` MDM/Silver path. | Do not infer PE from `private_offering` or fund names. Reconcile the intended source, capture, Bookkeeping path, and consumer; only then define a supported PE cohort and check denominator. The current snapshot cannot support a PE record-quality check. |
| Person | SEC submissions and ownership owner name-presence and letter-pattern checks; CIK identifier contract. | All 781 Silver rows without a Person link exactly match source classification holds; 32 have a Company link and 749 have neither. Both hold reasons are configured as nonblocking. Do not flag unresolved rows; if later classified, validate the corresponding Person/Company link. |
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
