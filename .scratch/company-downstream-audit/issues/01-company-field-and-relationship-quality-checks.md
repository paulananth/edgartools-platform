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
- [x] Enumerate configured kinds and refreshed connected-snapshot population counts (legacy MDM rechecked 2026-11-08 17:20 ET; governed MDM rechecked 17:06 ET). Legacy `mastering_master` has 449,281 rows: 449,272 canonical masters and nine aliases. Canonical kinds: 10,905 Companies, 12,937 fund structures, 31,125 people, and 394,305 securities; branch, government, international organization, and venue have no legacy masters. At 17:06 ET, governed `mdm.master_entity`, `mdm.current_record`, and `mdm.relationship_version` each still have zero rows, so governed-kind counts and generation cannot be confirmed here. Earlier governed counts remain prior observations only.
- [x] Correct the 16:06 whole-Company field totals to count nonempty nested values, not JSON field wrappers (read-only current legacy aggregate, 2026-11-08 16:09 ET; no values emitted). Current Company masters: 10,875/10,905 names, 10,695 addresses, 6,414 SIC, 6,217 fiscal year ends, 5,787 incorporation states, and 3,258 jurisdictions. GLEIF status/legal form/managing LOU/validation/registration fields each appear on 3,258 masters; entity-creation date appears on 2,693 and authority entity ID on 3,141. Source-field presence is listed by feed in the complete 17:15 ET table below; the earlier 16:09 source-wrapper counts are superseded. These are presence measures, not requiredness or correctness targets.
- [x] Resolve missing names in assigned ADV adviser Company masters (read-only current legacy aggregate and pure reprojection, 2026-11-08 16:55 ET; no names or identifiers emitted). The 30 name-empty masters are all stored with `status=review`. Re-running the existing `prepare_current_records` and `prepare_master_records` calculations over their 78 retained assertions reproduces 30 `authoritative_identifier_conflict` reviews, all on the `cik` namespace; it also produces zero names, matching the stored projection. The name claims exist and are eligible, but the merge intentionally withholds all fields for these identities while their authoritative CIK conflict is unresolved. This is not a confirmed field-quality defect and should not become a missing-name check. Keep the 30 cases in the steward identity-conflict queue; do not resolve them automatically.
- [x] Revalidate after rebasing onto current `origin/main` with `uv run --no-project --with pytest -- pytest -q -p no:cacheprovider tests/unit/test_profiling_genericity.py` (99 passed, 0.27 s) and `git diff --check` (clean), 2026-11-08 17:28 ET.
- [x] Trace current null Company fact, line-item, and measure pointers to source identities (read-only 2026-11-08 16:20 ET; identifiers were not emitted). All 21,294 null `company_fact` rows fall on nine distinct CIK keys, none matching a current `sec.company.v1` binding; one key resolves to a Company master through `sec.nport.registrant.v1`, and eight have no current CIK identifier. All 414 null line-item rows and 720 null measure rows fall on the same two CIK keys, with no current CIK identifier or source binding. Current key coverage is 320/329 for facts and 309/311 for line items and measures, below the profile's recorded `inclusion: 1.0`. This is a measured difference from the profiled coverage baseline; `inclusion` is descriptive profile evidence, not an enforced SLA, so confirm intended source scope before calling it a quality failure. It is not a wrong populated pointer. No populated pointer falls outside the current Company master ID set. Decide whether the N-PORT-only Company identity should be a valid link target, then trace the eight unmastered fact keys and two line/measure keys through source coverage. The prior 14:30 “All Company” fact/line counts equaled the SEC subgroup; distinguish current table totals from rows linked through that specific source binding.
- [x] Reconcile unassigned GLEIF Level 1 assertions and GLEIF deferrals to their queues (read-only MDM aggregate, 2026-11-08 15:25 ET). All 458 of 3,716 GLEIF Level 1 assertions without an assigned master have an open `binding_required` review; no assertion is silently absent from review. A separate 39 deferred GLEIF records are `unsupported_identity_kind`: 34 have probable kind `fund_structure`, three `government`, and two no probable kind. These are unresolved source identities/classifications, not Company master defects, and must remain separate from populated-entity denominators.
- [x] Refresh Company identifier cardinality after population growth (read-only streamed canonical masters, 2026-11-08 13:25 ET). BD number: 106 values on 106 masters; CIK: 8,361 on 8,361; CRD: 2,337 on 2,337; LEI: 3,359 on 3,359. Every value is distinct across masters, and no master has multiple values in any namespace.
- [x] Trace ADV custodian assertions, `CUSTODIAN` declarations, Silver row grain, and the configured Silver check (read-only 2026-11-08 14:56 ET). All 3,017 declared adviser/custodian pairs exactly equal the 3,017 unique Silver pairs; no source-only or Silver-only pair exists. Silver has 3,022 rows because five filing/custodian pairs are each repeated, with distinct fact values; this is permitted by the declared one-row-per-filing-and-custody-row grain. Of 498 declared custodian target keys, 494 have retained assertions; all four missing keys match the configured nonblocking `invalid_lei_checksum` deferrals and account for six null Silver pointers. The remaining 475 null pointers cover 263 name-only keys without a configured holder; those cases correctly wait. All 2,541 populated custodian pointers match the exact current source key/master; adviser pointers are populated on all rows. The 494 retained custodian assertions include 106 BD-number and 114 LEI records (all assigned), and 274 name-only records (11 assigned by the exact-name holder and 263 correctly waiting); all contain a name. The actual `silver_writer.checks.run` execution evaluated `related_person_is_y_or_n` on 3,022 rows: zero failed, flagged, or refused. A separate aggregate found no null, negative, or over-13-digit amounts. No new check or defect is warranted from these measurements.
- [x] Trace the configured 13F security and filing paths through current Silver to canonical Company/Security identities (read-only 2026-11-08 13:48 ET). Bookkeeping reports the 13F security run complete with 44/44 work items verified and the filing run complete with 3/3 verified. Silver contains 168 filing rows and 283,725 holdings. All holdings join a filing accession; 52 distinct holding accessions match filings. The CUSIP key and Security pointer match the same current Security on 283,715 holdings. The remaining 10 rows share one CUSIP with no Security master or source assertion; that key matches the one `invalid_cusip_checksum` deferral, which the source contract already sets aside nonblocking. This is an explained outcome, not a new defect. Filing CIK and Company pointer match on 146 rows; 22 rows across two distinct CIKs have null pointers, no current CIK master of any kind, no matching Company source assertion, and no open review. No nonnull pointer is wrong-kind, orphaned, or mismatched to its CUSIP/CIK. Trace the two manager keys to retained capture or a documented coverage boundary; keep them as source-coverage candidates until explained.
- [x] Refresh all operational Silver table row counts on the current snapshot (read-only 2026-11-08 15:40 ET). Company fact 5,134,979; line item 96,807; measure 168,360; insider position 14,331; insider reporting owner 5,743; ADV custody 3,022; registration offering 732; registration statement line 27,415; relationship 55,320 (`ISSUED_BY` 42,383, `IS_SUBFUND_OF` 12,937); N-PORT holding 0; 13F filing 168; 13F holding 283,725. Counts alone do not establish pointer identity; cohort-level downstream comparison remains open.
- [x] Refresh declared relationship counts after the new assertions appeared (read-only 2026-11-08 13:50 ET). Current source counts remain 48 `SUCCESSOR_ENTITY`, 3,017 `CUSTODIAN`, 12,937 `IS_SUBFUND_OF`, 245,130 `ISSUED_BY`, 4,962 `BENEFICIAL_OWNER_OF`, and 14,886 `EMPLOYED_BY`. These are declaration sightings, not distinct governed edge counts; relationship key, endpoint and time comparisons remain open.
- [x] Measure identifier cardinality in both directions for every populated kind with a bounded reverse claim (read-only 2026-11-08; Company refreshed 13:25 ET, Security refreshed 12:46 ET). Current Company BD number (106), CIK (8,361), CRD (2,337), and LEI (3,359) values are each unique across masters, with no master holding multiple values per namespace. Person CIK (31,125) maps to one Person master; 4,311 values appear in both SEC submissions and ownership-owner feeds and resolve to one master each, with no Person holding multiple CIKs. Fund-structure series IDs (12,937) and LEIs (12,867) each map to one fund master, with no fund master holding multiple values. Security effective identifiers: CUSIP 384,249 distinct values (zero repeated across masters), FIGI 1,392,524 (zero repeated), ISIN 390,955 (zero repeated), LoanX 423 (one repeated across two masters), SEDOL 22,832 (three repeated across two masters), and ticker 129,394 (366 reused; one on four masters against the configured forward limit of three, held for review). These are legacy assignment results; the current governed MDM projection is empty.
- [x] Recompute nested nonempty source field and identifier values across the full retained assertion store (read-only streaming scan, 2026-11-08 17:15 ET). The cursor exhausted 1,257,503 assertions across 14 feeds; the total includes 2,938 `iapd.adv.filings.v2` Company assertions, of which 2,335 distinct legacy Company masters are linked and three assertions are unassigned. The v2 feed is not in the active Company merge source order. Per-feed nested-value counts are in the table below; they establish source field presence only, not semantics, requiredness, or full downstream coverage.
- [x] Reconcile the three unassigned `iapd.adv.filings.v2` assertions to their review state (read-only aggregate, 2026-11-08 17:21 ET). All three are in open `conflicting_identifiers` review. Do not count them as missing Company masters or add a link-completeness failure for these held identity claims.
- [x] Reproduce the operator-selected Company control trace in legacy MDM/Silver and select controls for the other populated kinds. The Company control resolves to one Company with one SEC Company and one GLEIF assertion, 15 populated MDM field names, two identifier namespaces, 25,135 fact rows, 437 line-item rows, 760 measure rows, 10 issuer-position rows, three insider issuer rows, and 57 `ISSUED_BY` edges targeting the Company. One control each was traced for fund structure, Person, and Security; their details and limits follow below. Governed identity remains unavailable in this snapshot.
- [ ] Complete the batch-level all-kind audit: compare every retained assertion and canonical master by configured kind, source binding, identifier namespace, populated field, and downstream consumer; publish per-kind denominators, unresolved/held outcomes, mismatches, and temporal/source evidence. Existing aggregate scans and representative traces are evidence, but do not yet establish a checked result for every record or every Company field.
- [x] Refresh typed edge pairs, listing MIC coverage, Company row-local checks, and Silver row counts after the master population growth (read-only 2026-11-08 15:31–15:46 ET). Silver has 55,320 edges: 42,383 `ISSUED_BY` and 12,937 `IS_SUBFUND_OF`; both N-PORT pair comparisons and the 4,139 Person/issuer pair comparisons were re-run below. Listing MIC results and Company row-local checks were remeasured on the current snapshot, and all 12 operational Silver table counts were refreshed. This does not close role-cohort grouping or current governed-MDM comparison.
- [x] Refresh current pointer-based downstream counts for all Company source roles with assigned master IDs (read-only 2026-11-08 16:31 ET). Counts for SEC, GLEIF, ADV adviser, assigned ADV custodian, N-PORT registrant, and their union are in the current cohort table below. Cohorts overlap; only current matching pointer IDs count, while null and registration rows are separate.
- [x] Rebuild the current mapped non-US and 13F-filer identity sets and refresh their downstream rows (read-only 2026-11-08 16:38 ET). The pinned SEC place mapping yields 1,405 foreign/Canadian Companies; GLEIF adds 57 non-US Companies with no SEC place, for 1,462. The current 13F manager set has eight Companies. Their current downstream counts are included below. Registration rows remain attributed by current CIK only because the stored MDM pointer generation is unidentified.
- [ ] Complete the Company trace separately for each configured source role/profile and cohort: SEC filers/issuers, GLEIF legal entities, ADV advisers, ADV custodians, N-PORT registrants, Company records with the `fund` profile, and mapped non-US Companies. Record overlapping cohort denominators and role-specific source fields and consumers; do not treat these labels as separate MDM kinds.
- [ ] Trace typed relationship paths for every populated kind, including `ISSUED_BY` from Security to its allowed issuer kinds; verify endpoint kind, direction, current MDM identity, time basis, and source evidence. Source assertions include 48 GLEIF `SUCCESSOR_ENTITY`, 3,017 ADV `CUSTODIAN`, 12,937 N-PORT `IS_SUBFUND_OF`, 245,130 N-PORT `ISSUED_BY`, 4,962 `BENEFICIAL_OWNER_OF`, and 14,886 `EMPLOYED_BY` declarations; repeated filing sightings must be reduced to governed edge grain before comparing to Silver.
- [x] Compare N-PORT `ISSUED_BY` declaration endpoints to current Silver pairs after population growth (read-only 2026-11-08 15:43 ET). The 245,130 declarations reduce to 225,221 distinct Security-master/issuer-source pairs. Of these, 42,385 resolve to both a current Security master and one Company target; Silver has 42,383 current pairs, with 42,383 exact overlaps, two resolved source-only candidates, and zero Silver-only pairs. Remaining declarations without two assigned endpoints are not confirmed missing edges. The two resolved candidates await N-PORT `links`/landing/merge stages, so they are not yet confirmed publication defects.
- [x] Recompare N-PORT `IS_SUBFUND_OF` endpoints, kinds, profiles, and Silver periods after population growth (read-only 2026-11-08 15:43 ET). All 12,937 declarations are 12,937 distinct pairs; every pair resolves from `fund_structure` to `company`, both endpoints have the `fund` profile, and all 12,937 exactly match Silver with zero source-only or Silver-only pairs. All Silver starts remain nonempty `observed` file-date fallbacks; authoritative inception remains unknown.
- [x] Recompare ownership relationship endpoint sets to the owner Silver table after population growth (read-only 2026-11-08 15:46 ET). `BENEFICIAL_OWNER_OF` has 4,962 declarations and `EMPLOYED_BY` 14,886; each type has the same 4,139 distinct mastered Person/issuer Company pairs and exact overlap with all 4,139 distinct nonnull Person/issuer pairs in `insider_reporting_owner`, with zero source-only or Silver-only pairs. Each type also has 280 source/target pairs without both current endpoint masters. The Silver table does not preserve typed capacity or periods; the governed relationship projection remains empty.
- [x] Assess GLEIF successor endpoint assignment and reconcile ADV custodian endpoint pairs (GLEIF read-only 2026-11-08 12:03 ET; ADV read-only 14:56 ET). None of 48 `SUCCESSOR_ENTITY` source subjects has an assigned Company master; all 48 remain in open `binding_required` review, while 26 targets resolve to a legacy Company. These source subjects are part of the broader unassigned GLEIF review coverage; do not count them as missing published edges. For ADV, the 3,017 declared adviser/custodian pairs exactly match the unique Silver pair set; open details are recorded in the completed custody trace above. The governed relationship projection remains empty.
- [x] Determine whether private equity has a separate representation in the active MDM/Silver path. The eight-kind catalog has no PE kind; `fund` is a profile on Company/fund structure. Active IAPD ADV rules master adviser filings and custodians, not private-fund records. Retained ADV schemas still describe private-fund details and PE roster indicators, but the read-only local Silver snapshot has no private-fund table (3,022 custody rows; zero N-PORT holdings). This establishes no current PE quality denominator; it does not establish defects in any PE records. Verified against current config/schema and local Silver on 2026-11-08 10:25 ET.
- [ ] Finish tracing N-PORT registrants, funds, series, holdings, and securities to their mastered fund/security/company or other entity records. Keep N-PORT series distinct from ADV private funds. Legacy fund-structure masters: 12,937, all with the `fund` profile; Company `fund` profiles and N-PORT registrants match at 1,947. All 12,937 `IS_SUBFUND_OF` source endpoint pairs match Silver at 15:43 ET. At the 17:04 ET Bookkeeping status check, both `sec.nport.security` runs remained active and neither had verified `land_holding`. One run had 3/18 items verified; it was waiting at `holding`, `holding_rows`, and `record`, with `land_holding` pending. The other had 14/17 items verified; `land_holding` was pending and `merge` waiting. No completed holding landing is available for measurement. Recheck no more frequently than every 30 minutes. All subfund starts are `observed` file-date fallbacks; authoritative inception remains unknown.
- [x] Refresh Security listing MIC coverage on the current population (read-only 2026-11-08 15:36 ET; pinned MIC reference checksum verified). The 1,392,524 distinct listing FIGIs are unchanged. Of these, 617,684 have MICs; all are valid in pinned `iso-10383-mic` version 1 and match the configured 246-code exchange mapping. There are zero invalid, mismatched, or mapped-exchange missing MICs. The 774,840 nulls remain 414,643 unmapped exchanges with composite FIGI, 42,639 unpaired exchanges without composite FIGI, and 317,558 with neither exchange nor composite FIGI. The contract allows null MICs for these source states; no missing-MIC check is warranted.
- [x] Trace the legacy non-US Company cohort through source assertions, identifiers, field presence, and grouped Silver consumers (read-only 2026-11-08 14:27–14:30 ET). Pinned SEC place mapping identifies 1,405 records; 57 additional records without an SEC place have a non-US GLEIF jurisdiction under the approved country mapping (1,462 total). A further 601 of 3,258 nonempty GLEIF jurisdictions map non-US; the subsets overlap and must not be added. Cohort downstream counts are recorded below. This is a legacy/Silver trace; current governed identity remains unverified. The configured `international_organization` kind has no legacy masters.
- [x] Refresh all 16 configured Silver MDM pointer columns and both relationship endpoints against the current legacy master IDs and pinned relationship endpoint-kind contract (read-only 2026-11-08 14:10 ET). Company facts/line items/measures, insider, ADV, 13F, and relationship pointers have zero IDs absent from legacy masters and zero wrong-kind rows. Current counts are in the pointer-membership table below. Registration pointers remain unmatched to legacy IDs (491 offering rows and 17,407 statement lines); their owning MDM generation is unverified because governed tables are empty, so this is not yet evidence they are stale or wrong. N-PORT holding links still have zero rows. Membership and kind do not prove source-key identity or temporal correctness.
- [x] Compare every configured Silver link's source key and pointer with the current legacy `mastering_record` source binding (read-only 2026-11-08 14:15 ET). Sixteen link contracts were evaluated. Company fact, line-item, measure, insider, ADV adviser/custodian, 13F filing and 13F holding pointers exactly match when their source key has one assigned legacy master; all other nulls correspond to no retained source record or an unassigned source key. No source key maps to multiple legacy masters. Registration differs: 491 offering rows across 412 keys and 17,407 statement-line rows across 340 keys point to IDs different from the current legacy CIK binding; one offering row and three statement rows are null despite a current binding. Because governed MDM is empty and these Silver IDs are absent from legacy master, classify this as a generation-divergence candidate pending producer and authoritative-generation identification, not a confirmed stale-pointer defect.
- [x] Trace the one observed Security ticker over the configured three-master forward claim through actual Form 4 records and issuer declarations. Two Form 4 assertions carrying it are both in open `conflicting_identifiers` review, as the configured `on_several: review` rule requires; neither silently auto-binds. The same four Security masters have three `ISSUED_BY` declarations targeting two GLEIF source subjects, neither present in retained GLEIF source assertions, and no Silver issuer edge. The ticker case is handled by review, not a confirmed quality defect; the missing GLEIF targets remain a source-coverage candidate. Verified from read-only current legacy MDM/source/Silver data on 2026-11-08 10:47 ET.
- [x] Compare raw Security identifier claims across OpenFIGI and N-PORT with configured cardinality (read-only 2026-11-08 12:15 ET). Source assertions had 370 repeated ISIN values across two or three assigned source entity IDs (154 present in both feeds, 216 N-PORT-only; 26 cross multiple N-PORT key classes). These are raw claim collisions, not effective-master duplicates. Source-level CUSIP and FIGI claims had no repeated values across assigned entities; SEDOL had three repeated values and LoanX one, each within the configured five-master forward claim. Ticker had 366 reused values, one appearing on four assigned entities against a forward claim of three; the corresponding Form 4 assertions were held for review. Effective-master and withheld-claim reconciliation was a separate follow-up below.
- [x] Reconcile repeated source ISIN claims against effective legacy master identifiers and N-PORT withholding (read-only 2026-11-08 12:22 ET). The effective `mastering_master` projection has zero duplicate CUSIP, FIGI, or ISIN values across Security masters. It has three repeated SEDOL values and one repeated LoanX value, each on two masters and within the configured forward claim of five; 366 ticker values are reused, with one on four masters against a forward claim of three and the over-limit case held for review. N-PORT has 394 CUSIP-keyed withheld ISIN occurrences over 371 source subjects (370 distinct ISINs); 154 of those values also occur as accepted claims on another master. This matches the configured CUSIP-first keep-separate behavior. Raw source collisions are not effective-master duplicates and are not confirmed defects.
- [x] Verify the SEC–GLEIF jurisdiction binding rule's current approval state and proof (policy and `rules/merge/pending-proofs.yaml`, 2026-11-08 11:00 ET). `sec-gleif-name-jurisdiction` is active for Company with a 300/300 measured proof (95% one-sided lower bound 0.991062) and zero violations in 257 adversarial cases. This establishes the rule is approved and enabled; it does not establish when the legacy records were last processed or explain the 134 field disagreements.
- [x] Trace the 134 jurisdiction candidates against their accepted legacy masters, field winners, retained assertions, and available processing history (pinned place mapping plus configured `jurisdictions_agree` logic, read-only 2026-11-08 15:01 ET). Recomputed 134 disagreements among 3,073 pairs with both populated fields. All are accepted Company masters; SEC wins `state_of_incorporation`, GLEIF wins `jurisdiction`, and neither field has a recorded conflict list. Both source assertions are present. No current `mastering_decision` rows reference these master/source IDs. SEC Company source effective time is null for all 3,258 SEC/GLEIF pairs, while each matched GLEIF assertion has a nonnull effective time. The source configuration says SEC incorporation effective time is unknown. Therefore the records remain unresolved candidates: this store cannot establish the match route, processing rule version, or whether the source values describe the same time.
- [x] Compare Form 4 issuer CIKs to current Company identities and Security `ISSUED_BY` edges (bounded, read-only MDM-to-Silver join, 2026-11-08 15:21 ET). Among 4,447 assigned v2 assertions, 4,359 issuer CIKs resolve to a Company: 2,822 rows have a current edge to that Company, six have an edge to a different Company, and 1,531 have no current edge. The remaining 88 issuer CIKs have no Company master. These are assertion counts, not distinct Security counts. Because the contract's filing-period effective time is absent from the active reader and all v2 effective times are null, the six differing edges and 1,531 missing edges are temporal/source-coverage candidates, not confirmed wrong relationships. The 88 missing Company identities are source-coverage candidates.
- [x] Break down SEC Company classification deferrals by configured rule step and distinct source-record locator (read-only 2026-11-08 11:10 ET). All 69,816 blocking events map to distinct locators. Step 11 leaves 67,166 unclassified with no probable kind; step 1 adds 1,062 without a probable kind; step 7 adds 73 without a probable kind. The other 1,515 are explicitly held as probable Company (599), Person (658), fund structure (226), or government (32). This measures the configured hold-back population without treating every deferral as a defect.
- [x] Re-measure row-local configured Company Silver checks on the current stored population (read-only 2026-11-08 15:40 ET). `company_fact`: 5,134,979 rows, 3,113,260 eligible period pairs; `company_line_item`: 96,807 rows, 46,971 eligible pairs; `company_measure`: 168,360 rows. Period ordering, empty-value/reason consistency, and allowed measure windows each have zero failures; all three `quality` columns are null on every row. The four `company_fact` `one_value` checks remain unmeasured because they apply within each delivery, not the combined historical tables.
- [x] Reconcile the 70 N-PORT fund structures without a master LEI to their retained assertions (read-only 2026-11-08 11:24 ET). All 70 have a `sec_series_id` in the master and source assertion; none of their retained N-PORT fund assertions claims an LEI. The configured series-ID rule can identify them without a LEI, so the 70 are not defects and are not comparable to the two proving-run exceptions that lacked identity evidence.
- [x] Reconcile missing Person links on insider reporting owners to classification holds using the exact filing-owner key across MDM and Silver (read-only 2026-11-08 11:27 ET). All 781 Person-null owner rows match 781 distinct source records: 331 `classification_deferred` and 450 `classification_entity_undetermined`. Of those, 32 already link to a Company (14 deferred, 18 undetermined); 749 have neither an owner Person nor Company link (317 deferred, 432 undetermined). The key sets match exactly, with no unmatched rows.
- [x] Verify whether those unresolved owner rows are allowed to land (read-only config review, 2026-11-08 11:28 ET). `sec.ownership.reporting_owner.v1` explicitly treats both classification reasons as nonblocking, and Bookkeeping lands owner rows after merge. The 749 without either link are expected to remain unresolved while classification is held; do not flag them as broken links without a later classification decision.
- [ ] Reproduce the earlier protocol-7 entity-link resolver comparison for every populated Silver link. Its prior row-level counts cannot be rerun while governed MDM tables are empty on the current shared connection; historic producer and safe refresh timing also remain unresolved.
- [ ] Map Silver relationship endpoints from legacy IDs to current MDM identities by configured source keys, then compare typed edges, direction, and effective dates. Silver has 55,320 rows; the governed relationship projection is empty in the current connection, while a prior snapshot reported 13,442. Confirm the loaded producer and identity transition before deciding whether to repair or retire any rows.
- [x] Determine whether missing listing MIC is a defect under the configured source contract (read-only config review, 2026-11-08 12:42 ET). The OpenFIGI source says MIC comes from the local MIC reference lookup and is null when no mapping exists; it explicitly expects no MIC for a composite listing or an unpaired exchange code. The full legacy scan's 414,643 composite/no-MIC rows, 42,639 unpaired-exchange/no-composite rows, and 317,558 rows with neither exchange nor composite venue detail therefore do not establish missing-MIC defects. All 617,684 present MICs remain valid and mapped. No completeness check is warranted for this optional field. Extending the exchange crosswalk requires an approved authoritative code mapping, not a quality rule inferred from the rows.
- [x] Record currently confirmed source-validation failures by distinct pattern in the finding ledger (read-only evidence and contract mapping, 2026-11-08 17:06 ET). Four rows separate N-PORT fund LEI checksum, N-PORT Security CUSIP checksum, N-PORT Security invalid-CUSIP deferrals, and 13F Security CUSIP checksum outcomes, with counts, validation support, and existing dispositions. No new Silver check is justified by these already-detected source deferrals.
- [x] Map the confirmed input-validation patterns to DataKitchen TestGen `validity` and the existing Dataset Contract identifier validator (shape/check-digit validation) (2026-11-08 17:06 ET). No unsupported check is represented as `quality.yaml`; no Company, Person, Security, fund-structure, or other MDM completeness target is inferred from optional field presence.
- [ ] Draft check definitions in the owning source contract or Silver table spec; measure them on the pinned records, include counts in comments, and prove each check with a planted invalid record before proposing activation.
- [ ] For cross-table or cross-store checks without a supported primitive, document the exact predicate and smallest required engine/configuration change as a separate issue; do not approximate it with a misleading field-only check.
- [ ] Report coverage for every Company role/cohort and every configured MDM kind, confirmed defects, candidate findings still under investigation, check definitions and measurements, and deferred work. Do not create external tickets unless requested.
- [x] Learning → skill: `none` (reviewed `skills/data-quality/SKILL.md` on 2026-11-08 14:01 ET). It already requires evidence-backed findings, supported generic checks, planted-invalid proofs, and separate tickets for unsupported predicates; this audit found no additional reusable rule to add.

