# Trace every mastered entity and convert confirmed defects into data-quality checks

Type: task
Status: in progress
Blocked by: none

## Goal

Repeat the AAPL-style trace for every populated MDM kind: start from each
entity's authoritative MDM identity, inspect every configured source field and
downstream field, then follow typed relationships and cross-store references.
Within Company, cover every represented source role/profile and subgroup:
SEC filers and issuers, GLEIF legal entities, ADV advisers and custodians,
N-PORT registrants, fund-profiled Companies, and international Companies.
Also cover N-PORT fund structures, private equity wherever the configured model
represents it, and every other populated entity kind. Establish from
configuration whether private equity is a separate kind, a Company
classification, or another modeled structure; do not assume. Treat overlapping
Company roles as overlapping cohorts, not additive entity counts.
Record evidence-backed issues and convert defects that can be expressed by the
existing data-quality engine into checks. Propose a separate implementation
ticket for any required check primitive the engine does not support.

Use the local captured stores and pinned rules only. Do not request provider
data, change source or matching rules, modify catalog contents, activate a
pipeline, or inspect Gold as part of this audit. Report counts and masked or
invented examples, never names or identifiers from records.

## Checklist

- [x] Confirm the reference method and current check formats: the operator-selected Company is the control trace; Silver table specs declare `checks`; the data-quality skill lists supported checks; DataKitchen TestGen research is pinned at `docs/research/datakitchen-testgen-test-types-2026-11-02.md`, sourced from [`DataKitchen/dataops-testgen`](https://github.com/DataKitchen/dataops-testgen/tree/3606859cf8bb4f809d2b19acc51462420829c4ab/testgen/template/dbsetup_test_types) (reviewed 2026-11-08 07:22 ET).
- [x] Enumerate configured kinds and the refreshed connected-snapshot population counts (read-only 2026-11-08 12:46 ET). Legacy `mastering_master` has 449,281 rows: 449,272 canonical masters and nine aliases. Canonical kinds: 10,905 Companies, 12,937 fund structures, 31,125 people, and 394,305 securities; branch, government, international organization, and venue have no legacy masters. Governed `mdm.master_entity`, `mdm.current_record`, and `mdm.relationship_version` remain empty, so governed-kind counts and generation cannot be confirmed here. Earlier governed counts remain prior observations only.
- [x] Refresh Company identifier cardinality after population growth (read-only streamed canonical masters, 2026-11-08 13:25 ET). BD number: 106 values on 106 masters; CIK: 8,361 on 8,361; CRD: 2,337 on 2,337; LEI: 3,359 on 3,359. Every value is distinct across masters, and no master has multiple values in any namespace.
- [ ] Finish tracing the ADV custodian assertions and declared `CUSTODIAN` links through source identity and Silver (refreshed read-only 2026-11-08 13:48 ET). Of 3,022 Silver rows (498 distinct custodian keys), all adviser pointers are present; 2,541 custodian pointers match their exact current source key/master. The remaining 481 null pointers comprise 475 rows whose source key has assertions but no assigned master, plus six rows across four keys with no retained source assertion. There are no wrong-key or wrong-entity populated pointers. The 494 source assertions comprise 106 BD-number records and 114 LEI records, all assigned; 274 name-only records include 11 assigned by one exact-name holder and 263 that have no configured holder and correctly wait. All 494 contain a name, satisfying the existing name-presence check; four invalid-LEI rows are already set aside by identifier validation. Reconcile the four source-absent keys, 3,017 declaration grain, and monthly filing history before calling any row defective.
- [x] Trace the configured 13F security and filing paths through current Silver to canonical Company/Security identities (read-only 2026-11-08 13:48 ET). Bookkeeping reports the 13F security run complete with 44/44 work items verified and the filing run complete with 3/3 verified. Silver contains 168 filing rows and 283,725 holdings. All holdings join a filing accession; 52 distinct holding accessions match filings. The CUSIP key and Security pointer match the same current Security on 283,715 holdings. The remaining 10 rows share one CUSIP with no Security master or source assertion; that key matches the one `invalid_cusip_checksum` deferral, which the source contract already sets aside nonblocking. This is an explained outcome, not a new defect. Filing CIK and Company pointer match on 146 rows; 22 rows across two distinct CIKs have null pointers, no current CIK master of any kind, no matching Company source assertion, and no open review. No nonnull pointer is wrong-kind, orphaned, or mismatched to its CUSIP/CIK. Trace the two manager keys to retained capture or a documented coverage boundary; keep them as source-coverage candidates until explained.
- [x] Refresh Silver row counts across the configured entity consumers (read-only 2026-11-08 13:34 ET). Company fact 5,134,979; line item 96,807; measure 168,360; insider position 14,331; insider reporting owner 5,743; ADV custody 3,022; registration offering 732; registration statement line 27,415; relationship 55,320 (`ISSUED_BY` 42,383, `IS_SUBFUND_OF` 12,937); N-PORT holding 0; 13F filing 168; and 13F holding 283,725. Counts do not establish pointer identity; typed edge and per-cohort comparisons remain separate work.
- [x] Refresh declared relationship counts after the new assertions appeared (read-only 2026-11-08 13:50 ET). Current source counts remain 48 `SUCCESSOR_ENTITY`, 3,017 `CUSTODIAN`, 12,937 `IS_SUBFUND_OF`, 245,130 `ISSUED_BY`, 4,962 `BENEFICIAL_OWNER_OF`, and 14,886 `EMPLOYED_BY`. These are declaration sightings, not distinct governed edge counts; relationship key, endpoint and time comparisons remain open.
- [x] Measure identifier cardinality in both directions for every populated kind with a bounded reverse claim (read-only 2026-11-08; Company refreshed 13:25 ET, Security refreshed 12:46 ET). Current Company BD number (106), CIK (8,361), CRD (2,337), and LEI (3,359) values are each unique across masters, with no master holding multiple values per namespace. Person CIK (31,125) maps to one Person master; 4,311 values appear in both SEC submissions and ownership-owner feeds and resolve to one master each, with no Person holding multiple CIKs. Fund-structure series IDs (12,937) and LEIs (12,867) each map to one fund master, with no fund master holding multiple values. Security effective identifiers: CUSIP 384,249 distinct values (zero repeated across masters), FIGI 1,392,524 (zero repeated), ISIN 390,955 (zero repeated), LoanX 423 (one repeated across two masters), SEDOL 22,832 (three repeated across two masters), and ticker 129,394 (366 reused; one on four masters against the configured forward limit of three, held for review). These are legacy assignment results; the current governed MDM projection is empty.
- [x] Inventory nonempty source assertion fields and identifiers for all 13 feeds represented in the refreshed legacy mastering snapshot (read-only 2026-11-08 13:12 ET). Total: 1,254,565 assertions. This is presence evidence only; it does not validate field semantics, requiredness, or full downstream coverage. ADV custodian and 13F counts and field presence are added below.
- [x] Reproduce the operator-selected Company control trace in legacy MDM/Silver and select controls for the other populated kinds. The Company control resolves to one Company with one SEC Company and one GLEIF assertion, 15 populated MDM field names, two identifier namespaces, 25,135 fact rows, 437 line-item rows, 760 measure rows, 10 issuer-position rows, three insider issuer rows, and 57 `ISSUED_BY` edges targeting the Company. One control each was traced for fund structure, Person, and Security; their details and limits follow below. Governed identity remains unavailable in this snapshot.
- [ ] Trace every entity in deterministic batches through source-to-MDM identity, each MDM field, and each linked downstream field; report coverage, missing links, conflicts, duplicates, stale references, and applicable per-kind denominators.
- [ ] Refresh all downstream and relationship comparisons after the legacy master population grew by 207 Companies and 622 Securities; retain earlier Silver, MIC, and cohort values as dated prior-snapshot evidence until remeasured.
- [ ] Complete the Company trace separately for each configured source role/profile and cohort: SEC filers/issuers, GLEIF legal entities, ADV advisers, ADV custodians, N-PORT registrants, Company records with the `fund` profile, and mapped non-US Companies. Record overlapping cohort denominators and role-specific source fields and consumers; do not treat these labels as separate MDM kinds.
- [ ] Trace typed relationship paths for every populated kind, including `ISSUED_BY` from Security to its allowed issuer kinds; verify endpoint kind, direction, current MDM identity, time basis, and source evidence. Source assertions include 48 GLEIF `SUCCESSOR_ENTITY`, 3,017 ADV `CUSTODIAN`, 12,937 N-PORT `IS_SUBFUND_OF`, 245,130 N-PORT `ISSUED_BY`, 4,962 `BENEFICIAL_OWNER_OF`, and 14,886 `EMPLOYED_BY` declarations; repeated filing sightings must be reduced to governed edge grain before comparing to Silver.
- [x] Compare legacy N-PORT `ISSUED_BY` declarations to Silver by exact endpoint pair (read-only 2026-11-08 11:42 ET). The 245,130 declarations reduce to 225,221 distinct Security/issuer-source pairs; 43,601 target a retained GLEIF assertion. Silver has 42,383 pairs, all backed by the source pair set, with zero Silver-only pairs. Of 1,218 source-only pairs, 1,214 lack a mastered GLEIF target; one has neither endpoint mastered; one has a Company issuer master but no Security master; and two have both Security and Company masters but no Silver edge. All 1,421 declarations behind these source-only pairs have a nonempty start. These two are omission candidates; one current N-PORT run still has its `links` step pending, so a final publication gap is not yet established.
- [x] Compare N-PORT `IS_SUBFUND_OF` endpoints and both endpoint kinds/profiles to Silver (read-only 2026-11-08 11:57 ET). All 12,937 distinct legacy source pairs resolve to a `fund_structure` with the `fund` profile and a `company` with the `fund` profile. Exact Silver endpoint comparison has 12,937 overlaps, zero mastered source pairs absent from Silver, and zero Silver pairs without a mastered source pair. All Silver starts are nonempty and `valid_from_basis=observed`; the source has no authoritative start, so the configured file-date fallback remains provisional.
- [x] Compare ownership relationship endpoints to their designated owner Silver table (read-only 2026-11-08 11:57 ET). `BENEFICIAL_OWNER_OF` and `EMPLOYED_BY` each produce the same 4,139 distinct mastered Person/issuer Company pairs; both sets exactly match the nonnull Person/issuer endpoints in `insider_reporting_owner`, with zero source-only or Silver-only pairs. The Silver table does not preserve relationship type/capacity as a distinct edge, so typed capacity and period behavior still require current governed MDM evidence; the governed relationship projection is empty in this snapshot.
- [x] Assess source endpoint assignment for GLEIF successor and ADV custodian links (earlier legacy snapshot, read-only 2026-11-08 12:03 ET; custodian evidence superseded by 13:12 ET refresh). None of 48 `SUCCESSOR_ENTITY` declarations has an assigned source Company master; all 48 source subjects are in open `binding_required` review, and 26 target subjects resolve to a legacy Company. The earlier snapshot had no custodian source assertions; the refreshed snapshot now has 494, including 263 without a master. Reconcile the new custodian identities and source keys before characterizing link coverage. The governed projection remains empty.
- [x] Determine whether private equity has a separate representation in the active MDM/Silver path. The eight-kind catalog has no PE kind; `fund` is a profile on Company/fund structure. Active IAPD ADV rules master adviser filings and custodians, not private-fund records. Retained ADV schemas still describe private-fund details and PE roster indicators, but the read-only local Silver snapshot has no private-fund table (3,022 custody rows; zero N-PORT holdings). This establishes no current PE quality denominator; it does not establish defects in any PE records. Verified against current config/schema and local Silver on 2026-11-08 10:25 ET.
- [ ] Finish tracing N-PORT registrants, funds, series, holdings, and securities to their mastered fund/security/company or other entity records. Keep N-PORT series distinct from ADV private funds. Legacy fund-structure masters: 12,937, all with the `fund` profile; the prior Company fund-profile count is 1,947. The prior 12,937 `IS_SUBFUND_OF` source endpoint pairs exactly match Silver. `nport_holding` had zero rows at the 2026-11-08 13:34 ET Silver refresh while the runs remained active at the last 13:11 ET status check. All subfund starts are `observed` file-date fallbacks; authoritative inception remains unknown.
- [x] Measure Security listing MIC against pinned MIC version 1 and the configured 246-code OpenFIGI exchange crosswalk (pre-growth population, 2026-11-08 10:54 ET). Of 1,392,524 listing rows, 617,684 have a MIC; all are valid and match the configured mapping, with zero invalid, mismatch, or mapped-exchange missing-MIC rows. The remaining 774,840 nulls split into 414,643 composite FIGI/unmapped-exchange rows, 42,639 unpaired-exchange rows without composite FIGI, and 317,558 rows with neither exchange nor composite FIGI. The source-contract review establishes nulls are allowed for these cases. Refresh this scan after the 622-Security increase.
- [x] Trace the entire legacy non-US Company cohort through source assertions, identifiers, field presence, and Silver references. Pinned SEC place mapping identifies 1,405 records; 57 additional records without an SEC place have a non-US GLEIF jurisdiction under the approved country mapping (1,462 total). This is a legacy/Silver trace; current governed identity remains unverified. The configured `international_organization` kind has no legacy masters.
- [x] Compare every Silver MDM pointer directly with the complete legacy master-ID set. Read-only full-table grouping covered all 16 configured link columns on 2026-11-08 10:29 ET: every populated Company-fact/line-item/measure, insider, ADV-adviser, and relationship endpoint ID matched a legacy master; `adv_custody.custodian_mdm_id` was null on all 3,022 rows; registration pointers (491 offering rows and 17,407 statement-line rows) did not match any legacy master ID; all three N-PORT holding links had zero rows. Those registration IDs belong to an unverified MDM identity generation because governed master tables are empty on this connection; the comparison is membership evidence, not proof that they are stale or wrong.
- [x] Trace the one observed Security ticker over the configured three-master forward claim through actual Form 4 records and issuer declarations. Two Form 4 assertions carrying it are both in open `conflicting_identifiers` review, as the configured `on_several: review` rule requires; neither silently auto-binds. The same four Security masters have three `ISSUED_BY` declarations targeting two GLEIF source subjects, neither present in retained GLEIF source assertions, and no Silver issuer edge. The ticker case is handled by review, not a confirmed quality defect; the missing GLEIF targets remain a source-coverage candidate. Verified from read-only current legacy MDM/source/Silver data on 2026-11-08 10:47 ET.
- [x] Compare raw Security identifier claims across OpenFIGI and N-PORT with configured cardinality (read-only 2026-11-08 12:15 ET). Source assertions had 370 repeated ISIN values across two or three assigned source entity IDs (154 present in both feeds, 216 N-PORT-only; 26 cross multiple N-PORT key classes). These are raw claim collisions, not effective-master duplicates. Source-level CUSIP and FIGI claims had no repeated values across assigned entities; SEDOL had three repeated values and LoanX one, each within the configured five-master forward claim. Ticker had 366 reused values, one appearing on four assigned entities against a forward claim of three; the corresponding Form 4 assertions were held for review. Effective-master and withheld-claim reconciliation was a separate follow-up below.
- [x] Reconcile repeated source ISIN claims against effective legacy master identifiers and N-PORT withholding (read-only 2026-11-08 12:22 ET). The effective `mastering_master` projection has zero duplicate CUSIP, FIGI, or ISIN values across Security masters. It has three repeated SEDOL values and one repeated LoanX value, each on two masters and within the configured forward claim of five; 366 ticker values are reused, with one on four masters against a forward claim of three and the over-limit case held for review. N-PORT has 394 CUSIP-keyed withheld ISIN occurrences over 371 source subjects (370 distinct ISINs); 154 of those values also occur as accepted claims on another master. This matches the configured CUSIP-first keep-separate behavior. Raw source collisions are not effective-master duplicates and are not confirmed defects.
- [x] Verify the SEC–GLEIF jurisdiction binding rule's current approval state and proof (policy and `rules/merge/pending-proofs.yaml`, 2026-11-08 11:00 ET). `sec-gleif-name-jurisdiction` is active for Company with a 300/300 measured proof (95% one-sided lower bound 0.991062) and zero violations in 257 adversarial cases. This establishes the rule is approved and enabled; it does not establish when the legacy records were last processed or explain the 134 field disagreements.
- [x] Trace the 134 jurisdiction candidates against their accepted legacy masters, field winners, and retained assertion presence (pinned place mapping plus configured `places_agree` logic, read-only 2026-11-08 11:08 ET). All 134 are accepted Company masters; each field winner is from its expected source, and both SEC Company and GLEIF Level 1 assertions are retained for every candidate. This rules out missing source assertions as the explanation, but not stale/effective-time or identity-history causes.
- [x] Break down SEC Company classification deferrals by configured rule step and distinct source-record locator (read-only 2026-11-08 11:10 ET). All 69,816 blocking events map to distinct locators. Step 11 leaves 67,166 unclassified with no probable kind; step 1 adds 1,062 without a probable kind; step 7 adds 73 without a probable kind. The other 1,515 are explicitly held as probable Company (599), Person (658), fund structure (226), or government (32). This measures the configured hold-back population without treating every deferral as a defect.
- [x] Re-measure row-local configured Company Silver checks on the current stored population (read-only 2026-11-08 13:56 ET). `company_fact`: 5,134,979 rows, 3,113,260 eligible period pairs; `company_line_item`: 96,807 rows, 46,971 eligible pairs; `company_measure`: 168,360 rows. `period_start_not_after_end`, `empty_value_has_reason`, and `window_years_known` each have zero failures; all three `quality` columns are null on every row. `one_value` checks remain unmeasured because they apply to individual deliveries, not the combined historical tables.
- [x] Reconcile the 70 N-PORT fund structures without a master LEI to their retained assertions (read-only 2026-11-08 11:24 ET). All 70 have a `sec_series_id` in the master and source assertion; none of their retained N-PORT fund assertions claims an LEI. The configured series-ID rule can identify them without a LEI, so the 70 are not defects and are not comparable to the two proving-run exceptions that lacked identity evidence.
- [x] Reconcile missing Person links on insider reporting owners to classification holds using the exact filing-owner key across MDM and Silver (read-only 2026-11-08 11:27 ET). All 781 Person-null owner rows match 781 distinct source records: 331 `classification_deferred` and 450 `classification_entity_undetermined`. Of those, 32 already link to a Company (14 deferred, 18 undetermined); 749 have neither an owner Person nor Company link (317 deferred, 432 undetermined). The key sets match exactly, with no unmatched rows.
- [x] Verify whether those unresolved owner rows are allowed to land (read-only config review, 2026-11-08 11:28 ET). `sec.ownership.reporting_owner.v1` explicitly treats both classification reasons as nonblocking, and Bookkeeping lands owner rows after merge. The 749 without either link are expected to remain unresolved while classification is held; do not flag them as broken links without a later classification decision.
- [ ] Reproduce the earlier protocol-7 entity-link resolver comparison for every populated Silver link. Its prior row-level counts cannot be rerun while governed MDM tables are empty on the current shared connection; historic producer and safe refresh timing also remain unresolved.
- [ ] Map Silver relationship endpoints from legacy IDs to current MDM identities by configured source keys, then compare typed edges, direction, and effective dates. Silver has 55,320 rows; the governed relationship projection is empty in the current connection, while a prior snapshot reported 13,442. Confirm the loaded producer and identity transition before deciding whether to repair or retire any rows.
- [x] Determine whether missing listing MIC is a defect under the configured source contract (read-only config review, 2026-11-08 12:42 ET). The OpenFIGI source says MIC comes from the local MIC reference lookup and is null when no mapping exists; it explicitly expects no MIC for a composite listing or an unpaired exchange code. The full legacy scan's 414,643 composite/no-MIC rows, 42,639 unpaired-exchange/no-composite rows, and 317,558 rows with neither exchange nor composite venue detail therefore do not establish missing-MIC defects. All 617,684 present MICs remain valid and mapped. No completeness check is warranted for this optional field. Extending the exchange crosswalk requires an approved authoritative code mapping, not a quality rule inferred from the rows.
- [ ] Write an issue ledger with one row per evidenced failure pattern: checkable condition, observed count and denominator, affected table/field, impact, snapshot/rule version, source evidence, and confirmed or unconfirmed cause.
- [ ] Map each confirmed defect to a DataKitchen TestGen category and to a supported platform check (`identifier`, `in_set`, `one_value`, `not_after`, or `reason_if_empty`) where it fits; use baseline checks only when an approved business reference exists.
- [ ] Draft check definitions in the owning source contract or Silver table spec; measure them on the pinned records, include counts in comments, and prove each check with a planted invalid record before proposing activation.
- [ ] For cross-table or cross-store checks without a supported primitive, document the exact predicate and smallest required engine/configuration change as a separate issue; do not approximate it with a misleading field-only check.
- [ ] Report coverage for every Company role/cohort and every configured MDM kind, confirmed defects, candidate findings still under investigation, check definitions and measurements, and deferred work. Do not create external tickets unless requested.
- [ ] Learning → skill: record any reusable trace or check-design rule in the relevant skill, or write `none` with the reason.

## Measured evidence and unresolved checks

These measurements come from the local read-only snapshot observed on
2026-11-08. They are not a globally consistent snapshot across stores; preserve
the stated store and table denominator with every conclusion.

**Snapshot qualification:** refreshed reads of the designated shared
`local-test-server` found 449,281 raw legacy `mastering_master` rows,
comprising 449,272 canonical masters and nine aliases. At 2026-11-08 12:46 ET
the canonical kinds were 10,905 Company, 12,937 fund structure, 31,125 Person,
and 394,305 Security. At 13:12 ET the assertion store held 1,254,565 rows
across 13 feeds. A 13:51 ET read found zero rows in governed
`mdm.master_entity`, `mdm.current_record`, and `mdm.relationship_version`; these
tables have no row-level security policy. Every governed-store count and
resolver comparison remains an earlier reported measurement that is not
reproducible against this current connection. Treat those rows as provisional
leads, not confirmed current defects, until the intended populated governed
snapshot is identified.

| Finding | Measurement | Current assessment | Next validation |
|---|---|---|---|
| Form 13F Company and Security links | The 2026-11-08 12:44 ET Bookkeeping runs completed (44/44 securities work items; 3/3 filing work items verified). Silver has 168 manager filing rows and 283,725 holding rows. All holding rows join a filing accession; 52 distinct holding accessions are present. 146 filing CIKs match the exact Company MDM pointer; 22 rows across two CIKs have no Company master/source assertion or open review. 283,715 holding CUSIPs match the exact Security pointer; the remaining 10 rows share one CUSIP set aside under the existing nonblocking `invalid_cusip_checksum` contract check. No present pointer is wrong-kind or points to a different entity than its key. | The 10 null Security pointers reflect an already measured identifier validation outcome. The two missing manager identities remain source-coverage candidates. The source also has a `share_class_one_letter` check; its per-run failure count was not available in the status summary. | Trace the two Company keys to retained capture or documented coverage boundaries. Read the prepared 13F quality evidence for the share-class check count; do not infer zero failures from completed receipts. |
| Silver relationship edge counts and endpoint identity | Legacy N-PORT source: 245,130 `ISSUED_BY` declarations, 225,221 distinct Security/issuer-source pairs; 43,601 have a retained GLEIF assertion. Silver: 42,383 pairs. Exact comparison has 42,383 overlap, 1,218 source-only, zero Silver-only; 1,214 source-only pairs lack a mastered GLEIF target, one lacks both masters, one lacks a Security master, and two have both masters but no Silver edge. One current N-PORT run still has `links` pending. For `IS_SUBFUND_OF`, all 12,937 distinct fund-structure/Company pairs resolve to endpoints with the `fund` profile and exactly match Silver; zero source-only or Silver-only pairs. Every Silver subfund start is `observed` (file-date provisional). | N-PORT subfund endpoint coverage matches the legacy source pair set. Two fully mastered `ISSUED_BY` pairs remain possible omissions until the pending stage completes. These comparisons use legacy IDs only; the governed MDM relationship projection is empty, so current governed identity/effective-time evidence is unavailable. | Reconcile the two fully mastered issuer pairs after the pending stage completes; then repeat both comparisons on the populated governed MDM generation and verify evidence and temporal semantics. |
| Other configured relationship types and consumers | Legacy source assertions declare 48 `SUCCESSOR_ENTITY`, 3,017 `CUSTODIAN`, 4,962 `BENEFICIAL_OWNER_OF`, and 14,886 `EMPLOYED_BY`. None of the 48 successor declarations has a source Company master; all 48 source subjects are in open `binding_required` review, while 26 target subjects resolve to a legacy Company. The refreshed custodian feed has 494 assertions: 224 distinct legacy masters and 263 assertion rows without a master. Silver `adv_custody` has 3,022 rows with null custodian MDM IDs. Both ownership types reduce to the same 4,139 distinct mastered Person/issuer Company pairs; each exact set matches nonnull owner/issuer endpoints in `insider_reporting_owner`, with zero source-only or Silver-only pairs. The owner Silver contract does not retain typed relationship capacity as a separate edge. | Successor and custodian results remain source/target coverage limits, not confirmed broken links. The new custodian assertions do not explain all 3,017 declarations or the null Silver pointers; exact key and publication-grain reconciliation is open. Ownership endpoint pairs reach Silver, but typed capacity/period behavior is not verified by this endpoint-only comparison. The governed MDM projection is empty; custody's five-row difference is not a valid comparison until filing/row grain is reconciled. | Reconcile all 3,017 declarations against custodian source keys, the 494 assertions, and Silver rows at the configured filing/month grain. Explain the 263 unassigned assertions and refresh-id outcome. Reconcile the 48 successor source reviews through the normal binding decision path. Confirm ownership typed-edge and time evidence in a populated governed snapshot; verify the producer generation. |
| Silver entity-link resolver comparisons | Earlier reported current-resolver deltas: Company fact 5,113,685, line item 96,393, measure 167,640, insider position issuer 13,622, owner Person 4,962 set IDs, owner Company 32, and insider issuer 5,199. Reported no-current-master/null rows were 21,294, 414, 720, 709, 781, 5,711, and 544. | These exact-resolver comparisons are not reproducible while governed projection is empty. Preserve them as unverified prior measurements, not confirmed current defects; historic producer and refresh timing also remain unknown. | Identify the populated governed snapshot, rerun each table against the protocol-7 resolver, then trace confirmed rows to landing generation and runtime. |
| Registration links | Earlier resolver read reported offerings: 491 matches, 1 resolvable null and 240 no-current-master null; statement lines: 17,407 matches, 3 resolvable null and 10,005 no-current-master null. | The four resolvable-but-null rows are candidates only until that populated resolver snapshot is reproduced. | Rerun against populated governed MDM, trace any confirmed rows to landing receipts, and prove the check with a planted null ID. |
| ADV adviser/custodian links | Earlier resolver read reported 3,022 set adviser IDs across 1,864 keys without current masters, and 3,022 null custodian IDs across 498 keys (106 BD-number, 118 LEI, 274 name-only). | The current governed source-record projection is empty, so the earlier no-pointer counts are not reproducible now. The completed ADV run targeted legacy `mastering`; this does not prove governed MDM received the records. | Verify the run target, then compare adviser and identifier-based custodian keys with populated current assertions, masters, and receipts. Keep name-only cases conditional. |
| Insider reporting-owner identity links | `insider_reporting_owner`: 5,743 rows; 4,962 Person links, 32 Company links, 749 with neither, and no row with both. All 781 Person-null rows match the 781 retained source records deferred (331) or undetermined (450) by exact filing-owner key; the 32 Company links split across those queues (14 and 18), leaving 749 unlinked (317 and 432). Both classification reasons are explicitly nonblocking in the source contract, and the Bookkeeping flow lands owner rows after merge. | This is not a pointer mismatch: all owner-link gaps align exactly with unresolved classification. A null Company link is expected for known People; the 749 neither-linked rows are permitted unresolved cases, not proven invalid entities. | Keep them out of link-failure checks while classification remains unresolved. If later classified as a Person or Company, require the corresponding link and validate its current MDM identity. |
| N-PORT holding link coverage and load state | Refreshed status at 2026-11-08 13:50 ET: both `sec.nport.security` Bookkeeping runs remain `running` with unchanged progress since 13:11 ET. The 2026-11-06 11:54 ET run has 14 verified steps, `land_holding` and `processed` pending, and `merge` waiting. The 2026-11-06 21:31 ET run has 3 verified, 3 reported, 3 waiting, and 9 pending; `identifiers`, `series`, and `submissions` are verified, while `holding`/`holding_rows` wait and `combine`, `holding_combine`, `issuer_reduce`, `land_holding`, `links`, `merge`, `prepare`, `processed`, and `reduce` are pending. Current Silver `nport_holding` count was refreshed to zero at 13:34 ET. | The holding population remains unqualified while landing is pending. Earlier Silver relationship endpoint and identifier comparisons still describe the pre-growth identity snapshot. | Refresh the Silver holding count after the runs advance or finish, and confirm the deployed worker version before measuring N-PORT holding quality. Do not resume, cancel, or alter the runs as part of this read-only audit. |
| Company jurisdiction cross-source disagreement | Of 3,073 legacy Company records with a valid mapped SEC state-of-incorporation code and nonempty GLEIF jurisdiction, 134 disagree under the complete configured `places_agree` semantics, including U.S. territory aliases and country/subdivision compatibility. Reproduced with the pinned `sec-place-codes` canonical mapping and read-only aggregation over the full legacy Company population. All 134 are accepted Company masters; both expected source assertions are retained and each field winner is from its expected source. `sec-gleif-name-jurisdiction` is active with a 300/300 proof (95% one-sided lower bound 0.991062) and 0 violations across 257 adversarial cases. | Confirmed cross-source field disagreement, but not yet a confirmed data defect: the fields are deliberately source-owned separately, and the remaining cause may involve identity history, effective time, or processing under an earlier rule. The measured rule proof supports matching on its proof cohort; it does not attest every field pair. | Trace the exact assertions' effective times, bound/decision history, and producing rule version. Decide whether each disagreement represents an entity mismatch or a source-level quality issue before defining an enabled check. |
| Company Silver row-local checks | Full current stored-population evaluation at 13:56 ET: `company_fact` 5,134,979 rows, with 3,113,260 eligible period pairs; `company_line_item` 96,807 rows, with 46,971 eligible period pairs; `company_measure` 168,360 rows. The configured row-local checks `period_start_not_after_end`, `empty_value_has_reason`, and `window_years_known` each have zero failures. All three `quality` columns are SQL null on every row, so no persisted row-level quality tags are present. | The measured current rows satisfy these three checks; no row-level defect was found on these predicates. This is direct SQL evaluation against the current Silver snapshot, not proof that a Bookkeeping load report recorded the same counts. | Recover per-delivery report evidence for the four `company_fact` `one_value` checks; their semantics are delivery-scoped and cannot be safely re-evaluated over the combined historical tables. |
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
| Company | IAPD ADV custodian | 494 | 224 | 263 |
| Fund structure | N-PORT fund | 25,874 | 12,937 | 0 |
| Person | SEC submissions | 31,097 | 31,097 | 0 |
| Person | SEC ownership reporting owner | 4,962 | 4,339 | 0 |
| Security | OpenFIGI | 733,538 | 382,649 | 0 |
| Security | N-PORT security | 428,262 | 393,510 | 6 |
| Security | SEC ownership security v1 | 398 | 335 | 63 |
| Security | SEC ownership security v2 | 5,273 | 1,508 | 826 |
| Security | SEC 13F securities | 5,758 | 5,746 | 0 |

The refreshed 13:12 ET source snapshot contains 1,254,565 assertions across 13
feeds. ADV custodian assertions now exist; their 263 unassigned rows and the
3,017 declared custodian links still need exact key and run-window
reconciliation. The 13F feed has 5,758 assertions linked to 5,746 legacy
Security masters. Its configured Silver filing and holding consumers are
populated, and the current pointer audit appears below. Neither feed's
presence establishes complete capture by itself. The ownership-security rows
without a master and the six N-PORT-security rows should be reviewed alongside
their deferred reasons.

| Entity family / source feed | Assertions | Nonempty source fields (count each) | Nonempty identifiers (count each) |
|---|---:|---|---|
| Company — SEC Company | 6,414 | `address`, `description`, `fiscal_year_end`, `name`, `sic`, `state_of_incorporation` (6,414) | `cik` (6,414) |
| Company — GLEIF Level 1 | 3,716 | `address`, `gleif_entity_creation_date`, `gleif_entity_status`, `gleif_initial_registration`, `gleif_legal_form`, `gleif_managing_lou`, `gleif_registration_authority`, `gleif_registration_authority_entity_id`, `gleif_registration_status`, `gleif_validation_source`, `jurisdiction`, `name` (3,716) | `lei` (3,716) |
| Company — IAPD ADV filings | 2,938 | `address`, `name` (2,938) | `crd` (2,938) |
| Company — IAPD ADV custodians | 494 | `address`, `name` (494) | `bd_number` (106); `lei` (114) |
| Company — N-PORT registrant | 5,841 | `address`, `name` (5,841) | `cik` (5,841) |
| Fund structure — N-PORT fund | 25,874 | `name` (25,874) | `sec_series_id` (25,874); `lei` (25,734) |
| Person — SEC submissions | 31,097 | `legal_name` (31,097) | `cik` (31,097) |
| Person — SEC ownership reporting owner | 4,962 | `legal_name` (4,962) | `cik` (4,962) |
| Security — OpenFIGI | 733,538 | `market_sector`, `name_of_issuer`, `security_type`, `security_type2` (733,538) | `figi` (733,538); `cusip` (353,491); `isin` (380,047); `ticker` (243,729) |
| Security — N-PORT security | 428,262 | `asset_category`, `currency`, `derivative_category`, `investment_country`, `issuer_type`, `name_of_issuer`, `restricted`, `share_class`, `title_of_class` (428,262) | `cusip` (391,953); `isin` (425,310); `sedol` (23,533); `loanx` (440) |
| Security — SEC ownership security v1/v2 | 5,671 | none | none |
| Security — SEC 13F securities | 5,758 | `name_of_issuer`, `share_class`, `title_of_class` (5,758) | `cusip` (5,758) |

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
| International Company cohort | Refreshed denominator: 1,462 legacy Companies; 1,405 have SEC place mapped `FOREIGN`/`CANADIAN`, and 57 additional Companies have no SEC place but a mapped non-US GLEIF jurisdiction. The current GLEIF non-US subset is 600. | Earlier cohort trace found Company facts, line items, measures, insider/owner links, and `ISSUED_BY` targets, but its field/downstream counts predate the master growth. | Refresh cohort source fields and every downstream join against the current Company/Silver population; keep the older values as prior evidence only. |
| Fund structure | One master with two N-PORT fund assertions, `name`, `sec_series_id` and LEI namespaces, and one `IS_SUBFUND_OF` assertion. | One legacy Silver `IS_SUBFUND_OF` edge; zero `nport_holding` rows. Its start is observed at the filing date and remains flagged as provisional. |
| Person | One Person linked to one SEC submissions assertion and one SEC ownership reporting-owner assertion; its source assertions declare one `BENEFICIAL_OWNER_OF` and three `EMPLOYED_BY` links. | One `insider_reporting_owner.person_mdm_id` row links to it, but no Silver relationship rows touch it. This is a candidate relationship-coverage gap pending producer and endpoint reconciliation. |
| Security | One Security with two OpenFIGI assertions and one N-PORT Security assertion; one `ISSUED_BY` declaration. | One Silver `ISSUED_BY` edge starts at it; zero `nport_holding` rows. |

These single-record controls verify that the trace follows source assertions,
master fields/identifiers, typed relationship declarations, and downstream
references for each populated legacy kind. They do not replace the unresolved
full-population producer and current-governed comparison.

### Governed snapshot availability

A refreshed connection to the designated shared `local-test-server` on
2026-11-08 found 449,281 raw rows in legacy `mastering_master`, but zero in governed
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

Read-only streamed the 449,272 canonical legacy master records on 2026-11-08
12:46 ET. Counts are nonempty values per field/identifier; they describe presence only, not whether
the value is correct or required. Do not turn low counts into failures without
the field's source and business contract.

| Kind and denominator | Nonempty MDM fields | Nonempty identifiers |
|---|---|---|
| Company (10,905) | `name` 10,905; `address` 10,724; `fiscal_year_end` 6,217; `gleif_entity_creation_date` 2,693; `gleif_entity_status` 3,258; `gleif_initial_registration` 3,258; `gleif_legal_form` 3,258; `gleif_managing_lou` 3,258; `gleif_registration_authority` 3,258; `gleif_registration_authority_entity_id` 3,141; `gleif_registration_status` 3,258; `gleif_validation_source` 3,258; `jurisdiction` 3,258; `sic` 6,414; `state_of_incorporation` 5,787 | `cik` 8,361; `crd` 2,337; `lei` 3,359; `bd_number` 106 |
| Fund structure (12,937) | `name` 12,937 | `sec_series_id` 12,937; `lei` 12,867 |
| Person (31,125) | `legal_name` 31,125 | `cik` 31,125 |
| Security (394,305) | `asset_category` 389,114; `currency` 393,500; `derivative_category` 5,264; `investment_country` 392,902; `issuer_type` 390,300; `market_sector` 382,648; `name_of_issuer` 394,305; `restricted` 390,318; `security_type` 382,500; `security_type2` 380,488; `share_class` 1,499; `title_of_class` 394,141 | `cusip` 375,650; `figi` 1,392,524; `isin` 390,955; `loanx` 424; `sedol` 22,092; `ticker` 129,767 |

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

Earlier read-only full-table grouping compared every nonnull populated Silver
MDM pointer with all 448,443 IDs in legacy `public.mastering_master`. It read
link columns, counted membership, and emitted no entity values or IDs. The
legacy master population has since grown to 449,281 raw rows; refresh pointer
membership and typed endpoint checks before treating these earlier totals as
current. A membership match proves only that the pointer exists in that legacy
master snapshot; it does not prove that the source key, entity kind, or
relationship evidence is correct.

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
| Companies | Separate `company` kind; SEC Company, GLEIF Level 1, IAPD ADV, N-PORT registrant, and 13F filer inputs. Refreshed legacy MDM: 10,905; governed count unavailable. 3,258 have a nonempty GLEIF jurisdiction; the current place comparison yields 1,462 non-US Companies (600 have mapped non-US GLEIF jurisdiction). SEC Company classification has 69,816 distinct blocking hold-back records, 68,301 without a probable kind (prior source snapshot). | Company facts, line items, measures, insider issuer/owner links, ADV custody, registration links, and 13F filing-manager links. The current 13F filing snapshot has 168 rows: 146 pointers match current Company CIK identities; 22 rows across two CIKs have null pointers because neither a Company master nor a matching source assertion exists. | Partial. The two filer identities need source coverage tracing; refresh other role/cohort joins, classification dispositions, and trace the 134 accepted SEC/GLEIF field disagreements to effective times and identity history. |
| Company roles and overlapping cohorts | Counts are not additive: refreshed Company identifiers include 8,361 CIK, 2,337 CRD, 3,359 LEI and 106 BD-number values; cardinality is unique across all four namespaces. The prior `fund` profile count is 1,947; the current mapped non-US cohort is 1,462. Roles include SEC filer/issuer, GLEIF legal entity, ADV adviser/custodian, N-PORT registrant, and 13F filer. | Current ADV custody has 3,022 rows: all adviser pointers are present; 2,541 custodian pointers exactly match source key/master. The 263 unassigned name-only custodian records have no holder in the configured source set and follow the expected wait path; six rows across four keys lack any retained source assertion. The other 475 rows with null pointers are explained by the 263 wait records. No populated pointer is mismatched. | Partial. Reconcile the four source-absent ADV custodian keys and 3,017 relationship declarations at filing/month grain; then refresh each remaining role's current source-key denominator and downstream join. Do not count source rows as distinct Companies. |
| N-PORT funds | `fund_structure` is the series-level master; Company can separately hold profile `fund`. Refreshed legacy fund structures: 12,937; prior Company fund-profile count: 1,947. | N-PORT holding spec includes fund, registrant Company and Security links. Current Silver `nport_holding` remains at zero (read-only 13:34 ET) while both Bookkeeping runs remained active at the latest 13:50 ET check. The 12,937 `IS_SUBFUND_OF` rows and endpoint pair comparison are prior-snapshot results with file-date-provisional starts. | Partial. Registrant/series, identity and relationship comparisons need refreshing after the active runs advance; keep file-date starts provisional. Cross-store governed identity remains open. |
| Private equity and ADV private funds | Current MDM catalog has eight kinds; no PE kind. `fund` is a profile available on Company and `fund_structure`; N-PORT fund records create `fund_structure` masters keyed by SEC series ID. Current `iapd.adv` mastering rules cover adviser filing and custodian records, not private-fund records. The pinned relationship catalog defines `INVESTMENT_ADVISER_TO` for an adviser-profile entity to a fund-profile entity, but active source rules do not emit it. Older/parallel ADV schema/docs retain private-fund detail and firm-roster PE indicators (`fund_type`, `any_pe_funds`, `pe_fund_count`); legacy docs name the relationship `MANAGES_FUND`, so that historical terminology needs reconciliation before reuse. | Earlier Silver snapshot had 3,022 `adv_custody` rows, zero `nport_holding` rows, and no `adv_private_fund` table. The refreshed ADV custodian assertions do not represent private funds. Historical `sec_adv_private_fund` schema is not evidence that the active configured pipeline populated or masters PE funds. | No current PE cohort or denominator can be audited. Reconcile intended source, capture, Bookkeeping path, and consumer before defining PE quality checks. Do not infer PE from a `private_offering` filing or fund name, and do not convert absence of a configured PE population into a record-level failure. |
| International companies/entities | Refreshed legacy Company: 1,405 with SEC place mapped `FOREIGN`/`CANADIAN`; 57 more with no SEC place but mapped non-US GLEIF jurisdiction; 1,462 total. Of 3,258 nonempty GLEIF jurisdictions, 600 map non-US. Legacy `international_organization` has zero masters; governed count unavailable. | Prior Silver cohort measurements list facts, line items, measures, insider/issuer links, owner links, and `ISSUED_BY` edges; refresh them because the Company population changed. | Partial. Current non-US denominator is measured; current source identity and downstream trace, plus the 134 jurisdiction disagreements, remain open. |
| People | Separate `person` kind; legacy MDM: 31,125; current governed count unavailable. Sources are SEC submissions and beneficial-ownership reporting-owner assertions. | `insider_reporting_owner` has 5,743 rows; 4,339 distinct nonnull Person links resolve to legacy Person, 781 rows have no Person link. | Partial. Conditional owner type and full entity-to-downstream trace remain open; null count is not itself a defect. |
| Securities | Separate `security` kind; refreshed legacy MDM: 394,305; governed count unavailable. Sources include 13F (5,758 assertions/5,746 linked masters), N-PORT Security and OpenFIGI. | The configured 13F Silver path has 283,725 holdings: 283,715 `security_mdm_id` values match the exact current CUSIP identity. Ten rows with one absent CUSIP are covered by the existing `invalid_cusip_checksum` deferral; no populated pointer is mismatched. Earlier Silver snapshot had 42,383 `ISSUED_BY` and zero N-PORT holdings; both relationship/holding counts need refresh. Earlier MIC result: 617,684 present of 1,392,524 listings. | Partial. Refresh N-PORT issuer/holding edges and listing coverage; trace the two missing 13F manager Company identities; prove current governed identity. Missing MIC is allowed for configured lookup cases; do not treat it as a defect without new evidence. |
| Other configured kinds | `branch`, `government`, `international_organization`, and `venue` are configured. Legacy MDM has zero masters for these kinds; governed counts unavailable because its projection is empty. Company classification rules can defer probable government candidates; venue is a listing lookup target, not a populated entity kind in this snapshot. | No Silver rows establish downstream use of those absent masters. | Not traceable as populated entity families in the connected snapshot. Verify candidate/deferred records and source onboarding separately; do not convert absence into a quality failure. |

## Candidate check definitions

These are check contracts to measure and prove, not enabled checks. DataKitchen
TestGen classifies the link and relationship predicates as referential or
consistency checks, owner completeness as completeness, and identifier
cardinality as uniqueness. The platform Silver engine currently supports only
`identifier`, `in_set`, `one_value`, `not_after`, and `reason_if_empty`, so
these cross-record predicates cannot be represented truthfully as existing
field-only checks.

### Existing quality checks and gaps by entity family

| Family | Existing configured checks | Measured gap or next check |
|---|---|---|
| Company, including international Company records | SEC name presence, registered-agent/placeholder-address handling, pinned SEC place-code validity; GLEIF name and address checks; ADV name presence; N-PORT registrant provisional registration-start flag. | Reconcile SEC incorporation place with GLEIF jurisdiction for the 134-record candidate cohort after source/effective-time tracing. Use a cross-source consistency check only after the cause is resolved; the observed field-presence counts are not completeness targets. |
| N-PORT fund structure | Series ID and LEI format/cardinality rules; `subfund_start_is_authoritative` flags when the start is provisional. | The 70 masters without LEI all have a series ID and no source LEI claim; this is allowed by the configured rule. Do not make LEI mandatory. Holdings remain unavailable in the observed snapshot. |
| Private equity and ADV private funds | No PE kind or PE-specific quality contract in the current MDM/source rules. Current MDM has N-PORT `fund_structure` records and `fund` profiles; retained ADV schemas describe private-fund detail and PE roster indicators but do not connect those records to the active `iapd.adv` MDM/Silver path. | Do not infer PE from `private_offering` or fund names. Reconcile the intended source, capture, Bookkeeping path, and consumer; only then define a supported PE cohort and check denominator. The current snapshot cannot support a PE record-quality check. |
| Person | SEC submissions and ownership owner name-presence and letter-pattern checks; CIK identifier contract. | All 781 Silver rows without a Person link exactly match source classification holds; 32 have a Company link and 749 have neither. Both hold reasons are configured as nonblocking. Do not flag unresolved rows; if later classified, validate the corresponding Person/Company link. |
| Security | N-PORT issuer-placeholder and filed share-class checks; 13F share-class check; CUSIP/ISIN identifier checks. | Effective legacy master identities have zero repeated CUSIP, FIGI or ISIN values; repeated raw N-PORT ISIN claims are withheld under the CUSIP-first rule. A candidate uniqueness/cardinality check must measure effective identifiers and verify source-level conflicts remain withheld; do not fail every repeated raw claim. Missing MIC is explicitly allowed for composite and unpaired listings, so no completeness check is appropriate. |
| Branch, government, international organization, venue | No populated master family in the legacy snapshot; no downstream quality denominator. | Do not emit zero-failure checks over empty populations. Inspect deferred government candidates and venue lookup behavior after an authoritative populated governed snapshot is available. |

### Check disposition across the audited families

No new check is enabled from this audit. Invalid filed identifiers are already
caught by Dataset Contract validation; other observed patterns are explained
by configured behavior, lack a complete denominator, or remain unconfirmed.
The three current row-local Company checks pass on the stated Silver snapshot.
This is not a claim that every entity has been fully traced or that all data is
defect-free.

The confirmed validation findings in the measured inputs are 14 invalid
N-PORT fund LEI checksums, 2,428 invalid N-PORT Security CUSIP checksums, one
additional invalid N-PORT CUSIP, and one invalid 13F CUSIP checksum. Existing
Dataset Contract validation already catches these; the fund LEI cases are
blocking and the Security CUSIP cases follow their configured nonblocking
disposition. The current Company Silver predicates have zero failures on the
measured rows. No new check is ready to activate: the 134 international
Company place disagreements need identity/time explanation, the two 13F filer
identities and four ADV custody keys need source-coverage tracing, and N-PORT
holding checks need a completed, verified landing. Private-equity and the four
currently empty entity kinds have no active populated denominator, so they
cannot yet yield record-level checks.

| Finding or predicate | DataKitchen TestGen category | Existing platform support | Decision |
|---|---|---|---|
| Invalid filed identifier shape or check digit (N-PORT fund: 14 invalid LEI-checksum deferrals; N-PORT Security: 2,428 invalid-CUSIP-checksum and one invalid-CUSIP deferrals; 13F Security: one invalid-CUSIP-checksum deferral) | Validity; the pinned TestGen types have no check-digit equivalent (regex pattern is not a checksum check). | Existing Dataset Contract identifier-format validation applies shape/check digits and records a typed deferral. The fund reason is blocking; Security's invalid-CUSIP reasons are explicitly nonblocking. | Already detected; do not duplicate it in `quality.yaml`. Reconcile the 14 fund LEI deferrals through the normal data-quality disposition. Preserve the configured nonblocking treatment for invalid Security identifiers. |
| Security effective identifier cardinality and source-claim disposition | Uniqueness and consistency | Identifier claims are constrained by the merge contract; field-only Silver checks cannot see accepted versus withheld claims. | No effective-master duplicate was observed for CUSIP, FIGI, or ISIN. Keep CUSIP-keyed conflicting ISIN claims withheld; do not flag raw repeats as defects. |
| Silver MDM pointers resolve to the correct current entity | Referential integrity | No current field-only check can join Silver to the authoritative MDM resolver. | Candidate for a generic cross-store Silver check; requires current governed MDM data and a planted bad-pointer proof. |
| Typed relationship type, direction, endpoints, and effective dates agree with MDM | Referential integrity and consistency | No existing check can compare the Silver edge with authoritative typed MDM relationships. | Candidate for a relationship-aware extension to the cross-store check; source-only pairs remain unconfirmed while N-PORT load steps are pending. |
| Owner link matches the classified Person-or-Company role | Completeness and consistency | The current check kinds do not express conditional cross-field rules. | Candidate for a conditional check only after classification is final; keep the 781 currently held rows out of failure counts. |
| SEC incorporation place and GLEIF jurisdiction agree for the same entity and time | Consistency | No current field-only check can compare both sources and effective-time history. | Investigate the 134 disagreements first; do not add an enabled check until entity identity, rule version, and effective time explain them. |
| Listing MIC is present | Completeness | Source field is optional; the configured reference lookup returns null for composites and unpaired exchange codes. | No check: the missing values are permitted by the source contract. Consider a crosswalk-coverage change only when an approved authoritative mapping is available. |

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
4. **Configured Security identifier cardinality**: group active identifier
   claims by namespace and current Security identity, then apply each
   namespace's source, key-class, forward-claim, and approved tolerance rules.
   This must distinguish repeated supporting SEDOL/LoanX/ticker claims from
   an identifier used as a binding key; raw duplicate counts are insufficient.

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
