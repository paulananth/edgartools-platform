---
name: openmetadata-deploy
description: Start, stop, restart or recover the local OpenMetadata server (Compose project edgartools-openmetadata, port 8587) and read back that it is healthy. Use when asked to deploy, bring up, shut down or restart OpenMetadata, after Docker or OrbStack restarts, or when its server container will not start. Publishing and the catalog stay in the openmetadata skill.
---

# Deploy OpenMetadata

The local catalog server is one Compose project, `edgartools-openmetadata`: the
server, its PostgreSQL, its Elasticsearch and a one-off migration, on
`127.0.0.1:8587`. Its data is in two named volumes, `db-data` and `es-data`.
Credentials, the AI Governance clearout, upgrades and catalog resets are the
[openmetadata skill](../openmetadata/LOCAL-SERVER.md); this skill only brings
the server up, takes it down and recovers it.

## Hard stops

| Never | Instead |
|---|---|
| `docker compose down -v`, or remove a volume | `docker compose ... stop`, or `down` without `-v`. Only a full reset the operator asked for removes volumes (LOCAL-SERVER, "Full local instance rebuild") |
| Run compose from a stale checkout | Run it from a checkout at current `origin/main`: an old compose file maps port 8585 and a file mount, not 8587 |
| Print or paste the private `.env` | Source it in a private shell, or let `init.sh` read it |
| Stop other projects' containers to save memory without being asked | Stop only what was named, and say what else is running |

## Deploy or bring up

1. **Docker answers.** `docker info`. If it does not, start OrbStack (below)
   and wait for it; report the blocker if it stays down.
2. **Run the entrypoint** from a current checkout:
   `bash infra/openmetadata/init.sh`. It starts the stack, waits for health,
   bootstraps or reuses credentials and clears AI Governance. A cold start
   takes 10 to 20 minutes.
3. **Read it back.** All three containers `healthy`, and
   `GET http://127.0.0.1:8587/api/v1/system/version` answers 200 with the
   pinned release. A healthy container alone is not a deployment: also
   `docker port <server container>` must show `127.0.0.1:8587`.

To only start an already initialized server, without credentials work:
`OPENMETADATA_HOST_PORT=8587 docker compose -p edgartools-openmetadata -f infra/openmetadata/docker-compose.yml up -d --wait`.

## Shut down

`docker compose -p edgartools-openmetadata -f infra/openmetadata/docker-compose.yml stop`
keeps containers and data. Say what is still running afterwards.

## Restart Docker or OrbStack

OrbStack holds memory after its containers stop, so freeing it means
restarting the engine itself: `orbctl stop`, then `orbctl start`. `orbctl
restart` restarts Linux machines only and does nothing to Docker.

Containers come back in no order. The server can start before its database and
exit 127, or stay down: wait until PostgreSQL and Elasticsearch are `healthy`,
then run the compose `up -d --wait` above, which starts the server last.

## When the server will not start

| Symptom | Cause | Fix |
|---|---|---|
| `error mounting ... not a directory` for a repository path | An old compose file bound a file of a worktree that has since been deleted; Docker made an empty folder in its place | Remove that empty folder, then recreate the server from a current compose file (it mounts inline content, not a path): `up -d --wait` |
| Server answers on 8585, not 8587 | Compose run from a stale checkout | Recreate from a current checkout with `OPENMETADATA_HOST_PORT=8587` |
| Exit 127 right after an engine restart | Started before its database was healthy | Wait for `healthy`, run `up -d --wait` |
| A `Created` replacement beside a running original, port unbound | A wedged recreate | Remove both containers, never the volumes, then `up -d --wait` (LOCAL-SERVER, "Local server") |

Recreating the server container loses nothing: the catalog is in the volumes.

## Memory

The stack is three JVM-heavy containers. Compose sets the heaps through
`CATALOG_SERVER_HEAP_OPTS` (server, default `-Xmx768m -Xms768m`) and
`CATALOG_SEARCH_HEAP_OPTS` (Elasticsearch, default `-Xms512m -Xmx512m`), which
holds the whole stack near 2 GB (server 0.9, search 1.1, PostgreSQL 0.1) where
1 GB heaps used about 2.8 GB. A catalog of this size runs well on them.

- Change a heap by setting the variable and running `up -d --wait`; the
  containers are recreated and the data stays.
- Read the effect with `docker stats --no-stream`, and the heap itself with
  `-Xmx` in the container's Java arguments. The resident figure runs above the
  heap (metaspace, buffers).
- If the server restarts with `OutOfMemoryError` in its log, or search
  queries time out, raise that one heap by 256m; do not lower it again.
- The Docker engine keeps memory after its containers stop; returning it is
  an engine restart (above), not a heap change.

## Lesson

A container that mounts a path inside a worktree is tied to that worktree's
life. Deployable infrastructure mounts nothing from a checkout: use inline
Compose `configs`, or a path under the user's data folder.
