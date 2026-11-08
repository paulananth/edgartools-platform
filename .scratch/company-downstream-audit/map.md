# Mastered entity and downstream data audit

**Status: IN PROGRESS.** Audit every populated MDM kind through its configured
source fields, relationships, and downstream fields, then turn only
evidence-backed defects into repeatable data-quality checks. Scope includes
Companies, international entities, N-PORT fund structures, private-equity
representation, people, securities, and any other populated entity kind. This
covers MDM and Silver; Gold is out of scope.

## Work

- [01 — Trace mastered entity fields and relationships, then define data-quality checks](issues/01-company-field-and-relationship-quality-checks.md)

Use the existing AAPL trace as the control case. Follow the same configured
source, master, relationship, and downstream paths for the full Company
population. Check definitions must follow this repository's data-quality
engine and may use DataKitchen TestGen as a reference for check categories;
TestGen is not a runtime dependency.

The configured MDM catalog has eight kinds. The refreshed legacy MDM snapshot
has four populated kinds: Company (10,905), fund structure (12,937), person
(31,125), and security (394,305). Branch, government, international
organization, and venue have no legacy master rows in this snapshot. A
fund profile is also permitted on Company, so fund coverage must include both
Company fund profiles and fund-structure masters. `private_equity` is not a
configured MDM kind. The active IAPD ADV MDM rules master adviser filings and
custodians, not private-fund records. Retained/parallel ADV schema and docs
describe private-fund detail and PE roster indicators, but the current local
Silver snapshot has no private-fund table; therefore no PE cohort or record
quality denominator is available in the active path. Do not infer PE from a
private-offering form or fund name. Non-US companies remain in the Company kind,
whose configured jurisdiction field is sourced from GLEIF; report that subgroup
separately from the configured `international_organization` kind.

For this audit, “Company type” means a configured role, source, profile, or
measured cohort attached to the Company kind; these overlap and must not be
summed as distinct Companies. The trace therefore covers SEC filers/issuers,
GLEIF legal entities, ADV advisers, ADV custodians, N-PORT registrants,
Company records with the `fund` profile, and mapped non-US Companies. N-PORT
`fund_structure` is a separate kind. ADV private funds/PE have no active
representation or denominator in the observed path. The other configured MDM
kinds are Person, Security, branch, government, international organization,
and venue; each is accounted for separately in the coverage matrix below.

The refreshed local legacy source assertion store contains 1,254,565 assertion
rows across 13 feeds. It now includes 494 ADV custodian assertions and 5,758
13F Security assertions, which were absent from the earlier snapshot. Field
and identifier presence by feed is in the issue ledger. The latest read found
449,281 legacy master rows (449,272 canonical masters and nine aliases). A
16:02 ET read found zero rows in each governed MDM entity, current-record, and
relationship table. This blocks current governed-kind, generation, and
relationship verification in this local snapshot.
Earlier protocol-7 resolver counts recorded in the issue ledger therefore
cannot be reproduced on this connection and remain prior, unverified
observations. Do not treat them as current defects until the populated governed
snapshot is identified.

The 2026-11-08 14:15 ET source-key comparison checked all 16 configured Silver
links against the exact current legacy source bindings. Non-registration
links match the current binding when one exists; registration pointers
diverge from the current legacy CIK identities and require producer-generation
identification. The 14:30 ET Company cohort matrix covers SEC filers/issuers,
GLEIF entities, ADV advisers/custodians, N-PORT registrants/fund profiles,
mapped non-US Companies, and 13F filers; it includes 1,462 mapped non-US
Companies and the 1,947 Company `fund` profiles. Its Silver attribution is
historical, however: current Silver row counts were refreshed at 15:40 ET, so
the role-specific row counts must be recomputed before they are reported as
current. Company fields have not been stratified by role. Private equity has no
active representation or denominator, and branch, government, international
organization, and venue have no populated legacy master denominator.

At 16:06 ET, the full Company master population was re-aggregated by populated
field without emitting any field values: 10,905 names, 10,724 addresses, 6,414
SIC fields, 6,217 fiscal year ends, 5,787 incorporation states, and 3,258
jurisdictions. Each core GLEIF status/legal-form/LOU/validation/registration field is
present on 3,258 Company masters; entity-creation date is
present on 2,693 and registration-authority entity ID on 3,141. This establishes
population-wide field presence only; source-role requiredness and per-Company
field correctness remain open.

