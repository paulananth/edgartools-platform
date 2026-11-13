# Local server and rebuilds

Part of the `openmetadata` skill: [SKILL.md](SKILL.md) says when to read this.

## Local server

### Edgartools instance and private credentials

The Edgartools local instance is a separate Compose project named
`edgartools-openmetadata`, bound to `127.0.0.1:8587`, with its own
`edgartools-openmetadata_db-data` and `edgartools-openmetadata_es-data`
volumes. The prior `edgartools-catalog` project on port 8585 is independent;
starting or initializing this instance must not stop it or remove its volumes.
The operator handles any retirement of the prior instance separately.

The repository-root `.env` is ignored by Git and must remain mode `0600`.
`bash infra/openmetadata/init.sh` reads it without printing values. On a fresh
2.0.7 instance, initialization changes the default administrator password to a
generated password, issues a 30-day personal access token, stores the login
and token in `.env`, then verifies that token with an API read. Subsequent runs
keep a working token. Do not paste or print `.env` values; load the file in a
private shell when a client needs `OPENMETADATA_URL`,
`OPENMETADATA_LOGIN_EMAIL`, `OPENMETADATA_LOGIN_PASSWORD`, or
`OPENMETADATA_TOKEN`:

```bash
set +x
set -a
source .env
set +a
```

The `.env` file must contain shell-compatible `KEY=VALUE` assignments. The
initialization helper refuses non-local endpoints and any server version other
than 2.0.7. If using a different private environment file, set
`OPENMETADATA_ENV_FILE` to its path when invoking `init.sh`; keep that file
outside Git and mode `0600`.

### Exclude bundled demo lineage

Operator policy excludes vendor demonstration lineage from this platform's
OpenMetadata catalog. The local compose file enforces it with an empty seed
resource mounted before the release jars.
Keep that override on rebuilds and upgrades; recheck its resource path and
classpath precedence against the running version. Delete only edges proven
to match the bundled examples, through native APIs, and read them back after
a server restart. Preserve real assets, relationships and database volumes.
Never restore these examples to populate a graph.

Problem: deleting demo edges alone lets them return at startup. Root cause:
the pinned release unconditionally seeds missing edges, even when endpoint
objects are soft-deleted. Fix: retain the empty configuration override and
verify zero demo edges after restart. Lesson: deletion is complete only when
the producer of unwanted metadata is also suppressed.

Initialization also excludes the two vendor AI demo services and their sample
children through the native API. The skill's `scripts/initialize.py` inventories
the children by service, checks that the inventory is complete, soft-deletes
each child and parent, and requires native readback to confirm active absence
and retained deleted markers. Keep those markers: the vendor's asset seeder
checks deleted objects too, so hard deletion would let the examples return.
Repeating initialization is safe. Preserve unrelated services.

Problem: on the pinned 2.0.2 local server, listing LLM models with
`include=all` returns HTTP 404, while reading a model by ID with
`include=all` returns its tombstone. Root cause: collection and item reads
have different deleted-entity behavior in this release. Fix: inventory active
children by service, require complete pagination, verify each soft-deleted ID
with `include=all`, then re-list active children. Lesson: qualify deleted-state
readback for each endpoint shape instead of assuming list and item reads match.

Use the existing Docker context and the private `.env` file above. The
initialization command starts the separate server, waits for health, bootstraps
and verifies credentials, then requires the demo-service exclusion to pass:

```bash
bash infra/openmetadata/init.sh
```

Check Docker first. If it is unreachable, report that blocker. Preserve other
users' containers and volumes. A cold start may take 10–20 minutes. The compose
file accepts `CATALOG_SERVER_HEAP_OPTS` and `CATALOG_SEARCH_HEAP_OPTS`.
Keep the configured heap values when reinitializing an existing instance.
Direct compose startup is only the server-start stage, not completed platform
initialization. Rerun `bash infra/openmetadata/init.sh` to apply the idempotent
exclusion and readback to an already running server.
Keep the helper behind this repository entrypoint; directly invoking a helper
inside the skill directory is checkout-only and fails the installed-skill doctor.

A compose recreate can leave the server wedged: Docker reports "cannot stop
container: ... tried to kill container, but did not receive an exit event" and
leaves a `Created` replacement beside the running original, which then exits
137 and leaves the port unbound while its logs still show healthy requests. Recover by removing both the stale `Created` container and the
wedged original, then bringing the stack up with
`docker compose -f infra/openmetadata/docker-compose.yml up -d --wait`. The
named `db-data` and `es-data` volumes carry the catalog, so remove the
containers, never the volumes, and confirm the PostgreSQL data directory is
still populated before restarting. The catalog survives the recreate intact.

