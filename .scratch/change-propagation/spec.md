# Spec: Incremental Change Propagation

**Status:** ready-for-agent  
**Feature slug:** `change-propagation`  
**Related map:** [Incremental Change Propagation](map.md)  
**Decision baseline:** Accepted grilling recommendations through 2026-08-20

---

## Problem Statement

The platform currently has incremental-looking entry points, but it does not have one trustworthy change-processing contract spanning SEC acquisition, silver, MDM, gold, and Neo4j. Several stages rescan broad inputs, overwrite landing objects, infer completeness from missing files, depend on finite native load history, or rebuild complete downstream generations. A successful workflow can therefore mean that tasks ran without proving that every new, modified, or retired fact reached every required consumer exactly once in business meaning.

This creates four user-visible risks:

1. Agents and dashboards can read a mixture of publication states because silver, MDM, gold, and graph activation are not bound to one durable decision watermark.
2. Corrections and retirements can be missed because current contracts primarily represent rows that exist, not the authoritative completion of a source scope or the removal of a formerly current member.
3. A replay, retry, parser upgrade, or overlapping run can repeat expensive work, overwrite an immutable-looking landing key, or allow an older result to win.
4. Operators cannot prove that a run was bounded to its affected-key closure, nor reliably roll serving state back to the last complete cross-stage publication.

The platform needs an incremental change-propagation process that selects only new or semantically modified source revisions, explicitly represents retirements and complete empty scopes, computes the smallest correct downstream closure, and publishes stage-local immutable results. The process must converge under at-least-once delivery, preserve the accepted architecture in which silver is the Runtime System of Engagement, keep bronze persistence optional, and expose only complete aligned publications as Agent-Grade Read state.

## Solution

Introduce an immutable **Change Propagation Run** coordinated by a durable PostgreSQL ledger. A run freezes a selected set of logical source revisions, the contract/parser/configuration versions used to interpret them, the dependency policy used to calculate their **Affected-Key Closure**, and the set of expected stage producers. Late arrivals go into a later run. Retries reuse the frozen selection and produce new attempts, while corrected content or changed interpretation creates an explicitly related child run.

Every selected source revision is normalized into a `SourceChange` whose identity is independent of transport. Direct SEC acquisition and bronze replay emit the same contract; a bronze object reference is optional. Content-addressed immutable objects carry row payloads, while the ledger, manifests, and queues carry identities, hashes, versions, scope declarations, and locations.

Silver producers publish three lifecycle operations:

- `UPSERT` supplies a complete authoritative row for the selected revision.
- `RETIRE` closes a previously current row without deleting its history.
- `SCOPE_COMPLETE` proves the authoritative membership of a replacement scope, including a complete empty scope.

Silver landing keys are immutable and include table, run, producer, logical batch, and content hash. Snowflake loads only files named by a verified manifest. A Snowflake transaction applies the scope mutation and records its publication marker atomically. PostgreSQL uses a prepare, external transaction, read-back verification, finalize protocol with fenced attempts and a transactional outbox. Missing output is never interpreted as successful emptiness; no-impact work records an explicit outcome.

The dependency registry combines dbt lineage with code-owned MDM and graph mappings. Its version is frozen into each run. It translates committed silver publications into the smallest correct keys, scopes, partitions, models, and graph partitions for downstream processing. Reads may examine a wider indexed candidate set when algorithms require neighbors, but writes remain bounded and the candidate and mutation counts are recorded.

MDM consumes sealed silver publications, applies domain-content hashes to all entity families, evaluates only affected domains and their versioned neighbor closure, writes asynchronous enrichments to separate overlays, and transactionally emits graph publication events with canonical mutations. Full reconciliation uses the same rules and emits only differences.

Gold refreshes only affected models and their minimum correct partitions after their declared upstream barriers are complete. MDM-independent models may proceed after silver; MDM-dependent company models wait for the matching MDM publication. Dynamic tables remain available only when observed refresh behavior satisfies the bounded-work policy. Unexpected full refreshes are rejected or quarantined unless an operator explicitly authorizes a rebuild.

The graph becomes an immutable candidate-generation system backed by content-addressed node and edge partitions plus generation-membership records. Unchanged partitions are reused. A candidate freezes the exact eligible MDM row set, verifies full content, endpoint validity, eligibility, counts, digests, and parity, then activates through one Snowflake registry and pointer transaction followed by PostgreSQL finalization. Stable serving views preserve the Native App and dashboard contract, while compatibility views reconstruct generation-shaped physical relations during migration.

Each stage produces a local immutable publication identity. The coordinator marks a run `READY` only when every required stage has a terminal disposition, including explicit `NO_IMPACT`, and their input/output lineage aligns. The resulting composite **Decision Watermark** points to exact silver, MDM, gold, and graph publications plus the deployment cohort and policy versions. Agent-facing reads use only the last complete watermark. Explore surfaces may expose partial state only when clearly labeled as incomplete.

