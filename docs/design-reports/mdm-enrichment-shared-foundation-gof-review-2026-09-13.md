# MDM Enrichment Shared Foundation

## GoF design review and implementation-readiness report

Prepared by OpenAI Codex  
13 September 2026

## Contents

1. Executive summary
2. Key findings
3. Implications
4. Recommendations
5. Appendix

## Executive summary

**Verdict: proceed to the shared-foundation specification, but do not open implementation work yet.** The accepted program boundary is sound: capture each external publication once, preserve it as source-grained evidence, and let independently releasable domain consumers decide whether that evidence may publish. This keeps GLEIF authority separate from SEC, IAPD, and PCAOB authority and prevents a captured LEI record from becoming a Company merely because it exists.

**Pattern recommendation: use Strategy only for source-publication behavior, selected through the active Source Family Registry.** The strategy should let publication discovery, inventory verification, delta-continuity checks, and normalization vary while the existing ledger-gated capture Facade retains authorization, lease fencing, hashing, immutable S3 writes, read-back verification, and ledger finalization. Use a stateful protocol only because a source publication coordinates several operations; continue to use plain callables for single-step variation.

**Cost:** a publication Strategy adds another registry-selected indirection. Its protocol can become a dumping ground for source-specific details, and its callers must understand which strategy is installed. Keep the interface publication-scoped, keep shared security and persistence out of it, and reject an active registry entry when no installed strategy can satisfy its declared cadence and completeness contract.

The missing work is not another pattern. It is a precise data contract for publication aggregates, normalized record versions, candidates, decisions, accepted bindings, deferred evidence, independent checkpoints, and a persistent run lineage spanning acquisition through graph publication. The current tables prove parts of that contract, but they do not yet bind the whole enrichment lifecycle.

### At a glance

| Theme | Observation | Implication |
| --- | --- | --- |
| Program boundary | 26 workstreams separate shared capture from domain publication | Preserve this boundary; do not build a generic legal-entity publisher |
| Existing design | Six source families already use registry-selected policies behind one capture Facade | Extend the proven seam rather than create a parallel framework |
| Pattern choice | Publication behavior varies at runtime; the invariant transaction does not | Strategy fits; Template Method does not |
| Evidence model | Fetch decisions and source revisions are durable, but there is no multi-artifact publication aggregate | Add a publication identity and inventory above artifact rows |
| Run lineage | `run_id` is durable on two MDM evidence tables, but not across the source-to-export chain | Specify one persisted root run plus phase-level bindings |
| Consumer isolation | The plan requires independent family and consumer checkpoints | Key checkpoint state by consumer and source family; never share advancement |
| Review semantics | Existing match review represents entity-pair adjudication only | Use distinct evidence-bound decision kinds; review must never imply merge |
| Implementation gate | Offline replay must reproduce inventories, transitions, and hashes without publishing | Keep implementation blocked until the spec fixes schemas and acceptance tests |

### Review scope

The review covered the accepted parent map, five resolved program decisions, the shared-foundation charter, the Company child decisions, three ADRs, the acquisition ledger and registry seams, MDM evidence/run/checkpoint models, path catalog, command registration, and focused contract tests. It inventoried six installed source-family policies, eight migrated acquisition commands, and four MDM commands that produce run-bound evidence. No application, schema, AWS, Snowflake, schedule, backfill, or production change was made.

## Key findings

### 1. The source-grained / consumer-grained split is the correct architecture

The accepted design separates one immutable source capture from multiple domain consumers. That is the load-bearing decision. GLEIF Level 1, relationship, exception, and mapping records share a publication source but not a single publication meaning. Company, Security, Fund, Branch, Adviser, Audit Firm, Government, International Organization, Sole Proprietor, and Market/Venue consumers have different identity and relationship authority.

This split also establishes the right failure boundary: a Security consumer may fail or roll back without advancing the Fund checkpoint, and a captured unsupported endpoint remains evidence rather than being coerced into Company. The design should preserve source-wide capture, source-family checkpoints, and consumer-owned publication transactions as three separate concepts.

### 2. Strategy is already proven at the acquisition boundary