## Measured evidence and unresolved checks

These measurements come from the local read-only snapshot observed on
2026-11-08. They are not a globally consistent snapshot across stores; preserve
the stated store and table denominator with every conclusion.

**Snapshot qualification:** refreshed reads of the designated shared
`local-test-server` found 449,281 raw legacy `mastering_master` rows,
comprising 449,272 canonical masters and nine aliases. At 2026-11-08 12:46 ET
the canonical kinds were 10,905 Company, 12,937 fund structure, 31,125 Person,
and 394,305 Security. The 13:12 ET assertion snapshot held 1,254,565 rows
across 13 feeds; a full stream at 17:15 ET found 1,257,503 rows across 14
feeds. A 17:06 ET read found zero rows in governed
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
| Silver links resolved by configured source key | All 16 declared Silver link contracts were grouped by source key and compared with `mastering_record` for the same source code and key. Facts, line items, measures, insider issuer links, 13F links, and ADV adviser links exactly match their one current legacy assignment when present. Nulls elsewhere correspond to missing or unassigned legacy source records; no source key has multiple current legacy IDs. | This is a direct source-key-to-legacy-binding comparison, stronger than pointer membership, but it is not the protocol-7 governed resolver. The governed MDM tables remain empty, so previous current-governed resolver counts cannot be reproduced. Null links need source coverage/classification review and must not be blanket-flagged. | Identify the intended populated governed generation and compare the same contract keys against its resolver; trace any source-unbound rows to retained captures and disposition. |
| Registration links | Compared each Silver `cik` with the exact `sec.company.v1` source binding. 491 offering rows across 412 CIK keys and 17,407 statement-line rows across 340 CIK keys have nonnull pointers different from the current legacy binding. One offering row and three statement-line rows have a null pointer despite a bound CIK. Another 240 offering rows across 237 CIKs and 10,005 statement rows across 218 CIKs have null pointers and no retained source record. | The populated IDs are confirmed to diverge from the current legacy source-key binding and are absent from the legacy master table; their producing/authoritative generation remains unknown because governed MDM is empty. Treat as a cross-generation discrepancy candidate, not a confirmed stale-link defect. Four null-but-bound rows are current link-refresh candidates if the legacy generation is authoritative. | Identify the registration load’s pinned MDM generation and producer, then repeat against that authoritative resolver. If legacy MDM is authoritative, trace all 491/17,407 mismatches and four resolvable nulls to the registration landing receipts; prove the generic link check with a planted bad pointer. |
| ADV adviser/custodian links and custody facts | Source-key comparison found all 3,022 adviser pointers exact across 1,864 filing keys. For custody, 2,541 pointers match across 231 assigned custodian keys; 475 null rows cover 263 name-only keys correctly left unassigned. Six additional null rows cover four keys with no retained assertion; all four keys match `invalid_lei_checksum` deferred records. The 3,017 declared adviser/custodian pairs exactly equal 3,017 unique Silver pairs. The five additional Silver rows are repeated filing/custodian pairs with distinct fact values, allowed by the Silver grain. The check runner measured `related_person_is_y_or_n` on all 3,022 rows: zero failures, flags, or refusals. | No mismatched populated pointer or source/Silver pair was found. Expected waits, checksum deferrals, and repeated fact rows explain all nulls and the 3,022-versus-3,017 count difference. | No new check. Preserve nonblocking deferral and row-grain behavior; remeasure on a complete, pinned load if the active feed changes. |
| Insider reporting-owner identity links | `insider_reporting_owner`: 5,743 rows; 4,962 Person links, 32 Company links, 749 with neither, and no row with both. All 781 Person-null rows match the 781 retained source records deferred (331) or undetermined (450) by exact filing-owner key; the 32 Company links split across those queues (14 and 18), leaving 749 unlinked (317 and 432). Both classification reasons are explicitly nonblocking in the source contract, and the Bookkeeping flow lands owner rows after merge. | This is not a pointer mismatch: all owner-link gaps align exactly with unresolved classification. A null Company link is expected for known People; the 749 neither-linked rows are permitted unresolved cases, not proven invalid entities. | Keep them out of link-failure checks while classification remains unresolved. If later classified as a Person or Company, require the corresponding link and validate its current MDM identity. |
| N-PORT holding link coverage and load state | Refreshed at 2026-11-08 14:26–14:30 ET: `nport_holding` remains at zero. The Nov 6 11:54 ET run progressed: prepare/identifier/series/submission and related aggregation steps are verified; holding landing and processed remain pending, merge waits. The Nov 6 21:31 ET run remains earlier: holding/holding_rows wait, downstream combine/link/land/merge/processed steps are pending. | No holding denominator is available yet; source-to-Silver identity and holding quality cannot be concluded from zero rows. | Recheck after at least 30 minutes, or after a known run completion. Verify the deployed producer and governed MDM generation after landing; do not resume, cancel, or alter active runs as part of this read-only audit. |
| Company jurisdiction cross-source disagreement | Of 3,073 legacy Company records with both fields populated, 134 disagree under the complete configured place-comparison semantics. All 134 are accepted; SEC and GLEIF each win their expected, separately owned field, with no field-conflict entries. Both assertions are retained. No current `mastering_decision` row references the IDs. SEC effective time is null for all 3,258 matched pairs; GLEIF effective time is populated. The source contract says SEC incorporation effective time is unknown. | Confirmed field disagreement, not a confirmed data defect. Current legacy evidence lacks the pair's match route, processing rule version, and comparable SEC effective time. The matching proof (300/300; 0 violations in 257 adversarial cases) validates only its proof cohort. | Obtain source-to-master route and run/rule history, then determine whether a source-quality or identity issue exists. Do not enable a cross-source consistency check until the time and identity semantics are established. |
| Company Silver row-local checks | Full current stored-population evaluation at 15:40 ET: `company_fact` 5,134,979 rows, with 3,113,260 eligible period pairs; `company_line_item` 96,807 rows, with 46,971 eligible period pairs; `company_measure` 168,360 rows. The configured row-local checks `period_start_not_after_end`, `empty_value_has_reason`, and `window_years_known` each have zero failures. All three `quality` columns are SQL null on every row, so no persisted row-level quality tags are present. | The measured current rows satisfy these three checks; no row-level defect was found on these predicates. This is direct SQL evaluation against the current Silver snapshot, not proof that a Bookkeeping load report recorded the same counts. | Recover per-delivery report evidence for the four `company_fact` `one_value` checks; their semantics are delivery-scoped and cannot be safely re-evaluated over the combined historical tables. |
| Listing venue MIC coverage | Refreshed full-population snapshot at 15:36 ET: 1,392,524 Security listing details compared with 2,313 valid entries in pinned `iso-10383-mic` version 1 and 246 configured OpenFIGI exchange mappings. Of 617,684 present MICs, all were valid and matched the configured mapping; zero invalid, mismatch, or mapped-exchange missing-MIC rows. The 774,840 null MICs were 414,643 unmapped-exchange rows with composite FIGI, 42,639 unpaired-exchange rows without composite FIGI, and 317,558 rows with neither exchange nor composite FIGI. The source contract explicitly allows null MIC for composite/unpaired listings, and rows with neither exchange nor venue evidence supply no MIC input. | No MIC completeness defect is established. Every present MIC passed the pinned reference and mapping on the refreshed population; the null groups reflect allowed or absent source input. Current governed Venue population is empty. | No MIC completeness check is warranted. Do not add a MIC-presence check; any crosswalk expansion needs approved authoritative reference data. |
| Security ticker fan-out and review behavior | Of 129,394 distinct legacy ticker values, 366 appear on more than one Security; one value appears on four, above the configured `ticker.forward: 3` claim. The four masters have three CUSIPs, four ISINs, 69 FIGIs, four distinct issuer-name values, and four security-type values. Two Form 4 source assertions carry the over-limit ticker; both are open `conflicting_identifiers` reviews. The four Securities declare three `ISSUED_BY` links to two GLEIF source subjects, neither retained in the current GLEIF assertion set; none has a Silver `ISSUED_BY` edge. | The configured Form 4 rule sends a reused ticker reaching several Securities to review, and both observed records follow that path. The ticker case is not an auto-binding defect. The issuer edges cannot be confirmed because the required target source records are absent; do not invent endpoints or count these as missing Silver edges until source coverage is reconciled. | Trace the two absent GLEIF targets through retained capture receipts and the relevant load window. Check additional over-limit ticker cases only when they can be aggregated without exposing ticker values; preserve the existing review outcome. |

