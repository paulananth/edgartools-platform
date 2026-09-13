# GLEIF Open-Data Augmentation Research

Date: 2026-09-11
Scope: official GLEIF open data, bulk files, API, identifier mappings, legal
entity relationships, and their potential use in the EdgarTools AWS data path.

## Executive conclusion

GLEIF is a valuable **additive** source for legal-entity identity, lifecycle,
and accounting-consolidation relationships. It can add a globally standardized
LEI; official, previous, trading, and transliterated names; legal and
headquarters addresses; legal jurisdiction and form; entity and LEI statuses;
registration-authority provenance; corporate events and successors; direct and
ultimate accounting parents; branches; fund structures; and crosswalks to
selected identifiers. GLEIF publishes the underlying LEI data free of charge
under CC0, and provides both bulk and query access
([open-data policy](https://www.gleif.org/en/about/open-data),
[LEI Data Terms of Use](https://www.gleif.org/en/meta/lei-data-terms-of-use/)).

GLEIF should **not** replace SEC CIK as the key of the EdgarTools company
dimension, and an LEI should not be inferred from a name alone. No official
SEC-CIK-to-LEI mapping was identified in the reviewed GLEIF mapping catalog.
GLEIF's `registeredAs` value is local-registration-authority-specific, not a
global business identifier and not generally a CIK. For example, GLEIF's Apple
Inc. record uses California registry identifier `806592`, whereas Apple's SEC
CIK is `320193`
([live API result](https://api.gleif.org/api/v1/lei-records?filter%5Bentity.legalName%5D=Apple%20Inc.&page%5Bsize%5D=5)).

The recommended first step is therefore a small, offline, read-only proof of
value. It should use a fixed GLEIF snapshot, generate evidence-bearing match
candidates for a stratified SEC-company sample, and measure precision,
coverage, enrichment yield, parent-relationship coverage, exceptions, and
freshness. No production schema or pipeline change should precede that proof.

This memo separates confirmed GLEIF/repository facts from proposed integration
inferences. It is research only; no implementation or deployment was performed.

## Confirmed data availability

### Data products

| Product | Confirmed content | Cadence and format | Best prospective use |
| --- | --- | --- | --- |
| Level 1 LEI-CDF 3.1 | LEI and legal-entity identity, names, addresses, registration authority and identifier, jurisdiction, category, legal form, status, dates, successors, events, and LEI-registration metadata | Golden Copy in XML, JSON, and CSV, three times daily | Reproducible entity enrichment and LEI source references |
| Level 2 RR-CDF 2.1 | Directional direct/ultimate accounting consolidation, international branch, fund manager, sub-fund, and feeder relationships, plus relationship periods, state, registration state, and validation evidence | Golden Copy in XML, JSON, and CSV, three times daily | Corporate and fund relationship evidence |
| Level 2 reporting exceptions 2.1 | Explicit reasons a direct or ultimate parent is not published | Golden Copy in XML, JSON, and CSV, three times daily | Preserve negative/unknown evidence instead of interpreting missing edges |
| Concatenated files | Unmodified daily files from LEI issuers for Level 1, relationships, and exceptions | XML, daily | Source-faithful audit/reconciliation, not the easiest operational feed |
| Golden Copy delta files | New or revised records relative to an 8-hour, 24-hour, 7-day, or 31-day baseline | XML, JSON, and CSV with each Golden Copy publication | Incremental refresh after a full snapshot |
| GLEIF API | Search/filter/fuzzy matching, LEI records, parent and child links, issuers, code lists, and mapped identifiers | JSON:API over HTTPS | Bounded discovery, adjudication, and proof-of-value lookups |
| Identifier mapping files | BIC, ISIN, MIC, S&P CIQ Company ID, OpenCorporates ID, QCC code, and GEM Entity ID mappings are listed in the current catalog | Mapping-specific, from daily to monthly | Connect issuers, instruments, financial institutions, venues, registry data, Chinese entities, and energy assets |
| Code lists and quality products | Registration authorities, ISO 20275 entity legal forms, accepted jurisdictions, rules, reports, challenges, and policy-conformity data | Versioned lists and periodic reports | Interpretation, validation, and quality gates |

GLEIF distinguishes the once-daily Concatenated Files from its curated Golden
Copy database. The latter removes technical duplicate LEIs, retains complete
records across issuer-transfer glitches, adds normalized/geocoded addresses,
and is published at 02:00, 10:00, and 18:00 UTC. GLEIF also publishes four
delta windows with each Golden Copy release
([Golden Copy specification overview](https://www.gleif.org/en/lei-data/gleif-golden-copy)).
That makes Golden Copy the better candidate for an EdgarTools ingestion source,
while Concatenated Files remain useful for source-level reconciliation.

On 2026-09-11 the official Concatenated download page listed 3,428,431 Level 1
records, 668,828 relationship records, and 6,185,301 reporting exceptions
([current download inventory](https://www.gleif.org/en/lei-data/gleif-concatenated-file/download-the-concatenated-file)).
The counts are not directly comparable: a subject may have multiple
relationships and two exception categories, and the Level 1 population includes
historical/end-state records. They demonstrate scale and the need to ingest all
three products, not a relationship-coverage percentage.

### Level 1: legal-entity identity and lifecycle

The current LEI-CDF 3.1 model provides:

- a 20-character LEI;
- a primary legal name, alternative names, previous legal names, trading or
  operating names, languages, and transliterations;
- legal, headquarters, alternate-language, and transliterated addresses;
- the registration authority code and the entity's identifier at that
  authority;
- legal jurisdiction as an ISO 3166 country or subdivision code;
- entity category, including `GENERAL`, `FUND`, `BRANCH`, `SOLE_PROPRIETOR`,
  resident-government entity, and international organization;
- an ISO 20275 entity legal-form code, or an exceptional textual form;
- entity status, creation date, expiration information, and zero or more
  successor entities;
- event groups with event type, effective/recorded dates, validation document
  type/reference, status, sequencing, and affected fields; and
- LEI registration status, initial/last-update/next-renewal dates, managing
  issuer, validation authority, and validation/corroboration level.

The complete field definitions and cardinalities are in the
[LEI-CDF 3.1 specification](https://www.gleif.org/en/lei-data/access-and-use-lei-data/level-1-data-lei-cdf-3-1-format).
The model explicitly supports previous and trading/operating names
([LEI-CDF 3.1 release documentation](https://www.gleif.org/content/4_lei-data/1_access-and-use-lei-data/2_level-1-data-lei-cdf-3-1-format/lei-cdf_version_3.1-documentation.html)).

Entity status and LEI registration status must remain separate. An entity can
be `ACTIVE` while its LEI registration is `LAPSED`; conversely, duplicate,
annulled, retired, transferred, and pending-transfer registrations carry
different operational meanings. GLEIF's current format documents all status
values and renewal metadata
([LEI-CDF 3.1 registration fields](https://www.gleif.org/en/lei-data/access-and-use-lei-data/level-1-data-lei-cdf-3-1-format#registration)).

### Level 2: relationships are narrower than general ownership

GLEIF's parent relationships mean **direct accounting consolidating parent** and
**ultimate accounting consolidating parent**. They are not generic equity
ownership, beneficial ownership, control, or SEC filer-affiliation assertions.
The RR-CDF also represents international branches and three fund-specific
relationship types:

- `IS_FUND-MANAGED_BY`;
- `IS_SUBFUND_OF`; and
- `IS_FEEDER_TO`.

Each relationship can carry periods, active/inactive state, accounting-standard
qualifiers, record-registration status, validation level, document type, and a
validation reference
([RR-CDF 2.1 specification](https://www.gleif.org/en/lei-data/access-and-use-lei-data/level-2-data-relationship-record-rr-cdf-2-1-format)).

Absence of a published parent edge is not evidence of no parent. The Reporting
Exceptions file distinguishes `NO_LEI`, natural-person control,
non-consolidating structures, no known controlling person, and non-public
information, separately for direct and ultimate parent reporting. GLEIF notes
that an entity need not disclose non-public parent information to obtain or
renew an LEI
([Reporting Exceptions 2.1](https://www.gleif.org/en/lei-data/access-and-use-lei-data/level-2-data-reporting-exceptions-2-1-format)).

The Q2 2026 GLEIF report makes the practical limitation concrete: 99% of the LEI
population had submitted direct and ultimate parent reporting, but only 4%
reported a direct parent with an LEI and 4% a direct parent without an LEI;
89% reported no direct parent under the accounting-consolidation definition and
3% reported non-public information. Ultimate-parent proportions were similar.
The same report says 42.6% of direct-parent relationships and 41.7% of
ultimate-parent relationships were entity-supplied only
([Q2 2026 business report](https://www.gleif.org/lei-data/global-lei-index/download-global-lei-system-business-reports/download-global-lei-system-business-report-q2-2026/q2-2026-quarterly_business_report.pdf)).
Therefore Level 2 is high-value evidence where present, not a complete corporate
hierarchy.

### Identifier mappings and other augmentation paths

GLEIF's reviewed mapping catalog currently lists:

- BIC-to-LEI, published monthly;
- ISIN-to-LEI, published daily for participating national numbering agencies;
- MIC-to-LEI, published monthly;
- S&P CIQ Company ID-to-LEI, updated weekly in LEI Search/API;
- OpenCorporates ID-to-LEI, published biweekly;
- QCC Code-to-LEI, published monthly; and
- GEM Entity ID-to-LEI, published monthly.

The current list and update history are on the
[GLEIF mapping page](https://www.gleif.org/en/lei-data/lei-mapping). GLEIF's
certification checks the mapping partner's methodology, but a mapping's scope is
still product-specific. The ISIN feed currently includes newly issued ISINs from
participating numbering agencies, with legacy expansion described as future
work
([ISIN-to-LEI page](https://www.gleif.org/en/lei-data/lei-mapping/download-isin-to-lei-relationship-files)).
The OpenCorporates file covers more than half of the global LEI population and
is not expected to cover entities such as some funds that are not registered as
companies
([OpenCorporates-to-LEI page](https://www.gleif.org/en/lei-data/lei-mapping/download-oc-to-lei-relationship-files)).

No official CIK mapping was identified in this catalog. This is a bounded
finding from the sources reviewed, not proof that no CIK mapping exists
anywhere. Mapping-file terms can also differ from the general CC0 LEI-data
terms; for example, GLEIF publishes a separate license agreement for the BIC
mapping. Each selected mapping must receive its own license and coverage review
before ingestion
([BIC-to-LEI page](https://www.gleif.org/en/lei-data/lei-mapping/download-bic-to-lei-relationship-files)).

### Quality and provenance

GLEIF standardizes a record's link to a local authoritative source using a
Registration Authority code and authority-specific entity identifier. Its
Registration Authorities List contains more than 1,050 registers and validation
sources across 232 jurisdictions
([Registration Authorities List](https://www.gleif.org/en/lei-data/code-lists/gleif-registration-authorities-list)).

GLEIF applies duplicate and governance pre-checks, XSD validation, daily data
quality checks, monthly reports, and a public challenge mechanism. Its published
rules test formatting, plausibility, business rules, relationship integrity,
timeliness, lifecycle, and other quality dimensions
([quality framework](https://www.gleif.org/en/lei-data/gleif-data-quality-management),
[data-quality checks](https://www.gleif.org/en/lei-data/gleif-data-quality-management/data-quality-checks)).
In Q2 2026, 87.9% of Level 1 records were fully corroborated, while the overall
LEI renewal rate was 57.1%
([Q2 2026 business report](https://www.gleif.org/lei-data/global-lei-index/download-global-lei-system-business-reports/download-global-lei-system-business-report-q2-2026/q2-2026-quarterly_business_report.pdf)).

The Policy Conformity Flag indicates timely renewal plus complete parent
reporting or an accepted exception. GLEIF explicitly says this flag is **not** a
data-quality indicator; it complements the technical quality program
([Policy Conformity Flag](https://www.gleif.org/en/lei-data/access-and-use-lei-data/policy-conformity-flag)).
An EdgarTools consumer should keep entity status, LEI registration status,
renewal dates, corroboration level, relationship validation, conformity, and
source publication time as distinct quality signals.

## Access, licensing, and operational characteristics

### Bulk access

Golden Copy is the preferred candidate for a production-scale source because it
is de-duplicated, complete across issuer-file glitches, enriched, and provides
deltas. The full and delta files are available in XML, JSON, and CSV
([download page](https://www.gleif.org/en/lei-data/gleif-golden-copy/download-the-golden-copy)).

For a canonical ingest, XML offers XSD validation and JSON preserves repeating
fields and GLEIF extensions while being easier to parse. CSV should not be the
canonical format: GLEIF's current data dictionary says repeating fields are
limited to five entries in CSV, and CSV omits extension information such as
geocoding and the Conformity Flag
([GLEIF Data Dictionary](https://www.gleif.org/en/lei-data/access-and-use-lei-data/gleif-data-dictionary)).

### API access

The production API supports filters, full-text and field searches, fuzzy
matching of names and addresses, Level 2 traversal, code lists, issuers, and
mapped identifiers. It is based on Golden Copy
([API overview](https://www.gleif.org/en/lei-data/gleif-api),
[API documentation](https://api.gleif.org/docs/)). The official documentation
currently sets a limit of 60 requests per minute per user. On 2026-09-11,
bounded calls succeeded without a credential, and a one-record query reported a
Golden Copy publish time of `2026-09-11T08:00:00Z` and 3,428,023 total records
([live API inventory](https://api.gleif.org/api/v1/lei-records?page%5Bsize%5D=1)).

The API is appropriate for the offline proof, interactive investigation, and
small adjudication batches. It is not the right transport for repeatedly
scanning the full population; bulk full-plus-delta files avoid rate pressure and
make snapshot replay easier.

### Terms and reliability

GLEIF provides its LEI access service free of charge and the LEI/LE-RD data
under CC0. The terms reserve GLEIF's right to suspend or modify the service,
provide it without an uninterrupted-service guarantee, and state that the data
is supplied as-is from third-party applications and information. They also
prohibit implying that a downstream product is endorsed by GLEIF
([LEI Data Terms of Use](https://www.gleif.org/en/meta/lei-data-terms-of-use/)).

An implementation would therefore need immutable capture metadata, retries,
checksums, replayable snapshots, source attribution, and a clear non-endorsement
statement. The CC0 status of core LEI data must not be projected onto mapping
partner data or linked external datasets without reviewing their terms.

## Fit with the current EdgarTools model

### Confirmed repository seams

The existing MDM architecture already has useful generic seams:

- `mdm_source_ref` binds any `(source_system, source_id)` pair to an entity with
  priority, confidence, and match time
  ([schema](../../edgar_warehouse/mdm/migrations/001_initial_schema.sql#L38-L45),
  [ORM](../../edgar_warehouse/mdm/database.py#L210-L230)).
- `mdm_entity_attribute_stage`, source-priority rules, and field-survivorship
  rules support source-ranked candidate attributes
  ([schema](../../edgar_warehouse/mdm/migrations/001_initial_schema.sql#L126-L155),
  [attribute stage](../../edgar_warehouse/mdm/migrations/001_initial_schema.sql#L180-L192)).
- Generic temporal relationship types, properties, source mappings, and
  relationship instances can preserve source-specific evidence rather than
  flattening it
  ([relationship schema](../../edgar_warehouse/mdm/migrations/001_initial_schema.sql#L230-L289)).
- The current `mdm_company` golden record is CIK-centered. It has canonical
  name, incorporation state, and a single parent pointer, but no LEI, legal and
  headquarters addresses, legal jurisdiction/form, entity status, LEI status,
  or GLEIF provenance fields
  ([company schema](../../edgar_warehouse/mdm/migrations/001_initial_schema.sql#L52-L67)).
- The company resolver matches exact CIK first and fuzzy name second. It also
  logs that the SEC source currently has no parent-CIK column
  ([resolver](../../edgar_warehouse/mdm/resolvers/company.py#L1-L63),
  [parent behavior](../../edgar_warehouse/mdm/resolvers/company.py#L230-L258)).
- `GOLD.COMPANY` remains keyed by CIK and adds MDM entity ID, display name,
  tracking status, and the existing parent pointer
  ([dbt model](../../infra/snowflake/dbt/edgartools_gold/models/gold/company.sql#L1-L48)).
- The MDM already models advisers, securities with `isin`, and funds with
  adviser and jurisdiction fields, creating possible non-company integration
  surfaces
  ([domain tables](../../edgar_warehouse/mdm/migrations/001_initial_schema.sql#L70-L120)).

### Proposed integration inferences

The following are recommendations, not current behavior:

1. **Keep CIK authoritative for the SEC company dimension.** Register an LEI as
   a separate `mdm_source_ref`, not as a replacement key.
2. **Make matching evidence-bearing and fail closed.** Prefer an already-known
   LEI or a verified authority-specific registry crosswalk. Never treat
   `registeredAs` as CIK unless both its Registration Authority and identifier
   semantics prove that it is a CIK. Use exact normalized name plus jurisdiction
   and address as candidate evidence; fuzzy name alone should go to review.
3. **Preserve GLEIF's source grain.** Store the publication timestamp, file
   family/version, LEI issuer, registration authority, authority identifier,
   registration and entity statuses, renewal dates, validation level,
   conformity flag, and match method/confidence.
4. **Do not flatten Level 2 into `parent_company_entity_id`.** Model direct and
   ultimate accounting-consolidation edges separately and retain relationship
   status, periods, qualifiers, validation, and exception records. A single
   parent column loses both semantics and explicit missingness.
5. **Treat lifecycle records as history.** Successors, legal-entity events,
   status changes, and retired/duplicate LEIs should be temporal evidence, not
   destructive overwrites.
6. **Use category-specific entity routing.** `GENERAL` entities may enrich
   companies; `FUND` records and fund relationships may augment funds and
   advisers; `BRANCH` is a relationship-aware organizational unit. Do not force
   every LEI record into `mdm_company`.
7. **Use ISIN-to-LEI as issuer evidence, not instrument identity.** An ISIN maps
   a security to its issuer's LEI. This can connect `mdm_security.isin` to an
   issuing entity but does not mean the LEI identifies the security itself.

## Ranked opportunities

| Rank | Opportunity | Expected value | Main gate |
| --- | --- | --- | --- |
| 1 | LEI cross-reference plus legal name/name history, jurisdiction, legal form, addresses, status, and source provenance | High-value Company 360 enrichment and stronger entity review | Demonstrate high-precision SEC-to-LEI linkage; no fuzzy-only auto-merge |
| 2 | Direct and ultimate accounting-parent relationships plus explicit exceptions | Fills a known SEC-source gap and improves global group context | Keep semantics separate; measure low edge coverage and validation levels |
| 3 | ISIN-to-LEI issuer linkage | Connects existing MDM ISINs to issuer entities and group context | Mapping coverage is limited to participating NNAs/new issuance |
| 4 | Fund-manager, umbrella/sub-fund, and feeder/master relationships | Augments MDM funds/advisers with standardized global structure | Category routing, relationship validation, and SEC fund-identifier matching |
| 5 | Entity lifecycle events and successor graph | Supports mergers, name/legal-form changes, liquidation, and durable identity history | Temporal model and idempotent replay |
| 6 | BIC, MIC, OpenCorporates, S&P CIQ, QCC, and GEM crosswalks | Adds bridges to institutions, venues, registry data, commercial IDs, China coverage, and energy assets | Per-map licensing, coverage, data availability, and need justification |
| 7 | Golden Copy geocoding and normalized addresses | Location reconciliation and matching evidence | Preserve raw issuer address; validate geocode accuracy and data minimization |

## Small offline proof of value

Run this as a read-only analysis outside production MDM and without changing
canonical data:

1. Freeze a source manifest containing retrieval time, API/Golden Copy publish
   time, CDF versions, URLs, hashes, and record counts.
2. Select a stratified sample of 200 SEC companies: large and small issuers,
   financial and non-financial firms, active and inactive filers, common-name
   collisions, recent name changes, and several known parent/subsidiary cases.
3. Query the API within its 60-request/minute limit, or filter one downloaded
   JSON/XML Golden Copy snapshot. Generate candidates from legal/other names,
   jurisdiction, legal/HQ addresses, registration authority/ID, BIC/S&P IDs,
   and relationship context. Do not write matches into MDM.
4. Manually adjudicate all proposed matches for the sample. Label deterministic,
   high-confidence multi-attribute, ambiguous, and no-match outcomes; record the
   exact evidence for each decision.
5. For accepted matches, extract Level 1 enrichment, direct/ultimate parents,
   relationship exceptions, successors/events, mapped identifiers, status,
   renewal/corroboration/conformity, and the snapshot timestamp.
6. Separately test a small set of known `mdm_security.isin` values and MDM fund
   or adviser entities. Do not mix their coverage results with company results.
7. Produce a replayable result bundle and compare a second snapshot to prove
   idempotent matching and well-defined update/retirement behavior.

Minimum report metrics:

- SEC-to-LEI candidate rate, accepted-match rate, ambiguity rate, and no-match
  rate with the full sample as denominator;
- precision from manual adjudication, including common-name false positives;
- match counts by evidence tier and by LEI registration/corroboration status;
- field-by-field enrichment yield for accepted matches;
- direct-parent, ultimate-parent, exception, and no-record rates as distinct
  measures;
- percentage of accepted records that are `ISSUED`, `LAPSED`, conforming,
  fully corroborated, or stale by last update/next renewal;
- ISIN-to-issuer and fund/adviser relationship coverage on their own
  denominators; and
- replay parity between snapshots, including changed, successor, duplicate,
  retired, and disappeared candidate behavior.

Suggested proof acceptance bar: no false positive among automatically accepted
matches; every accepted match has at least two independent evidence dimensions
unless it uses a deterministic verified identifier; every relationship and
exception preserves source metadata; and a second run is idempotent. Coverage
should be reported, not used to relax precision.

## Risks and decisions required before implementation

- **Coverage bias:** LEIs identify entities that obtained an LEI, commonly due
  to financial-market or regulatory needs; they do not enumerate all SEC
  registrants, subsidiaries, or legal entities. Q2 2026 had over 3.1 million
  active LEIs globally, not a universal business register
  ([Q2 2026 report](https://www.gleif.org/lei-data/global-lei-index/download-global-lei-system-business-reports/download-global-lei-system-business-report-q2-2026/q2-2026-quarterly_business_report.pdf)).
- **Parent semantics and sparsity:** accounting consolidation is narrower than
  legal, beneficial, or economic ownership, and published parent LEIs are a
  small subset of the population.
- **Staleness:** `LAPSED` is not the same as inactive. Renewal, last-update,
  corroboration, entity status, and events must be evaluated together.
- **Identifier collision:** authority-specific `registeredAs` values cannot be
  compared across authorities or treated as CIK without proof.
- **Many-to-many and history:** entities can have multiple former names,
  successors, events, securities, and relationship versions. CSV and flattened
  golden-record columns can silently lose this structure.
- **Schema evolution:** GLEIF publishes CDF versions, XSDs, examples, and API
  change documentation. Consumers should tolerate additive JSON fields and pin
  the accepted schema/version
  ([supporting documents](https://www.gleif.org/en/lei-data/access-and-use-lei-data/supporting-documents)).
- **License boundary:** core LEI data is CC0, but mapping files and downstream
  partner datasets require separate review.
- **Service dependency:** API availability is not guaranteed; production-scale
  ingestion should use captured bulk snapshots and deltas with checksums and
  retries.

Before implementation, decide which domain is the tracer bullet (company
identity is recommended), whether the initial product is analyst-facing
enrichment or resolver evidence, the acceptable auto-match evidence tiers, the
snapshot retention policy, and whether relationship exceptions are published to
gold or remain an MDM evidence surface.

## Source boundary

All external factual sources reviewed for this memo are official GLEIF web
pages, API responses, API documentation, schemas, or reports retrieved on
2026-09-11. References to EdgarTools behavior are links to the repository state
on branch `codex/gleif-open-data-research`. Proposed architecture and proof
steps are explicitly labeled as recommendations and have not been implemented.