Migration proceeds through verified, non-serving candidates. First establish the ledger, contracts, identities, dependency registry, cohort manifest, and evidence skeleton. Then make silver landing and lifecycle publication correct, migrate MDM to Snowflake-backed reads and versioned overlays, finish dbt gold and retire the legacy Python full-snapshot path, wire selective MDM publication, introduce graph partition reuse, and finally enable the coordinator and Decision Watermark. Each source family moves through shadow, verified, authoritative, rollback-horizon, and legacy-removal states. At every phase, one serving authority remains active.

## User Stories

1. As a platform operator, I want each run to freeze its selected source revisions, so that late arrivals cannot silently change work already being verified.
2. As a platform operator, I want new arrivals after sealing to enter a later run, so that run membership remains immutable.
3. As a platform operator, I want retries to reuse the same frozen selection, so that transient failures do not create a different business result.
4. As a platform operator, I want corrected input or changed interpretation to create a related child run, so that repair lineage is explicit.
5. As a platform operator, I want to inspect a run's source revisions, affected keys, producers, publications, and outcomes, so that I can explain any serving result.
6. As a platform operator, I want to retry one failed stage without replaying completed stages, so that recovery remains bounded.
7. As a platform operator, I want to cancel unfinished work without invalidating completed immutable publications, so that safe partial recovery is possible.
8. As a platform operator, I want every required stage to report a terminal outcome, so that silence cannot be mistaken for success.
9. As a platform operator, I want explicit no-impact outcomes, so that a legitimately unchanged run is distinguishable from missing work.
10. As a platform operator, I want overlapping runs blocked only where their scopes overlap, so that unrelated changes can proceed concurrently.
11. As a platform operator, I want expiring leases protected by fencing tokens, so that a stale worker cannot finalize after ownership has moved.
12. As a platform operator, I want state-age and lease-churn alerts, so that stuck processing is detected before freshness is lost.
13. As a platform operator, I want a bounded production canary, so that a release proves the real incremental path without widening operational risk.
14. As a release owner, I want every publication bound to an immutable deployment cohort, so that code and data outcomes can be reproduced together.
15. As a release owner, I want state-machine versions and aliases instead of in-place-only definitions, so that rollout and rollback target exact orchestration code.
16. As a release owner, I want a machine-readable acceptance artifact, so that approval binds the exact candidate, datasets, publications, policies, and evidence.
17. As a release owner, I want skipped checks to prevent a passing verdict, so that incomplete validation cannot authorize activation.
18. As a release owner, I want each migration phase to have an activation and rollback checkpoint, so that failures do not force an all-or-nothing cutover.
19. As a release owner, I want old producers drained before an alias switch, so that incompatible runs are not redriven across a cohort boundary.
20. As a release owner, I want expand-and-contract schema changes retained through the rollback horizon, so that the prior cohort remains operable.
21. As a data engineer, I want direct SEC acquisition and bronze replay to emit the same source-change contract, so that persistence choice does not alter semantics.
22. As a data engineer, I want the bronze reference to be optional, so that bronze remains an archive and replay aid rather than a mandatory system boundary.
23. As a data engineer, I want source identity to include logical key, revision, content hash, and interpretation versions, so that byte and semantic changes are distinguishable.
24. As a data engineer, I want producer revisions to be monotonic per source key, so that delayed delivery cannot make an older revision current.
25. As a data engineer, I want arrival time used only for observability, so that clock ordering does not decide business precedence.
26. As a data engineer, I want immutable filing conflicts to fail closed, so that an accession cannot silently acquire contradictory content.
27. As a data engineer, I want mutable source snapshots to accept new content hashes as new revisions, so that authoritative corrections propagate.
28. As a data engineer, I want semantically identical content to record an observed no-op, so that transport churn does not cause downstream work.
29. As a data engineer, I want parser and configuration upgrades to reprocess unchanged bytes, so that interpretation changes are represented.
30. As a data engineer, I want periodic inventory reconciliation to enqueue only missing versions, so that completeness can be repaired without full replay.
31. As a data engineer, I want filing completeness to require the configured document set, so that partial filings cannot retire valid current facts.
32. As a data engineer, I want replacement sources to prove complete snapshot scope, so that absence can safely become retirement.
33. As a data engineer, I want parse failure to preserve the prior active scope, so that a malformed replacement cannot erase good data.
34. As a data engineer, I want complete empty snapshots to publish an explicit zero-member scope, so that authoritative deletion is representable.
35. As a data engineer, I want source payloads stored under immutable content-addressed keys, so that parallel attempts cannot overwrite one another.
36. As a Snowflake operator, I want loads driven by exact manifests, so that finite copy history and prefix polling are not correctness mechanisms.
37. As a Snowflake operator, I want every file checksum, row count, contract version, scope, and producer verified, so that corrupt or incomplete landing sets cannot publish.
38. As a Snowflake operator, I want scope updates applied in one transaction, so that upserts, retirements, scope completion, and publication markers become visible together.
39. As a Snowflake operator, I want one stream or cursor per consumer, so that independent consumers cannot steal one another's change position.
40. As a Snowflake operator, I want actual refresh actions and work statistics recorded, so that a successful refresh does not falsely imply incremental execution.
41. As a Snowflake operator, I want unexpected full refreshes rejected beyond a policy budget, so that cost and latency remain bounded.
42. As a Snowflake operator, I want operator-authorized full rebuilds labeled explicitly, so that exceptional maintenance is not confused with steady-state behavior.
43. As a silver consumer, I want an upsert to contain a complete row, so that partial enrichment cannot erase newer canonical fields.
44. As a silver consumer, I want asynchronous enrichments stored in keyed overlay relations, so that enrichment races cannot replace parser output.
45. As a silver consumer, I want retirements to close current validity while preserving history, so that corrections remain auditable.
46. As a silver consumer, I want each table classified by lifecycle behavior, so that snapshots, observations, projections, and audit data obey explicit semantics.
47. As a silver consumer, I want per-column authority policies, so that immutable evidence, current source values, enrichments, and derived fields merge correctly.
48. As a silver consumer, I want reject events deduplicated by source, parser, and fingerprint, so that retries do not inflate quality counts.
49. As a silver consumer, I want dormant datasets to stay dormant until a real producer exists, so that empty placeholders do not become false contracts.
50. As a data steward, I want every retirement linked to the source revision and scope proof that caused it, so that historical changes are defensible.
51. As a data steward, I want quarantined changes isolated from serving state, so that unresolved data cannot leak into current decisions.
52. As a data steward, I want operator exclusions to be immutable, explicit, and reasoned, so that poisoned inputs can be bypassed without hiding them.
53. As a data steward, I want an earlier unresolved revision to block only later revisions of the same source key, so that unrelated data keeps flowing.
54. As a data steward, I want reappearing members handled as new valid intervals, so that retirement and restoration history stays intact.
55. As an MDM operator, I want MDM to consume only sealed silver publications, so that entity resolution never races incomplete table output.
56. As an MDM operator, I want canonical content hashes for every entity family, so that unchanged entities skip resolution consistently.
57. As an MDM operator, I want a versioned closure policy, so that the reason an entity or neighbor was reconsidered is reproducible.
58. As an MDM operator, I want only affected domains and required neighbors evaluated, so that identity processing scales with actual change.
59. As an MDM operator, I want candidate reads and mutation writes counted separately, so that a wide lookup does not hide an unbounded rewrite.
60. As an MDM operator, I want canonical mutation and publication outbox insertion in one transaction, so that graph events cannot be lost.
61. As an MDM operator, I want relationship changes to participate in publication state, so that edge-only changes reach the graph.
62. As an MDM operator, I want eligibility rules shared across export, verification, and graph sync, so that stage disagreement cannot activate an inconsistent graph.
63. As an MDM operator, I want full reconciliation to use the same content and closure rules, so that it identifies drift without creating gratuitous mutations.
64. As a gold model owner, I want the dependency registry to identify exact upstream publications, so that each model refresh is causally explainable.
65. As a gold model owner, I want each model to declare its minimum correct partition, so that refreshes do not scan unrelated history.
66. As a gold model owner, I want MDM-independent models to run after silver, so that they do not wait on unnecessary identity work.
67. As a gold model owner, I want MDM-dependent models to wait for the matching MDM publication, so that joins cannot mix generations.
68. As a gold model owner, I want external Explore models refreshed only when their own inputs change, so that SEC runs do not trigger unrelated work.
69. As a gold model owner, I want the recorded outcome to include selected models, partitions, action, timestamp, row counts, work, and digest, so that boundedness is measurable.
70. As a graph operator, I want graph candidates built from an exact frozen eligible-row set, so that verification and activation refer to the same content.
71. As a graph operator, I want stable partition keys independent of run time and watermark, so that unchanged partitions can be reused.
72. As a graph operator, I want content hashes to cover nodes, edges, properties, evidence, endpoints, and eligibility, so that reuse never omits a meaningful change.
73. As a graph operator, I want graph generation metadata excluded from content hashes, so that identical content remains reusable across generations.
74. As a graph operator, I want retired, invalid, quarantined, or superseded facts absent from the current graph, so that graph state matches canonical eligibility.
75. As a graph operator, I want retries to reuse the candidate generation identity while recording distinct attempts, so that recovery is idempotent and auditable.
76. As a graph operator, I want candidate verification to cover partition completeness, digests, counts, endpoints, eligibility, and parity, so that activation is evidence-based.
77. As a graph operator, I want activation to change one Snowflake active pointer atomically, so that all graph readers switch generations together.
78. As a graph operator, I want active and recent verified generations retained, so that serving rollback is immediate.
79. As a graph operator, I want garbage collection to respect live watermark and generation references, so that rollback data is not deleted.
80. As a Native App consumer, I want stable node and edge views preserved, so that the physical storage migration does not break my contract.
81. As a dashboard consumer, I want compatibility relations available during graph migration, so that generation-filtered internal queries keep working until updated.
82. As an agent, I want reads pinned to the latest complete Decision Watermark, so that a decision never mixes silver, MDM, gold, or graph publications.
83. As an agent, I want the watermark to include cohort and policy versions, so that the decision surface is reproducible.
84. As an agent, I want incomplete or mismatched candidates barred from activation, so that partial work cannot become Agent-Grade Read state.
85. As an analyst, I want an Explore surface to label partial data clearly, so that I can inspect progress without mistaking it for an authoritative decision state.
86. As an on-call engineer, I want serving rollback separate from operational recovery, so that I can restore readers before diagnosing or repairing writes.
87. As an on-call engineer, I want a bad ready run preserved and superseded rather than mutated, so that incident evidence remains intact.
88. As an on-call engineer, I want a compensating child run for repair, so that correction lineage is explicit.
89. As an on-call engineer, I want overlapping new work paused during rollback reconciliation, so that the repair target does not keep moving.
90. As an on-call engineer, I want code rollback allowed only when schemas and publications remain compatible, so that rollback does not compound data corruption.
91. As a security operator, I want least-privilege stage roles, so that each worker can mutate only its owned records and destinations.
92. As a security operator, I want immutable S3 objects and cross-environment reference rejection, so that payloads cannot be overwritten or mixed across environments.
93. As a security operator, I want evidence artifacts free of secrets, so that release proof can be retained and reviewed safely.
94. As a test engineer, I want a versioned reference dataset covering every source family, so that lifecycle and closure behavior is regression tested.
95. As a test engineer, I want a domain-state oracle independent of the legacy pipeline, so that existing defects are not blessed as expected behavior.
96. As a test engineer, I want duplicate, missing, delayed, reversed, overlapping, and poisoned deliveries injected, so that convergence claims are demonstrated.
97. As a test engineer, I want failures injected at every prepare, external-write, verify, and finalize boundary, so that recovery behavior is proven.
98. As a test engineer, I want add, modify, retire, empty, unchanged, parser-upgrade, repair, and reappearance cases, so that lifecycle completeness is verified.
99. As a test engineer, I want expected and actual selected keys, partitions, models, candidates, and graph partitions compared, so that unexplained work fails acceptance.
100. As a test engineer, I want repeated no-op runs to plateau at zero business mutations, so that idempotency is observable across every stage.
101. As a test engineer, I want targeted and full reconciliation to agree with no unexplained drift, so that incremental correctness is continuously checked.
102. As a test engineer, I want rollback rehearsals for every migration phase, so that recoverability is proven before production authority moves.
103. As a cost owner, I want closure expansion, processed ratios, elapsed time, requests, and compute measured against budgets, so that “incremental” has an enforceable meaning.
104. As a developer, I want one versioned dependency registry shared by planning and runtime, so that affected-key selection cannot drift between stages.
105. As a developer, I want contract versions separate from parser and schema versions, so that compatibility and interpretation changes are managed independently.
106. As a developer, I want additive minor contracts and fail-closed incompatible majors, so that rolling deployments cannot silently misread events.
107. As a developer, I want generated database assets changed through their generators until retirement, so that deployment output remains reproducible.
108. As a developer, I want each source family migrated as a vertical slice, so that real end-to-end evidence arrives before broad legacy removal.
109. As a developer, I want legacy code frozen except for safety fixes during migration, so that the comparison baseline stays stable.
110. As a developer, I want a slice considered complete only after production evidence, rollback proof, horizon expiry, and legacy removal, so that “done” means one authoritative path remains.

