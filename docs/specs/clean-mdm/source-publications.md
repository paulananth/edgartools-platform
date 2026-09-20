# Source publication verification

Ticket 11 implements a **source-only offline verification API** in
`edgar_warehouse/mdm/clean/source_publications.py`. It creates no tables, roles,
master records, consumer receipts or acquisition status flags. The fixture is
synthetic and is not native GLEIF qualification or matching calibration.

## Contract and authority

Register the immutable dataset through the existing governed `register_dataset`
path. Its `body.publication_contract` pins:

| Field | Version 1 meaning |
| --- | --- |
| `version` | Integer `1` |
| `format` | `clean-mdm-publication-v1`, the normalized adapter manifest format |
| `continuity` | `sequence-predecessor-sha256-v1` |
| `publication_family` | One of the dataset's declared publication families |
| `required_members` | Exact, nonempty set of unique member names; up to 128 |
| `replacement_scope` | Exact scope label shared by this family's publications |
| `revision_versions` | Pinned contract, parser, schema and configuration versions of acquisition revisions |

The [versioned fixture](../../../tests/fixtures/clean_mdm/publication_v1/dataset.json)
is a complete example. Golden Copy requires Level 1, relationships and reporting
exceptions together. Mapping publications require their own contract and recovery
plan. Several record-level dataset adapters may later consume the same aggregate.

The manifest is itself a captured immutable `source_revision`. The verifier
accepts its revision UUID and reads its artifact reference from the ledger; it
does not accept caller-supplied bytes as proof. The manifest contains version,
source family, publication family, source-native publication identity, integer
source sequence, full/delta mode, coverage, replacement scope, predecessor and
members. Each member declares its logical source key, name, byte count and raw,
canonical-source and domain-content SHA256 hashes. Publisher manifests need no
internal database UUIDs: the verifier resolves them from the captured inventory.

This adapter format deliberately does not infer sequences from filenames, arrival
order or ledger observation positions. A native GLEIF adapter must map actual
publisher release metadata and predecessor evidence into the contract, retaining
the original metadata. That mapping and its native-format tests are ticket 12.
Unsupported metadata cannot be guessed into this format.

## Verification and permissions

`PublicationVerifier(ledger_engine, open_artifact).verify(store, source_code=...,
manifest_revision_id=...)` reads the registered dataset from MDM and opens a
read-only acquisition transaction using the existing processor role. The caller
supplies an artifact opener restricted to its approved local root or S3 bucket.
The returned frozen object stores canonical JSON; accessing `.evidence` returns
a copy. It is an in-process result, **not a signed authorization token**. Reloaded
or externally supplied proof JSON must be verified against source evidence again.

For the manifest and every member, verification requires a fresh immutable
revision with an immutable CAPTURED transition tied to the same decision, family,
logical key and observation position. It rejects derived reinterpretations until
a lineage-verification contract exists. It checks exact publication, coverage,
scope and interpretation versions. Every physical file is streamed and its raw
SHA256 recomputed; member interpretation hashes must match the pinned ledger
interpretation. Canonical/domain hashes are not recomputed by an unversioned
parser. Native adapters remain responsible for producing those interpretations.

The publication inventory query must find exactly the declared members plus one
manifest, with no duplicate logical keys, extra or conflicting revisions. Missing
bytes, malformed JSON, duplicate JSON fields, nonfinite numbers, absent members,
hash/version conflicts and duplicate member identities all fail closed. Delivery
limits are 1 MiB per manifest and 1 GiB per member, up to 128 members. Memory use
for member hashing is bounded to 1 MiB; native full-source support must qualify
suitable limits or a separately versioned partitioning contract before activation.

There are no new grants. Capture and revision materialization use their existing
roles; verification uses processor SELECT privileges inside a read-only
transaction. MDM reads use its restricted runtime role. The future hosted actor
composition and any narrower read grants remain a deployment gate.

A proof pins revision UUIDs for lineage, hashes, exact inventory, dataset digest,
source metadata and verified byte counts. Its inventory digest excludes local
acquisition UUIDs and sorts by member name, so delivery order cannot change source
content identity. The complete proof includes local lineage and therefore is
stable on replay of the same ledger, not across independently created ledgers.
A later conflicting capture under the same native publication fails subsequent
verification; append-only evidence does not justify ignoring that conflict.

## Coverage and recovery

File delivery verification is separate from source coverage. A full baseline
requires `COMPLETE`, the declared replacement scope and no predecessor. A delta
requires `PARTIAL` and an explicit predecessor sequence plus manifest SHA256.
Both can be completely delivered. A delta never gains full replacement authority
because all its files arrived.

`plan_continuity(verified_publications, target_sequence=..., previous=...)`
proposes work for exactly one dataset, publication family and scope. At most 128
verified candidates are accepted. The previous publication must be independently
proved **fully consumed** by the consumer; a bounded checkpoint carrying its name
is insufficient. Exact predecessor sequence AND hash must connect every delta.

Among proven delta paths ending at the requested source sequence, version 1
selects the smallest delivered byte total, then fewest publications, then proof
digests for deterministic ties. Even a cheaper full snapshot does not displace a
valid delta route. With no route, it selects a newer full baseline, optionally
followed by contiguous deltas, reaching the same target. With neither, it fails
closed. Mixed sibling families, native publication conflicts and checkpoint
rewinds fail. Selection uses source metadata, never publication-name sorting.

The result includes all selected proofs and an aggregate digest suitable for
`continuity_proof` on a scoped batch. `consumption_complete` and
`downstream_complete` remain false: the plan certifies neither. The caller must
freeze this plan in its run input and preserve it across bounded work; repeated
verification cannot silently replace an already frozen run plan.

## Transaction boundary and remaining integration

Verification finishes before any MDM transaction opens. Acquisition history and
bytes survive a rolled-back MDM transaction. The existing commit capability can
atomically retain the returned proof with its family cursor and publication
intent, but still treats proof JSON as caller evidence. It does not call this
verifier across databases. The existing generic manifest CLI is unchanged.

Before native Company consumption is enabled, ticket 12 must wire this API into
the consumer before Merge Stage, authenticate each batch's membership in the
verified inventory, freeze the recovery plan and implement exact whole-publication
record accounting. It must establish the completed predecessor from that
accounting; this module cannot infer it from a partial batch cursor. Downstream
export/graph receipts and root-run completion retain their separate gates.

The offline tests use actual acquisition capture/revision APIs and real PG16
migrations with restricted runtime logins in separate MDM and acquisition
databases. They exercise lost acknowledgement, reordered/repeated delivery,
normalization reproducibility, malformed/absent/conflicting evidence, verified
partial deltas, deterministic recovery, source retention after failed MDM commit,
and proof persistence on the successful retry. The source-only fixture leaves
zero identities, assertions, projections, batches, checkpoints and publication
intents. No bytes are deleted or persistent local databases migrated.
