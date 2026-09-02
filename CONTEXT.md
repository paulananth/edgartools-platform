# EdgarTools Platform

The shared language for the AWS-first SEC EDGAR data platform: production operator readiness, and the decision-support facts consumed by trading agents (and humans auditing those facts).

## Language

### Snowflake operational roles

**Deployer Role**:
The account role that creates and owns Terraform-managed Snowflake infrastructure (warehouses, schemas, the dashboard Streamlit app) — deployment of infrastructure, not ownership of pipeline data objects.
_Avoid_: Owning EDGARTOOLS_GOLD dynamic tables or the manifest-pipeline procedures, running dbt against gold

**Loader Role**:
The account role that owns and refreshes the pipeline's data objects — the EDGARTOOLS_GOLD dynamic tables and the manifest-pipeline procedures (LOAD_EXPORTS_FOR_RUN, REFRESH_AFTER_LOAD, PROCESS_RUN_MANIFEST_STREAM) — deliberately distinct from the Deployer Role so that pipeline-object ownership cannot drift to whichever role happens to run `dbt run` or a manual fix that day; `dbt run --target prod` and the manifest task must always execute as this role.
_Avoid_: Reusing the Deployer Role or ACCOUNTADMIN for gold-table/procedure ownership, letting ownership vary by whichever role last touched an object

**Reader Role**:
The read-only consumption-layer role for dashboards and reports (the Streamlit-in-Snowflake dashboard runs as this role by Terraform pin; the standalone dashboard is bring-your-own-connection and not required to use it) — SELECT only, never owns or mutates pipeline objects.
_Avoid_: Granting write/ownership privileges, treating "dashboard" and "report" as distinct concepts (they are the same thing in this platform)

### Data plane (ingest and engagement)

**Staged Warehouse Object**:
An immutable, random-token-scoped warehouse object written before ETag-guarded promotion to a canonical silver key; it is operational scratch data, not bronze evidence or a release input after successful promotion.
_Avoid_: Canonical silver, bronze archive, release evidence

**Canonical Silver**:
The current objects at `warehouse/silver/sec/silver.duckdb` and `warehouse/silver/sec/shards/shard-{0-3}.duckdb` — the live typed Runtime System of Engagement. Current versions of these keys are not reclaim candidates.
_Avoid_: Staged Warehouse Object, identity-refresh run snapshots, historical gold `run_id=` copies

**Joined Live Key**:
The S3 object key after `StorageLocation.join()` prefixes `WAREHOUSE_STORAGE_ROOT` (already ending in `/warehouse`) onto a relative write path. Lifecycle filters match this key string, not the relative path.
_Avoid_: Using `silverstage/` as an S3 lifecycle prefix, treating the Python relative path as the object key

**VersionId Reclaim**:
Permanent removal of billed bytes on a versioned bucket by deleting specific `Key` + `VersionId` pairs. Key-only delete and `aws s3 rm` leave payloads billed behind delete markers.
_Avoid_: Recursive `s3 rm`, Terraform one-shot deletes, unversioned DELETE

**Runtime System of Engagement**:
Silver warehouse state (typed tables after parse) is the authoritative published business state against which processors compute Lifecycle Diffs; the Change Ledger decides acquisition and processing eligibility and records completion.
_Avoid_: Silver as processing ledger, Bronze as business state, edgartools local disk cache as shared state, agent queries against DuckDB silver

**Agent System of Engagement**:
Snowflake Decision Contract objects only; agents never read silver or bronze directly.
_Avoid_: Runtime silver as agent API, ad-hoc SEC calls from the agent

**Human Explore System of Engagement**:
Labeled Explore Mode over Snowflake gold (and related analytics tables), not valid as Trading Decision input.
_Avoid_: Unlabeled explore as agent view

**SecGateway**:
The exclusive warehouse path for SEC network I/O, implemented with edgartools; every successful response eligible to affect warehouse state is captured as Bronze Persist evidence before processing.
_Avoid_: Parallel sec_client downloads for the same objects after cutover, parse paths that call SEC

**Verified-Evidence Acquisition Idempotency**:
Skip an SEC request only through a Change Ledger Fetch Decision backed by exact Verified Source Evidence, a sealed out-of-scope classification, or an operator exclusion; interpretation-version changes reprocess verified Bronze without redownloading.
_Avoid_: Silver row as download proof, S3 presence alone, parser upgrade as automatic refetch, worker cache decision

**Daily Identity Refresh**:
The recurring company-identity refresh for tracked entities whose recent SEC daily-index activity signals that their submissions state may have changed.
_Avoid_: Daily full-universe identity sweep, filing ingestion

**Identity Backstop Sweep**:
The periodic refresh of company identity across the complete active company-eligible universe (`entity_type = operating` or present in the captured canonical SEC ticker snapshot), covering administrative submissions changes that have no filing signal.
_Avoid_: Daily identity refresh, historical filing backfill, MDM Reconciliation Backstop

**MDM Reconciliation Backstop**:
The periodic full-universe MDM match, survivorship, and relationship re-derivation pass that catches drift a bounded 1-hop incremental pass cannot see: multi-hop ripple, below-threshold near-misses, and skip-if-unchanged hash staleness.
_Avoid_: Identity Backstop Sweep, Daily Identity Refresh, Per-Type Exact Relationship Parity, mdm reconcile, limited mdm mastering

**Identity Refresh Slot**:
One scheduled opportunity to run either a Daily Identity Refresh or an Identity Backstop Sweep; it may be completed or deferred but never overlaps another identity refresh.
_Avoid_: Concurrent refresh trigger, untracked skipped schedule

**Overdue Identity Backstop**:
An Identity Backstop Sweep displaced by an active refresh and therefore prioritized at the next available Identity Refresh Slot.
_Avoid_: Silently skipped weekly sweep, narrow refresh taking priority

**Identity Refresh Batch Delta**:
The immutable, CIK-batch-scoped company-identity result produced within one Identity Refresh Run; it is not canonical silver and is eligible for consolidation only after its declared batch succeeds.
_Avoid_: Per-batch canonical publication, mutable shared batch output, treating a partial delta as a completed refresh

**Identity Refresh Reducer**:
The sole run-scoped publisher that verifies the complete Identity Refresh Batch Delta set, merges it with canonical silver, and performs the one ETag-guarded canonical promotion for that refresh run.
_Avoid_: Distributed canonical writers, canonical publish before complete-batch verification, bypassing the existing merge and promotion guard

**Identity Refresh Run**:
The immutable execution identity binding one selected CIK universe, one reference snapshot, one warehouse image, its declared batch deltas, and (only after complete verification) one canonical silver publication.
_Avoid_: Reusing successful deltas with changed inputs or image, retrying a failed batch as a new unbound refresh, publishing a partial run