## Implementation Decisions

### Governing semantics

- Silver remains the Runtime System of Engagement. Snowflake's Decision Contract remains the Agent System of Engagement. Bronze persistence is optional and must not become a required hop.
- Delivery is at-least-once. Correctness comes from immutable identities, deterministic state transitions, idempotent writes, explicit lifecycle operations, and reconciliation. The system must not claim exactly-once transport.
- A Change Propagation Run is an immutable selected set of logical source revisions plus frozen contract, parser, configuration, dependency, eligibility, and cohort versions.
- The Affected-Key Closure is the smallest set of source keys, business keys, dependent keys, scopes, models, and graph partitions required for correct downstream state. It is data recorded by the run, not an ephemeral query result.
- One run may contain multiple source families when they share the frozen policy and cohort. Selection closes at an item-count threshold or timer. Late changes belong to the next run.
- A run is Agent-Grade only when all required stage publications align and every expected producer has a verified terminal disposition.

### Identity and contract model

- Use distinct immutable identifiers for run, producer, attempt, file, stage publication, and composite Decision Watermark. An attempt identifier must never appear in a content path or business identity.
- Define `SourceChange` around source family, logical source key, monotonic source revision, canonical source content hash, change reason, event observation time, contract version, parser version, configuration version, and optional bronze reference.
- Filing source completeness requires the accession and full configured document set. Replacement sources such as submissions, company facts, catalogs, and ADV require a proved complete snapshot and declared replacement scope.
- Treat a later observation with the same versioned domain-content hash as consumed no-impact. Treat a new parser, configuration, or schema interpretation as reprocessing even when source bytes are unchanged.
- Emit one lifecycle envelope per business-key mutation. Group envelopes in an immutable manifest. Emit `SCOPE_COMPLETE` once per authoritative replacement scope rather than per row.
- Keep payload rows in immutable Parquet objects. Messages and ledger records carry only identities, versions, hashes, counts, scope declarations, and object references.
- Contract compatibility is versioned independently from parser and storage schema versions. Additive compatible changes use minor versions; incompatible major versions fail closed unless a declared adapter exists.

