# MDM Enrichment Program plan

## Outcome

Deliver external MDM enrichment as a portfolio of independently releasable,
source-grained consumers. One shared foundation captures and proves source
evidence; domain consumers decide whether and how that evidence may publish.

## Dependency graph

```text
Accepted program decisions
          |
          v
Shared enrichment foundation
          |
          v
Company + OpenCorporates tracer bullet
          |
          +----------------------+----------------------+
          |                      |                      |
          v                      v                      v
Security + ISIN            Branch + BIC        Fund relationships
          |                      |                      |
          +----------------------+----------------------+
                                 |
                                 v
                 Adviser/Audit-Firm legal-entity binding
                                 |
          +----------------------+----------------------+
          |                      |                      |
          v                      v                      v
Government + QCC/GEM   International organization   Market/Venue + MIC
          |
          v
Sole-proprietor/Person boundary

Conditional source decisions may run after the foundation contract is fixed;
an adopted source joins only the consumer whose domain and authority gates pass.

Production rollout, operations/stewardship, retention/cost control, and program
verification are cross-cutting gates on every releasable consumer.
```

## Workstream control contract

Every workstream inherits the Universal release gates below and has an owner
role and terminal outcome in the
[specification ownership index](spec-index.md). Its future specification must
name the exact source authority, immutable evidence inventory, domain owner,
operational owner, approved budget, and Release Owner. Until then, the role in
the index owns decision completion rather than production mutation.

Mandatory workstreams terminate only with a verified specification and the
production evidence required by their charter. A mandatory decision may instead
prove that evidence must remain captured-only. Conditional workstreams terminate
in `adopt`, trigger-bound `defer`, or reasoned `reject`; only `adopt` creates an
implementation specification. Cross-cutting workstreams terminate separately
for each consumer and finally at Enrichment Program Complete.

Authority is explicit at this resolution: GLEIF and its identified mapping
publication are authoritative only for the evidence they publish; SEC remains
authoritative for CIK, filings, and reported financials; IAPD and PCAOB retain
their existing Adviser and Audit Firm authority. Mapping certification proves a
published identifier/LEI pair, not the local MDM identity. A conditional source
has no production authority until its source decision is `adopt` and its
consumer specification fixes the narrower field-level contract.

## Phase 0 — Shared enrichment foundation

Owner: [Shared enrichment foundation](workstreams/00-shared-enrichment-foundation.md)

Specify and prove the reusable contracts before any consumer implementation:

- source registry, authority, license, cadence, and immutable publication identity;
- temporary S3 Bronze staging and low-cost immutable Source Artifact Archive
  retention for Level 1, relationship, exception, and mapping families;
- a Bookkeeping Root Run and Change Ledger authorization joined by one run
  identity spanning source, MDM, export, graph, and operator evidence;
- Change Ledger records for every logical pipeline transition and every physical
  S3 location or storage-class transition;
- independent family checkpoints, delta-gap recovery, full reconciliation, and
  deterministic replay;
- current-state disaster recovery from the newest ledger-authorized complete
  Source Publication, without an operational dependency on archive restore;
- latest-complete-publication retention per enrichment family, with
  Change-Ledger-authorized deletion of superseded bytes and permanent manifests,
  hashes, lineage, MDM Commit Evidence, and deletion evidence;
- temporary-only delta bytes retained through all required consumer and
  downstream verification, then deleted without an archive copy;
- permanent normalized evidence, Change Ledger and Bookkeeping history,
  stewardship decisions, temporal MDM history, manifests, hashes, lineage,
  MDM Commit Evidence, and deletion evidence independent of raw-byte retention;
- normalized source-grain evidence with temporal versions and record hashes;
- accepted-link, candidate, conflict, deferred-domain, and retirement states;
- stewardship decisions that never imply an entity merge;
- source-family observability, cost attribution, and reviewed retention hooks; and
- least-privilege AWS roles with capture, publication, release, and deletion
  authority separated.

Exit: the foundation spec, schema proposal, threat model, TDD seams, migration and
rollback plan, and offline replay fixture pass review. No production data is
published by this phase alone.

## Phase 1 — First evidence-backed Company consumer

Owners: [Company legal-entity enrichment](workstreams/01-company-legal-entity.md)
and [OpenCorporates-to-LEI mapping](workstreams/13-opencorporates-mapping.md).

Finish the existing Company map's specification task, then implement a bounded
tracer bullet:

- capture the complete current GLEIF Level 1, relationship, and exception baseline;
- import the 308 adjudicated links as seed evidence and revalidate every link;
- publish only approved or deterministic unique Company-to-LEI bindings;
- project the approved legal-form, jurisdiction, lifecycle, registration, and
  registration-authority fields without overwriting SEC evidence;
- capture all direct/ultimate consolidation records and reporting exceptions;
- publish relationships only when both endpoints are accepted Companies;
- retain missing endpoints and unsupported domains as nonpublishing evidence;
- ingest OpenCorporates mapping evidence at its native cadence without treating
  it as entity-merge authority; and
