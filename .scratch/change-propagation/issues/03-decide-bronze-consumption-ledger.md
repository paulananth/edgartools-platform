# Decide the bronze consumption ledger and source cursor contract

Type: grilling
Status: resolved
Blocked by: none

## Question

What exact identity, ordering, completeness, and disposition contract lets a
bronze replay select only never-consumed or content-modified source material
without changing Bronze Persist's optional role?

Decide the contract across submissions snapshots, pagination files, filing
artifacts/accessions, company facts, reference catalogs, and ADV bulk inputs:
object key/version/content hash, logical source key, parser/config version,
accession/document completeness, late arrival, explicit repair, retry, and the
rule for advancing a cursor only after silver publication succeeds. Resolve how
newer dated bronze objects supersede intact older checkpoints and how immutable
SEC conflicts fail closed without last-writer-wins behavior.

## Answer

### Decision

Use a PostgreSQL consumption ledger keyed by **Logical Source Revision**, not a
global time cursor and not a silver-table checkpoint. Direct `SecGateway`
acquisition and bronze replay both normalize into the same **Source Change**;
the bronze reference is nullable. Bronze remains an optional archive and replay
source rather than a mandatory hop.

The ledger is authoritative for selection and disposition. An object listing,
dated prefix, local checkpoint, queue receipt, or Snowflake load history may
accelerate discovery, but none may prove that source material was consumed.

### Source-change identity

Every observed source revision records:

- source family and logical source key;
- producer-issued monotonic revision ordinal and predecessor revision for that
  key, assigned before transport;
- canonical byte hash and versioned domain-content hash;
- observation time for telemetry only;
- contract, parser, schema, and parser-configuration versions;
- acquisition reason: steady-state, replay, backfill, repair, or reprocess;
- optional bronze bucket/key/version ID/ETag reference;
- completeness type and declared replacement scope, when applicable; and
- causing parent revision/run for repair, supersession, or reinterpretation.

The source family, logical key, revision ordinal, content hash, and
interpretation versions form the comparison identity. `run_id`, S3 key,
business date, arrival time, ETag alone, and mutable “latest” pointers are not
source identity.

An object observed later with the same versioned domain-content hash is a
consumed `NO_IMPACT` revision. New source bytes, a new parser/configuration
version, or a changed canonical domain hash is selectable even when the logical
source key is unchanged.

### Source-family keys and completeness

| Source family | Logical source key and revision | Completeness required before Scope Completion or retirement |
| --- | --- | --- |
| Submissions company snapshot | Company CIK plus the main submissions resource; the serialized acquisition producer issues the next dense per-CIK ordinal at the authoritative SEC observation and names its predecessor. | Valid main snapshot plus the complete declared pagination-file inventory. Company, address, former-name, and submission-file replacement scopes are declared separately so one incomplete child scope cannot retire another. |
| Submissions pagination file | Company CIK plus SEC-declared pagination filename; the child carries its parent main-snapshot revision and the serialized producer's dense per-file ordinal. | Complete verified bytes for that file and membership in the main snapshot's ordered pagination inventory. A newer main snapshot cannot mark an unacquired referenced file complete. |
| Filing/accession artifacts | Accession plus configured document role/name. The immutable source revision is ordinal 1; the accession manifest binds the ordered required document set and each document hash. Changed bytes are a conflict, not ordinal 2. | The accession is complete only when every configured required document is present and verified. Optional documents are explicitly classified; absence is never inferred from a failed fetch. |
| Company facts | Company CIK plus company-facts resource; the serialized acquisition producer issues the next dense per-CIK ordinal at the authoritative SEC observation and names its predecessor. | One fully parsed authoritative snapshot for the CIK and an ordered membership digest for each replacement fact scope. |
| Reference catalog | Catalog name/source scope. The producer validates the source-published effective version plus a serialized same-version correction counter, then maps that position to the next dense per-scope ordinal before transport. | The complete catalog, member count, and ordered member-key digest, including a legitimate zero-member catalog. |
| ADV filing/bulk source | SEC/IARD dataset identity plus declared period or filing accession, as appropriate. Immutable filing keys use ordinal 1. For replacement/bulk keys, the producer validates source-declared period/version plus a serialized same-period correction counter, then issues the next dense per-key ordinal. | Verified complete archive/filing plus the declared adviser, office, disclosure, fund, or roster scope. Rolling-window absence does not retire an older row unless the newer input proves authority over that same scope. |

Immutable filing artifacts are additive after capture. If the same
accession/document identity is observed with different bytes, selection fails
closed as an immutable-content conflict. Neither arrival order nor a higher S3
version makes either copy authoritative. The conflict is quarantined until an
operator supplies an immutable repair attestation that identifies the accepted
bytes and reason; the original evidence remains retained.

Mutable snapshots such as submissions, company facts, catalogs, and applicable
ADV datasets accept a new hash as a new Logical Source Revision. The new
revision supersedes older current membership only for scopes whose completeness
it proves.

### Ordering and cursor

Ordering is a producer-issued dense ordinal per logical source key and is
assigned before queue or object transport. Where SEC/IARD publishes an
effective version or period, the producer first rejects a lower source-native
position and orders an authenticated same-position correction with its fenced
correction counter. Where the source exposes only a mutable current snapshot,
the acquisition producer holds the key's fenced lease and fetches the
authoritative response. In either case the producer transactionally allocates
the next dense ordinal plus predecessor while writing the durable source-change
outbox. The same revision metadata is stamped on an optional bronze object. It
is never allocated when the consumer happens to receive the object.