### Durable run ledger

- PostgreSQL is authoritative for run selection, lifecycle state, dependency closure, attempts, leases, external transaction attestations, publications, outbox delivery, and Decision Watermark readiness.
- Store constrained current-state records for efficient coordination plus immutable attempts, transitions, outcomes, exclusions, supersessions, and verification attestations. Do not build an unrestricted event-sourcing framework.
- Use the lifecycle `SELECTING`, `SEALED`, `SILVER_PUBLISHED`, `DOWNSTREAM_PROCESSING`, and `READY`, with terminal or exceptional states `FAILED`, `QUARANTINED`, and `SUPERSEDED`.
- Seal the expected producer set before any stage publication. A producer must report a verified publication, explicit no-impact, quarantine, exclusion, or failure outcome.
- Use expiring work leases with monotonically increasing fencing tokens. Every finalize operation checks the current token.
- Serialize revisions for the same logical source key. An unresolved earlier revision blocks only later revisions for that key.
- Use a prepare, external-commit, read-back-verify, finalize protocol across PostgreSQL and Snowflake. The external transaction writes its idempotency marker in the same transaction as target mutations.
- Insert each downstream outbox record in the same PostgreSQL transaction that finalizes the producing stage. Enforce uniqueness by source publication and consumer.
- Preserve durable identities, hashes, counts, transitions, decisions, attestations, and references beyond payload retention. Payload deletion requires expiration of replay, rollback, audit, and every live dependent watermark reference.