At 16:09 ET, mapped source fields were also checked by Company role without
printing records or raw values. The 6,414 SEC Company assertions each contain
name, address, description, fiscal year end, SIC, and incorporation state. All
3,716 GLEIF assertions contain name, address, jurisdiction, status/legal-form/
LOU/validation/registration fields, and creation date. Name/address appear in
all 2,938 ADV adviser and all 494 ADV custodian assertions; the 5,841 N-PORT
registrant assertions also all have name/address. These are source input
counts, not survivor field completeness or downstream quality. Current Company
binding counts are SEC 6,414, GLEIF 3,258 assigned/458 unbound, ADV adviser
2,337, ADV custodian 224 assigned/263 name-only unbound, and N-PORT
registrant/fund 1,947.

At 16:12 ET, current role IDs were compared with the current Company fact and
line-item tables. SEC-bound Company IDs reach 5,113,685 facts and 96,393 line
items; GLEIF-bound IDs reach 3,771,437 facts and 68,816 line items. ADV adviser
and N-PORT registrant IDs reach none of these tables. Current table totals are
5,134,979 facts and 96,807 line items, so 21,294 facts and 414 line items are
outside the SEC-bound cohort. The 14:30 “All Company” figures match the SEC
cohort rather than current table totals. Treat this as an unresolved
attribution discrepancy until the residual pointers and identity generation
are traced; do not yet label it a bad link.

Dependent checks were refreshed after population growth. At 15:36 ET all
617,684 present MICs remained valid against the pinned reference and exchange
mapping; permitted null-MIC groups were unchanged. At 15:40 ET the current
Company Silver row checks had zero failures (3,113,260 eligible fact periods,
46,971 eligible line-item periods, and all 168,360 measure windows valid).
At 15:43 ET, 42,383 of 42,385 resolved N-PORT issuer pairs exactly matched
Silver; two source-only pairs await pending load stages, and there are no
Silver-only pairs. At 15:43 ET, all 12,937 N-PORT subfund pairs matched Silver
with observed file-date starts. At 15:46 ET, each ownership edge type's 4,139
mastered Person/issuer pairs exactly matched `insider_reporting_owner`; 280
pairs per type lack both assigned endpoints. Governed relationship comparison
remains unavailable because its tables are empty.

The permitted 16:01 ET Bookkeeping refresh found 29 active runs: ten
`sec.registration` to Silver, four `sec.company-facts` to Silver, three
OpenFIGI to mastering, two N-PORT Security runs, and ten ownership security
symbol runs. N-PORT Silver holdings remain at zero. Both N-PORT runs still
await holding landing; one is waiting in holding/holding_rows/record and the
other has pending reduction. No run was changed.

Relationship reconciliation remains partial. Silver has 55,320 rows: 42,383
`ISSUED_BY` and 12,937 `IS_SUBFUND_OF`. The latter use the approved
file-date-provisional start (`valid_from_basis=observed`); the unknown true
inception remains flagged. At 15:43 ET, 245,130 `ISSUED_BY` declarations
reduced to 225,221 distinct Security/issuer-source pairs; 42,385 pairs resolve
to both current endpoints, 42,383 match Silver, two are source-only pending
the active `links`/landing/merge stages, and none are Silver-only. Unresolved
endpoint declarations are not counted as missing published edges. The prior
1,218 source-only count used a broader, earlier endpoint population and is
superseded for the resolved-pair comparison. All 12,937 `IS_SUBFUND_OF` pairs
match Silver exactly. The current governed relationship projection is empty.

The refreshed 13F flow is configured end to end and loaded: the security run
completed with 44/44 work items verified and the filing run with 3/3 verified
at 12:44 ET. Silver has 168 filing rows and 283,725 holdings; all holdings join
to one of 52 filing accessions. Current CIK-to-Company matching resolves 146
filing rows; 22 rows across two CIKs have no current Company master, source
assertion, or open review. Current CUSIP-to-Security matching resolves 283,715
holdings; 10 rows share one CUSIP with no master or source assertion, and that
key matches the existing nonblocking `invalid_cusip_checksum` deferral. No
populated pointer is wrong-kind or mismatched to its filed key. Only the two
manager CIKs remain unexplained source-coverage candidates. The run summary did
not expose the count for the configured one-letter share-class quality check.

The N-PORT `IS_SUBFUND_OF` endpoint set also matches exactly: all 12,937
distinct source pairs resolve from a `fund_structure` with the `fund` profile
to a `company` with the `fund` profile, and all 12,937 appear in Silver with
zero source-only or Silver-only pairs. Every Silver start is present and uses
`valid_from_basis=observed`; the source does not provide an authoritative
inception date, so the configured file-date fallback remains provisional.