- prove daily delta, weekly candidate backstop, monthly reconciliation, replay,
  conflict review, rollback, and cost gates.

Exit: one immutable release evidence set passes every consumer gate in dev and
then in a bounded production canary approved by the Release Owner.

## Phase 2 — Parallel first domain consumers

After the shared foundation is stable, execute these independently and in
parallel where their edit surfaces do not overlap:

- [Security and issuer enrichment](workstreams/02-security-and-issuer.md) with
  [ISIN-to-LEI mapping](workstreams/10-isin-mapping.md);
- [Branch legal-entity enrichment](workstreams/04-branch-legal-entity.md) with
  [BIC-to-LEI mapping](workstreams/11-bic-mapping.md); and
- [Fund legal-entity relationships](workstreams/03-fund-relationships.md), keeping
  `IS_FUND-MANAGED_BY`, `IS_SUBFUND_OF`, and `IS_FEEDER_TO` distinct.

Each creates its specification and schema/test plan before code. A failure in one
consumer cannot roll back or advance another consumer's checkpoint.

## Phase 3 — Remaining explicit domains and open mappings

- [Bind accepted GLEIF identities to Adviser and Audit Firm](workstreams/05-adviser-audit-firm.md)
  without coercing them into Company.
- Add explicit [Government Entity](workstreams/06-government-legal-entity.md)
  and [International Organization](workstreams/07-international-organization.md)
  consumers.
- Resolve the [Sole Proprietor versus Person business-capacity boundary](workstreams/08-sole-proprietor-person-boundary.md)
  before any publication.
- Add a [Market/Trading Venue domain](workstreams/09-market-trading-venue.md)
  before [MIC](workstreams/12-mic-mapping.md) publication.
- Route [QCC](workstreams/15-qcc-mapping.md) and
  [GEM](workstreams/16-gem-mapping.md) evidence to accepted Company or
  Government identities at their native cadence.
- Keep every unsupported or unidentified endpoint in a deferred, nonpublishing
  state with an objective retry trigger.

Exit: every captured GLEIF category, relationship type, and open mapping record
has an explicit domain route or a reasoned nonpublishing disposition.

## Phase 4 — Conditional enrichment-source decisions

Evaluate [S&P CIQ](workstreams/14-sp-ciq-mapping.md),
[market data](workstreams/20-market-data-sources.md),
[sanctions](workstreams/21-sanctions-sources.md),
[ESG](workstreams/22-esg-sources.md),
[credit](workstreams/23-credit-sources.md), and
[other commercial-company sources](workstreams/24-commercial-company-sources.md)
independently. Every evaluation ends in:

- `adopt`: authority, license, value, safety, cadence, cost, replay, retention,
  and domain-owner gates pass;
- `defer`: a named missing prerequisite and objective review trigger; or
- `reject`: retained evidence and reason.

Adoption creates a new consumer-spec revision; it never injects the source into
the GLEIF job merely because the source also uses LEI.

## Phase 5 — Production and continuous operation

The [production rollout](workstreams/30-production-rollout.md),
[operations and stewardship](workstreams/31-operations-and-stewardship.md),
[retention and cost control](workstreams/32-retention-and-cost-control.md), and
[program verification](workstreams/33-program-verification.md) workstreams gate
every adopted consumer:

1. Verify focused and full local tests against frozen source fixtures.
2. Apply schema changes in dev with reversible migrations and a dry-run backfill.
3. Build immutable AWS ECR images and deploy bounded ECS/Step Functions canaries.
4. Prove source inventory, terminal dispositions, uniqueness, temporal behavior,
   idempotency, recovery, MDM/export/graph parity, and rollback.
5. Measure runtime, peak memory, requests, storage growth, and cost per validated
   output; approve an explicit budget.
6. Promote to production only with one immutable evidence set and Release Owner GO.
7. Operate independent daily/native-cadence checkpoints, weekly review backstops,
   monthly reconciliations, alarms, runbooks, and retention reviews.

## Universal release gates

- Complete, hash-verified source inventory and stable publication identity.
- Every candidate terminal or explicitly unresolved; no silent omissions.
- Zero name-only automatic links and zero duplicate active external bindings.
- Accepted evidence retains source, publication, record hash, run, rule/reviewer,
  observed/effective time, and supersession history.
- No source-authority overwrite or cross-domain semantic coercion.
- Deterministic replay, idempotent rerun, and fail-closed independent checkpoints.
- Exact downstream parity for applicable MDM, export, and graph records.
- Tested rollback preserves source and stewardship evidence.
- Runtime, memory, request, storage, and validated-output cost remain within the
  consumer's approved budget.
- Future heuristic auto-linking remains prohibited until an independent holdout
  demonstrates a lower confidence bound of at least 99.9% with zero uniqueness
  violations.

## Program completion

Planning is complete when all workstreams in this plan own their remaining
decisions and future specification. Delivery is complete when every mandatory
consumer has production evidence and every conditional source has shipped or
has a documented defer/reject outcome with an objective review trigger.