### Silver publication

- Classify every silver table as one of: authoritative scoped snapshot, immutable observation/evidence, derived projection, or append-only audit/quarantine.
- Define each column as immutable-first, latest-authoritative, independently enriched, derived, or operational-only. Merge and hashing behavior follows this policy.
- Compute canonical, versioned domain-content hashes that exclude operational timestamps, run identifiers, file names, and serialization differences.
- `UPSERT` always carries the complete row owned by its producer. Move asynchronously owned values, including MDM identifiers and independent scoring, to keyed overlay relations joined at query time.
- `RETIRE` closes the current validity interval with the causing source revision and scope proof. It never physically deletes history.
- A scoped snapshot includes scope identity, member count, ordered member-key digest, and `SCOPE_COMPLETE`. A valid complete empty snapshot publishes zero members and its completion marker.
- Parse failure or incomplete scope proof publishes no retirement and no scope completion; prior active state remains authoritative.
- Landing object identity includes table, run, producer, logical batch, and content hash. Files are immutable and retry attempts reuse their content identity.
- A manifest enumerates the exact files, checksums, row counts, contract/schema versions, source revisions, scopes, and expected producers for one publication.
- Snowflake loads only manifest-named files. Native copy history is operational evidence, not the idempotency authority.
- Apply all mutations for a table/scope and its publication marker in one explicit transaction. The marker records examined, inserted, updated, retired, unchanged, rejected, and quarantined counts plus content digests.
- Allow parallel processing for disjoint tables, partitions, keys, and scopes. Serialize or deterministically order overlapping scopes.
- Derived silver work consumes committed base-silver publications and their recorded closure, never uncommitted landing output.
- Datasets with no downstream consumer still produce a silver publication or explicit no-impact outcome. They do not manufacture downstream work.
- Keep the current filing-feed placeholder dormant until a real producer and lifecycle contract are implemented.
- Deduplicate rejects by source-change identity, parser version, and deterministic reject fingerprint.

### Dependency and affected-key planning

- Maintain one versioned dependency registry containing dbt model lineage plus code-owned MDM domain, relationship, overlay, graph-property, and eligibility mappings.
- Bind the registry version and calculated closure digest to the run before processing begins.
- Union causal inputs that affect the same target and schedule the target once. Preserve the full input-cause set for explanation.
- Permit algorithms to read a wider indexed candidate set where neighbor comparison is required. Record candidate counts and enforce bounded target writes.
- For gold, calculate the minimum correct time/business partition per affected model rather than using one global refresh range.
- Express model-specific barriers. MDM-independent gold work depends on matching silver publications; MDM-dependent gold work depends on matching silver and MDM publications.

### MDM processing

- Consume sealed silver publications, not mutable silver database state without a publication boundary.
- Apply canonical domain-content hashing to company, adviser, fund, person, security, and all relationship families.
- Define a versioned MDM dependency DAG and closure policy. Reconsider changed records, declared dependents, and neighbors whose canonical result could change.
- Store MDM-owned identifiers and other asynchronous results in versioned overlay relations keyed to the source row and MDM publication.
- Apply canonical entity and relationship mutations and enqueue graph publication events in one PostgreSQL transaction.
- Use a single versioned eligibility policy across MDM export, graph selection, graph verification, and serving. Eligibility covers validity, activity, quarantine, and supersession.
- Record exact input silver publications, closure, examined/written/skipped counts, relationship changes, unresolved/quarantine counts, overlay digest, eligibility version, and outbox watermark.
- Run full reconciliation through the same canonical hashing and mutation rules. Reconciliation reports drift and emits only differences.

### Gold processing