**Identity Reference Snapshot**:
The once-per-Identity-Refresh-Run global ticker and reference-data result consumed by the Identity Refresh Reducer together with the complete batch-delta set.
_Avoid_: Reference fetch/write per CIK batch, a reducer combining deltas with an unbound or later reference version

**Identity Refresh Publication Retry**:
A bounded retry of only the Identity Refresh Reducer after an interrupted or ETag-conflicted promotion; it rehydrates canonical and re-merges the same verified Identity Refresh Run inputs without repeating batch capture.
_Avoid_: Re-running successful batches for a publication race, replacing run inputs during retry, unbounded silent retries

**Identity Refresh Aggregate Integrity**:
The reducer processes the declared batch-delta set in its manifest order and rejects any ambiguous same-key merge conflict, so no partial or arbitrarily resolved identity refresh can become canonical.
_Avoid_: Arrival-order merge, last-writer-wins conflict handling, publishing a subset after a rejected delta

**Bronze Persist**:
Mandatory immutable evidence of every successful source response eligible to affect warehouse state, recorded before its processing decision.
_Avoid_: Optional raw archive, changed-content-only capture, Bronze as processing-state authority

**Bronze Artifact**:
One immutable source byte sequence addressed by its canonical content identity; multiple Source Captures may reference the same artifact while retaining distinct observation provenance.
_Avoid_: Payload copy per poll, mutable latest object, request ID as content identity

**Raw Evidence Hash**:
The digest of the exact source bytes that identifies one Bronze Artifact without claiming those bytes represent a business change.
_Avoid_: Domain hash, request identity, transport metadata as meaning

**Canonical Source Hash**:
A versioned digest of source content after removing transport-only representation differences but before interpreting it as business facts.
_Avoid_: Raw-byte equality as semantic equality, unversioned normalization, parsed-row hash

**Domain Content Hash**:
A versioned digest of the business meaning produced under one interpretation identity, excluding operational timestamps, attempts, paths, and serialization details.
_Avoid_: Ingest timestamp in change identity, run ID in business hash, raw artifact checksum as row meaning

**Lifecycle Diff**:
The business-key comparison between one complete interpreted source revision and the prior authoritative Silver publication, yielding changed or new upserts, scope-proved retirements, unchanged members, or explicit no-impact.
_Avoid_: Rewrite unchanged scope, byte-difference mutation, absence without Scope Completion

**Pinned Silver Publication**:
The exact authoritative Silver state against which a Lifecycle Diff is calculated; the Change Ledger records its identity and the resulting publication evidence without duplicating Silver row authority.
_Avoid_: Mutable latest during diff, PostgreSQL row copy as business authority, unpinned read

**Scope Publication Fence**:
The compare-and-swap guard requiring an overlapping Silver mutation to retain its Pinned Silver Publication as the current predecessor; disjoint scopes may publish concurrently.
_Avoid_: Last-writer-wins, stale diff commit, global Silver lock

**Bronze Evidence Retention**:
Every distinct Bronze Artifact is preserved indefinitely as replay and audit evidence; archival storage transitions are allowed, but deletion requires an explicit audited exception.
_Avoid_: Delete after processing, automatic retention expiry, duplicate-byte version accumulation

**Ledger Reinitialization**:
Restoration of local processing authority from a new complete Source Authority baseline beginning at the recovery point, without reconstructing lost historical ledger decisions.
_Avoid_: Infer old decisions from Bronze, pretend historical continuity, resume from an unverified partial baseline

**Initial Ledger Bootstrap**:
The first production Ledger Epoch established through the same authorized Hybrid Source Baseline, catch-up, verification, and cutover path used for later reinitialization.
_Avoid_: Import legacy checkpoints as authority, incremental start without baseline, separate untested bootstrap semantics

**Reinitialization Authorization**:
The explicit audited decision to create a new Ledger Epoch, naming its reason, baseline cutoff, source-family coverage contract, deployment cohort, and authority identity before recovery work begins.
_Avoid_: Automatic empty-ledger rebuild, implicit epoch creation, activation without evidence

**Hybrid Source Baseline**:
The complete starting state for a new ledger epoch, combining closed Source Authority change intervals with fresh complete snapshots for every source family lacking complete change capture.
_Avoid_: Filing-index-only recovery, stale Bronze inventory as current proof, ready with uncovered source family

**Baseline Coverage Contract**:
The sealed set of required source families and their accepted completeness proofs for a Ledger Epoch; every required family must complete before authority may activate.
_Avoid_: Partial baseline activation, automatic failure exclusion, unlisted required source

**Source Family Registry**:
The versioned authority contract naming each source family's logical keys, acquisition method, completeness proof, poll or change-discovery policy, and required Silver producers; an affected required family cannot activate under a new version without scoped baseline and catch-up evidence.
_Avoid_: Deployment-defined completeness, undocumented source addition, producer set inferred at runtime

**Registry Transition**:
A bounded change to a healthy epoch's Source Family Registry with an explicit effective boundary, affected-family baseline, catch-up, and activation gate; a new Ledger Epoch is reserved for initialization or lost ledger authority.
_Avoid_: Full epoch rebuild for every source change, deploy-time registry mutation, mixed registry versions without a boundary

**Baseline Catch-up Barrier**:
Proof that every source family covers its Hybrid Source Baseline through the sealed activation high-water mark, using a final complete snapshot wherever change capture is incomplete.
_Avoid_: Activate then catch up, rebuild acquisition blackout, unclosed baseline gap

**Ledger Epoch**:
One continuous period of local processing authority beginning at a verified Hybrid Source Baseline; evidence from earlier epochs remains historical unless explicitly selected for backfill, repair, or reprocessing.
_Avoid_: Inferred pending work across reinitialization, hidden epoch reset, historical Bronze automatically queued

**Environment Authority Boundary**:
The rule that fetch decisions, observations, Bronze evidence bindings, processing decisions, and epochs belong to one environment and account; external evidence requires an explicit checksum-verified operator import that creates local lineage.
_Avoid_: Dev capture satisfying production implicitly, shared mutable acquisition state, cross-account artifact reference without import authority

**Silver Baseline Candidate**:
A complete, non-serving Silver state rebuilt from one Hybrid Source Baseline to establish a new Ledger Epoch, activated only after its coverage, counts, and content are verified.
_Avoid_: Trust existing Silver after ledger loss, patch an unexplained state, serve the rebuilding candidate

**Immutable Source Conflict**:
Contradictory Bronze Artifacts observed under one immutable source identity; all evidence is retained and the source key is quarantined until an explicit repair decision resolves processing authority.
_Avoid_: First-writer-wins, latest-writer-wins, overwrite contradictory evidence