### Legacy identity, deferral, and review queues

These are counts of rows in the legacy MDM deferral and review tables at the
same snapshot. A queue row is not necessarily a distinct entity or a defect;
it shows where classification, identifier, or binding work was retained.

| Source family | Retained queue evidence | Assessment |
|---|---|---|
| Company | 69,816 blocking SEC Company `classification_deferred` records; all 69,816 have distinct retained source-record locators. Configured steps classify 599 as probable Company, 658 probable Person, 226 probable fund structure, and 32 probable government; 68,301 have no probable kind (step 11: 67,166; step 1: 1,062; step 7: 73). | Most of this snapshot's held records reach the rule's no-match/fall-through path. This is a measured classification-coverage gap, not proof that the hold is wrong: source records still need business review before any new kind or rule is defined. |
| International Company / GLEIF | 39 nonblocking `unsupported_identity_kind` deferrals (34 probable `fund_structure`, three `government`, two with no probable kind); 1,891 distinct `binding_required` review subjects, 1,433 closed and 458 open. All 458 unassigned Level 1 assertions are in the open queue. | The 458 source identities remain unresolved but are visible in review; they are not confirmed missing Company masters. The separate 39 deferred records are not in mastered-kind denominators. The connected governed projection is empty, so no current governed endpoint comparison is possible. |
| N-PORT fund | 14 blocking `invalid_lei_checksum` deferrals. | Existing identifier validation is catching invalid LEIs. Reconcile the retained source assertions and correct or disposition them through the normal workflow. |
| N-PORT Security | 2,428 `invalid_cusip_checksum` deferrals and one `invalid_cusip`; all six unassigned assertion rows are in open `conflicting_identifiers` review. | Invalid CUSIPs are kept out of matching by the configured dataset contract; the six identifier conflicts remain explicit review work, not auto-assigned securities. |
| Person / ownership owner | SEC submissions have 11,096 `classification_deferred` and 34,038 `classification_entity_undetermined` events. Ownership owner has 331 deferred and 450 undetermined records, exactly matching all 781 Silver rows without a Person link by filing-owner key. | SEC submissions counts remain event counts, not unique people. For ownership owners, 32 of the 781 also have a Company link; 749 have neither. This is unresolved classification coverage, not evidence of a stale or broken pointer. |
| Security ownership references | Ownership Security v1 has 398 assertions: 335 resolve to the sole current ticker holder, 55 have no current holder and remain unassigned, and eight have multiple holders and remain in open conflict review. Active v2 has 5,273 assertions: 4,447 resolve to the sole current ticker holder, 725 have no current holder and remain unassigned, and 101 have multiple holders and remain in open conflict review. No assigned Security falls outside the exact current ticker-holder set. The 15/83 `missing_record_identity` deferrals and 8/101 conflict reviews are expected terminal handling under current rules. The active v2 contract carries accession, issuer CIK and symbol; ticker is a lookup cross-reference, not an identifier, and no Security is created. | Of 4,447 assigned v2 assertions, 4,359 issuer CIKs have a Company identity: 2,822 current `ISSUED_BY` edges target that Company, six target a different Company, and 1,531 have no current edge. Eighty-eight issuer CIKs have no Company master. These are assertion counts. The contract's filing-period effective time is not read, and all v2 assertions have null `effective_at`, so the differences remain temporal/source-coverage candidates. | Establish whether the filing period can supply effective time and whether this source is authorized to state `ISSUED_BY`. Reconcile the six differing edges, 1,531 missing edges, and 88 unmastered issuers before deciding whether a contract change or check is warranted. Do not treat current-edge comparison as historical truth. |
| OpenFIGI | 37,681 nonblocking `not_found_by_openfigi` deferrals. | Not found may be an allowed lookup outcome; no completeness failure is asserted without an approved request/response coverage denominator. |

