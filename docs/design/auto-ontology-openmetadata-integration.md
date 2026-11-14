# AutoOntology and OpenMetadata integration plan

**Status:** proposal; product and deployment contract not yet verified. This is a plan only: no installation, connection, catalog publication, or data movement is authorized here.

## Goal

Add AutoOntology alongside OpenMetadata to make governed data easier to find and understand, without creating competing definitions, writers, or copies of source records. OpenMetadata remains the existing technical catalog and quality-result surface unless an explicit later decision changes that role.

## Repository facts

- Business meaning and stable logical identities belong to the repository's owning configuration and `CONTEXT.md`; the catalog is a projection, not a second model (`skills/data-catalog/SKILL.md`).
- `edgar_warehouse.rules.catalog.plan()` derives a deterministic catalog plan from rules. `rules catalog publish` reconciles the OpenMetadata-owned scope from that plan; `rules catalog check` verifies readback. Publishing is not a safe second-writer interface.
- The current publisher sends metadata one way from rules to OpenMetadata. The checked-in local OpenMetadata stack is pinned to 2.0.7 and is kept separate from the rules and data stores.
- `skills/data-catalog/references/PORTABILITY.md` already sets the direction for an independent visualization: preserve logical keys, provenance, typed relationships, lineage and destination-specific identity mappings; do not add another metadata database as a prerequisite.
- No AutoOntology package, configuration, adapter, or product documentation is present in this checkout. Its APIs, formats, security model, deployment, licensing and capabilities are unknown.

## Recommended integration shape

Treat AutoOntology initially as a **read-only semantic discovery view**, not as a second ontology authoring system and not as a replacement for OpenMetadata. Feed it the same approved, configuration-derived semantic inventory used to describe the platform. Keep OpenMetadata publication on the existing `rules catalog publish` path. Do not create bidirectional synchronization or let AutoOntology write into OpenMetadata.

The destination-neutral inventory is a contract to preserve, not a claim that the current OpenMetadata-shaped plan is already portable. If AutoOntology needs a different payload, add a pure export/projection from the canonical rules model, with stable logical keys and explicit destination mappings. Keep the adapter narrow: one inventory in, destination-specific representation out; isolate authentication, pagination, retries, reconciliation and readback inside the adapter. Do not put AutoOntology-specific identities into business rules.

If product evaluation shows AutoOntology is an ontology-authoring system rather than a read-only view, stop before implementation and decide its authority, review/approval path, and how approved changes enter repository rules. Do not allow two editable sources of truth by default.

## Alternatives considered

- **Read-only consumer of the existing OpenMetadata plan:** smallest first step, but the plan contains OpenMetadata-shaped names and native FQNs. Suitable only if product qualification proves those semantics are portable; do not treat native IDs as business identities.
- **AutoOntology as the authoring source:** could offer richer ontology editing, but introduces a second source of truth and an approval/import lifecycle. Defer unless the operator explicitly chooses it; if selected, import a pinned snapshot through review into repository rules, then use the existing publisher. Never let it write directly to OpenMetadata.
- **Shared semantic inventory with independent destination projections:** best long-term fit with the repository's portability guidance and the recommended read-only role. It avoids destination coupling but needs a versioned neutral contract; add that only when the verified AutoOntology import contract requires it.

**Decision:** begin with a read-only semantic projection from repository-owned configuration. Keep current OpenMetadata publication unchanged. Select direct consumption versus a new neutral export only after AutoOntology's actual contract is verified.

## Phased plan and exit criteria

### 0. Verify the product contract

Before choosing an adapter or installing anything, record the exact AutoOntology project/vendor, version, license, deployment mode and supported integration interfaces. Confirm:

- supported import/export formats or APIs, object/relationship types, lineage support and stable identity behavior;
- whether it consumes OpenMetadata metadata, a repository export, or both, and how deletions/revisions are reconciled;
- authentication, authorization, SSO, audit logging, network exposure, data retention, backup and upgrade requirements;
- whether it stores only metadata or can ingest source rows, samples, credentials or other sensitive content;
- the actual user journey it adds beyond OpenMetadata search, glossary and lineage.