The catalog publisher reads `OPENMETADATA_TOKEN` from the private environment.
The local PAT lasts 30 days; `init.sh` reissues it after it no longer passes
the API version readback and stores the replacement in `.env`. A publish that
answers 401 before then requires checking the server version and current `.env`
token, followed by rerunning initialization. Never put a PAT in a command
line, terminal output, repository file or PR. See
[Token issuance and lifetime](references/TOKEN-LIFECYCLE.md) for the pinned
2.0.7 API contract.

### Upgrade the local server

Check the target release's official upgrade guide and compatibility requirements before changing image pins. For the 2.0.2 → 2.0.7 upgrade, PostgreSQL 15+ and Elasticsearch 9.x are supported (9.3.0 recommended); run the metadata database migration before starting the new server.

Back up the metadata database outside the repository and validate the dump with `pg_restore --list`. Preserve the `db-data` and `es-data` volumes. A pre-upgrade dump is only for rollback: restore it into a clean database and start the matching source-version server. Never restore an old-version dump over the migrated database or run an older server against the upgraded schema.

Keep the `postgresql`, `execute-migrate-all`, and `openmetadata-server` images on the same target release. This repository's migration service runs `./bootstrap/openmetadata-ops.sh migrate` before the server. Use the repository entrypoint:

```bash
bash infra/openmetadata/init.sh
```

The initializer also performs the idempotent native-API demo exclusion/readback. Its release allowlist is intentionally fail-closed: qualify the target release's API behavior and tests before adding it; unknown releases must not run exclusions. After startup, verify `GET /api/v1/system/version` and the owned entity readbacks, then reindex all search indexes with the container CLI:

```bash
docker compose -f infra/openmetadata/docker-compose.yml exec -T openmetadata-server ./bootstrap/openmetadata-ops.sh reindex
```

Do not treat a healthy server alone as a completed upgrade. Read back the assets and lineage after reindex.

### Check service and asset lineage separately

In the verified 2.0.7 server, `GET /api/v1/lineage/getPlatformLineage?view=service` returns `nodes`, `upstreamEdges`, and `downstreamEdges` as keyed objects, not arrays. This is the service-level graph; a blank or sparse service canvas does not establish whether table lineage exists. Check each intended asset edge separately through `GET /api/v1/lineage/table/name/<URL-encoded-FQN>?upstreamDepth=1&downstreamDepth=1`, and inspect the returned upstream/downstream edges and column lineage.