### Source assertion trace across populated kinds

Read-only source assertions in legacy mastering were streamed and counted on
2026-11-08 17:15 ET. The current store contains 1,257,503 assertions across 14
feeds. Counts below are distinct feed assertions and nonempty nested field or
identifier values, not entity denominators. They establish source field
presence, not correctness or requiredness. The 2,938 `iapd.adv.filings.v2`
assertions are retained and mostly assigned to legacy masters, but v2 is not
in the current Company merge policy's source order; keep it distinct from the
active v1 role.

Joining each retained source assertion to its legacy `entity_id` and the
legacy master table gives this assignment coverage. A linked master means the
legacy store assigned the assertion; it does not certify the assigned identity
against the current governed authority.

| Kind | Source feed | Assertions | Distinct linked legacy masters | Assertion rows without a linked master |
|---|---|---:|---:|---:|
| Company | SEC Company | 6,414 | 6,414 | 0 |
| Company | GLEIF Level 1 | 3,716 | 3,258 | 458 |
| Company | IAPD ADV filings | 2,938 | 2,337 | 0 |
| Company | IAPD ADV filings v2 (not in current Company merge source order) | 2,938 | 2,335 | 3 (all open `conflicting_identifiers`) |
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

The 13:12 ET source snapshot contained 1,254,565 assertions across 13 feeds.
The full 17:15 ET stream below found 1,257,503 assertions across 14 feeds,
including retained ADV filings v2. The 14:56 ET ADV audit reconciled all 3,017 declared custody
pairs to Silver; 263 name-only assertions correctly wait for a configured
holder, and four missing assertion keys match invalid-LEI deferrals. The 13F
feed has 5,758 assertions linked to 5,746 legacy Security masters. Its
configured Silver filing and holding consumers are populated, and the current
pointer audit appears below. Neither feed's presence establishes complete
capture by itself. The ownership-security v1/v2 rows now have a bounded
ticker-lookup trace below; six N-PORT-security rows remain to be explained by
their deferral and source-coverage evidence.

