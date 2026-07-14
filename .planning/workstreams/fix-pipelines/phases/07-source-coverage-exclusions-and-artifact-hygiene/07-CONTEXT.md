# Phase 7: Relationship Graph Consistency, Temporal Lineage, And Artifact Hygiene - Context

**Gathered:** 2026-07-12
**Status:** Ready for planning
**Source:** User design grill (`grill-me`)

<domain>
## Phase Boundary

Phase 7 establishes an end-to-end, always-consistent serving contract between MDM relationship
truth and the Snowflake-hosted Neo4j Graph Analytics projection. It adds temporal relationship
history, generation-based graph publication, exhaustive relationship coverage evidence, and the
silver/bronze artifact safeguards needed to prevent relationship inputs from regressing.

PostgreSQL MDM remains the derivation and staging authority. Consumers read MDM relationship
serving views and Neo4j graph views through the same verified Snowflake generation boundary.
Neo4j remains a query projection optimized for direct and multi-level relationship traversal.

</domain>

<decisions>
## Implementation Decisions

### MDM and Neo4j consistency
- MDM is authoritative for relationship truth; Neo4j is a fully replaceable relationship-query projection.
- MDM and Neo4j must match by relationship identity and query-relevant properties, not only by counts.
- Each expected relationship must be traceable through source evidence, a silver business key, an MDM relationship/version key, and a Neo4j edge/version key.
- Node and relationship data activate as one complete generation. Partial per-type or node/edge activation is prohibited.
- Neo4j stores only evidenced relationships. Coverage exclusions are metadata, never synthetic edges.
- Each registered relationship type must be classified per generation as `populated`, `valid_zero`, or `excluded`; missing, stale, contradictory, or undocumented states block activation.
- `valid_zero` is recomputed and evidenced independently for every generation.

### Generation publication model
- PostgreSQL MDM commits relationship changes and a publication request transactionally; ingestion and graph publication have separate lifecycle states.
- One centralized publisher coordinates generation creation, while generation partitions build in parallel.
- The coordinator snapshots a committed MDM watermark and fans out immutable node-type and relationship-type partitions.
- High-volume types may be hash-sharded by stable source identifier; start with one partition per type and configure sharding only where volume warrants it.
- Each partition publishes a manifest with row count, stable-key hash, property hash, source watermark, and input fingerprint.
- Successful content-addressed partitions may be reused when their inputs are unchanged; failed partitions retry independently.
- The only serialized operation is the final active-generation pointer update.
- Snowflake graph contract rows carry `GENERATION_ID`; stable Native App views select through a one-row active-generation registry.
- Both MDM serving reads and Neo4j graph reads use the same Snowflake active-generation pointer.
- New generations target activation within five minutes of MDM commit; warn after five minutes and emit a hard operational alert after fifteen minutes. Declared large backfills may publish once within a bounded maintenance window.
- Retain at least the latest three verified generations and every generation from the preceding 30 days, whichever retains more. Never delete the active generation or its immediate predecessor.

### Relationship identity, versions, and time
- Relationship type plus stable source and target entity identifiers define logical identity; an immutable MDM relationship ID persists across generations.
- Each temporal version has its own immutable relationship-version ID. Generation IDs never form part of edge identity.
- Relationship validity is date-granular: `valid_from_date` is inclusive and `valid_to_date` is exclusive. Nullable bounds mean unknown beginning or no known ending.
- Operational ingestion, synchronization, and activation metadata may retain timestamps; timestamps do not define business validity.
- Every relationship version declares date provenance (`reported`, `filing_date_proxy`, or `unknown`). Ingestion timestamps must never silently substitute for effective dates.
- Validity dates and provenance are authoritative in MDM and synchronized to Neo4j as typed edge properties.
- The active graph generation contains complete non-quarantined relationship history, including ended versions. Current views filter to today; historical queries accept an explicit date.
- Strict date-specific queries exclude relationships whose validity cannot be proven for the requested date. Callers may explicitly include unknown dates, and results must label temporal uncertainty.
- Direct relationships are authoritative in MDM. Ordinary multi-hop paths are computed in Neo4j at query time. Materialized derived relationships require deterministic business meaning, provenance, and freshness policy and must be labeled `derived`.
- Identical overlapping relationship versions merge provenance. Conflicting overlaps use explicit relationship-specific source-priority and deterministic tie-break rules; unresolved conflicts are quarantined and block activation.
- Ordinary workflows never physically delete relationship history. Corrections close, supersede, or quarantine versions. Physical deletion is a separately authorized, audited repair/compliance workflow.
- Entity merges remap graph traversal endpoints to the surviving canonical entity ID while preserving original source identity and entity-merge lineage.

