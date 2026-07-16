# EdgarTools Platform

The shared language for operating the AWS-first SEC EDGAR data platform and deciding whether a production release is ready for operators.

## Language

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