| Entity family / source feed | Assertions | Nonempty source fields by field (count of assertions) | Nonempty identifiers by namespace (count of assertions) |
|---|---:|---|---|
| Company — SEC Company | 6,414 | `address` 6,409; `fiscal_year_end` 6,217; `name` 6,414; `sic` 6,414; `state_of_incorporation` 5,787 | `cik` 6,414 |
| Company — GLEIF Level 1 | 3,716 | `address`, `gleif_entity_status`, `gleif_initial_registration`, `gleif_legal_form`, `gleif_managing_lou`, `gleif_registration_authority`, `gleif_registration_status`, `gleif_validation_source`, `jurisdiction`, `name` 3,716 each; `gleif_entity_creation_date` 3,025; `gleif_registration_authority_entity_id` 3,549 | `lei` 3,716 |
| Company — IAPD ADV filings v1 | 2,938 | `address` 2,716; `name` 2,938 | `crd` 2,938 |
| Company — IAPD ADV filings v2 (not in active Company merge source order) | 2,938 | `address` 2,716; `name` 2,938 | `cik` 704; `crd` 2,938 |
| Company — IAPD ADV custodians | 494 | `address`, `name` 494 each | `bd_number` 106; `lei` 114 |
| Company — N-PORT registrant | 5,841 | `address`, `name` 5,841 each | `cik` 5,841 |
| Fund structure — N-PORT fund | 25,874 | `name` 25,874 | `sec_series_id` 25,874; `lei` 25,734 |
| Person — SEC submissions | 31,097 | `legal_name` 31,097 | `cik` 31,097 |
| Person — SEC ownership reporting owner | 4,962 | `legal_name` 4,962 | `cik` 4,962 |
| Security — OpenFIGI | 733,538 | `market_sector` 733,533; `name_of_issuer` 732,552; `security_type` 733,371; `security_type2` 729,717 | `cusip` 353,491; `figi` 733,538; `isin` 380,047; `ticker` 243,729 |
| Security — N-PORT security | 428,262 | `asset_category` 423,667; `currency` 428,235; `derivative_category` 7,117; `investment_country` 427,360; `issuer_type` 424,667; `name_of_issuer`, `title_of_class` 428,262 each; `restricted` 424,005; `share_class` 1,649 | `cusip` 391,953; `isin` 425,310; `loanx` 440; `sedol` 23,533 |
| Security — SEC ownership security v1 | 398 | none | none |
| Security — SEC ownership security v2 | 5,273 | none | none |
| Security — SEC 13F securities | 5,758 | `name_of_issuer`, `title_of_class` 5,758 each; `share_class` 572 | `cusip` 5,758 |

