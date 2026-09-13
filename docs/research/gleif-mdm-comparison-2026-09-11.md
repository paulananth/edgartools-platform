# GLEIF-to-MDM Comparison Approach

Date: 2026-09-11
Status: exploratory comparison completed; no production data, schema, or workflow was changed
Scope: compare the current EdgarTools company MDM with a fixed GLEIF Golden
Copy snapshot and define a safe augmentation path.

## Objective and decision

Measure whether GLEIF adds enough correctly linked identity, lifecycle, and
accounting-parent information to justify an AWS ingestion tracer bullet. The
comparison must answer four questions separately:

1. What fraction of current CIK-keyed MDM companies can be linked to exactly
   one LEI with auditable evidence?
2. Which GLEIF attributes are new, equal, or in conflict with current MDM and
   SEC silver data?
3. How often does GLEIF add a direct or ultimate accounting-consolidation
   parent, or an explicit reporting exception?
4. Can the same frozen inputs be replayed with identical candidates,
   adjudications, and accepted links?

CIK remains authoritative for the SEC company dimension. LEI is an additional
identifier and provenance source; it does not replace CIK. The proof is
read-only and may not write accepted matches into production MDM.

The live exploratory pass supports proceeding to a frozen-snapshot proof, but
not to production linking. Of 200 deterministically sampled MDM companies, 25
produced a provisional multi-attribute or exact-name review candidate, and only
8 met the pass's strongest automated evidence class. None were manually
accepted. The API changed Golden Copy publication during the run, proving that
a formal comparison must use captured bulk files rather than a moving API
snapshot.

## Confirmed source models

### EdgarTools MDM and SEC evidence

The current `mdm_company` record contains:

| Current field | Meaning in this comparison |
| --- | --- |
| `entity_id` | Durable MDM entity under evaluation |
| `cik` | Authoritative SEC company identifier and cohort key |
| `canonical_name` | Current MDM name; candidate-generation input, never sufficient alone |
| `ein` | SEC tax identifier; not a GLEIF identifier |
| `sic_code`, `sic_description` | SEC industry context; useful for adjudication, not deterministic linking |
| `state_of_incorporation` | Candidate jurisdiction evidence when comparable with GLEIF subdivision codes |
| `fiscal_year_end` | Context only |
| `ticker`, `primary_ticker`, `primary_exchange` | Context and collision adjudication; not core GLEIF Level 1 fields |
| `tracking_status` | Cohort stratification and SEC activity context |
| `parent_company_entity_id` | Existing generic parent pointer; its semantics must not be treated as direct or ultimate GLEIF accounting parent |
| `valid_from`, `valid_to` | Current golden-record validity |

These fields are defined by the
[`mdm_company` schema](../../edgar_warehouse/mdm/migrations/001_initial_schema.sql)
and ORM
([`MdmCompany`](../../edgar_warehouse/mdm/database.py)). The resolver matches
CIK exactly before its existing fuzzy-name fallback and notes that the SEC
company source has no parent-CIK field today
([`CompanyResolver`](../../edgar_warehouse/mdm/resolvers/company.py)).

Use the following existing evidence without changing its authority:

- `mdm_source_ref`: `(entity_id, source_system, source_id)`, priority,
  confidence, match time, and source-content hash;
- `mdm_entity_attribute_stage`: source-grained attribute candidates and
  selection state;
- `mdm_match_review`: pair, score, evidence, disposition, and reviewer;
- SEC silver `sec_company`, `sec_company_address`, and
  `sec_company_former_name`: current SEC identity, address, and name-history
  evidence;
- `sec_subsidiary_evidence`: filing-derived subsidiary name, jurisdiction,
  scope, date, and source location; and
- `mdm_relationship_instance`: typed temporal edges with source evidence,
  quarantine state, and per-run identity.

The existing run binding is defined in
[`019_mdm_run_identity.sql`](../../edgar_warehouse/mdm/migrations/019_mdm_run_identity.sql),
and the relationship temporal contract is defined in
[`006_relationship_temporal_contract.sql`](../../edgar_warehouse/mdm/migrations/006_relationship_temporal_contract.sql).