Ownership link endpoints reach their designated Silver consumer. The
`BENEFICIAL_OWNER_OF` and `EMPLOYED_BY` source sets each reduce to the same
4,139 distinct mastered Person/issuer Company pairs, exactly matching the
nonnull Person/issuer endpoints in `insider_reporting_owner` with no pair-set
difference. That Silver table does not preserve relationship type/capacity as
a separate edge, so the typed link and period semantics still need a populated
governed MDM snapshot. For GLEIF `SUCCESSOR_ENTITY`, none of 48 declarations
has a legacy source Company master; all 48 source subjects are held in open
`binding_required` review, while 26 targets resolve to a Company. This is
unresolved source identity, not a missing published edge. Across all 3,716
GLEIF Level 1 assertions, 458 are unassigned and all 458 are in open
`binding_required` review; the full review set has 1,891 subjects, 1,433
closed and 458 open. A separate 39 GLEIF deferred records have
`unsupported_identity_kind`: 34 probable `fund_structure`, three `government`,
and two without a probable kind. Do not infer private-equity status from the
probable `fund_structure` label. Keep these held/deferred inputs outside
mastered Company denominators. For ADV `CUSTODIAN`,
all 3,017 declarations have a mastered adviser. The earlier assertion snapshot
showed no custodian records; a refreshed read now finds 494 custodian
assertions: 106 have BD numbers and 114 have LEIs, all assigned; 274 are
name-only, of which 11 bind to one exact-name holder and 263 correctly wait
because none of the configured holder sources has their name. The assigned
assertions resolve to 224 distinct legacy masters. Four invalid-LEI rows are
already set aside by identifier validation. All 3,022 current Silver
custody rows have adviser IDs. Of these, 2,541 custodian IDs match the exact
source key and current master; 475 rows point to the 263 waiting keys, and six
rows across four keys have no retained source assertion. No populated pointer
is mismatched. All six rows across four keys match the four configured
nonblocking `invalid_lei_checksum` deferrals. The 3,017 declaration pairs
exactly match the 3,017 unique Silver pairs, with no source-only or Silver-only
pair. Silver has five additional rows because five filing/custodian pairs each
contain two distinct custody facts, which the declared row grain permits. The
configured `related_person_is_y_or_n` check ran on all 3,022 rows with zero
failures, flags, or refusals. This closes the ADV custody pair and row-grain
comparison; the complete per-Company field trace remains open.

At 2026-11-08 16:01 ET, the 29 active Bookkeeping runs remain: 10
`sec.registration` to Silver, three `openfigi` to mastering, four
`sec.company-facts` to Silver, two `sec.nport.security`, and ten
`sec.ownership` to security symbols. The N-PORT Silver holding count remains
zero. Both N-PORT runs still await holding landing; one is waiting in
holding/holding_rows/record and the other has pending reduction. One still has
links pending, with merge work pending/waiting. No run was changed. Respect the
30-minute inspection interval before the next status refresh.

Other legacy source assertions declare 48 `SUCCESSOR_ENTITY`, 3,017
`CUSTODIAN`, 4,962 `BENEFICIAL_OWNER_OF`, and 14,886 `EMPLOYED_BY`
relationships. The Silver relationship table contains only `ISSUED_BY` and
`IS_SUBFUND_OF`; ownership issuer/Person pairs land in `insider_reporting_owner`
instead.

The 12,937 N-PORT fund structures all have their SEC series identifier. Of the
70 without a master LEI, every retained source assertion also lacks an LEI
claim; the configured series-ID rule allows identity without one. This is not
a missing-LEI defect and should not become a mandatory-field check.

For insider reporting owners, all 781 Silver rows without a Person link match
781 distinct classification holds by the exact filing-owner key: 331 deferred
and 450 undetermined. Thirty-two of those rows have a Company link; the other
749 have neither owner link. The joins agree exactly, so these are unresolved
classification cases rather than broken pointers; the valid terminal handling
is configured: both classification reasons are nonblocking, and Bookkeeping
lands the owner rows after merge. Keep these rows out of link-failure checks
while classification remains unresolved; once classified, require the matching
Person or Company link.

The full legacy identifier scan found one ticker value held by four Security
masters, above the configured forward claim of three. Both retained Form 4
security assertions carrying that value are open `conflicting_identifiers`
reviews, matching the configured `on_several: review` behavior; no bad automatic
bind was observed. Those four Securities declare three `ISSUED_BY` links to two
GLEIF subjects that are absent from the retained GLEIF source-record index, and
none has a Silver issuer edge. This points to unresolved target-source coverage;
the absent targets and Silver edges are not yet confirmed record defects.