**Repair Revision**:
An immutable child revision that records which quarantined evidence may drive processing, which evidence was rejected, and the reason and authority for superseding the original conflict.
_Avoid_: Amend quarantined revision, delete rejected evidence, invisible operator correction

**Logical Source Revision**:
A verified source observation materialized after Source Capture, binding its reserved monotonic per-key position to canonical content and interpretation identities.
_Avoid_: Revision before evidence, consumer completion order, S3 arrival time as ordering, Bronze object path as business identity

**Source Observation Position**:
The monotonic per-key order reserved by a Source Fetch Decision before transport; not-modified, skipped, or failed attempts may leave unused positions without creating Logical Source Revisions.
_Avoid_: Dense revision requirement, response-arrival order, renumbering after retry

**Source Change**:
The transport-independent selection of a Logical Source Revision for a Change Propagation Run, carrying the Bronze Persist evidence reference for its source observation.
_Avoid_: Bronze object as the change itself, queue delivery as business identity, parser output row as source identity

**Change Ledger**:
The sole local authoritative record of each Logical Source Revision's processing disposition and progress; immutable source artifacts are evidence referenced by it, not competing control state.
_Avoid_: Bronze as processing-state authority, S3 listing as consumption state, dual authority

**Ledger State Record**:
The atomic pairing of constrained current state with immutable within-epoch transitions, attempts, outcomes, and reasons for one ledger-controlled lifecycle.
_Avoid_: Mutable status only, unconstrained event sourcing, current state without transition evidence

**Source Change Status**:
The Change Ledger's unified operator-facing projection for each discovered source candidate, showing its cause, fetch decision and state, Bronze evidence, logical revision, processing state, expected-producer progress, current blocker, and next action while immutable transition records remain the audit trail.
_Avoid_: Raw-table interpretation by operators, log-derived status, separate download and processing dashboards with conflicting truth

**Transition Ownership**:
The rule that each Change Ledger transition family has one authorized role, preventing workers from certifying their own publications or altering operator authority.
_Avoid_: Shared writer role, self-approved output, coordinator as universal database proxy

**Source Authority**:
The external publisher whose current source material defines what the platform may truthfully capture; for SEC-family data this is SEC or its designated source system.
_Avoid_: Bronze as original publisher, Change Ledger as source-content authority, downstream table as source truth

**Ledger-Gated Acquisition**:
No new source request may begin while the Change Ledger is unavailable; evidence from an already authorized in-flight request remains unprocessable until its original ledger lineage is reconciled.
_Avoid_: Local decision spool, Bronze fallback authority, ungated outage download

**Source Fetch Decision**:
The Change Ledger's required authorization or explicit skip decision for one source network request, recorded before any request is attempted and carrying the reason it may or may not proceed.
_Avoid_: Ungated SEC request, post-facto download audit, implicit skip

**Source-Key Fetch Ownership**:
Exclusive authority for one active source request against a logical source key; independent keys retain parallel fetch ownership.
_Avoid_: Same-key concurrent download, global fetch lock, deduplicate after racing SEC calls

**Fetch Attempt**:
One fenced execution of a Source Fetch Decision; a retry creates a new attempt while preserving the original cause, source position, request identity, and conditional validators.
_Avoid_: New source observation per retry, reused fencing token, racing finalization

**Fetch Cause**:
The immutable reason a Source Fetch Decision exists: a captured source discovery observation, a versioned poll policy, or an explicit operator repair, backfill, or reprocess request.
_Avoid_: Unexplained schedule trigger, worker-invented URL, missing causal lineage

**Poll Policy**:
The versioned Change Ledger rule for a source without complete change discovery, recording its last completed observation, next eligible time, conditional validators, and reason; a scheduler may request work, but only a due ledger decision authorizes the source call.
_Avoid_: Scheduler-owned acquisition truth, worker cache-age decision, post-facto poll authorization

**Discovery Manifest**:
The immutable, counted, and digested candidate set derived from one complete source discovery observation; every candidate must receive an explicit Fetch Decision before its interval closes.
_Avoid_: Downloaded-items-only inventory, omitted candidate as skip, workflow count as completeness

**Open Discovery Interval**:
A discovery interval with at least one required candidate still deferred or otherwise non-terminal; it remains incomplete, ages visibly, and cannot satisfy a baseline or catch-up barrier.
_Avoid_: Close with deferred candidate, timeout-to-skip, hidden coverage gap

**Acquisition Universe**:
The sealed, versioned set of source families, source keys, forms, and history boundaries for which source coverage and child-download decisions are authoritative.
_Avoid_: Entire SEC by implication, mutable tracking table as scope, unversioned command filter

**Universe Transition**:
A versioned Acquisition Universe change: additions require a complete scoped baseline, while removals end future coverage without rewriting or retiring Source Authority facts.
_Avoid_: Tracking-table-only change, delete facts on removal, incremental processing before added-key baseline

**Download Disposition**:
The explicit classification separating a terminal reason not to fetch, a temporary deferral, and the outcome of a request that was actually attempted.
_Avoid_: Generic skipped, rate-limit skip, treating not-modified as no request

**Not-Modified Observation**:
Evidence that an authorized source check found no new producer revision or content, linked to the prior Source Capture without creating new Bronze bytes or processing work.
_Avoid_: New source revision for every poll, invisible 304, no-impact Silver publication for an unchanged fetch

**Missing Source Artifact**:
An expected source candidate whose authorized fetch cannot obtain its artifact; it remains retryable or quarantined and never proves deletion or retirement by itself.
_Avoid_: 404 as retirement, not-found skip, close discovery interval without evidence

**Failed Source Response**:
A non-success source response retained as Fetch Attempt evidence with status, headers, timing, retry classification, and any diagnostic body reference; it creates neither a Bronze Artifact nor a Logical Source Revision.
_Avoid_: Error page as Bronze source data, 404 as source revision, logs as the only retry evidence

**Source Capture**:
A source response is durably acquired only when its immutable Bronze Persist evidence is verified and the exact evidence reference is finalized in the Change Ledger.
_Avoid_: Downloaded on network receipt, unverified upload success, untracked Bronze object

**Verified Source Evidence**:
The Change Ledger binding between an exact source identity, canonical checksum, terminal Source Capture, and verified Bronze Artifact required to prove that source need not be downloaded again.
_Avoid_: S3 path existence, Silver row as download proof, unverified artifact reference

**Orphaned Capture**:
Verified Bronze evidence whose authorized fetch was not finalized in the Change Ledger; it may be reconciled only to that pre-existing Fetch Decision, otherwise it remains quarantined.
_Avoid_: S3-created ledger authority, delete-and-forget evidence, attach to a different request

