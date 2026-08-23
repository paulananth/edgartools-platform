# Decide the Bronze capture, consumption ledger, and source cursor contract

Type: grilling
Status: resolved
Blocked by: none

## Question

What exact authority, acquisition, capture, identity, ordering, completeness,
and disposition contract lets the platform download and process only new or
meaningfully changed SEC material while proving what was downloaded,
processed, excluded, deferred, failed, or blocked?

Decide the contract across submissions snapshots, pagination files, filing
artifacts/accessions, company facts, reference catalogs, and ADV bulk inputs:
source authority, pre-request authorization, immutable Bronze evidence,
logical source keys and positions, parser/configuration versions, scope
completion, retries, conflicts, lifecycle diffs, operator status, and recovery
after loss of the PostgreSQL ledger.

## Answer

### Authority model

The four authorities are distinct and non-overlapping:

1. **SEC is the external Source Authority.** Its current source material
   defines what the platform may truthfully capture.
2. **Bronze is the mandatory immutable local evidence store.** Every successful
   SEC response capable of affecting warehouse state is captured and verified
   before processing. Identical bytes may reuse one content-addressed object,
   but every observation retains its own manifest and ledger lineage.
3. **PostgreSQL is the sole local change-control authority.** Its Change Ledger
   owns fetch authorization, observations, revision order, download and
   processing dispositions, leases, blockers, publications, and readiness.
4. **Silver is the authoritative published business state.** Lifecycle diffs
   compare against an exact pinned Silver publication; PostgreSQL records that
   publication's identity and outcome without duplicating Silver row state.

This decision supersedes the optional-Bronze part of ADR 0002. It preserves
Silver as the Runtime System of Engagement and preserves `edgartools` as the
exclusive SEC network gateway.

### Ledger-gated acquisition

Every source network request requires a **Source Fetch Decision** committed in
PostgreSQL before transport begins. A decision reserves a monotonic
**Source Observation Position** for the logical source key and records one
immutable cause:

- a captured discovery observation;
- a due, versioned poll policy; or
- an explicit operator repair, backfill, or reprocess request.

The scheduler may request work but cannot authorize it. A worker may execute a
decision but cannot invent its source key, URL, cause, or eligibility. If
PostgreSQL is unavailable, new SEC requests stop. An already authorized
in-flight request may finish its Bronze write, but its evidence is
unprocessable until reconciled to that original decision.

Only one fenced fetch may be active for a logical source key. Unrelated keys
remain parallel. A retry preserves the original decision, cause, position,
request identity, and conditional validators while creating a new immutable
attempt with a higher fencing token.

Terminal reasons not to download are intentionally narrow:

- `ALREADY_CAPTURED_VERIFIED`: exact ledger-bound source identity, terminal
  capture, checksum, and verified Bronze reference already exist;
- `OUT_OF_SCOPE`: the candidate is outside the sealed Acquisition Universe;
- `OPERATOR_EXCLUDED`: an authorized operator exclusion names its reason and
  evidence.

Not-due, rate-limited, leased, or backoff work is `DOWNLOAD_DEFERRED`, remains
open, records its next eligibility, and eventually alerts. HTTP `304` is a
`NOT_MODIFIED` observation linked to the prior capture. A non-success response
is Fetch Attempt evidence with status, headers, timing, retry classification,
and any diagnostic-body reference; it creates neither a Bronze Artifact nor a
Logical Source Revision. An expected `404` or missing object never proves
deletion or retirement.

### Capture and evidence

Successful source bytes become downloaded state only after:

1. immutable content-addressed Bronze storage succeeds;
2. checksum or equivalent read-back verification succeeds; and
3. PostgreSQL finalizes the exact artifact reference against the originating
   Fetch Decision.

The Bronze object is keyed by exact raw-byte hash. A per-observation manifest
binds environment, account, ledger epoch, logical source key, observation
position, source-native identity, request and response metadata, content hash,
and capture time. Every distinct Bronze Artifact is retained indefinitely;
storage-tier transitions are allowed, while deletion requires a separate
audited exception. This prospective policy does not reconstruct artifacts
removed under earlier accepted cleanup decisions.

If Bronze succeeds but ledger finalization fails, the object is an
**Orphaned Capture**. It may attach only to its original existing Fetch
Decision; otherwise it remains quarantined. S3 listings never create ledger
authority. Cross-environment or cross-account evidence requires an explicit,
checksum-verified operator import that creates local lineage.

### Source revision identity and ordering

A Logical Source Revision materializes only after verified capture. It binds:

- source family and logical source key;
- reserved Source Observation Position and source-native revision/period when
  supplied;