`SourceFamilyPolicy` exposes only `fetch()` and `is_complete()`. `build_capture_facade()` selects the policy from the active registry and retains the invariant sequence: validate the fenced decision, fetch, prove completeness, write content-addressed Bronze, verify, and finalize the ledger. Six source families are currently installed through `_POLICY_FACTORIES`, and the registry fails closed on unsupported acquisition modes.

That evolution is evidence for Strategy, not a hypothetical extension point. Git history shows the same seam absorbed submissions, company facts, reference catalogs, ADV filings, ADV bulk datasets, and conditional fetch without moving authorization or persistence into source-specific classes.

**Recommended shape:** add a publication-scoped strategy above the existing artifact-scoped policy. A GLEIF Golden Copy or delta is a publication with a verified inventory of related artifacts, not one payload. The publication strategy may discover the publication, enumerate artifacts, verify cross-file completeness and continuity, and normalize records. It must call the existing capture Facade for each authorized artifact rather than write S3 or mutate ledger state itself.

### 3. The existing Facade should remain narrow and authoritative

The current Facade is correctly one-directional. It is a single safe entrance into acquisition persistence, not a coordinator for domain consumers. Its narrowness is valuable because a source strategy cannot bypass the Fetch Decision, lease fencing, content hash, immutable-write verification, or terminal ledger transition.

Do not widen `SourceFamilyPolicy` until it owns orchestration, database transactions, S3 paths, or MDM publication. Do not add a second capture implementation for GLEIF. A publication coordinator can compose existing primitives, but the Facade remains the only artifact-capture path.

### 4. A source publication is a missing aggregate, not a Composite pattern

The current ledger models one fetch decision, one logical source key, and one source revision with one Bronze artifact reference. GLEIF needs one immutable publication identity that owns a complete inventory across Level 1, relationships, exceptions, and mapping artifacts. Without it, separate artifact rows can each be valid while the overall publication is incomplete or internally inconsistent.

Model this as relational data, not a GoF Composite. Consumers do not need to treat a publication and an artifact through one uniform interface, and leaf operations such as capture or hash verification have different invariants from publication-level continuity and inventory checks.

Minimum specification boundary:

| Record | Required identity and evidence |
| --- | --- |
| Source publication | Source, publication family, native publication ID, observed time, effective interval, registry version, manifest hash, capture run, lifecycle status, superseded publication |
| Publication artifact | Publication ID, artifact family, logical source key, immutable Bronze reference, content hash, byte count, format, parser contract |
| Source record version | Publication ID, native record key, record kind, canonical record hash, observed/effective interval, source status, superseded record |
| Consumer candidate | Consumer, domain, source-record version, candidate kind, proposed local identity or relationship, evidence hash, disposition |
| Stewardship decision | Candidate, decision kind, immutable before/after state, rule or reviewer, reason, run, decision time, superseded decision |
| Accepted binding/version | Consumer-owned temporal projection with source record, decision, run, validity, and supersession |
| Consumer checkpoint | Consumer, source family, publication family, committed baseline/publication, pending cursor, run, status, continuity proof |

### 5. Run identity is present but not yet end-to-end

ADR 0007 and Ticket 30 correctly bind origin `run_id` to `mdm_change_log` and `mdm_relationship_instance`; reruns preserve the original relationship version's run. Step Functions wiring also propagates the calling execution name into nested MDM commands, avoiding fragmented identities.

The shared-foundation requirement is wider. Source fetch decisions, source revisions, normalized record versions, candidates, stewardship decisions, accepted bindings, checkpoints, Snowflake exports, graph publication, and deletion decisions must resolve to one durable root run. A string repeated across tables is not enough if no persistent record defines the run, its source trigger, parent execution, image/parser/config identities, start/terminal state, or phase attempts.

The spec should define a root run and append-only phase attempts. Origin bindings remain immutable. Retries create a new phase attempt under the same root run or a new root run with an explicit replay-of link; they never rewrite the originating run on existing evidence.

### 6. Lifecycle state belongs in constrained data, not State objects

The acquisition schema already uses database constraints and role-owned transitions for fetch work, registry versions, processing outcomes, and evidence conflicts. That is the right enforcement layer for cross-process AWS work. Class-per-state objects would not prevent an ECS task or separate transaction from making an invalid transition and would split authority between Python and Snowflake Postgres.