**Processing Decision**:
The Change Ledger's classification of a Source Capture using both its logical content identity and its interpretation identity, determining whether processing is required or explicitly has no impact.
_Avoid_: Checksum-only skip, parser-blind deduplication, implicit no-op

**Interpretation Reprocess**:
New processing work over existing Verified Source Evidence caused by a changed parser, schema, contract, or configuration identity, without requiring a new source observation.
_Avoid_: Redownload for parser change, mutate prior interpretation, worker-selected evidence

**Processing Disposition**:
The explicit, reasoned classification of a captured revision as processing-required, no-impact, out-of-scope, operator-excluded, superseded, quarantined, retryable-failure, or processed.
_Avoid_: Generic process-skipped, free-text-only outcome, silence as success

**Processed Source Revision**:
A Logical Source Revision backed by a verified Silver publication or verified no-impact publication whose identity, counts, and digest are finalized in the Change Ledger.
_Avoid_: Parser success, landing upload, task success, workflow success

**Expected Producer Set**:
The sealed set of Silver producers, tables, and scopes that must each publish a verified outcome for one Logical Source Revision before it is processed.
_Avoid_: Infer expected output after execution, silence as no-impact, first-producer success as complete

**Source Lifecycle**:
The two independent Change Ledger histories for one source observation: its fetch decision and outcome, and its processing decision and outcome.
_Avoid_: Combined download-processing status, generic skipped, inference from workflow history

**Ordered Revision Queue**:
The per-key sequence of captured Logical Source Revisions awaiting processing; capture may advance, but a later revision cannot publish or become current before every earlier position has a terminal processing disposition.
_Avoid_: Fetch blocked by Silver completion, later-writer-wins, global processing order

**Gap Closure**:
An explicit exclusion or supersession that unblocks a later source position without claiming the closed revision was processed or advancing the cursor by itself.
_Avoid_: Exclusion as no-impact, partial publication activation, permanently poisoned key

**Complete-Snapshot Supersession**:
Automatic replacement of an earlier incomplete or quarantined mutable-snapshot revision by a newer revision that proves complete authority over the same replacement scope, with explicit ledger linkage.
_Avoid_: Partial newer snapshot wins, immutable filing supersession, unrecorded latest-wins

**Snapshot Coalescing Policy**:
The versioned source-family rule declaring whether multiple complete queued snapshots preserve distinct semantic history or may collapse to the latest complete state before processing.
_Avoid_: Universal latest-wins, worker-selected coalescing, coalesce immutable observations

**Coalescing Boundary**:
The point before any Silver producer publication commits for an older complete snapshot; coalescing is forbidden after this boundary.
_Avoid_: Coalesce partial publication, coalescing as rollback, stranded producer output

**Scope Completion**:
Proof that one Logical Source Revision authoritatively enumerates an entire replacement scope, including a valid scope with zero members.
_Avoid_: Missing output as empty scope, partial parse as complete, physical deletion as retirement proof

**Silver Landing Retirement Record**:
The explicit, append-only signal that a business key present in an earlier complete scope is absent from a newer Scope Completion for the same source family; written directly by the source family's own acquisition code into a shared landing companion relation the moment it proves the shrink, never inferred downstream from a missing row's absence.
_Avoid_: Absence-as-retirement, per-table bespoke retirement columns, inferring retirement at query/refresh time from what a collapse query didn't see

**Change Propagation Run**:
The immutable unit that binds one selected set of new, modified, or retired source facts to its parser/schema versions, Affected-Key Closure, expected producers, stage outcomes, and aligned publication watermarks.
_Avoid_: Mutable run ID, full-universe refresh, unbound retry, distributed transaction

**Affected-Key Closure**:
The smallest set of source keys, business keys, and derived dependents that must be recomputed for a Change Propagation Run to converge correctly without processing unrelated data.
_Avoid_: Literal changed rows only, full-universe recomputation, best-effort dependency selection

**Daily-Artifact Run Manifest**:
The immutable, ordered accession selection for one daily-artifact run, bound to its daily-index input identity, warehouse image, and parser/configuration versions; it is the only candidate set a resume may use.
_Avoid_: Re-selecting candidates on retry, mixing image or index inputs, adding repaired work through a later run's selection

**Daily-Artifact Outcome Ledger**:
The append-only, run-and-accession-scoped record of candidate attempts and dispositions. Successful work is final; only pending, retryable, or explicitly repair-authorized work may be resumed.
_Avoid_: Process-local telemetry as recovery state, overwriting failures, full-task rework after a partial success

**Daily-Artifact Repair Attestation**:
An immutable operator record that binds an immutable-content conflict, checksum evidence, repair action, and operator identity to one original manifest candidate before its bounded replay. It does not override the immutable-object guard.
_Avoid_: Accepting a mismatch silently, replacing an object without evidence, treating a new selection as repair

### Agent decision support

**Agent Decision Surface**:
The versioned, machine-readable set of SEC-derived facts and features an automated trading agent may read when forming a trading decision; humans may audit the same surface, but charts and dashboards are not the contract.
_Avoid_: Streamlit app as source of truth, research notebook export, ad-hoc SQL without a published contract, trading execution API

**Decision Feature**:
A named, typed field on the Agent Decision Surface with documented meaning, null semantics (unknown vs zero), and identity keys (for example CIK and fiscal period).
_Avoid_: Chart series, dashboard metric, unexplained column

**Trading Decision**:
An action choice formed by an agent *outside* this platform’s execution boundary (for example buy, sell, hold, size, or abstain); this platform supplies decision inputs, not order placement or portfolio management.
_Avoid_: Broker order, fill, portfolio rebalance inside the warehouse

**Human Audit View**:
A read-only UI (for example Streamlit-in-Snowflake) that shows the same facts available on the Agent Decision Surface so a person can verify what an agent would have seen.
_Avoid_: Primary product surface, customer research portal, operator release console

**Agent View Mode**:
A Human Audit View mode that renders only Decision Graph Bundle / Snowflake Decision Contract projections so a person can see what the agent is allowed to read at a Decision Watermark.
_Avoid_: Mixing unlabeled explore queries into agent view, calling free gold joins "what the agent saw"

**Explore Mode**:
A Human Audit View mode that may query gold (and related) tables beyond the Decision Contract for human investigation; it is not an input to Trading Decisions and must be visually and labeled distinct from Agent View Mode.
_Avoid_: Using explore as the agent source of truth, silent mode switching, explore without "not agent contract" labeling

**Decision Graph Bundle**:
The Agent Decision Surface unit of read: a multi-entity payload rooted at one subject (usually an issuer) that includes related entities and relationship edges the agent may use, bound to one Relationship Generation Snapshot / data watermark.
_Avoid_: Single-table company row, ad-hoc multi-query join by the agent, unbounded "whole graph" dump, Streamlit ego-network screenshot