- Select exact models and minimum partitions from the frozen dependency registry and upstream publication identities.
- Continue to use dbt for gold model ownership. Complete migration away from legacy Python full-snapshot gold generation before making incremental gold authoritative.
- Observe actual Dynamic Table refresh action, data timestamp, rows changed, and work. Use Dynamic Tables only where repeated evidence stays within the model's bounded-work policy.
- Use explicit streams or deterministic incremental materialization when Dynamic Table behavior cannot guarantee or demonstrate bounded processing.
- Treat an unexpected full refresh over budget as rejected or quarantined. Permit a full rebuild only through an explicit operator action recorded in the run.
- Exclude external Explore models from SEC-triggered runs unless their own upstream identities changed.
- Record for each gold publication the upstream publications, models, partitions, planned action, actual action, aligned data timestamp, rows, work metrics, output digest, and exceptions.

### Graph publication

- Consume a sealed MDM publication, its exact outbox watermark, and its frozen eligibility policy.
- Freeze the exact eligible MDM rows used to build a graph candidate. Later MDM changes belong to another candidate.
- Partition nodes by versioned node type plus a stable hash of entity identity. Partition edges by versioned relationship type plus a stable hash of logical relationship identity.
- Compute content hashes over the complete canonical nodes, edges, properties, evidence, endpoints, and eligibility representation. Exclude generation identifiers, run identifiers, and committed watermarks from content hashes.
- Store immutable content-addressed node and edge partition rows separately from generation-membership records. Reuse a partition only when its complete canonical content hash matches.
- Include changed entities, relationships, endpoints, property projections, and eligibility effects in graph closure.
- Make the candidate generation identifier stable across retries; store attempts separately.
- Verify every expected partition, content digest, node/edge count, endpoint reference, eligibility rule, and parity assertion before activation.
- Activate the candidate by atomically updating the Snowflake generation registry and active graph pointer, then verify the read path and finalize PostgreSQL state.
- Preserve stable public graph views. Provide temporary compatibility views that reconstruct generation-shaped node and edge relations for direct internal consumers while those consumers and grants migrate.
- Retain the active generation, a bounded set of verified predecessors, and every generation referenced by a live Decision Watermark or rollback record.
- Garbage collection is reference-aware and must never infer safety from age alone.

### Coordination and readiness

- Coordinate stages through short-lived workflows triggered from transactional outboxes. Do not create one long-running cross-stage workflow as the correctness authority.
- Relay sealed work on demand to AWS messaging with fencing and idempotency. AWS messaging is delivery infrastructure; PostgreSQL remains the authoritative queue and state record.
- Allow conditional parallelism in the stage DAG. Independent gold can run beside MDM; graph and MDM-dependent gold wait for MDM.
- Make retries stage-local and scope-local. Do not replay already verified upstream work for a downstream transient failure.
- Cancellation preserves verified publications, prevents the run from becoming Agent-Grade, and moves unfinished work to an explicitly related child run when processing resumes.
- `READY` requires every planned target to have a verified publication or a justified terminal no-impact disposition and requires all publication lineage to match the run's frozen inputs.
- Build the Decision Watermark as a composite pointer to exact stage publications, graph generation, deployment cohort, contract versions, dependency registry, and eligibility policy.
- Agent-facing reads resolve only the last complete active Decision Watermark. Partial Explore reads carry an explicit incomplete-state warning and cannot be used as the decision contract.
- Provide operator commands to inspect, explain, retry, repair, supersede, cancel, reconcile, and show affected closure for a run.
- Use this same contract for steady-state ingestion, replay, backfill, repair, and reconciliation. Their reason and selection policy differ; their lifecycle semantics do not.

### Migration and cutover

- Create a verified baseline that binds exact silver digests and inventories, Snowflake source state, MDM state, current gold outputs, active graph generation, cohort, and Decision Watermark.
- Rebuild candidate silver from the verified baseline plus immutable post-baseline source revisions. Do not treat historical mutable landing objects as a trustworthy rebuild source.
- Keep shadow candidates isolated and non-serving. The old path remains the sole serving authority until a phase's reconciliation and approval gate passes.
- Implement phases in this dependency order: contracts and ledger; immutable landing and candidate silver; silver verification; MDM Snowflake reads and overlays; dbt gold completion and legacy Python retirement; coordinated retirement of DuckDB readers/writers/shards; selective MDM outbox processing; graph physical reuse; coordinator and Decision Watermark.
- Reconcile the existing change-propagation tickets into these phases. Supersede or amend overlapping tickets instead of creating duplicate ownership.
- Drain old producers before switching an orchestration alias: stop new old-cohort runs, finish compatible executions, forbid cross-version redrive, capture a final baseline, then switch.
- Use expand-and-contract changes through the full rollback horizon. Remove old schemas and consumers only after no live run or retained watermark references them.
- Move each source family through `shadow`, `verified`, `authoritative`, `rollback horizon`, and `legacy removed` states.
- Start with company submissions and ticker/reference as the first vertical slice, followed by ownership Form 4. Continue with ADV, 13F, relationship families, financial/accounting, and text/evidence families.
- Keep the coordinator evidence-only until real stage publications exist. Do not let synthetic completion markers become serving authority.
- Use deterministic bounded canaries for each slice. A slice is complete only after authoritative production evidence, rollback proof, horizon expiry, and removal of its legacy producer/consumer path.