The new lifecycle tables should keep explicit enums, transition rows, database constraints, role grants, and optimistic/fenced guards. Python services may expose named transition functions, but lifecycle truth remains durable data.

### 7. Current MDM tables cannot carry the full enrichment evidence contract

`mdm_source_ref` records a current source-to-entity link and content hash, but its primary key includes `entity_id`; that does not by itself stop one external identifier from binding to multiple entities. `mdm_entity_attribute_stage` records source and effective date, but not publication, source revision, record hash, run, observed interval, decision, or supersession. `mdm_match_review` is an entity-pair review and cannot safely stand in for field conflicts, missing relationship endpoints, identifier mappings, or deferred-domain routing.

Do not overload these current-state tables. Preserve them as MDM projections and add source-grained evidence plus append-only decisions upstream. The consumer transaction may then derive a current projection from accepted evidence while retaining history and rollback inputs.

### 8. The design has strong proof gates that should remain implementation blockers

The accepted plan already requires deterministic replay, idempotent rerun, complete inventory, terminal dispositions, source-authority protection, independent checkpoints, downstream parity, rollback, and cost per validated output. The shared-foundation phase adds an especially useful negative gate: an offline fixture must reproduce inventories, state changes, and evidence hashes without publishing a domain record.

That test proves the foundation is evidence infrastructure rather than a hidden generic publisher. Keep it as the first executable proof before the Company tracer bullet.

## Implications

The shared foundation should be smaller than the full program but stricter than a utility library. It owns source publication identity, evidence capture, normalization lineage, run lineage, checkpoint mechanics, transition rules, and audit contracts. It does not own domain meaning, survivorship priority, accepted relationship semantics, or release approval for a consumer.

This yields one deliberate axis of polymorphism: source-publication behavior. Domain consumers are explicit modules with separate schemas and release fate, not interchangeable algorithms. Registry metadata selects an installed publication strategy; authority metadata does not become executable merely because a strategy exists.

The first Company consumer can reuse the foundation without forcing later Security, Fund, Branch, or mapping consumers into its schema. Conversely, the foundation can capture every GLEIF category without creating any MDM entity or graph edge.

## Recommendations

### Priority 0: Fix the foundation contract before implementation

1. **Define the publication aggregate and inventory invariants.** A publication becomes `verified_complete` only when every declared artifact is captured, hash-verified, parsed under a named contract, and reconciled to its manifest. Partial success never advances a checkpoint.
2. **Define the root run and phase-attempt model.** Bind acquisition, normalization, candidate generation, stewardship, MDM commit, export, graph, reconciliation, and retention evidence to durable lineage with immutable origin semantics.
3. **Define consumer-specific checkpoint keys and atomic advancement.** Use `(consumer, source_family, publication_family)` plus the exact committed publication/baseline. A checkpoint advances in the same transaction as the consumer's accepted evidence changes, never on capture alone.
4. **Define append-only evidence and decision tables.** Separate immutable source record versions, proposed candidates, stewardship decisions, and accepted temporal projections. Current-state MDM tables remain derived projections.
5. **Define authority and uniqueness constraints.** An installed source strategy grants no MDM authority. Enforce at most one active local binding for identifier families that require uniqueness, and quarantine conflicts before publication.

### Priority 1: Apply one pattern at the correct seam

**Use Strategy.** It lets source-publication discovery, continuity, completeness, and normalization change without touching ledger authorization, immutable capture, run binding, or domain publication.

**Domain shape:**

```text
Active Source Family Registry
          |
          v
Publication Coordinator ---- selects ----> EnrichmentPublicationPolicy
          |                                  |-- GLEIF Golden Copy
          |                                  |-- GLEIF Delta
          |                                  `-- GLEIF Mapping Publication
          |
          +---- per artifact ----> existing CaptureFacade
                                      |-- Fetch Decision + fenced lease
                                      |-- immutable S3 Bronze write
                                      `-- Change Ledger finalization
          |
          v
Verified normalized source evidence
          |
          +----> Company consumer checkpoint + transaction
          +----> Security consumer checkpoint + transaction
          +----> Fund consumer checkpoint + transaction
          `----> deferred nonpublishing evidence