**Bundle Subject**:
The primary entity the Decision Graph Bundle is built for (typically a company identified by CIK); related persons, advisers, funds, securities, and edges are included only as they attach to that subject under declared relationship types and applicability rules.
_Avoid_: Portfolio of tickers as one bundle, anonymous search result set

**Trading-Relevant Neighborhood**:
The v1 Decision Graph Bundle scope around a Bundle Subject: person edges that establish insider or reported executive employment, security/holding edges that establish ownership or institutional position when present, auditor edges when present, plus subject-level accounting Decision Features; adviser/private-fund structure is out of v1 unless it attaches through an already-included edge type.
_Avoid_: Full MDM type registry dump, ADV-first bundle, every historical edge without currency rules

**Current Neighborhood (default)**:
The Decision Graph Bundle edge set limited to Current-at-Watermark Relationships for the declared business date; ended or not-yet-current edges are omitted unless the consumer explicitly requests history.
_Avoid_: All generation-eligible edges as default, silent inclusion of former insiders as current

**Neighborhood History (optional)**:
Generation-Eligible Relationship Versions that are not current at the watermark, returned only when requested, each carrying temporal fields and an explicit not-current marker so agents cannot treat them as live.
_Avoid_: Default payload, history without valid_from/valid_to, mixing current and historical without flags

**As-Of Decision Features**:
Subject-level Decision Features published for the Bundle Subject at the bundle watermark: values must be the latest complete computation available for that as-of (not a stale prior export). Inputs may be multi-period history (for example 3y/5y CAGR, YoY growth); the *published* feature row is still a single current as-of view, with nulls when history is insufficient under declared rules.
_Avoid_: Shipping last week's factor file, treating null CAGR as zero, requiring the agent to recompute CAGR from raw facts for v1, conflating "uses historic inputs" with "may be stale"

**Primary Annual Feature Vector**:
The As-Of Decision Features taken from the most recent complete fiscal-year (FY) factor row available for the Bundle Subject at the watermark.
_Avoid_: Mixing FY and quarter metrics without labels, oldest FY, average of all years

**Latest Interim Feature Vector**:
When a non-FY fiscal period exists with period_end after the Primary Annual Feature Vector's period_end, its factor row is included alongside the annual vector and explicitly labeled as interim; otherwise it is omitted.
_Avoid_: Replacing FY with Q silently, inventing interim when none is newer than FY

**Snowflake Decision Contract**:
The v1 delivery of the Agent Decision Surface: published Snowflake objects (views, tables, or procedures) that return Decision Graph Bundles or their relational equivalent under a declared schema version; the Human Audit View queries these same objects.
_Avoid_: Streamlit-only data path, agent-private tables that diverge from audit UI, S3 file dump as the primary contract, undocumented ad-hoc gold joins

**Decision Watermark**:
The composite identity bound into every Decision Graph Bundle: Bronze Persist evidence-manifest identity, silver-derived parse/completeness claims (versions and section coverage), Relationship Generation Snapshot (or equivalent graph generation id), gold/feature as-of (run_id), and business date; a bundle is invalid for agent use if any required component is missing or the components are known to disagree.
_Avoid_: Wall-clock now, best-effort multi-table join without pins, gold-only or graph-only as sole identity

**Pure-SEC Decision Features**:
Decision Features derived only from SEC (and approved operator-supplied SEC-family) filings and platform calculations on those filings; market prices, market cap, and price-derived multiples are outside the Agent Decision Surface.
_Avoid_: PE, EV/EBITDA from prices, yfinance fields inside the bundle, silent nulls that look like "no market data loaded" mixed with accounting nulls without a separate market contract

**Decision Subject Universe**:
The set of Bundle Subjects eligible for agent consumption: entities in the platform tracked/active universe (MDM or company sync tracking status that marks the name as maintained), not every CIK that ever appears in raw gold rows.
_Avoid_: All COMPANY rows, ad-hoc one-off CIKs without tracking, investable cohort unless explicitly adopted later

**Bundle Coverage Flags**:
Structured present / empty / unavailable markers on each section of a Decision Graph Bundle (features, insiders, holdings, auditor, etc.) so partial data is explicit; empty means complete derivation with zero members, unavailable means the platform could not assert completeness for that section at the Decision Watermark.
_Avoid_: Omitting sections silently, zeros that mean "unknown", hard-failing the whole bundle for one missing optional section

**Decision Contract Version**:
An explicit integer (or major.minor) schema identity carried on every Decision Graph Bundle and Snowflake Decision Contract response; agents pin a supported version; breaking shape or semantics changes require a version bump.
_Avoid_: Docs-only changelog, watermark-only identity for shape, silent column renames

**Latest Complete Holdings Period**:
For institutional/13F-style holdings in a Decision Graph Bundle, the most recent report period that is fully loaded for the relevant managers/subject at the Decision Watermark; the section is still "current" under Current Neighborhood rules only relative to that lagged source period, and coverage metadata must expose the period and known reporting lag—not same-day market positions.
_Avoid_: Intraday holdings, treating missing 13F as zero position without unavailable, shipping all historical 13F periods in the default neighborhood

**Subject Feature Screen**:
A flat, Decision Watermark–aligned relation over the Decision Subject Universe of As-Of Decision Features (Primary Annual and optional Latest Interim labels) used to rank or filter many subjects without loading full Decision Graph Bundles.
_Avoid_: Full neighborhood in the screen, free gold joins labeled as the screen, screen without Decision Contract Version / watermark

**Subject Bundle Read**:
The single-subject retrieval of a Decision Graph Bundle (Trading-Relevant Neighborhood + features + coverage + watermark + contract version) for deep agent inspection before a Trading Decision.
_Avoid_: Requiring full-universe dump to inspect one CIK

**Deferred Access Control**:
v1 of the Agent Decision Surface does not implement product-level authentication (for example OAuth); access is whatever the operator's Snowflake (or equivalent) session already allows. The contract must remain callable behind a later pluggable access layer without changing Decision Feature semantics or bundle shape.
_Avoid_: Baking a one-off auth scheme into the bundle schema, blocking go-live on OAuth, assuming public internet exposure of Snowflake

**Agent-Grade Read**:
A Subject Bundle Read or Subject Feature Screen result whose Decision Watermark components are present and aligned; only Agent-Grade Reads are valid inputs to a Trading Decision. Misaligned or incomplete watermark components fail closed (no agent-grade payload), rather than best-effort join.
_Avoid_: Best-effort mismatched graph and features, silent degraded data for trading, "prefer gold" or "prefer graph" without invalidation