The N-PORT fund feed contains two assertions per 12,937 series in this
snapshot. Its 140 assertions without LEI correspond to 70 fund masters without
LEI. Read-only source-to-master tracing confirmed that all 70 have a series ID
and none of their retained source assertions claims an LEI. The configured
series-ID rule identifies them without a LEI; the two proving-run exceptions
refer to records without identity evidence and are not a missing-LEI
threshold. This is an allowed source state, not a defect. The 5,671 SEC
ownership-security assertions have no nonempty fields or identifiers because
their contract carries accession, issuer CIK and symbol in the record key and
uses ticker as a cross-reference. For active v2, current ticker-holder
assignment, wait, and review outcomes are reconciled below; temporal lookup
and the issuer relationship remain unresolved.

### Representative legacy control traces

Controls are selected for trace shape, not as a statistical sample. No master
values or identifiers are recorded here.

| Control family | Legacy source-to-master trace | Silver/downstream trace |
|---|---|---|
| Company control | One Company; one SEC Company assertion and one GLEIF Level 1 assertion; 15 populated field names and two identifier namespaces. | 25,135 Company-fact rows, 437 line-item rows, 760 measure rows, 10 issuer-position rows and three insider issuer rows link to it; 57 `ISSUED_BY` edges target it. No ADV or registration link rows in this control. |
| International Company cohort | Refreshed denominator: 1,462 legacy Companies; 1,405 have SEC place mapped `FOREIGN`/`CANADIAN`, and 57 additional Companies have no SEC place but a mapped non-US GLEIF jurisdiction. The 601 Companies with a non-US GLEIF jurisdiction overlap this cohort. | Current 14:30 ET grouping finds 269,277 facts, 5,704 line items, 9,920 measures, 1,480 insider positions, 588 owner issuer rows, 10 custody rows, 22 13F filings, 178 offerings and 5,020 statement lines by CIK, and 2,030 `ISSUED_BY` targets. All 134 SEC/GLEIF field disagreements are accepted with expected per-field source winners, but source identity route and comparable effective time are unavailable. Full entity-level field and source-key trace remains open. |
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

At the latest read-only Bookkeeping status check (2026-11-08 15:31 ET), 29
run records were in `running` state. This is a changing operational snapshot,
not a quality result:

| Pipeline family | Active runs | Status relevant to audit |
|---|---:|---|
| `sec.registration` → Silver | 10 | Read, land, and processed steps pending/waiting; registration Silver is partial. |
| `openfigi` → mastering | 3 | One merge running, one waiting, and one run still has requests pending. |
| `sec.company-facts` → Silver | 4 | Facts, landing, line items, measures, and processed steps pending/waiting. |
| `sec.nport.security` → mastering/Silver | 2 | Across the two runs, one has verified prepare, identifiers, series, submissions, holding, holding rows, combine, holding combine, issuer reduction, and issuers; the other is waiting in holding/holding rows and record. Both await `land_holding`; one still has links pending and merge work remains pending/waiting. Silver holding count is zero. |
| `sec.ownership` → security symbols | 10 | Active family count; no step detail was needed for the N-PORT holding check. |

Other active families: `sec.registration` → Silver (10), `openfigi` →
mastering (3), and `sec.company-facts` → Silver (4). No active run was changed.
Respect the 30-minute minimum interval before checking again.

These in-flight runs explain why empty or partial Silver tables cannot be
treated as completed quality populations. The audit has not changed or
restarted any run. Follow the 30-minute inspection interval in `CLAUDE.md`.

### Current Silver pointer membership and endpoint-kind checks

Read-only grouped checks at 2026-11-08 14:10 ET compared every populated
Silver MDM pointer with the current 449,281 raw legacy master IDs and resolved
master kinds. Every nonnull pointer outside the registration tables exists in
the legacy set; no alias pointers were found. For the two populated Silver
relationship types, all source and target IDs exist and satisfy the allowed
endpoint kinds in the pinned relationship catalog. A membership or kind match
does not prove that a pointer is the current identity for the row's source key,
or that a relationship has correct source evidence and effective dates.

| Silver pointer | Rows | Null pointer rows | Rows pointing to legacy master IDs | Distinct matching legacy IDs | Nonnull IDs absent from legacy masters |
|---|---:|---:|---:|---:|---:|
| `adv_custody.adviser_mdm_id` | 3,022 | 0 | 3,022 | 1,493 | 0 |
| `adv_custody.custodian_mdm_id` | 3,022 | 481 | 2,541 | 224 | 0 |
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
| `thirteenf_filing.manager_mdm_id` | 168 | 22 | 146 | 8 | 0 |
| `thirteenf_holding.security_mdm_id` | 283,725 | 10 | 283,715 | 5,746 | 0 |
| `registration_offering.registrant_mdm_id` | 732 | 241 | 0 | 0 | 491 |
| `registration_statement_line.registrant_mdm_id` | 27,415 | 10,008 | 0 | 0 | 17,407 |
| `relationship.source_master_id` | 55,320 | 0 | 55,320 | 55,320 | 0 |
| `relationship.target_master_id` | 55,320 | 0 | 55,320 | 4,125 | 0 |

The 481 null custodian pointers consist of 475 rows for 263 name-only
custodian records that have no configured source holder and correctly wait,
plus six rows across four keys with no retained source assertion. The other
2,541 pointers match the exact source key and current legacy master. The four
source-absent keys and declaration/month grain remain to reconcile before
classifying any row as defective.
Registration is the opposite case: its populated pointers are from an identity
set absent from the legacy master table. Since the governed projection is empty,
these may be valid pointers from a different MDM generation. Do not flag them as
orphans until the producing generation and authoritative resolver are identified.

## Coverage by entity family

### Company role and cohort trace (grouped snapshot, 2026-11-08 14:30 ET)

The counts below were grouped at 14:30 ET against legacy Company identities
and the Silver snapshot then available. They are retained for dated comparison,
not as current totals: the later 16:31–16:38 ET table refresh is the current
pointer-based comparison. Cohorts overlap and are not additive. Downstream counts
are rows reached by those identities; registration counts are attributed by
current legacy CIK because the stored registration pointers belong to an
unidentified MDM generation. The 14:15 source-key audit found registration
pointers diverge from current legacy CIK bindings, so those registration row
counts are not proof that the stored pointers are correct. Company
source-field presence by Company role is separately counted in the checklist;
master field presence is a whole-kind aggregate and does not establish
role-specific requirements or per-record correctness.