```

Suggested responsibilities, not implementation names:

- `EnrichmentPublicationPolicy`: discover one native publication, enumerate its declared artifacts, verify publication-level completeness/continuity, and normalize source records.
- `PublicationCoordinator`: load the active registry contract, invoke the policy, call the existing capture Facade for each artifact, and persist one verified publication inventory.
- `CaptureFacade`: retain the current authorization, fencing, hashing, immutable-write, read-back, and ledger-finalization behavior unchanged.
- `CompanyEnrichmentConsumer`, `SecurityEnrichmentConsumer`, and peers: explicit independently deployed consumers; each owns domain rules, checkpoint, transaction, rollback, and release evidence.

### Rejected patterns

- **Not Template Method:** variation must be selected by the active registry at runtime, and the existing code intentionally uses first-class policy objects rather than an inheritance hierarchy. Subclass hooks would hide control flow and make every source inherit unrelated steps.
- **Not Bridge:** source families and MDM domains are not a freely combinable cross-product. Most source/domain pairs are prohibited or deferred by authority and semantics, so two extensible hierarchies would advertise invalid combinations.
- **Not Command:** Step Functions, the acquisition command registry, run manifests, and durable ledgers already provide delayed execution, logging, and replay identity. A class per enrichment action would duplicate those mechanisms without supplying missing evidence constraints.
- **Not State:** lifecycle transitions must be enforced across processes and transactions in Snowflake Postgres. Database constraints and append-only transition evidence are stronger than in-memory state classes.
- **Not Composite:** a publication owns many artifacts, but clients should not treat publications and artifacts uniformly. A relational aggregate and inventory constraint are clearer.

### Priority 2: Preserve what is already working

Do not change these boundaries while writing the specification:

- AWS-only deployment, S3 immutable capture, Snowflake native pull, and Snowflake Postgres MDM writes.
- The Fetch Decision before network access, fenced lease ownership, content-addressed Bronze objects, and read-back verification.
- Active registry versioning and fail-closed rejection of unsupported acquisition/completeness contracts.
- SEC authority for CIK, filings, and reported financials; GLEIF authority only for its published evidence.
- Independent consumer checkpoints, releases, rollback, budgets, and operational ownership.
- Immutable origin `run_id` on existing MDM evidence and no backfill fiction for historical unknowns.
- Deferred evidence for unsupported domains and missing endpoints; no generic entity creation and no name-only automatic links.

### Priority 3: Require test seams in the specification

The specification should name pass/fail tests before code is written:

| Layer | Required proof |
| --- | --- |
| Unit | Policy manifest parsing, artifact inventory, continuity, record hashing, classification, and invalid-state rejection |
| Contract | Every active registry declaration maps to an installed policy with matching cadence, acquisition mode, completeness, and parser contract |
| Database integration | Invalid transitions, duplicate active bindings, cross-consumer checkpoint advancement, and unbound evidence fail closed |
| Storage integration | Same bytes deduplicate while observations remain distinct; mismatched bytes quarantine; a partial publication never verifies |
| Replay | Frozen publication artifacts reproduce identical record inventory, hashes, candidates, decisions, and checkpoint proposal |
| Negative publication | Foundation replay produces zero MDM current-state, export, or graph mutations |
| Recovery | Missing/corrupt/discontinuous delta selects a provably covering larger delta or full reconciliation without advancing failed families |
| Rollback | Consumer rollback restores projections/checkpoint while preserving source evidence, decisions, and run lineage |

## Conclusion

The accepted architecture is directionally correct and has a proven GoF seam. The right move is not to add more patterns. Extend Strategy once, at source-publication scope, and preserve the existing capture Facade as the invariant authority boundary. Put lifecycle, checkpoint, uniqueness, and lineage guarantees in durable schemas and transactions.

The design is ready for `docs/specs/mdm-enrichment/shared-foundation.md` after the specification fixes the seven data boundaries listed above. It is not ready for schema migration or runtime implementation. Company Ticket 17 should remain blocked until that specification passes offline replay and negative-publication review.

## Appendix

### A. Candidate selection trace

| Index | Evidence | Candidates |
| --- | --- | --- |
| What varies | Source publication discovery, inventory, continuity, and normalization | Strategy, Template Method |
| Cause of redesign | New source families have different formats/cadences while capture invariants stay fixed | Strategy, Bridge, Facade |
| Intent scan | Runtime-selected algorithm; unified safe entry; durable queued/replayable work | Strategy, Facade, Command |
| Applicability result | Runtime registry selection and multiple coordinated source operations are real; inheritance and source×domain cross-product are not | Recommend Strategy; retain existing Facade; reject Template Method, Bridge, Command |

### B. Evidence references

| File | Evidence used |
| --- | --- |
| `.scratch/mdm-enrichment-program/workstreams/00-shared-enrichment-foundation.md:10` | One AWS source-evidence path and required foundation contracts |
| `.scratch/mdm-enrichment-program/plan.md:69` | Phase 0 schema, run, checkpoint, replay, security, and exit gates |
| `.scratch/mdm-enrichment-program/plan.md:116` | Independent parallel consumer and checkpoint requirement |
| `.scratch/mdm-enrichment-program/plan.md:188` | Universal inventory, lineage, replay, rollback, parity, and cost gates |
| `docs/adr/0010-independent-source-grained-mdm-enrichment-consumers.md:5` | Accepted source-capture / domain-publication separation |
| `docs/adr/0007-bind-mdm-commit-evidence-to-originating-run.md:1` | Existing immutable-origin MDM run identity contract |
| `edgar_warehouse/acquisition/facade.py:1` | Existing non-bypassable capture Facade and its invariant responsibilities |
| `edgar_warehouse/acquisition/facade.py:60` | Narrow `SourceFamilyPolicy` Strategy protocol |
| `edgar_warehouse/acquisition/registry_ledger.py:436` | Six registry-selected policy factories and fail-closed mode validation |
| `edgar_warehouse/acquisition/models.py:45` | Durable fetch decisions and disposition constraints |
| `edgar_warehouse/acquisition/models.py:248` | Ordered source revision lineage and immutable Bronze reference |
| `edgar_warehouse/acquisition/models.py:500` | Versioned active source registry with activation gates |
| `edgar_warehouse/mdm/database.py:209` | Current source-reference identity shape |
| `edgar_warehouse/mdm/database.py:524` | Current attribute-stage provenance limits |
| `edgar_warehouse/mdm/database.py:571` | Current entity-pair match-review scope |
| `edgar_warehouse/mdm/database.py:608` | Run-bound MDM change evidence |
| `edgar_warehouse/mdm/database.py:888` | Temporal relationship evidence and immutable origin run |
| `edgar_warehouse/mdm/relationship_checkpoint.py:1` | Existing monotonic and resumable relationship checkpoint behavior |
| `edgar_warehouse/infrastructure/dataset_path_catalog.py:112` | Validated path catalog boundary |
| `tests/acquisition/test_facade.py:78` | Content-addressed capture and ledger finalization proof |
| `tests/acquisition/test_registry_ledger.py:190` | Registry activation and policy construction gates |
| `tests/mdm/test_run_identity.py:39` | Run identity columns, propagation, and immutable-origin proof |
| `tests/architecture/test_mdm_run_identity_wiring.py:1` | Nested Step Functions root-run propagation proof |

### C. Open design decisions for the foundation specification

These are specification decisions, not requests to implement:

1. Exact table names, keys, foreign keys, and temporal uniqueness rules for the seven record boundaries.
2. Whether the persistent root run belongs in the acquisition schema, MDM schema, or a shared control schema accessible to both without creating a second authority.
3. Exact transaction boundary between accepted decision, current MDM projection, and checkpoint advancement.
4. Publication-family taxonomy for GLEIF Level 1, relationships, exceptions, and independently scheduled mappings.
5. Delta continuity proof fields and the deterministic recovery-order algorithm.
6. Role grants for capture worker, publication coordinator, domain publisher, steward, Release Owner, and retention operator.
7. Exact S3 path templates and Snowflake native-pull manifests for normalized enrichment evidence.

### D. Review method and limitations

This was a static design review against repository state at commit `d4c597f34d7d1ce753c88f5853dcb476c3d6ff55` on 13 September 2026. It did not query live AWS, Snowflake, or GLEIF endpoints because the requested scope was design review only and the next deliverable is an offline specification. External cadence and format statements were treated as already accepted research inputs from the repository's 12 September 2026 GLEIF decision records, not independently re-verified here.