**Exit:** a product/version decision and a supported, least-privilege integration path. If any required capability or security property is unavailable, revise the proposal before installation.

### 1. Specify the shared semantic contract

Inventory the fields and relationships needed for the agreed discovery journeys: logical key, object type, display name, definition, source/configuration provenance, domain membership, dataset grain, fields, glossary associations, typed lineage and pipeline dependencies. Keep execution evidence and observed business relationships separate from definitions and permitted relationship types. Include only metadata approved for discovery; exclude credentials, source rows, private record identifiers and unapproved relationship facts.

Map each logical key to AutoOntology's native identity separately from OpenMetadata FQNs. Record the payload schema/version, ownership scope, and behavior for unknown or unsupported concepts. Do not silently flatten typed links or treat a description-only fallback as equivalent to a searchable relationship.

**Exit:** a reviewed example mapping and explicit unsupported/gap list, with no business definition authored only in a destination.

### 2. Choose the read path and implement the adapter

Prefer a read-only projection from repository-owned configuration so both destinations share one semantic source. Reuse the existing `rules catalog plan` model only if its OpenMetadata-specific shape is adequate; otherwise introduce a separately versioned, destination-neutral catalog export rather than making AutoOntology scrape OpenMetadata's database or adding an intermediate metadata database.

The adapter should support dry-run/plan, scoped publication, readback, and idempotent reconciliation. It must own only the AutoOntology objects it creates; it must not delete or modify unrelated objects. Handle partial failures without reporting success until readback matches the intended logical objects and directed relationships. OpenMetadata's publisher remains unchanged.

**Exit:** deterministic plan from rules, an explicit ownership scope, safe credential handling, and adapter tests for create/update/no-op, wrong or reversed relationships, partial failure, replay, and stale owned objects.

### 3. Qualify an isolated end-to-end example

Use invented metadata only and a disposable AutoOntology instance or approved test tenant. Publish one connected example spanning a domain, glossary concept, technical dataset/field and a directed lineage or semantic relationship. Read it back through the native interface. Prove stable identities, correct direction, access controls, repeatability, and exact cleanup limited to test-owned objects. Include a deliberately incorrect expected relationship and require verification to fail. Do not use provider data or production credentials for this qualification.

**Exit:** the agreed user journey works in the real supported product/API, with exact readback and no unauthorized writes or sensitive payloads.

### 4. Deploy and operate only after approval

After the product contract and isolated qualification pass, prepare a separate deployment/service definition using the repository's approved infrastructure conventions. Define service ownership, resource limits, health checks, network ingress, TLS, secret storage, backups, upgrades, synchronization cadence, alerting, rollback, and resync/recovery. Keep AutoOntology storage separate from OpenMetadata's database and search store. Obtain explicit approval for the target environment and any external exposure or production metadata synchronization before deployment.

**Exit:** an approved runbook, least-privilege credentials, tested rollback/recovery, and a first read-only sync confirmed by native readback.

## Acceptance criteria

- One repository-owned semantic source; no unreviewed dual writing or destination-specific business definitions.
- OpenMetadata's existing plan/publish/check behavior remains intact.
- AutoOntology exposes the agreed search/browse journey and preserves logical identity, provenance, typed relationships and lineage supported by its contract.
- Only approved metadata is sent; no source rows, credentials or private record identifiers.
- Sync is scoped, idempotent and read-back verified; errors and partial state are visible, not reported as success.
- Deployment, access control, retention and recovery have explicit owners and evidence before production use.

## Decisions still required

1. Which exact AutoOntology project and version is intended, and where is its authoritative documentation or repository?
2. Is it a read-only discovery/visualization layer, an ontology authoring system, or both? The recommendation is read-only initially.
3. Which users and discovery journeys are in scope, and should OpenMetadata remain the default entry point with links to AutoOntology?
4. Which environment is intended for the first installation, and what identity, network, retention and synchronization constraints apply?

## Out of scope

Installing AutoOntology; accessing a vendor site or hosted tenant; connecting to production OpenMetadata, MDM, Snowflake or provider systems; changing rules or business definitions; copying source records; replacing the OpenMetadata publisher; and enabling production synchronization.