### Exact GLEIF comparison fields

Use Level 1 Golden Copy JSON or XML as the canonical comparison input. CSV is
not canonical because repeating fields and extensions can be truncated or
omitted. Field paths below use the GLEIF API JSON representation, which is
based on Golden Copy
([API documentation](https://api.gleif.org/docs/),
[Golden Copy downloads](https://www.gleif.org/en/lei-data/gleif-golden-copy/download-the-golden-copy)).

| GLEIF path | Compare with / proposed use |
| --- | --- |
| `attributes.lei` | Proposed `gleif_lei` source reference; validate 20-character format |
| `attributes.entity.legalName.{name,language}` | `mdm_company.canonical_name`; preserve raw and normalized forms |
| `attributes.entity.otherNames[]` | SEC former names and candidate aliases; preserve name type/language |
| `attributes.entity.transliteratedOtherNames[]` | Candidate evidence only; never sole auto-link evidence |
| `attributes.entity.legalAddress.*` | SEC business/mailing addresses where comparable; store independently |
| `attributes.entity.headquartersAddress.*` | SEC address evidence; do not silently collapse with legal address |
| `attributes.entity.registeredAt.{id,other}` | Registration Authority identity and provenance |
| `attributes.entity.registeredAs` | Authority-local registration identifier; never assume it is a CIK |
| `attributes.entity.jurisdiction` | SEC state/country of incorporation after explicit ISO mapping |
| `attributes.entity.category`, `subCategory` | Route `GENERAL`, `FUND`, and `BRANCH` records to appropriate domains |
| `attributes.entity.legalForm.{id,other}` | New ISO 20275 legal-form enrichment |
| `attributes.entity.associatedEntity.*` | Branch/fund context; retain source semantics |
| `attributes.entity.status` | New legal-entity lifecycle status; distinct from LEI status |
| `attributes.entity.creationDate` | New lifecycle evidence |
| `attributes.entity.expiration.{date,reason}` | New lifecycle evidence; not an SEC inactivity flag |
| `attributes.entity.successorEntity`, `successorEntities[]` | Temporal successor evidence; do not overwrite entity identity |
| `attributes.entity.eventGroups[]` | Typed legal-entity event history with affected fields and dates |
| `attributes.registration.initialRegistrationDate` | LEI-registration provenance |
| `attributes.registration.lastUpdateDate`, `nextRenewalDate` | Freshness and lapse assessment |
| `attributes.registration.status` | LEI status such as `ISSUED` or `LAPSED`; distinct from entity status |
| `attributes.registration.managingLou` | LEI issuer provenance |
| `attributes.registration.corroborationLevel` | Quality/evidence stratification |
| `attributes.registration.validatedAt`, `validatedAs` | Validation authority and local identifier |
| `attributes.conformityFlag` | Policy-conformity signal; not a general data-quality score |
| `attributes.bic`, `mic`, `ocid`, `qcc`, `gem`, `spglobal` | Optional mapped identifiers with separate coverage/license review |

The complete Level 1 semantics are specified in
[LEI-CDF 3.1](https://www.gleif.org/en/lei-data/access-and-use-lei-data/level-1-data-lei-cdf-3-1-format).

For Level 2, compare and preserve these fields at source grain:

| GLEIF relationship field | Required treatment |
| --- | --- |
| relationship-record `id` | Source record identity |
| `validFrom`, `validTo` | Source record validity, separate from relationship periods |
| `relationship.startNode.{id,type}` | Child/reporting entity identifier |
| `relationship.endNode.{id,type}` | Parent/related identifier; may be an LEI or another permitted node type |
| `relationship.type` | Keep `IS_DIRECTLY_CONSOLIDATED_BY` distinct from `IS_ULTIMATELY_CONSOLIDATED_BY`; also retain branch and fund relationship types |
| `relationship.status` | Active/inactive source relationship state |
| `relationship.periods[]` | Preserve each period and its type; do not reduce accounting and relationship periods to one date |
| `registration.*` | Publication status, dates, managing LOU, corroboration level/documents/reference |
| `extension.deletedAt` | Retirement/deletion evidence |

The source semantics are defined by
[RR-CDF 2.1](https://www.gleif.org/en/lei-data/access-and-use-lei-data/level-2-data-relationship-record-rr-cdf-2-1-format).
Direct and ultimate accounting parents are not generic legal, equity,
beneficial-ownership, or control parents.

Ingest Level 2 reporting exceptions as entity-level evidence even when no
parent edge exists. Keep direct-parent and ultimate-parent exception categories
separate, including `NO_LEI`, natural-person control, non-consolidating
structures, no known controlling person, and non-public information. Missing
relationship data, a reported exception, and an affirmative no-parent meaning
must never be collapsed
([Reporting Exceptions 2.1](https://www.gleif.org/en/lei-data/access-and-use-lei-data/level-2-data-reporting-exceptions-2-1-format)).

## Frozen comparison cohort

### Exploratory cohort executed on 2026-09-11

The read-only exploratory pass queried
`EDGARTOOLS_PROD.EDGARTOOLS_GOLD.MDM_COMPANY_ENTITY` and joined addresses from
`EDGARTOOLS_PROD.EDGARTOOLS_SILVER.SEC_COMPANY_ADDRESS`. At the query boundary,
the published MDM export contained 68,949 current rows (`valid_to IS NULL`), all
with CIK and canonical name. It contained 7,284 rows with a primary ticker,
37,057 with state of incorporation, and zero populated
`parent_company_entity_id` values. Every CIK joined to at least one SEC address,
although only 39,969 had a populated business city and 39,136 had a populated
business ZIP code.

Name collision is a material matching risk in the current population. A
case-insensitive, whitespace-trimmed grouping produced 68,718 distinct names,
223 duplicated-name groups covering 454 MDM rows, and 796 names of five or
fewer characters.

The exploratory cohort assigned each current MDM row to the first matching
stratum below, ordered each stratum by Snowflake `HASH(cik)`, and selected 50
rows per stratum:

| Executed stratum | Rule | Rows |
| --- | --- | ---: |
| `tickered` | non-empty primary ticker | 50 |
| `financial_unlisted` | no ticker and numeric SIC from 6000 through 6999 | 50 |
| `addressed_unlisted` | remaining rows with incorporation state and business city | 50 |
| `sparse` | all remaining current rows | 50 |

For each row, the pass requested up to ten GLEIF candidates with the official
API legal-name filter. It compared punctuation-normalized names and then tested
GLEIF legal/headquarters city and postal code against SEC business/mailing
addresses, plus GLEIF legal jurisdiction against available MDM/SEC state
values. The provisional classes were:

- `high_confidence_candidate`: exactly one of the returned candidates had an
  exact normalized name plus at least one jurisdiction, city, or ZIP match;
- `fuzzy_with_corroboration_review`: name similarity at least 0.90 plus at
  least one jurisdiction, city, or ZIP match;
- exact-name-only or multiple-exact-name results: review/ambiguity only;
- weak result: the API returned candidates without sufficient evidence; and
- no candidate.

These are generator outcomes, not identity adjudications. The page-size limit
means “exactly one” only describes the first ten returned candidates, not every
result for a broad query. For example, `Mercantile Bank` had 49 API results and
`Legacy` had 1,282. No class from this exploratory pass is eligible for an MDM
write or an accepted-link precision claim.

The pass issued 200 bounded API requests at 1.1-second spacing and received no
request errors. It completed by `2026-09-12T00:10:50Z`.

Representative outcomes show why the evidence tiers matter:

| MDM company | GLEIF result | Generator outcome | Lesson |
| --- | --- | --- | --- |
| `Hrt Financial Lp` | `HRT FINANCIAL LP` | exact name plus jurisdiction, city, and ZIP | Strong review candidate; still not accepted without adjudication |
| `Knights Of Columbus Asset Advisors` | `KNIGHTS OF COLUMBUS ASSET ADVISORS LLC` | 0.9444 name similarity plus jurisdiction, city, and ZIP | Legal-suffix normalization can improve recall when address evidence is retained |
| `Mercantile Bank` | exact-name/address candidate among 49 API results | provisional high-confidence within the first page | A broad result set cannot be declared unique without exhausting or narrowing candidates |
| `Legacy` | exact-name candidate among 1,282 API results, without address/jurisdiction agreement | ambiguous exact name | Exact name alone is unsafe |

### Primary company cohort

Freeze a reproducible 200-company cohort from one read-only MDM snapshot. Use
CIK and `entity_id` as the immutable cohort keys. Select strata before examining
GLEIF results:

| Stratum | Target | Selection purpose |
| --- | ---: | --- |
| Active, information-rich issuers | 50 | Name, incorporation, ticker, address, and former-name evidence available |
| Active, information-sparse issuers | 40 | Measure performance without strong address/alias evidence |
| Inactive or non-active tracking states | 30 | Test lifecycle and successor behavior |
| Common-name, short-name, or duplicate-normalized-name collisions | 30 | Measure false-positive pressure |
| Companies with former-name evidence | 20 | Test legal-name history and successor distinctions |
| Companies with existing parent/subsidiary evidence | 30 | Compare relationship semantics and coverage |

If a company qualifies for several strata, assign it deterministically to the
first applicable stratum and record all secondary flags. Within each stratum,
order by `sha256(cik || cohort_seed)` and take the target count. Record the seed,
query version, extraction time, row count, and SHA-256 of the canonical JSONL
cohort file.

### Secondary cohorts

Keep separate denominators and result tables for:

- `mdm_security` records with non-null ISIN, to assess ISIN-to-issuer-LEI links;
- `mdm_fund` and `mdm_adviser` records, to assess fund-manager,
  umbrella/sub-fund, and feeder/master opportunities; and
- `BRANCH`-category LEIs, which must not be forced into `mdm_company`.

Secondary results may justify later tickets, but cannot raise the company
cohort's coverage or precision.

## Candidate generation and evidence tiers

Normalize only for comparison; retain all raw values. Pin the normalization
code/version in the run manifest. Generate a bounded candidate set through
exact legal/other/former-name filters first, then optionally GLEIF fuzzy search
for manual-review candidates. Candidate generation is not acceptance.

| Tier | Evidence | Proof disposition | Eventual production disposition |
| --- | --- | --- | --- |
| A: deterministic identifier | Previously adjudicated LEI, or a verified authoritative crosswalk whose identifier semantics and scope are proven | Verify it still resolves to the same entity | Eligible for auto-link only after all go/no-go gates pass |
| B: strong multi-attribute | Exact normalized current/former legal name plus compatible jurisdiction and a materially matching legal/HQ address or verified authority identifier | Manual adjudication required | Review queue; not auto-linked by this proof |
| C: contextual | Exact name with only one supporting context field, or fuzzy/alias name with multiple supporting fields | Manual adjudication required | Review queue |
| D: weak/conflicting | Fuzzy or exact name alone, incompatible jurisdiction/address, multiple plausible entities, or evidence of distinct simultaneous entities | Reject or quarantine | Never auto-link |

No fuzzy-name-only match may auto-merge. No exact-name-only match may
auto-merge. `registeredAs` is deterministic only after `registeredAt` proves
the registry and a reviewed mapping proves that registry identifier's semantics;
it is not globally unique by itself. Ticker, SIC, and fiscal year-end are
corroborating context, not independent authoritative identifiers.

For every candidate, persist in the offline result bundle:

- `comparison_run_id`, MDM snapshot ID, GLEIF snapshot ID, cohort row ID;
- MDM `entity_id`, CIK, LEI, evidence tier, generator version, and rank;
- raw compared fields and normalized comparison values;
- per-field outcome: `equal`, `compatible`, `different`, `missing_mdm`,
  `missing_gleif`, or `not_comparable`;
- candidate score components, not only an aggregate score; and
- disposition, reason code, reviewer, review time, and any second-review result.

## Manual adjudication rules

1. Review every candidate in the proof, including all candidates that would
   qualify for an eventual automatic tier.
2. Accept only when identity evidence establishes the same legal entity, not
   merely the same brand, fund family, branch, parent, or successor.
3. Require two independent evidence dimensions unless Tier A uses a verified
   deterministic identifier. Name variants count as one dimension, and legal
   plus headquarters address count as one address dimension.
4. Reject or quarantine when two active legal entities share a name, when
   jurisdiction or registry evidence identifies a different entity, or when an
   apparent match is only a predecessor/successor or parent/subsidiary.
5. Require a second reviewer for every Tier C candidate, every conflicting
   field that could change identity, and every proposed rejection of an
   existing deterministic link. Disagreement remains `pending`; it is not
   resolved by averaging scores.
6. Use reason codes: `accepted_deterministic`, `accepted_multi_attribute`,
   `ambiguous_collision`, `different_legal_entity`, `parent_or_subsidiary`,
   `predecessor_or_successor`, `insufficient_evidence`, `no_candidate`, and
   `source_conflict`.
7. Preserve rejected pairs so reruns do not repeatedly present the same known
   false positive unless source evidence materially changes.

## Measurements

Use the full frozen cohort as denominator unless a metric explicitly names a
different denominator.

### Identity and enrichment

- candidate rate: cohort rows with at least one candidate / cohort size;
- unique-candidate rate and multi-candidate ambiguity rate;
- accepted-link, rejected, pending, and no-candidate rates;
- manually adjudicated precision by evidence tier;
- false-positive count and reason distribution, especially common-name cases;
- accepted matches by GLEIF entity category, entity status, registration
  status, corroboration level, conformity flag, and staleness band;
- field-level availability in MDM, availability in GLEIF, exact/compatible
  agreement, conflict, and net-new enrichment yield; and
- coverage by MDM stratum so information-rich companies do not hide sparse or
  inactive-company failure.

### Relationships and exceptions

For each accepted company link, independently count:

- published direct accounting parent;
- published ultimate accounting parent;
- direct-parent reporting exception by reason;
- ultimate-parent reporting exception by reason;
- relationship/exception record absent; and
- parent endpoint present but not linked to an accepted MDM entity.

Where current MDM parent/subsidiary evidence exists, label semantic comparison
as `same_accounting_parent`, `different_but_not_conflicting_semantics`,
`conflict`, or `not_comparable`. Never score a direct-parent match as an
ultimate-parent match, and never interpret an exception as an edge.

### Replay and operational quality

- identical-input candidate-set hash and adjudication replay parity;
- duplicate candidate and duplicate accepted-link counts;
- changed, new, retired, successor, and disappeared records across a second
  GLEIF snapshot;
- source file count/hash/schema/version validation;
- records rejected for malformed LEI, invalid node type, invalid interval, or
  unknown enum; and
- API request count/rate errors for proof discovery only; bulk ingestion must
  not depend on scanning the API.

## Live measured results

These results are from the bounded exploratory API pass described above. They
are useful for sizing the opportunity and refining the formal protocol, but
they are not acceptance evidence: the cohort/result bundle was not frozen,
candidates were not manually adjudicated, and the GLEIF publication advanced
during execution.

| Result | Measured value | Evidence artifact |
| --- | --- | --- |
| MDM company population at query boundary | 68,949 current exported rows; 68,949 with CIK/name; 7,284 with primary ticker; 37,057 with incorporation state; 0 with parent pointer | Read-only Snowflake aggregate documented above |
| Cohort size and stratum counts | 200 total; 50 each tickered, financial-unlisted, addressed-unlisted, and sparse | Deterministic `HASH(cik)` cohort documented above |
| Companies with any API result | 62/200 (31.0%); this includes weak and ambiguous results | Exploratory API pass |
| Provisional high-confidence generator result | 8/200 (4.0%): 4 tickered, 2 financial-unlisted, 2 addressed-unlisted, 0 sparse | Exploratory API pass; all remain pending review |
| Fuzzy plus corroboration review result | 14/200 (7.0%): 4 tickered, 5 financial-unlisted, 5 addressed-unlisted, 0 sparse | Exploratory API pass; no auto-link eligibility |
| Exact-name-only or ambiguous exact-name | 3/200 (1.5%): 2 ambiguous exact-name and 1 exact-name-only | Exploratory API pass |
| Weak / no-candidate | 37/200 weak (18.5%); 138/200 no candidate (69.0%) | Exploratory API pass |
| Review-worthy by executed stratum | tickered 10/50 (20%); addressed-unlisted 8/50 (16%); financial-unlisted 7/50 (14%); sparse 0/50 | Sum of provisional high, corroborated fuzzy, and exact-name review classes |
| Accepted / rejected / pending | 0 accepted; 25 provisional review candidates; 37 weak results; 138 no candidate | No manual adjudication was performed |
| Precision and false-positive count | Not measured | Requires manual adjudication of every candidate |
| Enrichment among 8 strongest provisional candidates | legal form 8; HQ address 8; other names 5; BIC 3; direct-child links 2 | Availability only, conditional on identity acceptance |
| Direct / ultimate parent coverage | 0 direct-parent and 0 ultimate-parent links among the 8 strongest provisional candidates | Too small and unadjudicated for a coverage conclusion |
| Direct / ultimate exception coverage | Not measured | API candidate pass did not capture the Reporting Exceptions family |
| Replay parity | Not measured | API responses spanned two Golden Copies |
| Secondary security/fund/adviser results | Not measured | Must retain separate denominators |

The GLEIF API metadata reported publication
`2026-09-11T08:00:00Z` for 195 requests and
`2026-09-11T16:00:00Z` for the final five. This is a concrete failure of the
formal fixed-input requirement, not merely a theoretical concern. The formal
proof must download and hash same-publication Level 1, relationship, and
exception files before candidate generation.

The observed candidate pattern also exposes a normalization seam. MDM's
current name normalizer drops legal-suffix tokens such as `inc`, `llc`, `lp`,
`plc`, `fund`, `group`, and `holdings`. Several plausible GLEIF matches
therefore appeared in the fuzzy-with-corroboration class even when their only
name difference was a legal suffix—for example, `Knights Of Columbus Asset
Advisors` versus `KNIGHTS OF COLUMBUS ASSET ADVISORS LLC`. The formal generator
should retain raw SEC/MDM/GLEIF names, add a versioned suffix-aware comparison
form for recall, and continue to require independent jurisdiction or address
evidence for acceptance.

### Interpretation

- GLEIF is not a universal join for this MDM population. A random current-row
  scan found no candidate for 69%, and the sparse stratum produced no
  review-worthy result.
- Address and jurisdiction evidence materially improve candidate quality. The
  experiment does not support name-only auto-linking.
- Tickered records had the highest review-worthy yield, but only 20% in this
  deterministic sample. Initial product scope should target information-rich
  entities rather than assume population-wide coverage.
- The strongest eight candidates showed consistent legal-form and headquarters
  enrichment, plus some former-name and BIC value. This is promising but
  conditional on manual identity acceptance.
- The run did not demonstrate parent enrichment: none of the strongest eight
  exposed a parent link, although two exposed child links. Relationship value
  must be measured from the frozen RR-CDF and Reporting Exceptions files after
  identity adjudication, not inferred from this Level 1 candidate pass.
- The appropriate next step is the formal frozen-snapshot proof below, not a
  production schema migration or resolver change.

## Proposed data model

Use additive source-grained tables for a tracer bullet; do not widen
`mdm_company` with every GLEIF field and do not overload its single parent
pointer.

1. `gleif_source_snapshot`: immutable `snapshot_id`, source family
   (`lei`, `relationship`, `exception`), CDF version, publication/retrieval
   timestamps, source URL, S3 URI, content hash, byte/record counts, and parser
   version.
2. `gleif_lei_record_stage`: `(snapshot_id, lei)` plus the exact Level 1 fields
   above, structured repeating names/addresses/events, raw-record hash, and
   validation status.
3. `gleif_relationship_record_stage`: `(snapshot_id, relationship_record_id)`
   plus typed nodes, relationship type/status/periods, registration evidence,
   deletion marker, and raw-record hash.
4. `gleif_reporting_exception_stage`: `(snapshot_id, lei, exception_category)`
   plus reason, reference dates, registration evidence, and raw-record hash.
5. `mdm_gleif_match_candidate`: deterministic candidate ID, run/snapshot IDs,
   MDM entity/CIK/LEI, evidence tier/components, normalized-field version,
   status, reason, and review audit fields.
6. Accepted LEI links use `mdm_source_ref` with
   `source_system = 'gleif_lei'` and `source_id = lei`. Before production use,
   add or prove a database invariant that one `(source_system, source_id)`
   cannot bind to multiple active MDM entities; the current composite primary
   key alone does not enforce that global uniqueness.
7. Accepted scalar attributes may flow through
   `mdm_entity_attribute_stage` under explicit field-survivorship rules.
   Repeating names, addresses, events, and registration metadata remain in
   source-grained tables or purpose-built history tables.
8. Add distinct relationship types for direct accounting consolidation,
   ultimate accounting consolidation, and each selected GLEIF branch/fund
   relation. Store GLEIF relationship-record ID and snapshot evidence in
   `source_evidence` and bind writes to `run_id`.
9. Keep reporting exceptions in their own entity/type-scoped evidence table;
   `mdm_relationship_coverage` is generation/type aggregate evidence and cannot
   represent a particular entity's parent-reporting exception.

## AWS ingestion seam

The production candidate stays within the repository's active AWS path:

```text
GLEIF Golden Copy full + deltas
  -> edgar-warehouse CLI in an operator-deployed ECS Fargate task
  -> immutable S3 bronze objects + checksum/source manifest
  -> validated normalized snapshot artifacts
  -> read-only comparison / candidate generation
  -> manual stewardship gate
  -> accepted source refs, attributes, and typed MDM relationships
  -> existing Snowflake export/native-pull and dbt gold path
```

Recommended S3 grain:

```text
warehouse/bronze/gleif/golden_copy/
  family=<lei|relationship|exception>/
  published_at=<UTC timestamp>/
  cdf_version=<version>/
  <original object and manifest>
```

Capture full snapshots first, then apply only deltas whose declared baseline is
present. Verify HTTPS result, expected media type, compressed and uncompressed
hashes, record count, schema version, and parse rejects before publishing a
snapshot as usable. Never mutate a captured source object. A failed family
invalidates the three-family comparison snapshot; relationship absence cannot
be evaluated from a partial publication.

Use the GLEIF API only for bounded proof discovery and adjudication within its
documented rate limit. Production-scale refresh should use Golden Copy full and
delta files. Schedules, runnable task definitions, image rollout, and runtime
values remain explicit application/operator actions outside passive Terraform,
consistent with this repository's AWS deployment boundary.

## Idempotency and snapshot contract

- Bind every comparison and accepted write to a non-empty `run_id`.
- Define `snapshot_id` from source family, publication time, CDF version, and
  content hash; reject a conflicting hash for the same declared publication.
- Define candidate identity deterministically from
  `(mdm_snapshot_id, gleif_snapshot_id, entity_id, lei, generator_version)`.
- Freeze the MDM cohort and all three GLEIF families before candidate
  generation. Do not compare a changing MDM state to a moving API result set.
- Replaying identical inputs must produce byte-identical canonical candidate
  rows, counts, evidence tiers, and accepted source links. Human adjudication
  is replayed from its append-only decision record, not re-decided silently.
- A newer source snapshot creates new source versions and explicit
  supersession/retirement outcomes. It must not erase prior evidence or reuse a
  previous run's publication timestamp.
- Relationship logical identity remains based on type/source/target; a changed
  period, status, or evidence creates or supersedes a version under the
  existing temporal contract.

## Go/no-go gates

Proceed to an implementation tracer bullet only when all gates pass:

1. **Source completeness:** all three GLEIF families have verified source
   manifests, supported CDF versions, hashes, counts, and zero unexplained
   parser rejects.
2. **Identity safety:** zero false positives among proposed deterministic
   auto-links; no name-only or fuzzy-name-only candidate is auto-linked; every
   accepted proof match has deterministic evidence or two independent evidence
   dimensions and manual adjudication.
3. **Collision safety:** every multi-candidate, jurisdiction conflict,
   predecessor/successor, parent/subsidiary, and category mismatch is routed to
   review or rejection with durable reason evidence.
4. **Authority preservation:** CIK remains the company key; LEI is additive;
   GLEIF cannot overwrite SEC-only facts under an undefined survivorship rule.
5. **Relationship fidelity:** direct and ultimate accounting parents are
   distinct, reporting exceptions are preserved separately, and no result is
   flattened into the generic parent pointer.
6. **Replay:** identical frozen inputs reproduce the full result bundle and
   accepted links without duplicates or unexplained changes.
7. **Change behavior:** a second snapshot correctly handles new, changed,
   lapsed, retired, duplicate, and successor records without destructive
   history loss.
8. **Database integrity:** an accepted LEI cannot bind to more than one active
   MDM entity, and conflicting evidence fails closed into quarantine/review.
9. **Measured value:** field and relationship enrichment yields are reported
   by cohort stratum. Low coverage is acceptable only as an explicit product
   tradeoff; it may not be compensated by relaxing precision.
10. **Operational fit:** the bulk full-plus-delta flow is bounded, observable,
    retryable, and costed on AWS; API rate limits are not on the production
    critical path.

A no-go does not imply that GLEIF is unusable. It means the failing surface
stays analyst-facing or manual-review-only until its evidence, precision,
replay, or source-integrity gap is resolved.

## Execution sequence

1. Export and hash the read-only MDM company population and the stratified
   cohort; record the exact query and source transaction/snapshot boundary.
2. Capture and validate same-publication Level 1, relationship, and exception
   Golden Copy artifacts.
3. Generate all candidates and freeze the evidence bundle before review.
4. Adjudicate under the rules above; compute identity and enrichment metrics.
5. Compare relationships and exceptions only for accepted identity links.
6. Replay the same inputs and require full parity.
7. Capture a second GLEIF publication, run delta behavior tests, and classify
   every change.
8. Fill the measured-results table and make a separate implementation decision
   for company identity, relationships, and each secondary domain.

## Source boundary

External facts and field semantics are taken only from official GLEIF sources:
the [API documentation](https://api.gleif.org/docs/),
[LEI-CDF 3.1](https://www.gleif.org/en/lei-data/access-and-use-lei-data/level-1-data-lei-cdf-3-1-format),
[RR-CDF 2.1](https://www.gleif.org/en/lei-data/access-and-use-lei-data/level-2-data-relationship-record-rr-cdf-2-1-format),
[Reporting Exceptions 2.1](https://www.gleif.org/en/lei-data/access-and-use-lei-data/level-2-data-reporting-exceptions-2-1-format),
and [Golden Copy](https://www.gleif.org/en/lei-data/gleif-golden-copy/download-the-golden-copy),
retrieved 2026-09-11. Repository behavior is derived from the linked schema and
source files on `codex/gleif-open-data-research`. Sections labeled proposed,
recommended, or go/no-go are design recommendations rather than current
behavior or measured outcomes.
