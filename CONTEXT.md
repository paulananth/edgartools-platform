# EdgarTools Platform

The shared language for the AWS-first SEC EDGAR data platform: production operator readiness, and the decision-support facts consumed by trading agents (and humans auditing those facts).

## Language

### Data plane (ingest and engagement)

**Runtime System of Engagement**:
Silver warehouse state (typed tables after parse) is where ingest jobs decide whether work is already done and what to mutate next.
_Avoid_: Bronze as default SoE, edgartools local disk cache as shared SoE, agent queries against DuckDB silver

**Agent System of Engagement**:
Snowflake Decision Contract objects only; agents never read silver or bronze directly.
_Avoid_: Runtime silver as agent API, ad-hoc SEC calls from the agent

**Human Explore System of Engagement**:
Labeled Explore Mode over Snowflake gold (and related analytics tables), not valid as Trading Decision input.
_Avoid_: Unlabeled explore as agent view

**SecGateway**:
The exclusive warehouse path for SEC network I/O, implemented with edgartools; on miss it loads into silver (and bronze only under Bronze Persist rules).
_Avoid_: Parallel sec_client downloads for the same objects after cutover, parse paths that call SEC

**Silver-Once Idempotency**:
Skip SEC network when silver already holds successful work for the skip key (for filings: accession + form-family + parser_version; for facts: CIK + facts_parser_version; catalogs: checkpoint completeness), unless force or version bump requires refresh.
_Avoid_: Always re-fetch, skip only by bronze presence, accession-only forever skip that blocks parser upgrades

**Bronze Persist**:
Optional raw archive of SEC (or other) payloads written only when an operator explicitly requests it, or when the source cannot be obtained via edgartools; not the default hot path.
_Avoid_: Always bronze first, treating bronze absence as agent-grade failure by default

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
The composite identity bound into every Decision Graph Bundle: silver-derived parse/completeness claims (versions and section coverage), Relationship Generation Snapshot (or equivalent graph generation id), gold/feature as-of (run_id), and business date; bronze content hashes only when Bronze Persist was used; a bundle is invalid for agent use if any required component is missing or the components are known to disagree.
_Avoid_: Wall-clock now, best-effort multi-table join without pins, requiring bronze sha for every agent-grade read, gold-only or graph-only as sole identity

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
The 24-hour interval ending at the final GO decision during which every required production-data, workflow, graph, Snowflake/dbt, and dashboard Gate Attestation must remain valid for the same Release Data Watermark.
_Avoid_: Indefinite production proof, mixed-window evidence

**Candidate Evidence Set**:
The append-only manifest and secret-safe evidence directory for one Release Candidate, retained whether its final disposition is GO, NO-GO, or superseded.
_Avoid_: Mutable latest report, overwritten failed attempt

**Release Evidence Automation**:
The deterministic tooling that creates and validates a Candidate Evidence Set, binds sanitized gate artifacts to it, and rejects identity drift or incomplete evidence without manufacturing human approval.
_Avoid_: Hand-authored manifest, automatic approval

**Release Seal**:
A verified signed Git tag on the evidence commit containing the finalized GO manifest.
_Avoid_: Branch-tip approval, unsigned tag

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
A GO decision in which every hard gate has committed, secret-safe evidence tied to the Release Candidate; missing proof remains NO-GO and cannot be replaced by risk acceptance.
_Avoid_: Conditional GO, accepted-basis PASS

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
