# MDM and analytical silver boundary: architecture requirements

Status: accepted architecture requirements; complete shared understanding confirmed
by Q7, reply verified 2026-09-26 11:11 ET. Implementation-detail qualification
remains pending. This is not an executable implementation ticket or evidence of
deployed behavior.

Basis: [architecture](architecture.md), [decisions](decisions.md),
[primary sources](research/2026-09-26-primary-sources.md) and the refreshed
[repository assessment](research/2026-09-26-repository-assessment.md).

## Problem and outcome

The operator needs to evolve MDM independently of analytical silver without
decoding the same input files twice on every run. Both consumers must see the
same preserved source facts, recover independently and report truthful completion.

The outcome is one durable parsed publication per pinned source input and reader
version, with independent MDM and analytical mappings. This is a derived reading
of a source publication, not a replacement publisher identity, selected master
record or analytical filtered table.

## Boundaries

| Component | Responsibility |
| --- | --- |
| Existing acquisition and source ledger | Authorize capture, verify raw evidence, identify source publication/scope and retain its lineage. |
| Shared reading | Decode the source structure, preserve fields/groups and publish bounded verified source records. |
| MDM Dataset Contract | Interpret source records as identity, field, role and relationship evidence under its pinned mapping. |
| Merge Stage | Own classification, binding/consolidation and field selection under the existing approved Mastering Policy. |
| Analytical mapping | Own analytical grain, filters, derived values, joins and analytical history. |
| Combined outputs | Declare required consumer coverage and compatible input watermarks before readiness. |

Business filtering, identity deduplication and master-field selection do not
belong in the shared reader. Consumers may reuse deterministic utility functions
while independently pinning the behavior they depend on. Irregular HTML/PDF and
existing source-specific readers keep their current exception until a separate
source contract proves a compatible reading boundary.

## Source-record fidelity

For structured formats preserve the original source field names and values,
unknown/unused fields, identifiers including leading zeros, nested records,
repeated groups and their order, attributes/namespaces needed to interpret XML,
and distinctions among absent, null and empty values. Retain source locators and
raw object/content identity. This is semantic source fidelity; exact bytes remain
bronze and are not reconstructed from a normalized encoding.

Avoid lossy numeric/date conversion in the shared layer when it would change
source interpretation. Consumer normalization retains provenance back to the
source value. Malformed records must be rejected with located evidence or fail
their publication according to an explicit source contract; they cannot silently
vanish. File delivery completeness, accounted rejects and source coverage are
separate facts. A bounded sample or partial delta does not authorize retirement
by absence.

## Version and publication contract

A parsed publication pins:

- source family and native publication/revision, coverage and replacement scope;
- verified raw object hashes/versions, all required input members and lookup snapshots;
- immutable reader code/dependency, read-contract, configuration and output-schema versions;
- record/partition inventory, content hashes, counts and reject dispositions;
- derived lineage to captured evidence, with each record's key or stable raw locator.

Execution identity follows these dependencies. MDM and analytical mappings get
separate immutable digests. MDM also pins its Mastering Policy. A composite
authoring-file digest remains useful for review but cannot be the sole raw-parse
skip key when only a consumer mapping changed.

Consumers pin a suitable parsed publication. A mapping-only update reuses it;
an incompatible reader update produces a new publication. An old active consumer
can keep using its protected old reading while the other migrates, within their
declared compatibility contracts. Exact historical reproduction requires every
pinned input and executable dependency; missing evidence fails closed rather
than substituting whatever is currently newest.

The current source verifier's fresh-capture checks do not authenticate a derived
parse by themselves. Define and test its derived-lineage verification before
integrating the new publication into MDM. Stable source codes and source record
keys survive mapping-version changes.

## Recovery and completion

Use existing acquisition/processing ledgers, Bookkeeping and the MDM journal as
the control authorities, with the existing run identity linkage. Parsed data is
stored as artifacts; it is not a new competing control ledger.

Readers work from a verified registered publication, not an unbounded S3 listing.
Publish immutable bounded members and manifest, verify their inventory, then
record the authorized parsed-publication outcome and durable delivery intent.
The concrete storage/ledger ordering must reconcile orphan artifacts, duplicate
delivery and a crash between artifact writes and control commits. No atomic
transaction spanning object storage and a database is claimed.

Each consumer records effects, checkpoints and publication intent in its own
required transaction. MDM preserves its existing master/journal/evidence atomic
boundary. On lost acknowledgements or retries, idempotency keys identify the
same publication, consumer version and bounded work; receipts prove completion.

Required observations are separate: captured, parsed/verified, MDM applied,
analytical applied and combined outputs published/verified. One successful
consumer does not imply completion of the other. A shared reader error affects
both for that input, but a consumer mapping failure is isolated. Export and graph
failures keep their existing downstream completion/reconciliation gates.

