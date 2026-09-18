# Source registry and evidence contract

Status: dataset metadata pinned to the existing acquisition authority and a
configuration-selected JSONL adapter are implemented. Native source contracts,
complete-publication accounting and unsupported-domain dispositions remain
integration work; the requirements below are not all implementation evidence.

## Extend the existing authority

The active acquisition registry already governs source-family coverage and
activation (`edgar_warehouse/acquisition/registry_ledger.py` and migration
`014_source_registry.sql`). Extend that versioned authority with dataset and
publication metadata; do not introduce a competing activation registry.

`source_code` identifies a dataset, not a provider or entity kind. SEC
submissions, SEC ownership filings, and IAPD ADV bulk are different datasets
even when their records describe one Company. Provider, source authority,
acquisition family, and dataset code are separate fields.

| Record | Required content |
| --- | --- |
| Dataset contract | Immutable `source_code`, provider and authority, acquisition family, registry version, adapter/version, schema version, source-record key definition, publication key/order rules, time semantics, declared completeness scope, supported kinds/roles/fields, deletion semantics, enabled consumers |
| Source publication | Dataset and native publication ID, schema version, publication/effective times, source-native revision/predecessor, complete/delta classification, coverage interval, member inventory/hashes/counts, verification result, capture run and source evidence references |
| Normalized assertion | Stable assertion ID, dataset, source-record key, publication, subject anchor, asserted kind, namespaced field/relationship/role, typed value and operation, source effective interval, native correction position, normalization version, artifact/member/record location and hash |
| Identity decision | Candidate anchors/IDs, input assertions, all conflicts and scores, selected action, policy/version/hash, reviewer or deterministic rule, originating run, superseded decision if any |
| Selected field | Identity/profile, field and value, winning assertion, eligible losing assertions, authority rule and policy digest, applicable valid time and projection watermark |
| Record disposition | Consumer and contract version, publication/record identity, accepted/unchanged/retracted/deferred/conflict/rejected outcome, reason and evidence, batch and originating run |

Use content-derived assertion identities from canonical business content plus
source identity, publication, and normalization version. Exclude wall-clock
ingest time, attempt IDs, transport paths, and delivery ordering from business
hashes. Same logical source version with different content is a conflict,
never an overwrite. Re-delivery of identical evidence returns its prior effect.

Record keys cannot be row numbers in a reordered download unless the source
contract explicitly defines ordinal identity within an immutable publication.
An ADV private-fund occurrence is filing accession plus fund index; PFID can
link identity but must not collapse distinct occurrences or assertions.

Source effective time, publication time, observation time, and recorded time
are separate. Missing effective time is explicit and follows a versioned
dataset rule; never replace it silently with load time. Publication order
cannot be inferred from filename sort unless its source contract proves it.

## Correction, replay, and complete scope

Normalized source assertions are immutable. A correction records supersession
within the source record/field chain; it does not rewrite another source's
assertion or erase the prior version. A retraction withdraws that assertion's
eligibility. Retiring a source dataset closes its governed contribution through
a journaled operation and recomputes winners from still-eligible sources.

The local adapter contract requires complete identifier/profile/relationship
collections on every normalized record, including records from patch sources.
Profile membership is a snapshot; ordinary and role-specific fields preserve
prior eligible values for null/unknown and use explicit clear/retract operations.
Role-field provenance retains the assertion that supplied the value, even when
a later profile snapshot repeats the membership with an unknown field.

Snapshot absence is meaningful only after manifest verification, complete
record accounting, and the dataset's scope-completion decision. A partial
file, missing parser member, failed batch, limit-bound sample, or daily delta
never proves absence. A complete identifier-pair snapshot may retract a pair
assertion, not the underlying Security or Company.

Adapters produce typed evidence only. They do not merge identities, select
winners, commit master changes, or call publishers. Configuration chooses the
adapter and its approved dataset/consumer contracts. Unknown schema or
unsupported domain retains raw/normalized evidence with a blocked disposition;
it cannot silently become success for a mandatory consumer.

## GLEIF and mapping extension boundary

The [existing source-file catalog](../../../.scratch/mdm-enrichment-program/source-file-pipeline-catalog.md)
is the accepted planning inventory. Its dated filenames and availability
observations are historical examples, not current endpoint checks. None of
these external enrichment adapters is implemented in the inspected runtime.

| Proposed dataset code | Publication/completeness family | Eligible consumer scope |
| --- | --- | --- |
| `gleif.lei` | Level 1 XML ZIP; independent baseline/delta/checkpoint | Accepted legal identity evidence; domain classification gates still apply |
| `gleif.relationship` | RR XML ZIP coordinated with reporting exceptions | Exact source-directed accounting, fund and branch relationships |
| `gleif.reporting_exception` | REPEX XML ZIP coordinated with RR | Preserve reason/exception evidence; missing parent is not proof of no parent |
| `gleif.isin_lei` | Independent complete pair snapshot | Security identifier to accepted issuer identity; no legacy-Security retirement from absence |
| `gleif.bic_lei` | Independent complete pair snapshot | Governed organization/Branch mapping; identifier semantics decide the endpoint |
| `gleif.mic_lei` | Independent complete pair snapshot | Venue-to-operator evidence; MIC is not a Company identifier |
| `gleif.opencorporates_lei` | Independent complete pair snapshot | Corroborating Company identifier with accepted jurisdiction/registration semantics |
| `gleif.qcc_lei` | Independent complete pair snapshot | Accepted Company/Government Entity identifier evidence |
| `gleif.gem_lei` | Independent complete pair snapshot | Accepted entity mapping; no inferred energy-asset ownership |

S&P CIQ bulk, OpenFIGI or other identifier services, market data, sanctions,
ESG, credit and commercial company feeds are not made approved implementation
scope by this table. Preserve the earlier program's conditional-source gates.

RR plus reporting exceptions must meet a coordinated completeness boundary;
Level 1 remains independent. Each of the six mappings has its own publication,
cadence, checkpoint and recovery. A consumer may require several families,
and advances only when all of its prerequisites are verified.

Existing SEC acquisition retains durable Bronze. For new enrichment, follow
the accepted temporary Bronze / latest verified complete Source Artifact
Archive contract, including authorized deletion evidence. Normalized evidence,
decisions and history remain permanent. Offline fixtures are retained
separately. The controlled cutover rebuild pins approved inputs for its whole
rehearsal; routine enrichment recovery may request a newer complete baseline
under a new ledger epoch and must not claim continuity it cannot prove.
