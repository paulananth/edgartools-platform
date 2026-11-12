# Local server and rebuilds

Part of the `openmetadata` skill: [SKILL.md](SKILL.md) says when to read this.

## Local server

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

Use the existing Docker context, private login/token environment variables
described below, and the named volumes. The initialization command starts the
server, waits for health, then requires the demo-service exclusion to pass:

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

The tool reads `OPENMETADATA_TOKEN`, or `OPENMETADATA_LOGIN_EMAIL` with
`OPENMETADATA_LOGIN_PASSWORD` (also accepts `OPENMETADATA_PASSWORD`), privately.
It refreshes the token through native login when login credentials are present.
Its result is counts only; a failed exclusion exits nonzero.

A login token of the local account expires within the hour; a publish that
answers 401 needs a new one. A token that worked for a read can still be
expired, and the expiry shows up on the first write: a GET answers 200 while
`PUT /api/v1/services/databaseServices` answers 401 "Expired token!". Refresh and retry the write; the publish is not the failing
step. When the private credentials are already in the environment, refresh
without the interactive prompt, base64-encoding the password and writing the
token to the private token file with a restrictive mode, and print neither the
password nor the token.

Resolve the endpoint and private credentials through
[Data Platform connection setup](../data-platform/SKILL.md#connection-urls-and-environment)
before this token-refresh operation.

Refresh it in the private terminal session, with
shell tracing off. Enter the local account password only at the hidden prompt;
the password is base64 encoded for the login API, and neither it nor the returned
token is printed:

```bash
set +x
set -euo pipefail
# Load the configured endpoint through Data Platform's connection setup.
read -r -p 'OpenMetadata email: ' OM_LOGIN_EMAIL
read -r -s -p 'OpenMetadata password: ' OM_LOGIN_PASSWORD
printf '\n'
OM_LOGIN_PASSWORD_B64=$(printf '%s' "$OM_LOGIN_PASSWORD" | base64 | tr -d '\n')
OM_LOGIN_BODY=$(jq -cn --arg email "$OM_LOGIN_EMAIL" --arg password "$OM_LOGIN_PASSWORD_B64" \
  '{email:$email,password:$password}')
OPENMETADATA_TOKEN=$(printf '%s' "$OM_LOGIN_BODY" | curl -fsS \
  -H 'Content-Type: application/json' -X POST \
  --data-binary @- "$OPENMETADATA_URL/api/v1/users/login" | jq -er '.accessToken')
export OPENMETADATA_TOKEN
unset OM_LOGIN_EMAIL OM_LOGIN_PASSWORD OM_LOGIN_PASSWORD_B64 OM_LOGIN_BODY
```

Keep the variables in the private shell only. Never echo or save the token in
the repository. The URL passed to `catalog.connect` is the server root; that
function adds `/api/v1`.
For longer-lived writable-token requests, consult
[Token issuance and lifetime](references/TOKEN-LIFECYCLE.md) first.

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

The current Compose file declares project `edgartools-catalog` and volumes
`db-data` and `es-data`. Confirm their resolved names and project labels; verify
that only those two volumes are in scope and no unrelated container uses them.
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
docker compose -f infra/openmetadata/docker-compose.yml up -d
```

Wait for PostgreSQL, Elasticsearch, migrations, and `openmetadata-server` to
report healthy. Read `GET /api/v1/system/version` and require the configured
version. Create a fresh local administrator token only after the deployment is
healthy. Then follow the catalog-only workflow above: read the side-effect-free
Rules plan, publish the configured catalog, require publisher readback, run the
independent read-only check, and verify the exact domain and glossary inventory
plus the absence of any forbidden shared object. Report the server rebuild
separately from catalog publication. Do not remove images, other projects'
containers, or any other volumes.