## Retention

Current parsed publications, versions required by active consumers and versions
referenced by unfinished/pinned work remain protected. Superseded artifacts are
eligible for bounded, auditable cleanup only after all protections clear and the
declared replay requirement is satisfied. Time-to-live alone is insufficient.

Reuse existing source-specific raw retention. SEC bronze and new-enrichment
archive/delta lifecycles are not silently unified. When accepted source retention
removes raw bytes, regenerated history cannot be promised; retain required parsed
evidence or explicitly report the unavailable replay horizon. Historical full
assertion copies are not added back to the MDM journal. Its compact receipts
retain source identity, pinned inputs/rules and decisive evidence as already chosen.

## First proof and test seam

Prove the behavior at the highest common seam: verified source inputs through
the parsed publication into the two independent consumers and their externally
observable outputs/receipts. Prefer existing publication, adapter and Merge Stage
seams. Instrument raw reader invocations only to verify the promised selective
replay; do not make tests mirror internal functions.

Local acceptance uses PostgreSQL 16 with real migrations and restricted roles;
it must run without Snowflake/AWS credentials and without prerequisite skips.
Local filesystem artifacts are a test adapter, not a new deployment architecture.
The target remains the existing AWS/S3 and analytical-serving direction.

Use pinned SEC Company and GLEIF inputs, with bounded fixtures plus matched
representative real-source samples when their approved artifacts are available.
The trial must account for Company classification/matching inputs, filings,
addresses, ticker/catalog evidence, GLEIF source members and lookup dependencies;
one conveniently filtered table cannot stand in for the input scope.

| Scenario | Required observable result |
| --- | --- |
| An unused JSON/CSV/XML field or repeated group is present | It survives shared storage and is available to a new mapping without a raw parse. |
| Identifier has leading zeros; field is absent/null/empty | Source distinctions survive, and each mapper applies its own declared semantics. |
| SEC countryCode-only address and state-only control | Both source fields survive; MDM output follows the approved country mapping with no invented source fact. |
| Same inputs and all version/dependency identities repeated | Same source and consumer business results, with no duplicate effects. |
| Only MDM mapping changes | No new raw parse; only MDM's affected work reruns; analytical outputs/receipts are unchanged. |
| Only analytical mapping changes | No new raw parse; only analytical work reruns; MDM effects/receipts are unchanged. |
| Reader correction | New derived publication links to the same raw evidence with the corrected reader version; adoption obeys consumer compatibility and identity approval gates. |
| MDM fails while analytics succeeds, then vice versa | Successful effects survive; failed work retries independently; combined output remains incomplete where required. |
| Crash around artifact/control commit or lost consumer acknowledgement | Recovery reconciles pending publication/receipts; no skipped committed work or duplicate effects. |
| Partial publication, rejects or absent expected members | Coverage/count accounting is explicit; no false complete output or retirement by absence. |
| Old consumer/run pins a superseded reading | Cleanup preserves it until protection clears; later approved cleanup does not break required replay. |
| Required raw/dependency evidence is missing | Replay fails with the missing identity; it does not silently use current inputs. |

Compare existing and new source/MDM/silver outputs on the same input scope and
policy versions. Separate intentional corrections from unexpected differences;
each intended difference needs its reason and approval under the existing rules.
Record row/key coverage, rejects/deferrals, relationships, field provenance and
identity parity, not merely pipeline success.

Measure total raw reads/parse work, parsed writes/storage, consumer reads and
mapping work, repeat/recovery work and validated-output duration/cost. Report
both normal delivery and replay. No savings percentage, performance threshold
or promotion approval is inferred from the architectural decision.

## Migration and engineering gates

Preserve current pipeline entry points and existing outputs through the bounded
proof. Rollout is a separate operator action after evidence review; broader entity
migration waits for this first proof. Existing matching-rule activation remains
an exact-fingerprint decision, independent of approving this topology.

Before generating executable implementation tickets, settle and record:

1. the source-evidence physical encoding, bounded partitioning and fidelity prototype;
2. derived-lineage/manifest schema and storage/control commit recovery protocol;
3. independent component digests, consumer compatibility and approved input envelope;
4. the existing-ledger integration and retention pin/cleanup mechanism;
5. explicit Source Contract/glossary amendments, source-file ownership and rollback plan;
6. reproducible proof commands and performance/cost acceptance criteria for rollout.

These are engineering qualification gates, not additional unasked product
decisions or claims that tests have already run. An implementation plan must resolve
them before handing tickets to another agent.

## Scope exclusions

Source acquisition redesign, SEC requests, new raw-retention rules, wholesale
parser replacement, all-entity migration, new identity rules, consumer activation,
AWS rollout and Snowflake deployment are outside this research/specification work.