Ordinal 1 has no predecessor; ordinal N names N-1. The ledger may admit N
before delayed N-1, but it stores N behind the gap and cannot make it current.
Bronze replay carries the producer revision/predecessor from its capture
manifest. Legacy bronze without that lineage must first receive a one-time,
immutable migration attestation derived from its original capture manifest and
source-native position; if precedence is still ambiguous, it is quarantined
rather than ordered by S3 arrival. An exact existing source-change identity is
deduplicated without allocating another revision.

Wall-clock observation, source date, S3 `LastModified`, and queue delivery
order are observability fields only. A claimed predecessor mismatch, a producer
revision collision with different content, or conflicting same-position
correction counters fails closed. A later authenticated producer revision with
identical versioned domain content produces a publication-backed `NO_IMPACT`
outcome. A copied/relisted object with no new producer revision is only a
transport duplicate and cannot move the cursor.

The consumption cursor is the latest authoritative Logical Source Revision
whose exact verified silver publication identity is recorded. It advances only
after the silver prepare/write/read-back/finalize protocol records either:

- a verified silver publication for the revision; or
- a verified silver publication outcome of `NO_IMPACT` for semantically
  unchanged content.

Landing upload, `COPY INTO` success, parsing success, or a DuckDB checkpoint is
insufficient. MDM, gold, and graph completion do not hold the bronze/source
cursor; after silver publication they consume independent stage-local
publications.

The ledger separately records the gap proof for every intervening ordinal. An
unresolved earlier revision blocks later revisions only for the same logical
source key. `EXCLUDED` and `SUPERSEDED` are terminal gap proofs, but they never
become the cursor and never advance it by themselves. Once every intervening
ordinal has an allowed terminal gap proof, a later revision's verified
`SILVER_PUBLISHED` or publication-backed `NO_IMPACT` outcome may move the cursor
directly to that later revision. Thus an explicit exclusion can unblock the
key without weakening the publication-only cursor rule.

### Dispositions

Each observed revision retains one current disposition backed by immutable
attempt and transition history:

- `PENDING`: observed and eligible for selection;
- `SELECTED`: frozen into one Change Propagation Run;
- `SILVER_PUBLISHED`: applied and verified under a silver publication;
- `NO_IMPACT`: verified under a silver publication without business mutation;
- `RETRYABLE_FAILURE`: the frozen work may be attempted again;
- `QUARANTINED`: content, completeness, version, or identity is unresolved;
- `EXCLUDED`: an operator-authorized immutable exclusion with reason/evidence;
- `SUPERSEDED`: replaced by an explicitly linked correction or reinterpretation.

Dispositions do not overwrite attempt evidence. Every retry has a distinct
attempt identity and fencing token while retaining the same frozen source
revision and run selection.

### Retry, repair, and late arrival

- A transient retry reuses the same Change Propagation Run, source selection,
  object/content identities, expected producer set, and publication identity;
  only the attempt identity changes.
- Corrected mutable content creates a new Logical Source Revision in a child
  run linked with reason `repair`.
- A new parser, schema, or configuration version creates a child reprocess run
  even when bytes are unchanged.
- A late older revision is recorded for audit but cannot replace a higher
  terminal producer revision. A late higher revision is selected into the next
  run; a sealed run never expands.
- A poisoned revision blocks its logical key/scope. It does not block unrelated
  source keys, and it cannot be bypassed without an explicit exclusion.

### Bronze discovery and checkpoint repair

Bronze inventory reconciliation enumerates immutable object versions and their
logical source identities, compares them with the consumption ledger, and
enqueues only missing or non-terminal revisions. It does not resume from a
single “latest date processed” cutoff.

Consequently, a bronze snapshot carrying a higher producer revision cannot be
masked by an intact older checkpoint: if its object version/content identity
has no terminal ledger record, reconciliation selects it even when its dated
prefix falls outside the old checkpoint window. A newer date prefix alone has
no precedence. Relisting or copying an already terminal revision does not
repeat business work.

Bronze object references are environment-bound and checksum-verified. A
reference to another environment is rejected, and credentials or mutable
infrastructure identifiers are never embedded in the source-change contract.

### Scenarios locked by this decision

1. An identical submissions snapshot with a new authenticated producer revision
   records a verified no-impact disposition and advances that logical key
   without downstream row mutations. Merely copying it to a new S3 version is
   deduplicated and does not move the cursor.
2. A submissions snapshot that omits a formerly listed pagination file cannot
   emit Scope Completion until the new main snapshot proves the new full file
   inventory; only then can removed members retire.
3. A complete reference catalog with zero members emits Scope Completion with
   count zero rather than no output.
4. Two different documents for the same immutable accession/document key are
   quarantined; neither wins by arrival order.
5. A parser upgrade over unchanged filing bytes creates a child reprocess run
   and can publish changed silver domain content.
6. A silver failure leaves the source cursor unmoved; retry uses the same
   source selection and does not reselect newer arrivals.

The hard-to-reverse ledger authority and Logical Source Revision identity must
be promoted into the planned Change Propagation Run ADR before code
implementation. This ticket supplies that ADR's accepted source-consumption
contract.