### Deployment orchestration (Step Functions)

**MDM Utility Machine**:
The single consolidated Step Functions state machine (`edgartools-prod-mdm-utility`) wrapping every MDM CLI subcommand behind one `{"mode": "<name>"}` execution input, generated by `write_mdm_utility_definition`. Consolidated (state-machine-consolidation wayfinder map, ticket 02) from 7 originally-separate one-machine-per-subcommand wrappers, which were later deleted outright once confirmed orphaned (ticket 05). The `mode` values (`mdm_run`, `mdm_sync_graph`, `mdm_verify_graph`, etc.) are internal dispatch keys, not live CLI subcommand names — mdm-stage-renaming ticket 01 renamed the underlying CLI subcommands (`mdm run`→`mdm mastering`, `mdm export`→`mdm publish`, `mdm sync-graph`→`mdm publish-relationships`, `mdm verify-graph`→`mdm reconcile`) without renaming these dispatch keys.
_Avoid_: "Exactly 7 machines" (stale — true only before consolidation); a `mode` value as a live CLI subcommand name; `generation_build` (a bespoke multi-stage pipeline, not mode-dispatched); `mdm_seed_universe` (its own standalone machine, explicitly excluded from consolidation — ticket 04)

**Single-Command Workflow Machine**:
The warehouse-side sibling of MDM Utility Machine: a Step Functions state machine wrapping exactly one warehouse CLI subcommand in a single ECS task (optionally wrapped in the `sec_fetch_active` lease for the two that call SEC at meaningful volume: `bootstrap_full`, `targeted_resync`), generated by the shared `write_single_workflow_definition` function — a different shared function from MDM Utility Machine's. 7 machines: `bootstrap_full`, `targeted_resync`, `full_reconcile`, `load_daily_form_index_for_date`, `catch_up_daily_form_index`, `gold_refresh`, `seed_universe`.
_Avoid_: MDM Utility Machine (MDM subcommands, mode-dispatched through one machine, not seven); Load History Machine / Graph Generation Build Machine (bespoke, no shared builder)

**MDM Pipeline Machine**:
A Step Functions state machine chaining a distinct head (bronze/silver capture, ownership parsing, or nothing) into the shared Publish→"Publish Relationships"→Reconcile tail (renamed from MdmExport→MdmSync→MdmVerify by mdm-stage-renaming ticket 01), usually ending in gold-refresh. Exactly 5 today: `mdm_gold`, `ownership_mdm_gold`, `silver_mdm_gold`, `bronze_seed_silver_gold`, `residual_holds_graph`.
_Avoid_: Treating these as duplicated in shape beyond the tail's ordering — the flags, Catch clauses, retry counts, and (for `bronze_seed_silver_gold`) an entire second "strict" branch are genuinely different per machine, not copy-paste variance (state-machine-consolidation wayfinder map, ticket 02 addendum)

