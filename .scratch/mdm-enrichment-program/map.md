# MDM Enrichment Program

Label: `wayfinder:map`

## Destination

A decision-complete, dependency-ordered program plan for source-grained external
MDM enrichment. The plan covers shared GLEIF capture, every identified MDM
consumer and GLEIF mapping family, conditional non-GLEIF sources, and the path
through production rollout, operation, stewardship, retention, and verification.

The destination is planning complete, not implementation complete. Each
consumer receives its own specification and release evidence before executable
implementation work is created or production publication is authorized.

## Notes

- AWS is the only deployment path. Source artifacts use S3, warehouse exports
  use the existing Snowflake native-pull path, and MDM writes use Snowflake
  Postgres through the repository's existing runtime contracts.
- Every decision session uses `/grilling`, `/domain-modeling`, and
  `/grill-with-docs`; Wayfinder sessions use `/wayfinder`.
- Preserve source authority. GLEIF does not overwrite SEC filings, reported
  financials, or CIK authority. Other sources receive their own authority
  decisions.
- Shared capture does not authorize publication. Each MDM Enrichment Consumer
  is independently specified, tested, deployed, reversible, and observable.
- Planning inclusion does not authorize a Conditional Enrichment Source.
- Detailed implementation tickets are created only after the owning consumer
  specification fixes schemas, migrations, test seams, and rollout gates.
- The evidence-backed first child is the existing
  [GLEIF Company augmentation map](../gleif-company-augmentation/map.md).
- Domain and authority separation is recorded by
  [Use source-grained evidence and independently releasable MDM enrichment consumers](../../docs/adr/0010-independent-source-grained-mdm-enrichment-consumers.md),
  with canonical terms in the [repository glossary](../../CONTEXT.md).

## Decisions so far

- [Set the MDM Enrichment Program boundary](issues/01-set-program-boundary.md)
  — cover every identified domain and source while keeping unsafe identity and
  relationship interpretations prohibited.
- [Choose the program and release structure](issues/02-choose-program-structure.md)
  — use a parent program with independently releasable consumers and explicit
  mandatory, conditional, and prohibited classifications.
- [Set domain, history, and stewardship boundaries](issues/03-set-domain-history-stewardship.md)
  — retain unsupported evidence without generic entities, start from a verified
  current baseline, and use evidence-bound review decisions.
- [Set retirement, release, and operating authority](issues/04-set-retirement-release-authority.md)
  — business-close without erasing history, release through hard evidence
  gates, and separate capture, stewardship, release, and deletion authority.
- [Define completion and planning artifacts](issues/05-define-completion-and-artifacts.md)
  — planning and program completion are distinct, conditional sources must
  terminate in adopt/defer/reject, and every workstream owns a future spec.
- [Inventory source files and pipeline routing](issues/06-inventory-source-files-and-pipeline-routing.md)
  — catalog the three Golden Copy families, their delta and recovery files,
  every approved mapping snapshot, and each domain or nonpublishing route.
- [Select the Golden Copy representation and completeness boundary](issues/07-select-golden-copy-representation-and-completeness.md)
  — use XML ZIP, coordinate Relationship Records with Reporting Exceptions,
  and keep the six identifier mappings independently checkpointed.
- [Set run, transaction, and artifact-transition authority](issues/08-set-run-transaction-and-artifact-transition-authority.md)
  — join Bookkeeping, Change Ledger, and MDM Commit Evidence by one `run_id`;
  commit bounded consumer batches atomically; and move verified temporary
  Bronze bytes into the low-cost immutable Source Artifact Archive.

## Program workstreams

- [Shared enrichment foundation](workstreams/00-shared-enrichment-foundation.md)
- [Company legal-entity enrichment](workstreams/01-company-legal-entity.md)
- [Security and issuer enrichment](workstreams/02-security-and-issuer.md)
- [Fund legal-entity relationships](workstreams/03-fund-relationships.md)
- [Branch legal-entity enrichment](workstreams/04-branch-legal-entity.md)
- [Adviser and audit-firm legal-entity enrichment](workstreams/05-adviser-audit-firm.md)
- [Government legal-entity enrichment](workstreams/06-government-legal-entity.md)
- [International-organization enrichment](workstreams/07-international-organization.md)
- [Sole-proprietor and Person boundary](workstreams/08-sole-proprietor-person-boundary.md)
- [Market and trading-venue enrichment](workstreams/09-market-trading-venue.md)
- [ISIN-to-LEI mapping](workstreams/10-isin-mapping.md)
- [BIC-to-LEI mapping](workstreams/11-bic-mapping.md)
- [MIC-to-LEI mapping](workstreams/12-mic-mapping.md)
- [OpenCorporates-to-LEI mapping](workstreams/13-opencorporates-mapping.md)
- [S&P CIQ-to-LEI mapping](workstreams/14-sp-ciq-mapping.md)
- [QCC-to-LEI mapping](workstreams/15-qcc-mapping.md)
- [GEM-to-LEI mapping](workstreams/16-gem-mapping.md)
- [Market-data sources](workstreams/20-market-data-sources.md)
- [Sanctions sources](workstreams/21-sanctions-sources.md)
- [ESG sources](workstreams/22-esg-sources.md)
- [Credit sources](workstreams/23-credit-sources.md)
- [Other commercial-company sources](workstreams/24-commercial-company-sources.md)
- [Production rollout](workstreams/30-production-rollout.md)
- [Operations and stewardship](workstreams/31-operations-and-stewardship.md)
- [Retention and cost control](workstreams/32-retention-and-cost-control.md)
- [Program verification](workstreams/33-program-verification.md)

See [the dependency-ordered plan](plan.md) and
[specification ownership index](spec-index.md). The
[source-file pipeline catalog](source-file-pipeline-catalog.md) records the
authoritative archive and member-file families for every proposed GLEIF path.
The completed structural and scope audit is recorded in
[plan verification](verification.md).

## Not yet specified

None at the parent-program level. Each workstream explicitly owns its remaining
research and specification decisions; uncertainty is not hidden here.

## Out of scope

- Implementing any source or consumer directly from this parent plan. A verified
  consumer specification must exist first.
- Non-AWS deployment, storage, workflow, registry, or secret-management paths.
- Replacing authoritative identifiers, merging from name similarity alone, or
  coercing evidence into an incompatible MDM domain.
- Treating accounting consolidation as legal ownership, beneficial ownership,
  control, or a generic parent relationship.
- Human-person enrichment from LEI evidence. The sole-proprietor workstream must
  decide the business-capacity boundary without asserting that an LEI identifies
  a natural person for unrelated purposes.