| Company role/cohort (14:30 ET historical cohort attribution; not refreshed to the 15:40 ET Silver snapshot) | Companies | Facts | Line items | Measures | Insider positions | Owner issuer rows | ADV adviser / custody rows | Offerings / statement lines by current CIK | 13F filings | Incoming `ISSUED_BY` / `IS_SUBFUND_OF` targets |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| All Company | 10,905 | 5,113,685 | 96,393 | 167,640 | 13,622 | 5,199 | 3,022 / 2,541 | 492 / 17,410 | 146 | 42,383 / 12,937 |
| SEC filer/issuer | 6,414 | 5,113,685 | 96,393 | 167,640 | 13,622 | 5,199 | 0 / 54 | 492 / 17,410 | 146 | 42,383 / 0 |
| GLEIF legal entity | 3,258 | 3,771,437 | 68,816 | 119,680 | 9,334 | 3,378 | 0 / 54 | 138 / 5,218 | 121 | 42,383 / 0 |
| ADV adviser | 2,337 | 0 | 0 | 0 | 0 | 0 | 3,022 / 0 | 0 / 0 | 0 | 0 / 0 |
| Assigned ADV custodian | 224 | 59,489 | 851 | 1,480 | 13 | 6 | 0 / 2,541 | 0 / 0 | 0 | 897 / 0 |
| N-PORT registrant / Company `fund` profile | 1,947 | 0 | 0 | 0 | 0 | 0 | 0 / 0 | 0 / 0 | 0 | 0 / 12,937 |
| Mapped non-US Company | 1,462 | 269,277 | 5,704 | 9,920 | 1,480 | 588 | 0 / 10 | 178 / 5,020 | 22 | 2,030 / 0 |
| 13F filer | 8 | 189,158 | 2,461 | 4,280 | 24 | 6 | 0 / 0 | 1 / 96 | 146 | 28 / 0 |

### Current Company-ID downstream coverage (2026-11-08 16:31–16:38 ET)

The following aggregates match current Silver pointer IDs against assigned
Company IDs from each source role. Cohorts overlap, so rows are not additive.
The all-Company row covers all 10,905 current Company IDs found across the
five Company source feeds. It counts linked rows only; null pointers are
handled separately above. Registration rows are attributed by current CIK,
not by their stored MDM pointers, because their pointer generation is
unidentified. The mapped non-US cohort uses the pinned SEC place mapping and
the approved GLEIF jurisdiction rule. Cohorts overlap and counts are not
additive.

| Current source role | Assigned Company IDs | Facts | Line items | Measures | Insider positions | Owner issuer rows | ADV adviser / custody | 13F filings | Offerings / statement lines by current CIK* | Incoming `ISSUED_BY` / `IS_SUBFUND_OF` target rows |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| All current Company identities | 10,905 | 5,113,685 | 96,393 | 167,640 | 13,622 | 5,199 | 3,022 / 2,541 | 146 | 492 / 17,410 | 42,383 / 12,937 |
| SEC Company | 6,414 | 5,113,685 | 96,393 | 167,640 | 13,622 | 5,199 | 0 / 54 | 146 | 492 / 17,410 | 42,383 / 0 |
| GLEIF legal entity | 3,258 | 3,771,437 | 68,816 | 119,680 | 9,334 | 3,378 | 0 / 54 | 121 | 138 / 5,218 | 42,383 / 0 |
| ADV adviser | 2,337 | 0 | 0 | 0 | 0 | 0 | 3,022 / 0 | 0 | 0 / 0 | 0 / 0 |
| Assigned ADV custodian | 224 | 59,489 | 851 | 1,480 | 13 | 6 | 0 / 2,541 | 0 | 0 / 0 | 897 / 0 |
| N-PORT registrant / fund Company | 1,947 | 0 | 0 | 0 | 0 | 0 | 0 / 0 | 0 | 1 / 96 | 0 / 12,937 |
| Mapped non-US Company | 1,462 | 269,277 | 5,704 | 9,920 | 1,480 | 588 | 0 / 10 | 22 | 178 / 5,020 | 2,030 / 0 |
| 13F filer | 8 | 189,158 | 2,461 | 4,280 | 24 | 6 | 0 / 0 | 146 | 1 / 96 | 28 / 0 |

\* Registration cohort counts match the current CIK column, not stored pointer IDs.

These totals reproduce most of the 14:30 matrix and refresh the all-Company
linked-row totals to 15:40 Silver counts. The table shows overlapping targets;
for example, current `ISSUED_BY` rows target identities present in both SEC and
GLEIF source cohorts. It does not establish that each target is the correct
legal issuer or that all relationship times are authoritative.

The SEC filer, GLEIF, and 13F counts reflect overlapping identity groups; the
same rows can be reached through more than one cohort. The assigned ADV
custodian cohort excludes 263 name-only source records that have no configured
holder and are correctly unassigned. Nested source-field counts by feed are
listed above; Company role-specific master survivorship, all row-level
cohorts, and full per-entity correctness remain open. This is
population-level impact evidence, not an assertion that every Company field
has been checked for every record.