- exact raw-byte hash;
- versioned canonical-source hash after transport-only normalization;
- versioned domain-content hash after interpretation;
- contract, parser, schema, and configuration identities;
- completeness type and declared replacement scope;
- verified Bronze artifact and observation manifest; and
- repair, supersession, coalescing, or reinterpretation parent when applicable.

`run_id`, S3 key, date prefix, arrival time, ETag alone, and mutable `latest`
pointers are not source identity. Positions are monotonic per key but need not
be dense: failed, skipped, and not-modified decisions may leave gaps without
creating revisions. Capture may run ahead after the previous fetch lifecycle
is terminal, but processing and publication remain ordered for the same key.

A `304`, or the same bytes under the same producer revision, records
`NOT_MODIFIED` without a new Logical Source Revision. A new authenticated
producer revision with the same domain content creates a revision with an
explicit publication-backed `NO_IMPACT`. Parser, schema, contract, or
configuration changes reprocess existing verified Bronze evidence and do not
redownload unless that evidence is missing, corrupt, incomplete, or subject to
an explicit acquisition repair.

### Source-family keys and completeness

| Source family | Logical key and revision evidence | Completeness required before Scope Completion or retirement |
| --- | --- | --- |
| Submissions company snapshot | Company CIK plus main submissions resource; source-native metadata and the reserved per-CIK observation position identify successive captured snapshots. | Valid main snapshot plus the complete declared pagination inventory. Company, address, former-name, and submission-file scopes remain separate. |
| Submissions pagination file | Company CIK plus SEC-declared filename, linked to its main-snapshot revision. | Verified file bytes and membership in the complete ordered pagination inventory. An unacquired referenced file leaves the discovery interval open. |
| Filing/accession artifacts | Accession plus configured document role/name. | Every configured required document is present and verified. Optional documents are explicitly classified; failed fetch absence is never completeness evidence. |
| Company facts | Company CIK plus company-facts resource and captured observation position. | One fully interpreted authoritative snapshot and ordered membership digest for every declared replacement scope. |
| Reference catalog | Catalog name/source scope plus source-published version when available and captured observation position. | Complete catalog, member count, and ordered member-key digest, including a valid zero-member catalog. |
| ADV filing or bulk source | SEC/IARD dataset identity plus period or filing accession, as appropriate. | Verified complete archive or filing plus declared adviser, office, disclosure, fund, or roster scope. Rolling-window absence cannot retire an older row outside the proved scope. |

A complete **Discovery Manifest** freezes the counted, ordered, digested
candidate set for an interval. Every candidate receives one Fetch Decision.
Deferred or failed candidates keep the interval open and block baseline or
catch-up completion.

The **Source Family Registry** versions every family's keys, acquisition mode,
completeness proof, poll or change-discovery policy, and required Silver
producers. The **Acquisition Universe** versions the included source families,
CIKs, forms, keys, and history boundaries. A family or universe addition needs
a complete scoped baseline; removal ends future coverage at an explicit
boundary without deleting or retiring SEC facts. Registry changes use a
bounded in-epoch transition with an effective boundary, affected-family
baseline, catch-up, and activation gate.

### Processing and Silver publication

Fetch and processing are separate ledger lifecycles. A Processing Decision
compares logical content plus interpretation identity and yields
`PROCESS_REQUIRED` or an explicit reasoned disposition:

- `NO_IMPACT`;
- `OUT_OF_SCOPE`;
- `OPERATOR_EXCLUDED`;
- `SUPERSEDED`;
- `QUARANTINED`; or
- `RETRYABLE_FAILURE`.

Before processing, the ledger seals the expected Silver producer, table, and
scope set. A revision is processed only after every expected producer records
a verified Silver publication or verified `NO_IMPACT`; parser success,
landing upload, workflow success, and `COPY INTO` success are insufficient.

Each producer computes a row-level **Lifecycle Diff** against the exact pinned
authoritative Silver publication:

- new or different business-key content emits `UPSERT`;
- identical content is unchanged;
- absence from a proved complete replacement scope emits `RETIRE`; and
- no mutations emit explicit `NO_IMPACT`.

An incomplete scope or parse failure cannot emit retirement or Scope
Completion. A complete empty scope is valid. Overlapping publication uses a
compare-and-swap scope fence: a stale attempt must recompute, while disjoint
scopes may publish concurrently.

A later complete mutable snapshot automatically supersedes an earlier
incomplete or quarantined snapshot for the same scope with explicit ledger
linkage. Immutable filing artifacts never use that rule. Snapshot coalescing is
a versioned family policy and is allowed only before any Silver producer output
for the older revision commits.

### Conflicts, repair, and status