- [Docker upgrade guide](https://docs.open-metadata.org/v2.0.x/deployment/upgrade/docker)
- [Upgrade backup and restore behavior](https://docs.open-metadata.org/v2.0.x/deployment/upgrade/how-does-it-work)
- [Minimum requirements](https://docs.open-metadata.org/v2.0.x/deployment/minimum-requirements)


This destructive reset is distinct from `rules catalog publish`, which keeps
the DatabaseService and retires only the exact old shared PipelineService after
the new per-source PipelineServices, Pipelines and lineage read back. For an
explicitly requested whole-service reset, delete every owned PipelineService
(source, standalone and any remaining retired shared service), then the owned
DatabaseService:

1. `GET /api/v1/services/<type>/name/<exact-owned-name>`. Check the name and
   the fully qualified name.
2. `DELETE /api/v1/services/<type>/<returned-id>?recursive=true&hardDelete=true`.
3. Repeat the GET and require 404.

Domains, glossaries, and terms are global. Deleting a service does not remove
them.

## Catalog-only clean rebuild

`rules catalog publish` reconciles the plan; it is not a delete-and-recreate
reset. Use it alone for normal refreshes. For an explicitly requested clean
rebuild, preserve the OpenMetadata PostgreSQL and search volumes, users,
workflows, roles, and instance settings. Do not use `docker compose down -v`,
drop the OpenMetadata database, or clear search storage for a catalog reset.

Before deleting anything, read the current plan and list every API page for the
owned services and global objects. Establish exact ownership by comparing each
identity with the current plan and the publisher's ownership boundary. Stop if
an object cannot be shown to be owned; global domains, glossaries, terms,
products, and quality definitions can contain unrelated curation. Record the
IDs and counts for the reviewed scope.

Delete in dependency order: owned products, owned quality cases, owned custom
quality definitions, every owned PipelineService, the owned database service,
owned glossary terms, owned glossaries, owned domains, then owned custom tags.
Remove products and cases before their referenced tables. Delete all owned
PipelineServices before the database service. For each service, verify the exact
service name and FQN first, delete by returned ID with `recursive=true&hardDelete=true`, then
repeat the GET and require 404. For each other resource, use its native API and
returned ID; use recursive deletion only when the owned children are in the
reviewed scope. Keep built-in definitions, classifications, tags,
relationships, workflows, and settings unless the plan explicitly owns them. If
a delete fails or ownership becomes unclear, stop and account for remaining
objects before continuing.

Four deletions have their own behavior on 2.0.7:

- **A quality case needs `recursive=true`.** `DELETE /dataQuality/testCases/{id}`
  answers 400 "testCase is not empty" without it, because the case carries a
  resolution-status child row. `recursive=true&hardDelete=true` clears the
  cascade.
- **Quality case ownership is by entity link, not by name.** The plan renames a
  case when its source's version moves (v1 to v2), so matching on the exact name
  leaves the stale case behind. Every live case whose `entityLink` names the
  owned service is owned.
- **`Certification.Gold` and `Certification.Silver` are built-in system
  entities.** The server refuses to delete them: "System entity [Gold] of type
  tag can not be deleted." They stay and the publisher reuses them. Only the
  plan's own `data_class.*` tags are deletable, and they go before the
  `data_class` classification that holds them.
- **A PipelineService the plan dropped is still owned.** A service absent from
  the current plan but serving the same rules namespace was retired by the
  rules change; it goes with the rest of the owned services.

Capture the per-load quality results before deleting anything that holds them.
A reset without a captured copy destroys evidence that no publish can
reconstruct, because the publisher restores results from a `--results` file or
a `--bookkeeping-run`, not from the server it just emptied. Read
[Quality result history](references/QUALITY-RESULT-HISTORY.md#capturing-results-before-a-reset)
for the capture and the conversion.

Publish the current plan only after the reviewed scope is empty. Require the
publish result's readback to match, run `rules catalog check` independently,
and verify the exact domain and glossary inventories plus the absence of any
forbidden shared object. A zero-removal publish after the rebuild is expected;
it means the fresh catalog already matches the plan. Report deletion counts
separately from publication counts. A catalog reset does not reset the
OpenMetadata server or prove that metadata ingestion or data pipelines ran.

## Full local instance rebuild

This is separate from a catalog-only clean rebuild. It removes the local
OpenMetadata PostgreSQL and Elasticsearch volumes, including the catalog,
users, workflows, roles, and instance settings. Use it only when the operator
explicitly requests a full local instance reset. A catalog reset must preserve
both volumes.

Before stopping the stack, confirm the active Docker context and inspect the
Compose project:

```bash
docker compose -f infra/openmetadata/docker-compose.yml ps
```

The Compose file declares project `edgartools-openmetadata` and volumes
`db-data` and `es-data`. Confirm the resolved names
`edgartools-openmetadata_db-data` and `edgartools-openmetadata_es-data`, their
project labels. Verify that only those two volumes are in scope and no
unrelated container uses them.
List volumes with the Compose project label, inspect each resolved volume, and
check consumers with `docker ps -a --filter volume=<resolved-volume-name>`.
If names, labels, project ownership, or consumers differ, stop and report them
before deleting anything.

After that scope is confirmed, stop the project and remove only its declared
volumes:

```bash
docker compose -f infra/openmetadata/docker-compose.yml down -v
```

Verify the two project volumes are absent, then redeploy:

```bash
bash infra/openmetadata/init.sh
```

The full reset also removed the local administrator state. Before running the
initializer, remove only the `OPENMETADATA_PASSWORD_CHANGED` line from the
private `.env`; this makes the credential bootstrap change the fresh default
administrator password and issue a new PAT. Keep the remaining endpoint and
login settings. The initializer waits for PostgreSQL, Elasticsearch,
migrations, and the server, then verifies credentials and demo exclusion.
Require `GET /api/v1/system/version` to report the configured release. Then
follow the catalog-only workflow above: read the side-effect-free
Rules plan, publish the configured catalog, require publisher readback, run the
independent read-only check, and verify the exact domain and glossary inventory
plus the absence of any forbidden shared object. Report the server rebuild
separately from catalog publication. Do not remove images, other projects'
containers, or any other volumes.