### Relationship coverage exclusions
- Coverage policy is machine-readable and consumed by graph verification and generation activation.
- `MANAGES_FUND` is `source_unavailable`: active-universe ADV primary attachments are paper filings without obtainable electronic documents.
- `HAS_PARENT_COMPANY` is `capability_not_implemented`: Exhibit 21 or equivalent parent/subsidiary capture and parsing is absent. It must not be mislabeled as unavailable source data.
- Exclusion records contain relationship type, category, exact source/parser dependency, evidence timestamp, evaluated population fingerprint, review trigger, and status.
- `MANAGES_FUND` fingerprints the evaluated adviser CIK/accession population. `HAS_PARENT_COMPANY` fingerprints the company universe and parser-capability version.
- Any relevant fingerprint change makes an exclusion stale. Stale exclusions fail coverage verification and prevent generation activation.
- Exclusions live in the generation coverage manifest with expected edge count zero; they never create placeholder nodes or edges.

### Semantic silver publication
- File size is never the authority for canonical silver health.
- Ordinary silver publication is monotonic: it rejects loss of protected canonical business keys and cannot be bypassed with `--force`.
- A partial local candidate is merged into a localized canonical copy, validated, and then promoted; it never directly overwrites canonical state.
- Protected domain-data tables use a fail-closed reviewed registry declaring business keys and deterministic provenance-based conflict policies. Ephemeral logs, checkpoints, staging, and temporary tables are excluded explicitly.
- A new domain table without a declared policy fails closed.
- Same-key differing values never use blind local-wins behavior. Per-table policies select an authoritative row using source timestamps/versions; ambiguous conflicts abort and emit a row-level report.
- Ordinary publishing permits additive compatible schema evolution only. Drops, incompatible type changes, key changes, and table removal require the explicit migration/repair workflow.
- Publishing records the canonical S3 object version/ETag, validates the merged candidate, and promotes only when canonical state is unchanged. A conflict aborts for explicit retry; it never silently uses last-writer-wins.
- Destructive corrections use a separate operator repair path with intent, dry-run diff, and audit output.

### Bronze artifact idempotency
- Artifact idempotency is enforced at the shared filing-artifact service boundary for every filing type, plus command-level DEF 14A and 13F regression tests.
- An intact immutable bronze artifact produces zero SEC network calls unless explicit artifact repair is selected.
- Bronze `--force` remains available only as a clearly labeled artifact-repair operation and records accession, previous object hash/version, replacement hash/version, operator context, and reason.
- Bronze `--force` does not imply or grant any silver monotonicity bypass.

### Required phase-exit evidence
- A partial silver candidate merges without losing canonical business keys.
- An ambiguous same-key row conflict aborts with a report.
- A simulated concurrent canonical update prevents promotion.
- Cached bronze artifacts cause zero SEC network calls.
- EDGE-07 reports `source_unavailable` without synthetic graph edges.
- EDGE-08 reports `capability_not_implemented` without synthetic graph edges.
- A deliberately stale exclusion fails verification and prevents activation.
- MDM and Neo4j match by stable node/edge identities and query-relevant properties for the active generation.
- Temporal direct and multi-hop queries respect `[valid_from_date, valid_to_date)` and strict unknown-date behavior.
- Entity merges preserve source lineage while restoring canonical graph connectivity.
- A failed partition retries without rebuilding unchanged content-addressed partitions.
- A failed generation leaves the prior verified generation active; rollback succeeds within the retention window.

### Plan structure
- `07-00`: mandatory live Native App capability preflight for contract loading, typed dates, supported graph metadata, BFS/multi-hop traversal, and stable-view generation switching. Semantic parity is the health authority, the platform-owned generation registry is the discovery authority, and experimental inventory APIs are informational only.
- `07-01`: relationship identity, temporal contract, provenance, direct/derived rules, source priority, and conflict handling.
- `07-02`: exhaustive generation coverage manifest, `valid_zero`, and EDGE-07/08 exclusions.
- `07-03`: transactional MDM publication queue, watermarks, lifecycle states, freshness SLO, and alerts.
- `07-04`: parallel generation builder, partition manifests, selective sharding, content-addressed reuse, and independent retries.
- `07-05`: Snowflake active-generation boundary, atomic activation, complete node/edge parity, historical graph queries, rollback, and retention.
- `07-06`: semantic silver merge/promotion, protected-table/conflict policies, optimistic concurrency, and bronze artifact idempotency/repair audit.
- `07-07`: bounded dev rehearsal covering exclusions, temporal traversal, entity merges, concurrency, partition retry/reuse, activation failure, and rollback.

