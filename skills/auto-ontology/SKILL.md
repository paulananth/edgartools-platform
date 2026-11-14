---
name: auto-ontology
description: Guides safe NVIDIA AutoOntology initialization, reset, and read-only connection to this platform's MDM, RDM, and Silver stores. Use when installing, cleaning, connecting, or qualifying AutoOntology for edgartools-platform.
---

# AutoOntology setup for EdgarTools

## Platform contract

AutoOntology sits above MDM, RDM, and Silver as a semantic discovery/query layer. MDM owns mastered identities and relationships; RDM owns approved code sets; Silver owns transaction facts and their master links. These are processing layers, not subject domains. AutoOntology is a consumer, never a writer, of those stores. Use [Data Platform connection rules](../data-platform/CONNECTIONS.md) to select each store and duty; do not derive one store URL from another or reuse worker, migration, or owner credentials.

OpenMetadata remains the catalog projection published from repository rules. AutoOntology does not replace `rules catalog publish`, write directly to OpenMetadata, or become a second business-definition source. Read [OpenMetadata](../openmetadata/SKILL.md) before changing its catalog.

The upstream [setup skill](https://github.com/NVIDIA/auto-ontology/blob/main/skills/nvidia-ontology-setup/SKILL.md), [management skill](https://github.com/NVIDIA/auto-ontology/blob/main/skills/nvidia-ontology-management/SKILL.md), and [query skill](https://github.com/NVIDIA/auto-ontology/blob/main/skills/nvidia-ontology-query/SKILL.md) describe the product. Read the versions shipped with the selected release; rolling `main` is not proof of installed behavior. Upstream supports Helm and Docker Compose; it does not provide an `auto-ontology init` CLI. This skill defines the platform's init workflow; never invent a command.

## Initialize (preserve by default)

1. Establish the exact target, deployment mode, pinned release/chart, public URL, current resource owner, and whether this is a new install or a reset. Inspect the existing target before changing it. If any value is unknown, stop before writes.
2. Keep AutoOntology's own application/ontology/vector state in storage separate from the MDM, RDM, and Silver databases. Never point its migrations at a platform store. Use private mode-0600 configuration for credentials; never place secrets in chat, command arguments, logs, or Git.
3. Use a disposable, invented-data target first. Read the selected release's ingestion behavior: AutoOntology may profile columns and sample values, generate embeddings, and call NVIDIA NIM. Obtain explicit approval for any external inference request and verify what data leaves the selected environment.
4. Before adding platform sources, obtain separate SELECT-only credentials scoped to the approved MDM, RDM, and Silver databases/tables. Do not use `MDM_DATABASE_URL`, `RDM_DATABASE_URL`, or `SILVER_DATABASE_URL` runtime credentials as AutoOntology credentials. If a read-only account or bounded scope is unavailable, stop; do not grant write access or broaden scope.
5. Verify the selected release's schema/table allowlists and sample-value controls. Upstream documents that environment `CONNECTION_STRINGS` has no table filters and that full table-level scoping is not yet guaranteed. If the required scope or sensitive-value exclusion cannot be proved, connect only synthetic data; do not connect hosted or production stores.
6. Follow the matching upstream Helm or Compose procedure. For Compose, inspect fixed `container_name` values and host ports first: the upstream stack uses PostgreSQL, UI, backend, ingestion, and pgAdmin ports and can collide with existing containers. Use a reviewed, version-matched override or an isolated target; never stop or reconfigure shared platform containers to make it fit.
7. Connect only the approved MDM, RDM, and Silver inputs. Keep Rules, Bookkeeping, Change Journal, raw source/capture stores, and Snowflake Gold out of scope unless separately approved.

Completion: the pinned deployment is healthy; the three approved sources are read-only and correctly scoped; semantic compilation/readiness succeeds; and a synthetic test confirms expected terms, relationships, and query behavior without changing any platform store.

## Reset and initialize (destructive)

Reset means delete **all state owned by the exact AutoOntology instance**—its ontology, connections, users/settings, application database, indexes, and vectors—then initialize it again. It never means clear MDM, RDM, Silver, OpenMetadata, or any shared platform volume.

1. Identify the exact Compose project or Helm release/namespace and enumerate the containers, database, PVCs/volumes, and external connections it owns. Prove no MDM/RDM/Silver data shares the deletion target. If ownership or volume contents are uncertain, stop.
2. State exactly what will be deleted and where. Obtain immediate confirmation for that target and scope before deletion. An earlier general request to "clean everything" does not authorize a different instance or shared volume.
3. Use only the selected release's documented reset/uninstall path. Upstream `docker compose down -v` and `helm uninstall` delete AutoOntology persistent data; do not run global Docker prune, remove unrelated volumes, or delete a shared PostgreSQL cluster.
4. Verify the old AutoOntology state is absent, then follow **Initialize**. Keep the reset repeatable and scoped; preserve platform databases and OpenMetadata volumes.

## Verify and hand off

Read back AutoOntology's source inventory, semantic model, relationships, and readiness through the selected release's supported API/MCP/UI. Test one positive and one unsupported question with invented or specifically approved data; inspect generated SQL and returned rows before presenting a claim. Confirm the three platform stores remain unchanged and that AutoOntology has no write grants. Record the exact release, target, source scopes, verification outcomes, and any unsupported mappings without logging credentials or real record values.

Treat generated concepts, joins, and SQL attributes as proposals until reviewed against repository definitions and evidence. Preserve provenance and relationship direction. Do not publish AutoOntology edits into OpenMetadata or rules automatically; route an approved business-definition change through its owning repository rules and existing publisher.
