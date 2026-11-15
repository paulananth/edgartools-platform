---
name: auto-ontology
description: Guides safe NVIDIA AutoOntology initialization, reset, and read-only connection to this platform's MDM, RDM, and Silver stores. Use when installing, cleaning, connecting, or qualifying AutoOntology for edgartools-platform.
---

# AutoOntology setup for EdgarTools

## Platform contract

AutoOntology sits above MDM, RDM, and Silver as a semantic discovery/query layer. MDM owns mastered identities and relationships; RDM owns approved code sets; Silver owns transaction facts and their master links. These are processing layers, not subject domains. AutoOntology is a consumer, never a writer, of those stores. Use [Data Platform connection rules](../data-platform/CONNECTIONS.md) to select each store and duty; do not derive one store URL from another or reuse worker, migration, or owner credentials.

OpenMetadata remains the catalog projection published from repository rules. AutoOntology does not replace `rules catalog publish`, write directly to OpenMetadata, or become a second business-definition source. Read [OpenMetadata](../openmetadata/SKILL.md) before changing its catalog.

The upstream [setup skill](https://github.com/NVIDIA/auto-ontology/blob/main/skills/nvidia-ontology-setup/SKILL.md), [management skill](https://github.com/NVIDIA/auto-ontology/blob/main/skills/nvidia-ontology-management/SKILL.md), and [query skill](https://github.com/NVIDIA/auto-ontology/blob/main/skills/nvidia-ontology-query/SKILL.md) describe the product. Read the versions shipped with the selected release; rolling `main` is not proof of installed behavior. Upstream supports Helm and Docker Compose; it does not provide an `auto-ontology init` CLI. This skill defines the platform's init workflow; never invent a command.

## Source scope and repeatable sync

Apply [Final exposable tables](../data-platform/FINAL-TABLES.md) before any sync:
only configured final master and silver outputs may enter AutoOntology.
The same authoritative table list controls managed mirrors and its eligibility
is projected to OpenMetadata. This narrows the store-level scope below.
The existing schema-scoped source config and helpers do not yet enforce this
table boundary; stop ingestion until exact reader grants and imported-table
identity checks are qualified. Existing sampling authorization covers only
eligible tables; it does not authorize internal tables.

**AutoOntology imports only MDM, RDM and Silver. Nothing else.** Rules,
Bookkeeping, Change Journal, raw captures, provider endpoints, Snowflake Gold
and OpenMetadata itself are excluded. The complete source list is
`infra/catalog-sources.json`; the same code handles each entry. The verifier
requires the private reader file, active connection strings and imported
catalog database list to match that list exactly.

The operator has authorized stored-value sampling and NVIDIA inference for
these three stores. Apply that standing authorization on subsequent syncs.
Keep generated concepts as proposals until reviewed.

Use separate SELECT-only source accounts. A missing reader is provisioned by
the committed script through the original private migration-role file; it is
not a reason to ask for sampling authorization again or give AutoOntology a
worker/owner login. Existing application accounts and grants are preserved.
Reader URLs use the standard store variable names in
`~/.local/share/edgartools/auto-ontology/reader.env`, mode `0600`. All live URLs,
credentials and service settings stay in private local files.

```bash
CATALOG_OWNER_ENV="$HOME/.local/share/edgartools/hosted-prod/connection.env" \
  bash infra/scripts/catalog-services.sh sync-auto
uv run --no-project --with 'psycopg[binary]' python <SKILL_DIR>/scripts/catalog-auto-verify.py \
  --config <deployment-source-config> \
  --auto-env ../auto-ontology/.env \
  --reader-env "$HOME/.local/share/edgartools/auto-ontology/reader.env"
```

Set `CATALOG_SOURCES_CONFIG`, `CATALOG_READER_ENV` or `AUTO_ONTOLOGY_DIR` to
select alternative private deployment paths. The owner file is used only by
provisioning; AutoOntology receives only the dedicated reader URLs. The sync
recreates the three application containers with the existing images, preserving
volumes, source stores and other containers. Check the configured database host
port against the existing application Postgres container before running it.

Problem: a healthy installation imported tables while storing zero searchable
embeddings. Root cause: upstream example API-key overrides masked the working
default NVIDIA key. Fix: replace placeholder overrides with the configured
default key and require a synthetic embedding request to succeed before sync.
Lesson: catalog counts and a successful ingestion log do not prove search
readiness. Verify exact live table/column counts and persisted embeddings for
each source, plus zero effective reader write privileges and TLS.

The verification command reports semantic compilation separately. To start it
after catalog/embedding verification passes, add `--enable-compilation`. This
uses the supported settings API; it is not a reset. Record the run outcome and
query qualification separately from catalog import. Check a running compilation
at the repository's 30-minute interval, with a deadline and an exit on success
or failure.

## Resource ownership and evidence

An image cache is not a running deployment. For local Compose, confirm active containers with `docker ps`; image labels show build/project provenance, while container labels identify the owning worktree or Compose project. Treat a cached AutoOntology image, pgvector image, or pgAdmin image as unused until a running container and Compose project prove otherwise. Keep AutoOntology's application images and volumes separate from OpenMetadata's server, metadata database, and search images.

## Local Compose secrets

Clone `NVIDIA/auto-ontology` outside this repository. Compose in that checkout is the installer. Keep a mode `0600`, gitignored `.env` there and in this repository. Copy the required keys into the checkout without printing them.

Required keys: `AUTH_SECRET`, `APP_URL`, `AUTO_ONTOLOGY_ADMIN_EMAIL`, `AUTO_ONTOLOGY_ADMIN_PASSWORD`, `POSTGRES_PASSWORD`, `PGADMIN_PASSWORD`, and `DEFAULT_MODELS_API_KEY`. Generate the first six when missing. The admin email must be an address Better Auth accepts; `@localhost` is rejected at sign-in even after the account is seeded. Recreate the frontend after changing it so seed-admin runs again. The operator sets the NVIDIA key in their own terminal. A Claude or other provider key is not a substitute: the default stack calls NVIDIA NIM and needs an `nvapi-` key. Prove acceptance with the models endpoint status only. Never print the key or the response body.

For a laptop, set `APP_URL` to `http://127.0.0.1:3000`. Do not publish that origin beyond localhost unless the operator asks for that exact exposure.

Blank `CONNECTION_STRINGS` copied from the upstream example before the first start. A placeholder sample database is not an approved source. Leave it empty until a scoped synthetic source, or a separately approved MDM, RDM, or Silver source, exists. Check host ports `3000`, `3001`, `3002`, `5050`, and `POSTGRES_PORT`, and the fixed container names, before Compose. Do not stop another stack to free them. Start and stop the sibling stack through `bash infra/scripts/catalog-services.sh start|stop`; set `AUTO_ONTOLOGY_DIR` only when the checkout is not the default sibling directory.


## Initialize (preserve by default)

1. Establish the exact target, deployment mode, pinned release/chart, public URL, current resource owner, and whether this is a new install or a reset. Inspect the existing target before changing it. If any value is unknown, stop before writes.
2. Keep AutoOntology's own application/ontology/vector state in storage separate from the MDM, RDM, and Silver databases. Never point its migrations at a platform store. Use private mode-0600 configuration for credentials; never place secrets in chat, command arguments, logs, or Git.
3. Use a disposable, invented-data target first. Read the selected release's ingestion behavior: AutoOntology may profile columns and sample values, generate embeddings, and call NVIDIA NIM. Obtain explicit approval for any external inference request and verify what data leaves the selected environment.
4. Before adding platform sources, obtain separate SELECT-only credentials scoped to the approved MDM, RDM, and Silver databases/tables. Do not use `MDM_DATABASE_URL`, `RDM_DATABASE_URL`, or `SILVER_DATABASE_URL` runtime credentials as AutoOntology credentials. When a reader is missing, use the generic provisioning workflow above with the private migration-role file. Stop only if a bounded SELECT-only reader cannot be provisioned; preserve existing application grants.
5. Verify the selected release's schema/table allowlists and sample-value controls. Upstream documents that environment `CONNECTION_STRINGS` has no table filters and that full table-level scoping is not yet guaranteed. For PostgreSQL, bound visibility with the dedicated role grants and verify the imported database inventory against the approved configuration. Apply the standing sampling authorization above. If a narrower table scope is required, prove it before ingestion; environment connections have no table-filter guarantee.
6. Follow the matching upstream Helm or Compose procedure. For Compose, inspect fixed `container_name` values and host ports first: the upstream stack uses PostgreSQL, UI, backend, ingestion, and pgAdmin ports and can collide with existing containers. Use a reviewed, version-matched override or an isolated target; never stop or reconfigure shared platform containers to make it fit.
7. Connect only the approved MDM, RDM, and Silver inputs. Rules, Bookkeeping, Change Journal, raw source/capture stores and Snowflake Gold are excluded.

Catalog sync completion: the deployment is healthy; the exact configured final-table identities match each imported source inventory with no internal or stale tables; table/column counts and embeddings match that scope; and source roles have TLS, only approved table reads and zero write privileges. Semantic compilation and query qualification are separate: require successful compilation and a synthetic positive/unsupported query before claiming query readiness.

## Reset and initialize (destructive)

Reset means delete **all state owned by the exact AutoOntology instance**—its ontology, connections, users/settings, application database, indexes, and vectors—then initialize it again. It never means clear MDM, RDM, Silver, OpenMetadata, or any shared platform volume.

1. Identify the exact Compose project or Helm release/namespace and enumerate the containers, database, PVCs/volumes, and external connections it owns. Prove no MDM/RDM/Silver data shares the deletion target. If ownership or volume contents are uncertain, stop.
2. State exactly what will be deleted and where. Obtain immediate confirmation for that target and scope before deletion. An earlier general request to "clean everything" does not authorize a different instance or shared volume.
3. Use only the selected release's documented reset/uninstall path. Upstream `docker compose down -v` and `helm uninstall` delete AutoOntology persistent data; do not run global Docker prune, remove unrelated volumes, or delete a shared PostgreSQL cluster.
4. Verify the old AutoOntology state is absent, then follow **Initialize**. Keep the reset repeatable and scoped; preserve platform databases and OpenMetadata volumes.

## Verify and hand off

Read back AutoOntology's source inventory, semantic model, relationships, and readiness through the selected release's supported API/MCP/UI. Test one positive and one unsupported question with invented or specifically approved data; inspect generated SQL and returned rows before presenting a claim. Confirm the three platform stores remain unchanged and that AutoOntology has no write grants. Record the exact release, target, source scopes, verification outcomes, and any unsupported mappings without logging credentials or real record values.

Treat generated concepts, joins, and SQL attributes as proposals until reviewed against repository definitions and evidence. Preserve provenance and relationship direction. Do not publish AutoOntology edits into OpenMetadata or rules automatically; route an approved business-definition change through its owning repository rules and existing publisher.
