---
name: openmetadata-deploy
description: Start, stop, read back or recover the local OpenMetadata server (port 8587) with one script that touches OpenMetadata alone. Use when asked to deploy, bring up, shut down, restart, check or set the memory of OpenMetadata, or when its server will not start. Publishing and the catalog stay in the openmetadata skill.
---

# Deploy OpenMetadata

Every step here is one command of one script. It works on the OpenMetadata
stack alone: the server, its PostgreSQL and its search, on `127.0.0.1:8587`. It
never stops, removes or reads anything else, and no command of it removes data.
Do not run `docker`, `docker compose` or any other system command for this work:
if the script cannot do a step, report that, and fix the script. Credentials,
the AI Governance clearout, upgrades and catalog resets are the
[openmetadata skill](../openmetadata/LOCAL-SERVER.md).

```
uv run --no-project python <this skill>/scripts/openmetadata.py <status|up|stop|recover>
```

Run it from a checkout at current `origin/main`: it reads that checkout's
compose file and refuses a stale one (another port, or a mounted path of a
checkout).

## The commands

| Need | Command | It answers |
|---|---|---|
| Is it up? | `status` | Each container's state, health and memory, the port, host-path mounts and the API read. Exit 0 only when all are right; every `PROBLEM:` line says what is not |
| Bring it up | `up` | Refuses a bad compose file, starts the stack, waits for health (a cold start takes 10 to 20 minutes), then prints `status` |
| Shut it down | `stop` | Stops the containers and prints that the two data volumes are kept |
| It will not start | `recover` | Removes the server container only, then `up`. The catalog is in the volumes and is not touched |
| Set the memory | `up --server-heap 768m --search-heap 512m` | Recreates the containers with those heaps; the data stays |

A deployment is read back with `status`, never from a container being up. It
reports `PROBLEM` when the API does not answer 200, the server is not on 8587,
or it mounts a host path.

First deployment, or a new password or token: run `bash infra/openmetadata/init.sh`
instead of `up`; it starts the stack through the same compose file and adds the
credentials and the clearout.

## Memory

The default heaps are 768m (server) and 512m (search), which holds the stack
near 2 GB where 1 GB heaps used about 2.8 GB. A catalog of this size runs well
on them. If the server's log shows `OutOfMemoryError`, or searches time out,
raise that one heap by 256m with `up --server-heap` or `--search-heap`; do not
lower it again. `status` shows each container's memory, and the resident figure
runs above the heap.

## When it will not start

| Symptom in `up` or `status` | Cause | Fix |
|---|---|---|
| "stale compose file", or "mounts a host path" | The checkout is old; it maps another port or mounts a file of a worktree that may be deleted | Update the checkout to `origin/main`, then `recover` |
| The server exited, the others are healthy | It started before its database was healthy | `recover` |
| `PROBLEM: the API answered 0` while all are healthy | The server is still starting | `status` again; after 20 minutes, `recover` |

Anything else, such as the container engine being down, is outside this skill:
report it as a blocker and stop.

## Lesson

A container that mounts a path inside a worktree is tied to that worktree's
life. Deployable infrastructure mounts nothing from a checkout: use inline
Compose `configs`, or a path under the user's data folder. The script's
preflight is what keeps that true.

## Handshake

Starts and stops the local catalog server for [openmetadata](../openmetadata/SKILL.md); the server stays stopped during a load, since a load never reads or writes the catalog. The table of who owns what and hands off to whom is [OWNERSHIP.md](../OWNERSHIP.md).