### the agent's Discretion
- Exact PostgreSQL/Snowflake table and column names where existing repository naming conventions impose a better equivalent.
- Exact Step Functions fan-out implementation and ECS worker payload shapes, within the AWS-only architecture and outside passive Terraform.
- Initial hash-shard counts and the volume threshold for enabling sharding.
- Concrete source-priority order per relationship type where existing MDM rules or SEC semantics already establish precedence.
- Exact generation cleanup schedule, provided the locked retention floor is preserved.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope and evidence
- `.planning/workstreams/fix-pipelines/ROADMAP.md` — Existing Phase 7 scope, success criteria, and milestone dependencies.
- `.planning/workstreams/fix-pipelines/REQUIREMENTS.md` — EDGE-07, EDGE-08, ARTF-01, and ARTF-02 requirements.
- `.planning/workstreams/fix-pipelines/phases/06-relationship-investigation-and-population/06-03-LOAD-COVERAGE-EVIDENCE.md` — Current source/artifact coverage evidence.
- `.planning/workstreams/fix-pipelines/phases/06-relationship-investigation-and-population/06-PATTERNS.md` — Existing MDM and graph implementation patterns.
- `.planning/workstreams/claude-mdm-source-recovery/FINDINGS.md` — ADV paper-filing evidence for MANAGES_FUND.

### MDM and graph runtime
- `edgar_warehouse/mdm/models.py` — Current entity, relationship, source-priority, and sync-state schema.
- `edgar_warehouse/mdm/relationships.py` — Relationship derivation and provenance behavior.
- `edgar_warehouse/mdm/graph.py` — Current graph registry and synchronization abstraction.
- `edgar_warehouse/mdm/snowflake_graph.py` — Snowflake-hosted Neo4j contract tables, views, migration, sync, and verification.
- `edgar_warehouse/mdm/cli.py` — MDM derive/sync/verify command boundary.
- `edgar_warehouse/mdm/dashboard_readonly.py` — Current pending graph-sync health semantics.

### Artifact and silver publication
- `edgar_warehouse/application/warehouse_orchestrator.py` — Canonical silver localization/publication and filing artifact flows.
- `edgar_warehouse/bronze_filing_artifacts.py` — Shared immutable filing-artifact cache behavior.
- `edgar_warehouse/infrastructure/filing_artifact_service.py` — Shared artifact refresh service boundary.
- `edgar_warehouse/infrastructure/object_storage.py` — S3 object operations available for optimistic promotion.
- `tests/application/test_warehouse_orchestrator_mdm.py` — Current remote silver publication tests.
- `tests/unit/test_loader_idempotency.py` — Current artifact idempotency and force-path tests.

### AWS execution
- `infra/scripts/deploy-aws-application.sh` — Operator-managed ECS task definition and Step Functions deployment path.
- `edgar_warehouse/application/` — Runtime command registry and workflow definitions.
- `infra/terraform/accounts/dev/` — Passive AWS infrastructure boundary; must not own runnable workloads.

</canonical_refs>

<specifics>
## Specific Ideas

- Stable Snowflake Native App views should switch generations by reading a one-row active-generation registry rather than being recreated individually.
- Partition manifests should permit equality checks through stable-key and property hashes before expensive row-level diff diagnostics.
- Relationship traversal APIs should offer current-by-default and explicit `as_of_date` behavior, with `include_unknown_dates` opt-in.
- Coverage manifests should make dashboards distinguish actual populated coverage, proven zero, unavailable source data, unimplemented capability, stale evidence, and pipeline failure.

</specifics>

<deferred>
## Deferred Ideas

- Adding non-AWS graph runtimes or restoring Neo4j Aura/Bolt deployment paths.
- Materializing arbitrary transitive closure relationships without an explicit business contract.
- Intraday business-validity precision; relationship validity remains date-only.
- Allowing destructive canonical silver changes through ordinary publication or `--force`.

</deferred>

---

*Phase: 07-source-coverage-exclusions-and-artifact-hygiene*
*Context gathered: 2026-07-12 via design grill*