Different bytes under one immutable SEC identity are both retained and
quarantined; neither first nor latest wins. An operator repair creates an
immutable child Repair Revision identifying accepted and rejected evidence and
the reason. It never rewrites the original observation.

Each transition family has one owner: the coordinator creates decisions and
seals; acquisition workers record attempts and captures; processors claim
work; the Silver finalizer verifies and finalizes publications; operators alone
authorize exclusions, repairs, universe changes, imports, and ledger
reinitialization. Database roles and constraints enforce these boundaries.

PostgreSQL exposes one **Source Change Status** projection per discovered
candidate with cause, fetch decision and state, Bronze evidence, logical
revision, processing state, expected-producer progress, blocker, and next
action. Immutable attempts, transitions, outcomes, and reasons remain the
audit history beneath that operational view.

### GoF implementation constraints

The implementation must follow the focused design-pattern review recorded in
the [canonical change-propagation spec](../spec.md#ticket-03-gof-implementation-constraints):

- Put the ledger-gated acquisition sequence behind one non-bypassable
  **Facade**. It accepts an existing fenced Source Fetch Decision, records the
  attempt, invokes the selected source-family policy, verifies immutable
  Bronze evidence, and finalizes Source Capture. It must not invent fetch
  decisions, parse source material, publish Silver, or coordinate downstream
  stages.
- Represent proven source-family differences as executable **Strategy**
  policies selected by the Source Family Registry. Prefer first-class
  functions or small protocol-conforming policy objects for discovery, fetch,
  and completeness proof over a class hierarchy. Authorization, hashing,
  Bronze finalization, and ledger transitions remain shared behavior.
- Use a lightweight **Command**-style acquisition handler registry that binds
  execution, scope resolution, and planned writes in one registration. Migrate
  acquisition commands incrementally and retain existing dispatch as a
  fallback until each command is covered; Ticket 03 does not authorize a
  wholesale orchestrator rewrite.
- Keep persisted fetch and processing lifecycles in PostgreSQL constraints,
  transition history, and a deterministic reducer or transition table. Do not
  model durable lifecycle truth as in-memory GoF State objects.
- Keep the transactional outbox as the durable delivery contract. Do not
  replace it with Observer callbacks.
- Do not introduce a Template Method superclass for similar source families
  until repeated co-change demonstrates a stable shared algorithm skeleton.

These choices respond to current evidence: acquisition dispatch and scope
resolution have drifted apart, source families have repeated but genuinely
different discovery and completeness behavior, and Bronze capture has needed
multiple fixes around immutability, dangling references, deduplication, and
orphan recovery. The patterns create explicit boundaries around those costs
without turning Ticket 03 into a broad framework rewrite.

### Initial bootstrap and ledger loss

The first production ledger and every recovery after loss of ledger authority
use the same explicit bootstrap protocol. An operator authorization names the
reason, source-family coverage contract, cutoff, deployment cohort, and new
Ledger Epoch. The platform does not infer lost decisions from Bronze and does
not silently continue an empty ledger.

The new epoch starts from a **Hybrid Source Baseline**:

- existing verified Bronze plus complete SEC change intervals where a source
  family provides adequate change capture; and
- a fresh complete SEC snapshot or bulk reconciliation for every family that
  lacks complete change capture.

All required families must satisfy the sealed Baseline Coverage Contract.
During the rebuild, acquisition continues; a Baseline Catch-up Barrier closes
each family through the activation high-water mark, using a final complete
snapshot where necessary. A complete non-serving Silver Baseline Candidate is
rebuilt, verified, and activated atomically. The old Silver state remains the
serving authority until activation. Pre-epoch Bronze remains historical
evidence unless explicitly selected for backfill, repair, or reprocessing.

### Scenarios locked by this decision

1. A due poll with unchanged content records `NOT_MODIFIED` and reuses the
   verified prior artifact; it does not manufacture downstream work.
2. A parser upgrade reuses verified Bronze evidence and may create changed
   Silver output without calling SEC again.
3. A submissions snapshot cannot retire a missing pagination member until the
   complete new inventory and every required child are verified.
4. A valid zero-member catalog emits Scope Completion with count zero.
5. Two documents for one immutable accession/document identity are
   quarantined; arrival order never chooses the winner.
6. A Silver failure leaves processing incomplete; later revisions for the same
   key cannot become current, while unrelated keys continue.
7. PostgreSQL loss halts new requests and requires an authorized Hybrid Source
   Baseline, Silver candidate, catch-up, verification, and new epoch activation.

This contract is recorded by
[ADR 0006](../../../docs/adr/0006-sec-bronze-ledger-silver-authority.md).