A source-assertion scan found 370 repeated ISIN values across OpenFIGI and
N-PORT Security claims. The effective legacy `mastering_master` projection has
zero repeated CUSIP, FIGI, or ISIN values across Security masters. N-PORT has
394 CUSIP-keyed withheld ISIN occurrences over 371 source subjects (370
distinct values); 154 of those values also occur as accepted claims on another
master. That is consistent with the configured CUSIP-first keep-separate
behavior. The effective master set also has three repeated SEDOL values and
one repeated LoanX value, each on two masters and within the configured
five-master forward claim. Ticker has 366 reused values; one reaches four
masters against a forward claim of three and remains held for review. The raw
ISIN collisions are not effective-master duplicates and are not confirmed
defects. A future uniqueness/cardinality check should measure effective
identifiers and verify raw conflicting claims remain withheld under the
configured source/key-class policy.

The refreshed legacy Company identifier scan on 2026-11-08 13:25 ET found no
duplicate identities: 106 BD-number, 8,361 CIK, 2,337 CRD, and 3,359 LEI
values each map to one Company master, and no Company master holds multiple
values in these reverse-one namespaces.
Person CIK values are unique across 31,125 Person masters; 4,311 CIKs appear in
both SEC submissions and ownership-owner assertions and resolve to the same
master, with no Person holding multiple CIKs. Fund-structure series IDs
(12,937) and LEIs (12,867) each map to one fund master, and no fund master
holds multiple values in those namespaces. These are legacy assignment checks;
they cannot stand in for the empty governed MDM projection.

For international Company records, the SEC–GLEIF `sec-gleif-name-jurisdiction`
binding rule is currently active. Its configured proof is 300/300 correct
(95% one-sided lower bound 0.991062) with zero violations in 257 adversarial
cases. A read-only full legacy Company comparison reproduced 134 disagreements
among 3,073 records under the complete configured place-comparison semantics.
All 134 are accepted Company masters; each SEC state-of-incorporation and GLEIF
jurisdiction field is won by its expected source, and both source assertions
are retained, with no field conflict entries. No current `mastering_decision`
rows explain the match route. SEC effective time is null for all 3,258 matched
pairs while GLEIF effective time is populated; the SEC source contract says its
incorporation effective time is unknown. This confirms a field disagreement,
not a defect: comparable time, match route, and processing rule version are
unavailable. The proof validates matching behavior on its measured cohort; it
does not attest every current field pair.

The active Form 4 Security reader is ticker-only: v2 reads accession, issuer
CIK, and symbol, but not filing period; all 5,273 v2 assertions have null
effective time. Of these, 4,447 resolve to one current ticker holder, 725 have
no current holder and remain unassigned, and 101 remain in conflict review
because multiple current Securities share the ticker. No assigned result
points outside the exact current ticker-holder set. A bounded MDM-to-Silver
comparison of those 4,447 assigned assertions found 4,359 issuer CIKs with a
Company identity: 2,822 current `ISSUED_BY` edges target it, six target a
different Company, and 1,531 have no current edge. The remaining 88 CIKs have
no CIK holder. These are assertion counts, not distinct Securities. Since the
reader does not retain filing period and all v2 effective times are null, the
six differing targets and 1,531 absent edges are temporal/source-coverage
candidates, not confirmed defects. The 88 missing Company identities also
need source-coverage review. Establish whether filing period supplies a valid
effective time and whether this source is authorized to state `ISSUED_BY`.

The SEC Company classification queue contains 69,816 distinct blocking source
records. The configured rules give 1,515 a probable kind (599 Company, 658
Person, 226 fund structure, 32 government); 68,301 have no probable kind,
including 67,166 at the final no-match step. The queue is a broad classification
coverage gap to investigate, but those holds are not record defects without
business review.

Three row-local checks on Company Silver also pass on the full stored snapshot:
period ordering on 5,134,979 facts and 96,807 line items, empty-value/reason
consistency on 96,807 line items and 168,360 measures, and the allowed measure
window on all 168,360 measures. Each predicate has zero failing rows. The four
filing-consistency checks on Company facts remain unmeasured because they apply
within each delivery; a combined-table comparison would change their meaning.

The full legacy listing scan found 1,392,524 listing rows. All 617,684 present
MICs are valid in pinned `iso-10383-mic` version 1 and match the configured
OpenFIGI exchange mapping; there are no missing MICs for mapped exchanges. Of
the 774,840 rows without MIC, 414,643 have a composite FIGI and an exchange not
in the current mapping, 42,639 have an unmapped exchange and no composite FIGI,
and 317,558 have neither exchange nor composite venue detail. Only the first
group has a composite FIGI, and the other exchange rows are unpaired by the
configured mapping. The source explicitly leaves MIC null for composite or
unpaired listings; rows without exchange/composite evidence likewise provide
no MIC input. Missing MIC is therefore allowed in these groups, not a quality
failure. Adding an exchange-to-MIC mapping would require approved authoritative
reference data; the audit does not infer one from observed values.