| Family | Configured representation and observed population | Downstream evidence | Audit status |
|---|---|---|---|
| Companies | Separate `company` kind; SEC Company, GLEIF Level 1, IAPD ADV, N-PORT registrant, and 13F filer inputs. Refreshed legacy MDM: 10,905; governed count unavailable. 3,258 have a nonempty GLEIF jurisdiction; 1,462 are in the mapped non-US Company cohort, including 601 with a non-US GLEIF jurisdiction. SEC Company classification has 69,816 distinct blocking hold-back records, 68,301 without a probable kind (earlier source snapshot). | Role-specific downstream counts are in the 14:30 ET cohort matrix. Company facts, line items, measures, insider links, ADV custody, registration links, and 13F filing links are represented. Of 3,716 GLEIF Level 1 assertions, 458 are unassigned and all 458 are in open `binding_required` review. 13F has 146 rows linked to a current CIK identity and 22 rows across two CIKs with no Company master, source assertion, or open review. | Partial. Full entity-level role field coverage and all row-to-current-governed identity checks remain open; resolve the two 13F filer keys, GLEIF binding reviews, and 134 accepted SEC/GLEIF place disagreements using source/effective-time history. |
| Company roles and overlapping cohorts | The 14:30 ET matrix measures SEC filer/issuer (6,414), GLEIF legal entity (3,258), ADV adviser (2,337), assigned ADV custodian (224), N-PORT registrant/Company `fund` profile (1,947), mapped non-US Company (1,462), and 13F filer (8). These overlap and do not sum. Company CIK (8,361), CRD (2,337), LEI (3,359), and BD-number (106) values are each unique across masters. | Current ADV custody has 3,022 rows: all adviser pointers are present; all 3,017 declared pairs exactly match Silver's unique pairs. The five row-count difference is permitted duplicate fact grain; four absent assertion keys are explained by invalid-LEI deferrals. No populated pointer is mismatched. | Partial. Full field presence by Company role and exhaustive per-Company tracing remain open. |
| N-PORT funds | `fund_structure` is the series-level master; Company can separately hold profile `fund`. Legacy fund structures: 12,937; N-PORT registrants and Company `fund` profiles match at 1,947. | All 12,937 `IS_SUBFUND_OF` endpoint pairs match the 15:43 ET Silver snapshot, with file-date-provisional starts. At 15:31 ET, Silver `nport_holding` remained zero. Across two active runs, one had verified preparation through issuer reduction and awaited landing; the other remained waiting in the holding path and record. | Partial. Holding link quality and completed publication cannot be measured until active runs finish; verify the producer and governed MDM generation. Keep file-date starts provisional. |
| Private equity and ADV private funds | Current MDM catalog has eight kinds; no PE kind. `fund` is a profile available on Company and `fund_structure`; N-PORT fund records create `fund_structure` masters keyed by SEC series ID. Current `iapd.adv` mastering rules cover adviser filing and custodian records, not private-fund records. The pinned relationship catalog defines `INVESTMENT_ADVISER_TO` for an adviser-profile entity to a fund-profile entity, but active source rules do not emit it. Older/parallel ADV schema/docs retain private-fund detail and firm-roster PE indicators (`fund_type`, `any_pe_funds`, `pe_fund_count`); legacy docs name the relationship `MANAGES_FUND`, so that historical terminology needs reconciliation before reuse. Thirty-four deferred GLEIF records have probable kind `fund_structure`, but the available classification does not identify them as private equity. | Earlier Silver snapshot had 3,022 `adv_custody` rows, zero `nport_holding` rows, and no `adv_private_fund` table. The refreshed ADV custodian assertions do not represent private funds. Historical `sec_adv_private_fund` schema is not evidence that the active configured pipeline populated or masters PE funds. | No current PE cohort or denominator can be audited. Reconcile intended source, capture, Bookkeeping path, and consumer before defining PE quality checks. Do not infer PE from a `private_offering` filing, an unclassified GLEIF fund, or a fund name, and do not convert absence of a configured PE population into a record-level failure. |
| International companies/entities | Refreshed legacy Company: 1,405 with SEC place mapped `FOREIGN`/`CANADIAN`; 57 more with no SEC place but mapped non-US GLEIF jurisdiction; 1,462 total. Of 3,258 nonempty GLEIF jurisdictions, 601 map non-US and overlap the SEC-place cohort. Legacy `international_organization` has zero masters; governed count unavailable. | The 16:31–16:38 ET current Company-ID matrix counts 269,277 facts, 5,704 line items, 9,920 measures, 1,480 insider positions, 588 owner issuer rows, 10 custody rows, 22 13F filings, 178 offerings and 5,020 statement lines by current CIK, and 2,030 `ISSUED_BY` targets. The 134 field disagreements are all accepted and use the expected source winner per field, but effective-time and match-route history is unavailable. | Partial. Role-specific master survivorship and all entity traces remain open. Do not classify the 134 candidates or enable a consistency check until comparable time and identity evidence exists. |
| People | Separate `person` kind; legacy MDM: 31,125; current governed count unavailable. Sources are SEC submissions and beneficial-ownership reporting-owner assertions. | `insider_reporting_owner` has 5,743 rows; 4,339 distinct nonnull Person links resolve to legacy Person, 781 rows have no Person link. | Partial. Conditional owner type and full entity-to-downstream trace remain open; null count is not itself a defect. |
| Securities | Separate `security` kind; refreshed legacy MDM: 394,305; governed count unavailable. Sources include 13F (5,758 assertions/5,746 linked masters), N-PORT Security and OpenFIGI. | The configured 13F Silver path has 283,725 holdings: 283,715 `security_mdm_id` values match the exact current CUSIP identity. Ten rows with one absent CUSIP are covered by the existing `invalid_cusip_checksum` deferral; no populated pointer is mismatched. The 15:43 ET N-PORT comparison found 42,383 matching current `ISSUED_BY` pairs and two resolved source-only candidates awaiting landing; N-PORT holdings remained zero at 15:31 ET. At 15:36 ET, 617,684 of 1,392,524 listing records had valid, mapped MICs; all configured-null groups are allowed. | Partial. Holding quality and the two 13F manager Company identities remain open; prove current governed identity. Missing MIC is allowed for configured lookup cases; do not treat it as a defect without new evidence. |
| Branch | Configured as an MDM kind; zero legacy masters and no governed rows available. | No Silver downstream references to a branch master were observed. | No populated denominator. Determine source and relationship path if a branch feed is onboarded; do not create zero-failure checks. |
| Government | Configured as an MDM kind; zero legacy masters and no governed rows available. SEC classification has 32 records with probable government kind in an earlier classification snapshot, but these are held source records, not mastered Government entities. | No Silver downstream references to a Government master were observed. | No populated master denominator. Resolve candidate classification and source onboarding before entity checks; do not treat candidates as confirmed records or defects. |
| International organization | Configured as an MDM kind; zero legacy masters and no governed rows available. This kind is distinct from non-US Companies, which remain Company records. | No Silver downstream references to an international-organization master were observed. | No populated denominator. Identify its authoritative source and relationship path before defining checks. |
| Venue | Configured as an MDM kind; zero legacy masters and no governed rows available. Current OpenFIGI Security listing MIC is a reference lookup field, not a populated Venue master. | Listings use the pinned MIC reference/crosswalk; no populated Venue master pointers were observed. Missing MIC is allowed for the configured composite/unpaired cases. | No populated master denominator. Do not misstate listing MICs as Venue entities or require MIC presence where the source contract allows null. |

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
| Company, including international Company records | SEC name presence, registered-agent/placeholder-address handling, pinned SEC place-code validity; GLEIF name and address checks; ADV adviser/custodian name checks; N-PORT registrant provisional registration-start flag. ADV Silver `related_person_is_y_or_n` ran on 3,022 rows with zero failures. | Reconcile SEC incorporation place with GLEIF jurisdiction for the 134-record candidate cohort after source/effective-time tracing. Use a cross-source consistency check only after the cause is resolved; the observed field-presence counts are not completeness targets. |
| N-PORT fund structure | Series ID and LEI format/cardinality rules; `subfund_start_is_authoritative` flags when the start is provisional. | The 70 masters without LEI all have a series ID and no source LEI claim; this is allowed by the configured rule. Do not make LEI mandatory. Holdings remain unavailable in the observed snapshot. |
| Private equity and ADV private funds | No PE kind or PE-specific quality contract in the current MDM/source rules. Current MDM has N-PORT `fund_structure` records and `fund` profiles; retained ADV schemas describe private-fund detail and PE roster indicators but do not connect those records to the active `iapd.adv` MDM/Silver path. | Do not infer PE from `private_offering` or fund names. Reconcile the intended source, capture, Bookkeeping path, and consumer; only then define a supported PE cohort and check denominator. The current snapshot cannot support a PE record-quality check. |
| Person | SEC submissions and ownership owner name-presence and letter-pattern checks; CIK identifier contract. | All 781 Silver rows without a Person link exactly match source classification holds; 32 have a Company link and 749 have neither. Both hold reasons are configured as nonblocking. Do not flag unresolved rows; if later classified, validate the corresponding Person/Company link. |
| Security | N-PORT issuer-placeholder and filed share-class checks; 13F share-class check; CUSIP/ISIN identifier checks. | Effective legacy master identities have zero repeated CUSIP, FIGI or ISIN values; repeated raw N-PORT ISIN claims are withheld under the CUSIP-first rule. The active Form 4 path has no issuer relationship rule; current matching finds six edges to a different Company and 1,531 absent edges for assigned assertions with a mastered issuer CIK, but missing filing-period effective time prevents a defect conclusion. Resolve whether Form 4 is authorized relationship evidence before proposing a typed-edge check. Missing MIC is explicitly allowed for composite and unpaired listings, so no completeness check is appropriate. |
| Branch, government, international organization, and venue | No populated master family in the legacy snapshot; no downstream quality denominator. | Do not emit zero-failure checks over empty populations. Resolve held government candidates and identify each kind's source onboarding before designing its checks; Venue is separately covered by listing MIC evidence above. |

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
identities need source-coverage tracing, and N-PORT holding checks need a
completed, verified landing. Private-equity and the four
currently empty entity kinds have no active populated denominator, so they
cannot yet yield record-level checks.

| Finding or predicate | DataKitchen TestGen category | Existing platform support | Decision |
|---|---|---|---|
| N-PORT fund LEI checksum invalid (14/25,874 source assertions) | Validity; a regex is not a checksum check. | Existing Dataset Contract identifier validation checks the checksum and records a blocking deferral. | Already detected; do not duplicate it in `quality.yaml`. Keep the source records held for the normal data-quality disposition. |
| N-PORT Security CUSIP checksum invalid (2,428/428,262 source assertions) | Validity; a regex is not a checksum check. | Existing Dataset Contract identifier validation checks the checksum and records a nonblocking deferral. | Already detected; do not duplicate it in `quality.yaml`. Preserve the configured nonblocking disposition. |
| N-PORT Security CUSIP invalid (1/428,262 source assertions) | Validity | Existing Dataset Contract identifier validation records a nonblocking deferral. | Already detected; do not duplicate it in `quality.yaml`. Preserve the configured nonblocking disposition. |
| 13F Security CUSIP checksum invalid (1/5,758 source assertions) | Validity; a regex is not a checksum check. | Existing Dataset Contract identifier validation checks the checksum and records a typed deferral. | Already detected; do not duplicate it in `quality.yaml`. Resolve through the source's configured deferral path. |
| Security effective identifier cardinality and source-claim disposition | Uniqueness and consistency | Identifier claims are constrained by the merge contract; field-only Silver checks cannot see accepted versus withheld claims. | No effective-master duplicate was observed for CUSIP, FIGI, or ISIN. Keep CUSIP-keyed conflicting ISIN claims withheld; do not flag raw repeats as defects. |
| Silver MDM pointers resolve to the correct current entity | Referential integrity | No current field-only check can join Silver to the authoritative MDM resolver. | Candidate for a generic cross-store Silver check; requires current governed MDM data and a planted bad-pointer proof. |
| Company facts, line items, and measures meet the profiled Company-key link coverage | Referential integrity and completeness | Their profile records `inclusion: 1.0`; current key coverage is 320/329 for facts and 309/311 for line items and measures. The nine fact keys include one Company identity bound only through N-PORT and eight without a current CIK identity; the two line/measure keys have no current CIK identity. | Measured difference from the profile baseline, not a confirmed failure of an enforced SLA. Confirm intended source scope and link-target policy before converting it into a failing check. Candidate for a generic cross-store/source-coverage measure; do not silently widen the SEC `source_code` contract or flag nulls until expected coverage is agreed. |
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