### Rollback, retention, and cleanup

- Separate serving rollback from operational recovery. Serving rollback moves the active composite watermark or graph pointer; operational recovery repairs or compensates writes.
- Retain silver publication history or an exactly reconstructable immutable representation. Maintain versioned MDM overlays and before/after mutation journals through the rollback horizon.
- Version agent-facing gold outputs or retain enough immutable inputs and verified procedures to restore the prior Decision Watermark without mixing newer state.
- On a bad ready run, move serving pointers to the last verified watermark, pause overlapping work, preserve the invalid run and its evidence, create a compensating child run, and reconcile before resuming.
- Allow code rollback only when the prior cohort is compatible with the retained schemas and publication contracts. Otherwise perform a forward repair.
- Set retention to the maximum of replay horizon, rollback horizon, longest expected run duration, audit requirement, and every live publication or watermark reference. This replaces the current short time-only cleanup assumptions.
- Rehearse both serving rollback and operational recovery at every migration phase.

### Delivery organization

- Build a small shared foundation first: contracts and hashing, PostgreSQL ledger, S3 identity conventions, prepare/verify/finalize protocol, dependency registry, deployment cohort identity, and evidence schema.
- Implement vertical source-family slices test-first rather than broad horizontal rewrites.
- Freeze legacy behavior except for safety and correctness fixes required to keep the comparison authority stable.
- Use isolated worktrees and non-overlapping ownership. Assign one serialized owner for shared orchestration, schema generators, and deployment surfaces.
- Perform the required design-pattern review before changing each existing code surface. Prefer local functions and narrow protocols; introduce a pattern only when current coupling and change history justify it.
- Land changes in dependency order: contracts and tests, shared foundations, producer and silver slice, downstream consumers, coordinator and acceptance, cutover, then legacy deletion.
- Continue generating deployed SQL and orchestration artifacts from their existing generators until the generator is explicitly retired.

## Testing Decisions

### Confirmed highest seam

The highest acceptance seam is **Change Propagation Run to Agent-Grade Read**. A test starts with a frozen set of source revisions and ends only when either:

- a complete Decision Watermark exposes the expected silver, MDM, gold, and graph state; or
- the run remains non-serving with a precise terminal reason and no partial state visible through the decision contract.

This seam must assert both business state and bounded work. A correct final row set is insufficient if the run scanned or rebuilt unexplained unrelated data.

### Test layers

- Contract and unit tests cover canonical hashing, identities, source revision ordering, lifecycle reduction, scope completion, compatibility versions, closure calculation, leases, fencing, state transitions, and no-impact outcomes.
- Local integration tests exercise immutable manifests, duplicate delivery, transactional publication markers, outbox finalization, scoped retirement, overlay joins, MDM closure, gold selection, graph partition reuse, and pointer activation with local substitutes where practical.
- Dev AWS/Snowflake end-to-end tests use the repository's dev account connection contract and real S3, messaging, ECS orchestration, PostgreSQL, Snowflake, and graph services. They must create a new post-deploy execution and inspect failed or caught states rather than trusting top-level workflow success.
- Isolated candidate reconciliation compares the new path with the versioned domain oracle and with the legacy serving path as diagnostic evidence. The legacy path never defines expected truth.
- A bounded production canary uses a deterministic source set and explicit work budgets. It publishes one machine-readable acceptance artifact and requires human approval of that artifact's digest before authority moves.

### Reference dataset and oracle

- Commit a versioned synthetic and sanitized reference dataset spanning every supported source family and hard lifecycle case.
- Define expected state at the domain level: source revisions, current and historical silver rows, retirements, scopes, MDM identities/relationships/overlays, gold partitions/results, graph content, and final watermark lineage.
- Include add, modify, unchanged re-observation, complete retirement, complete empty scope, parse failure, parser upgrade, configuration upgrade, operator repair, quarantine, supersession, and reappearance.
- Include conflicting immutable filings, changed mutable snapshots, sparse accounting updates, asynchronous MDM enrichment, relationship-only changes, and property-only graph changes.

### Delivery and failure matrix

- Run every scenario with duplicate, missing, delayed, reversed, and overlapping deliveries.
- Inject failure after prepare, after payload upload, during external transaction, after external commit but before acknowledgement, during read-back verification, before PostgreSQL finalize, after finalize but before outbox delivery, and during activation.
- Expire a lease and let a second worker acquire a higher fencing token; prove the stale worker cannot mutate or finalize.
- Retry the same frozen run and prove stable business identities, reused immutable payloads, and distinct attempt evidence.
- Create a corrected child run and prove it supersedes only the intended source revision and affected closure.
- Inject a poisoned source change and prove its scope is blocked or explicitly excluded while unrelated scopes continue.

### Stage assertions

- Silver assertions compare exact current and historical keys, content hashes, validity intervals, lifecycle reasons, scope membership counts/digests, rejects, and publication markers.
- MDM assertions compare exact input publications, candidate closure, canonical entity and relationship mutations, overlay content, quarantine state, outbox records, and eligibility decisions.
- Gold assertions compare selected models, minimum partitions, actual refresh action, aligned timestamps, row changes, output digests, and measured work.
- Graph assertions compare selected partitions, reuse versus rebuild decisions, complete node/edge/property/evidence content, endpoints, membership, candidate verification, serving pointer, compatibility views, and rollback generations.
- Decision Contract assertions prove every reader resolves one complete watermark and that partial or mismatched publications cannot leak into Agent-Grade views.

