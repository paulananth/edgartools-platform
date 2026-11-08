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

The configured MDM catalog has eight kinds. The observed populated legacy MDM
snapshot has four: Company (10,698), fund structure (12,937), person (31,125),
and security (393,683). Branch, government, international organization, and
venue are configured but had no legacy master rows in that observation. A
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

The local legacy source assertion store contains 1,248,313 assertion rows across
11 feeds; field and identifier presence by feed is in the issue ledger. A
fresh read of the designated shared server found 448,443 legacy masters, but
the governed MDM projection tables contain no rows and have no RLS policies.
Earlier protocol-7 resolver counts recorded in the issue ledger therefore
cannot be reproduced on this connection and remain prior, unverified
observations. Do not treat them as current defects until the populated governed
snapshot is identified.

Relationship reconciliation is still open. Silver has 55,320 rows: 42,383
`ISSUED_BY` and 12,937 `IS_SUBFUND_OF`. The latter use the configured
file-date-provisional start (`valid_from_basis=observed`); the unknown true
inception remains flagged. Legacy N-PORT source assertions declare 245,130
`ISSUED_BY` relationships, which reduce to 225,221 distinct Security/issuer
subjects. Endpoint matching found 42,383 pairs in both source and Silver, 1,218
source-only pairs, and no Silver-only pairs. Of the source-only pairs, 1,214
lack an assigned GLEIF master, one lacks both masters, one lacks a Security
master, and two have both endpoint masters but no Silver edge. Each of the two
are possible omissions, but the `links` stage is still pending in one current
N-PORT run. Their Silver relationship snapshot last loaded 2026-11-06 23:29 ET.

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
unresolved source identity, not a missing published edge. For ADV `CUSTODIAN`,
all 3,017 declarations have a mastered adviser but the
custodian source feed has no retained legacy assertions or masters; all 3,022
Silver custody rows have null custodian MDM IDs. These are source/target
coverage limits, not confirmed broken relationships. Five extra custody rows
cannot be classified without reconciling filing/row grain.

At 2026-11-08 12:00 ET, both N-PORT security Bookkeeping runs still showed
`running`, with zero `nport_holding` rows. The older run had `land_holding`
pending, `merge` waiting, and `processed` pending. The later run had
`land_holding`, `links`, `merge`, and `issuer_reduce` pending, with its holding
steps waiting. Do not resume, cancel, or otherwise alter these runs as part of
this read-only audit.

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

The assigned legacy identifier scan found no duplicate Company identities:
8,361 CIK, 2,337 CRD, and 3,258 LEI values each map to one Company master, and
no Company master holds multiple values in these reverse-one namespaces.
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
are retained. This confirms the disagreement is present in both source-backed
fields, but not that it is a defect: SEC and GLEIF fields remain separately
owned, and identity history, effective times, and the producing rule version
still need tracing. The proof validates matching behavior on its measured
cohort; it does not attest every current field pair.

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
group is a composite/no-MIC candidate; the remaining groups still need source
and business classification before a quality failure can be assigned.