**Warehouse Pipeline Machine**:
The warehouse-side sibling of MDM Pipeline Machine: a Step Functions state machine chaining bronze+silver capture into the MDM/gold tail, built from one shared template (`write_warehouse_mdm_gold_definition`) with a `daily_incremental`-specific branch (identity-refresh lease + windowed identity refresh ahead of capture). 1 machine: `daily_incremental` (`bootstrap` was the other one -- retired by state-machine-consolidation ticket 06: zero EventBridge schedule, exactly one execution ever, fully superseded by `daily_incremental`'s SEC-daily-index-driven selection; the shared template's `workflow_name`-keyed dispatch is left in place as a proven extension point rather than collapsed to a single caller).
_Avoid_: MDM Pipeline Machine (a distinct family whose head varies per machine, not one shared template); Single-Command Workflow Machine (one task, not a capture→MDM→gold chain); Load History Machine (a bespoke, more elaborately staged version of the same idea, not built from this shared template); `build_workflow_states` (a different function entirely -- namespaces the 7 Single-Command Workflow Machine workflows into the MDM Utility Machine's flat States dict, unrelated to this family)

**MDM Run Identity**:
The opaque correlation identity shared by every commit-evidence-producing MDM stage and retry in one MDM Pipeline Machine execution; a direct operator invocation or manual mutation request creates its own identity. Export, sync, and verification stages retain their existing execution correlation but do not accept this identity because they do not originate MDM Commit Evidence.
_Avoid_: ECS task-attempt identity, Relationship Generation Snapshot, wall-clock window, adding an unused identity argument to non-producing stages

**MDM Commit Evidence**:
The durable entity-change and relationship-version facts originated by one MDM Run Identity, used to count committed MDM outputs by type for that run; later mutation or export does not replace the originating identity.
_Avoid_: Full processing funnel, current-row last modifier, CloudWatch log window

**Graph Generation Build Machine**:
`generation_build` specifically — a bespoke partition-plan/fan-out-build/fan-in-verify/activate pipeline for a Neo4j-Snowflake graph generation. Has no sibling machine sharing its shape; not a duplication problem, and not the MDM Utility Machine despite being single-purpose.
_Avoid_: Grouping with the MDM Utility Machine as "standalone" or "single-stage" (an earlier ticket draft did this, before consolidation, and was corrected)

**Load History Machine**:
`load_history` specifically — the canonical ≥10-company loader, its own bespoke 4-stage pipeline (company-identity seed, windowed bronze+silver capture, fundamentals, MDM+gold), sharing no builder function with any other machine.
_Avoid_: Grouping with Single-Command Workflow Machine or Warehouse Pipeline Machine as if it shares their shape; `bootstrap_batched` (deleted, zero executions ever, superseded by this machine's sequential-windowed design)

**MDM Tail Sequencing Skeleton**:
The minimal, order-enforcing extraction from an MDM Pipeline Machine's tail — a shared helper that wires already-built `Publish`/`"Publish Relationships"`/`Reconcile` state dicts (renamed from `MdmExport`/`MdmSync`/`MdmVerify` by mdm-stage-renaming ticket 01) into the correct order (Publish before Publish Relationships, per `docs/data-architecture.md` Issue 3) and optionally appends `GoldRefresh`. Deliberately does not standardize each state's command flags, Catch clauses, or retry policy — those remain caller-owned, next to the comments explaining why they differ.
_Avoid_: A full unified "shared tail" abstraction covering flags/Catch/retry — rejected because the 5 MDM Pipeline Machines' tails are six genuinely distinct shapes, not one shape with parameters

### Production release readiness

**Current-Head Production Launch Readiness**:
The decision-complete evidence state for deploying an identified current release candidate through the production operator path.
_Avoid_: Historical go-live status, public launch readiness

**Release Candidate**:
An immutable integration-branch commit together with the exact warehouse and MDM image digests built from it; release evidence is valid only for that identity.
_Avoid_: Dirty checkout, floating branch tip, mutable image tag

**Release Evidence Manifest**:
The committed, secret-safe identity and evidence index for one Release Candidate, including its exact commit and warehouse/MDM image digests while excluding generated deployment details and sensitive infrastructure identifiers.
_Avoid_: AWS application manifest, prose-only release summary

**Release Data Watermark**:
The composite lineage identity that binds a release's bronze input, silver publication, Snowflake export, MDM publication, and hosted-graph generation to the same bounded data state.
_Avoid_: Latest data, single timestamp, business date alone

**Gate Attestation**:
A structured approval bound to one Release Candidate, Release Data Watermark, and evidence digest, issued by the named operator responsible for that gate.
_Avoid_: Prose sign-off, unbound approval, inherited PASS

**Live-Evidence Window**:
The 24-hour interval ending at the verified Release Seal timestamp during which every candidate-specific production-data, workflow, graph, Snowflake/dbt, dashboard, and Release Owner attestation must remain valid for the same Release Data Watermark. Standing mechanism-bound proofs such as the Rollback Rehearsal are referenced by the candidate but remain outside this window.
_Avoid_: Indefinite production proof, mixed-window evidence

**Candidate Evidence Set**:
The append-only manifest and secret-safe evidence directory for one Release Candidate, containing every preserved Evidence Attempt and retained whether its final disposition is GO, NO-GO, or superseded.
_Avoid_: Mutable latest report, overwritten failed attempt

**Evidence Attempt**:
An immutable set of candidate-specific gate evidence and attestations bound to one Release Data Watermark inside an open Candidate Evidence Set; a stale or failed attempt remains preserved when a later attempt supersedes it. It may reference a standing gate proof whose validity is independent of the attempt's watermark and clock.
_Avoid_: Overwritten evidence, mutable retry, new candidate for unchanged code and images

**Release Evidence Automation**:
The deterministic tooling that creates and validates a Candidate Evidence Set, binds sanitized gate artifacts to it, and rejects identity drift or incomplete evidence without manufacturing human approval.
_Avoid_: Hand-authored manifest, automatic approval

**Release Seal**:
A verified signed Git tag on the evidence commit containing the finalized GO manifest.
_Avoid_: Branch-tip approval, unsigned tag

**Operational Forensics Window**:
The seven-day period for which production CloudWatch execution and workflow logs remain directly queryable; durable run manifests and release evidence, not indefinite log retention, carry longer-lived proof.
_Avoid_: Treating CloudWatch logs as permanent evidence, retaining routine logs for 30 days by default

**Rollback Image Set**:
The current production image, the two most recent verified successful rollback images, and any additional image referenced by a currently running task; only this explicit set is protected from repository cleanup.
_Avoid_: Treating every registered task-definition revision as rollback intent, deleting a running-task image, unbounded tagged-image retention

**Release Authority Registry**:
The authoritative roster of identities allowed to attest release roles and seal a release; a Candidate Evidence Set cannot authorize its own approvers.
_Avoid_: Self-authorized signer, manifest-local trust list, unpinned approver roster

**Full-Chain Launch Pass**:
A release-candidate production execution in which every required workflow stage succeeds, including BatchSilver, MDM processing, MDM export, graph synchronization and verification, and gold refresh.
_Avoid_: BatchSilver-only pass, accepted downstream failure

**MdmExport Entitlement Preflight**:
A mandatory, fail-closed check immediately before every MDM export, also independently runnable by operators, that non-mutatively proves the deployed MDM runtime can use its injected production secret to reach the approved Snowflake target, match its expected execution context, run its warehouse, find all export targets with compatible schemas, and hold every effective privilege required by the export.
_Avoid_: Developer-connection check, release-only spot check, export-as-connectivity-test

**Production Target Marker**:
An opaque, non-secret identity value readable through the production Snowflake export path and pinned in the Release Evidence Manifest, whose exact match proves the runtime reached the canonical production target without exposing account identifiers.
_Avoid_: Account locator in Git, credential-payload self-identification, developer-account inference

**MdmExport Preflight Evidence**:
The versioned, deterministic, secret-safe result of one MdmExport Entitlement Preflight, bound to the Release Candidate and deployed MDM runtime identity and recording each capability check separately with freshness and sanitization metadata.
_Avoid_: Raw connector trace, CloudWatch-only proof, connection-success screenshot

**MdmExport Failure Disposition**:
One of `transient_retryable`, `operator_action_required`, or `unknown_fail_closed`, assigned by the MDM command before retry; only `transient_retryable` may consume the bounded command-owned retry budget.
_Avoid_: Blanket task retry, message-string guess, retry-unknown-by-default

**Data Integrity Gate**:
Release-candidate proof that bronze inputs reconcile to complete, uniquely identified silver filings and shard coverage, that a bounded rerun is idempotent, and that concurrent processing shows no contention or corruption.
_Avoid_: Clean-log check, map-success count

**Publish Contention Safety**:
Direct proof that concurrently processed BatchSilver work cannot lose an update because every overlapping publisher either writes a distinct immutable object or uses a guard that rejects stale publication; successful tasks, clean logs, and lucky final counts are insufficient substitutes.
_Avoid_: No-lock-errors inference, last-writer-wins upload, reconciliation-only concurrency PASS

**Table-Specific Reconciliation**:
Data Integrity Gate proof that each silver table touched by BatchSilver satisfies its own bronze-to-silver key expectations, declared primary-key uniqueness, required-parent integrity, and canonical semantic-content digest, including explicit legitimate-zero outcomes for optional and one-to-many parsers.
_Avoid_: Filing-count-only completeness, aggregate row-count equality, unexplained missing child rows

**Bounded Idempotency Rerun**:
A deterministic 16-batch, four-wave BatchSilver rerun at MaxConcurrency=4 against the unchanged Release Data Watermark, selected across routing bands, volume, boundary, parser, no-op, and guarded-publication cases to prove stable primary-key sets and semantic content without new bronze capture.
_Avoid_: Full rerun by default, hand-picked happy path, different-watermark comparison

**MaxConcurrency4 Data Integrity Evidence**:
The single deterministic, secret-safe artifact that binds a MaxConcurrency=4 BatchSilver execution to its Release Candidate and watermark and records every Map, table reconciliation, publication safety, no-refetch, observability, and bounded-rerun hard check without skipped results.
_Avoid_: CloudWatch transcript, prose checklist, split unbound reports

**Historical Reconstructed Integrity Result**:
A separately labeled technical assessment rebuilt from immutable historical execution, image, bronze, silver-object-version, log, and table evidence; it may support engineering confidence but cannot satisfy a current Release Candidate gate or the Live-Evidence Window.
_Avoid_: Retroactive current GO, stale Gate Attestation, reconstructed evidence presented as live

**Execution-Bound Integrity Capture**:
The ordered capture of a frozen bronze inventory, execution definition and batch manifest, post-full-run silver object snapshot, and post-rerun silver object snapshot for one unchanged Release Data Watermark within the Live-Evidence Window.
_Avoid_: Latest-state query, mixed execution evidence, mutable after-the-fact assembly

**Hosted Graph Completeness**:
The state in which every active, in-scope relationship at the release watermark is synchronized and MDM-to-graph parity is zero for each relationship type, with excluded types reported explicitly.
_Avoid_: Thin graph sample, aggregate-only parity

**Generation-Eligible Relationship Version**:
An authoritative relationship-version record committed by the generation watermark whose type is active, whose record is active, non-quarantined, and non-superseded, and whose canonical endpoints resolve to nodes included in that generation; ended history remains eligible.
_Avoid_: Is-active-only row, quarantined conflict, superseded version, dangling endpoint

**Current-at-Watermark Relationship**:
A Generation-Eligible Relationship Version whose proven date interval contains the release business date under `[valid_from_date, valid_to_date)` semantics; an unknown interval remains generation-visible but is not current for strict as-of traversal.
_Avoid_: Generation membership, unknown-date-as-current, timestamp-inclusive end date

**Relationship Coverage Record**:
The single fresh classification for one active relationship type in one graph generation: `populated` for nonzero eligible edges, `valid_zero` only when complete supported derivation over complete inputs proves zero, or `excluded` for a fingerprinted and approved source/capability boundary with a review trigger.
_Avoid_: Hardcoded populated type, inherited zero, undocumented exclusion, synthetic edge

**Approved Relationship Exclusion**:
A Release Owner-attested, generation-fresh decision that one registered relationship type is outside the current release scope because of an evidenced source or capability boundary, with zero MDM/graph edges, a population fingerprint, and an objective review trigger.
_Avoid_: Valid-zero workaround, permanent silent omission, technical gap without scope approval

**Required Relationship Type**:
A registered relationship type whose source population, derivation, generation publication, and Per-Type Exact Relationship Parity must complete before GO; a known ingestion gap is a hard blocker and cannot be converted into an exclusion or valid zero.
_Avoid_: Deferred required load, scope waiver after failure, unavailable label presented as complete

**Relationship Applicability**:
The evidence-backed determination that a required relationship type applies to a particular source/entity pair; completeness requires every applicable pair to be represented or explicitly resolved, while entities with no applicable source relationship legitimately have no edge.
_Avoid_: Edge for every entity, optional-type waiver, missing source treated as not applicable

**Relationship Applicability Ledger**:
The generation-bound, fingerprinted accounting of every source candidate for one Required Relationship Type as `applicable`, `not_applicable` with a stable reason, or `unresolved`; GO requires zero unresolved or missing candidates and binds applicable outcomes to exact MDM-to-graph parity.
_Avoid_: Entity-count denominator, unexplained no-edge entity, aggregate-only coverage

**Per-Type Exact Relationship Parity**:
Proof for one registered relationship type that the MDM eligible edge set and active hosted-graph edge set have equal counts, identities, canonical properties, temporal fields, valid endpoints, and Current-at-Watermark subset, with zero missing, extra, or leaked records.
_Avoid_: Aggregate edge count, count-only parity, staging-table-only proof

**Release-Bound Dashboard Approval**:
Operator approval of every launch-critical read-only dashboard view against the same release candidate and evidence watermark that passed the data and hosted-graph gates.
_Avoid_: Production-like UAT, stale-watermark approval, thin-sample approval

**Rollback Rehearsal**:
Pre-GO proof that operators can restore the prior approved image digests and safe concurrency setting using the documented AWS application rollout boundary without changing passive Terraform infrastructure.
_Avoid_: Unrehearsed rollback notes, post-launch-only recovery plan

**Direct-Evidence GO**:
A GO decision in which every hard gate has committed, secret-safe evidence tied to the Release Candidate and the signed Release Seal verifies against the finalized evidence commit; missing proof leaves the candidate not ready and cannot be replaced by risk acceptance.
_Avoid_: Conditional GO, accepted-basis PASS

**Direct-Evidence GO Packet**:
The Candidate Evidence Set used for the final decision: it is presented to the Release Owner while ready for review and becomes finalized only after the owner's GO attestation and verified Release Seal.
_Avoid_: Duplicate GO packet, parallel release summary, manually restated gate status

**Ready-for-Owner Candidate**:
A Release Candidate whose complete gate evidence and attestations validate for a Release Owner decision while its disposition remains unset; it is not yet GO.
_Avoid_: Preapproved release, automated GO, unsigned approval

**Release Decision Validation State**:
The readiness classification distinguishing incomplete evidence, readiness for a Release Owner decision, and effective sealed GO; human NO-GO and supersession remain separate dispositions.
_Avoid_: Conditional GO, warning-only GO, inferred NO-GO

**Production Operator Readiness**:
The state in which approved operators can deploy, verify, monitor, and recover the AWS, Snowflake, MDM, hosted-graph, and dashboard paths using bounded, secret-safe procedures.
_Avoid_: Customer launch, public dashboard launch

**Public Launch Readiness**:
The separate state in which customer-facing access, support, product policy, and external availability are ready; it is outside the current Wayfinder destination.
_Avoid_: Production operator readiness
**Relationship Generation Snapshot** — The transaction-consistent MDM and source-candidate state frozen at the committed Release Data Watermark. All eligibility, applicability, coverage, graph partitions, and parity evidence for one generation derive from this snapshot; later commits belong to the next generation.

**Relationship Source Coverage Window**:
The declared lower and upper source boundaries within which relationship history is complete; current-at-watermark proof may additionally require an entity-specific baseline before the upper boundary.
_Avoid_: All history, unspecified lookback, whatever is already loaded

**Required Relationship Source Candidate**:
An accession or metadata record that may establish, change, supersede, or disprove a Required Relationship Type inside the Relationship Source Coverage Window.
_Avoid_: Every entity, every 8-K, parsed row only

**Bulk-Load Completion Ledger**:
The generation-bound, accession-level accounting that binds every Required Relationship Source Candidate to verified artifacts, parser outcome, applicability, MDM relationship versions, and one allowed terminal status.
_Avoid_: Aggregate skipped count, workflow success, nonempty source table

**Reported Executive Employment**:
The `EMPLOYED_BY` scope evidenced by SEC proxy disclosure and Form 8-K Item 5.02 events for named executives or covered officers; it does not represent every employee of an issuer.
_Avoid_: Company workforce, compensation row as timeless employment, officer event without temporal effect