### Boundedness and idempotency

- Persist expected and actual selected source keys, business keys, dependent keys, scopes, candidate reads, mutations, gold models/partitions, and graph partitions. Any unexplained work fails the test.
- Define per-slice budgets for closure expansion, processed-to-changed ratio, elapsed time, compute, object requests, Snowflake work, and graph rebuild ratio.
- Repeat a completed run with no new semantic changes. The plateau must show zero silver business mutations, zero MDM decisions, zero gold partition changes, and zero graph rebuilds while still recording explicit no-impact outcomes.
- Compare targeted reconciliation with full reconciliation and require zero unexplained state drift.
- Verify incomplete, mismatched, quarantined, or superseded publications cannot activate or become the active Decision Watermark.

### Rollback and security

- Rehearse serving rollback to the prior composite watermark without mutating historical publications.
- Rehearse operational recovery through a compensating child run and prove that a repaired run can advance from the restored watermark.
- Verify reference-aware cleanup retains every live and rollback-referenced object, publication, overlay, gold output, and graph partition.
- Exercise least-privilege roles, environment isolation, cross-environment reference rejection, immutable object enforcement, and secret-safe logs/evidence.

### Existing testing seams to extend

The implementation should extend the repository's established seams rather than inventing separate harnesses: CLI and workflow entry points; silver event-reducer and landing-export idempotency tests; daily, batch, and release resume tests; MDM reader and publication-queue protocols; graph generation, migration, verification, and activation tests; dbt manifest/model selection and Snowflake status checks; Decision Contract tests; and architecture checks for dashboard access, graph workflows, deployment manifests, and secrets handling.

### Acceptance artifact

Produce one immutable machine-readable artifact per release candidate containing the cohort identity, commit and image digests, contract/parser/configuration/dependency/eligibility versions, reference dataset version, run and publication identities, expected and actual closures, stage outcomes, reconciliation results, boundedness metrics, failure-injection results, rollback results, security checks, exceptions, and final verdict. A required test recorded as skipped, unknown, or missing prevents a passing verdict. Human approval binds the artifact digest.

## Out of Scope

- Replacing `edgartools` as the SEC access and ownership parsing library.
- Changing silver's role as Runtime System of Engagement or the Snowflake Decision Contract as Agent System of Engagement.
- Making bronze persistence mandatory for steady-state ingestion.
- Adding non-AWS deployment, storage, registry, secret-management, or workflow-engine paths.
- Claiming exactly-once message delivery or using a distributed transaction across PostgreSQL, S3, Snowflake, and Neo4j.
- Physical deletion of source or business history as part of retirement processing.
- Rebuilding all source families in one release or performing a flag-day cutover.
- Treating the legacy pipeline as the expected-state oracle.
- Replacing dbt wholesale, or adopting Snowflake-native dbt execution as part of this change.
- Rebuilding Explore-only external datasets merely because an SEC change-propagation run occurred.
- Redesigning the public Native App graph interface; stable node and edge views remain the contract.
- Broad IAM expansion, new long-lived runner credentials, or runtime secret values managed by passive Terraform.
- Production deployment, data migration, or activation as part of this planning artifact.
- Legacy cleanup before its source-family slice has passed production acceptance and its rollback horizon has expired.

## Further Notes

- This spec is the canonical synthesis of the accepted recommendations from the diff-processing grilling. It refines the existing change-propagation map and tickets; it does not authorize implementation outside an assigned ticket or workstream.
- The existing ticket set must be reconciled against this spec before execution. Update or supersede overlapping tickets and preserve their historical links instead of opening duplicate tasks.
- Four focused ADRs must be accepted before the corresponding hard-to-reverse implementation: Change Propagation Run and ledger authority; stage publication identities and composite Decision Watermark; scoped replacement and historical retirement semantics; and content-addressed graph partitions with generation membership.
- Existing accepted ADRs remain controlling: silver is the exclusive Runtime System of Engagement, bronze is optional, `edgartools` owns SEC interaction, the Agent Decision Surface is the serving boundary, and the Loader Role governs Snowflake ingestion.
- Snowflake native histories are useful operational evidence but are not durable correctness ledgers. Copy deduplication has finite retention, Dynamic Table refresh can be non-atomic across selected leaves, and a successful refresh does not prove bounded incremental work.
- Current landing layouts can collide when parallel windows share a run identifier, and object writes can overwrite the same key. Immutable content-addressed paths and exact manifests are therefore a prerequisite, not a later optimization.
- Current graph generation physical tables duplicate complete generations, while stable serving views already provide a migration seam. Physical partition reuse must include migration of direct internal consumers, grants, verifier, cleanup, and activation logic before compatibility views can be removed.
- The first implementation plan should target the company submissions plus ticker/reference vertical slice and should explicitly identify the smallest code ownership surface, tests, candidate reconciliation, activation gate, rollback procedure, and legacy removal condition.
