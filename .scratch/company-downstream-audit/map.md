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
inception remains flagged. Legacy source assertions also declare 48
`SUCCESSOR_ENTITY`, 3,017 `CUSTODIAN`, 4,962 `BENEFICIAL_OWNER_OF`, and 14,886
`EMPLOYED_BY` relationships. The Silver relationship table contains only
`ISSUED_BY` and `IS_SUBFUND_OF`; the ADV custody fact table has 3,022 rows,
five more than the declared CUSTODIAN relationships. These are coverage
candidates: trace accepted endpoints, deferred reasons, grain, and intended
consumer before classifying missing edges. Two N-PORT security Bookkeeping
runs remain `running`, with holding land pending in both and links pending in
the later run. Do not refresh, delete, recreate, resume, or cancel data as part
of this read-only audit.

The full legacy identifier scan found one ticker value held by four Security
masters, above the configured forward claim of three. Both retained Form 4
security assertions carrying that value are open `conflicting_identifiers`
reviews, matching the configured `on_several: review` behavior; no bad automatic
bind was observed. Those four Securities declare three `ISSUED_BY` links to two
GLEIF subjects that are absent from the retained GLEIF source-record index, and
none has a Silver issuer edge. This points to unresolved target-source coverage;
the absent targets and Silver edges are not yet confirmed record defects.

The full legacy listing scan found 1,392,524 listing rows. All 617,684 present
MICs are valid in pinned `iso-10383-mic` version 1 and match the configured
OpenFIGI exchange mapping; there are no missing MICs for mapped exchanges. Of
the 774,840 rows without MIC, 414,643 have a composite FIGI and an exchange not
in the current mapping, 42,639 have an unmapped exchange and no composite FIGI,
and 317,558 have neither exchange nor composite venue detail. Only the first
group is a composite/no-MIC candidate; the remaining groups still need source
and business classification before a quality failure can be assigned.
