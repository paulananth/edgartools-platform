# Local testing: independent copies

A baseline is a known starting copy of test data. Each agent gets its own
writable copy. Refresh the starting copy after checks pass; retain a backup
so it can be restored. This is local testing, not a production deployment.

## Agent rules

- Work automatically within the assigned task. The operator authorized no
  intermediate approval prompts for this local testing work on 2026-10-16.
  Ask only when agents would overlap or the requested scope is unclear.
- Use a dedicated worktree for code. All agents share one PostgreSQL 16
  server, environment `codex-local-lab`, started by the command below.
  `copy <name>` is the separate data copy for a disruptive test. Another
  agent's files and that copy are never an automatic cleanup target.
- Keep the six stores together for a test copy: MDM, RDM, silver, Rules,
  Bookkeeping and Change Journal. Reuse their existing migrations and
  restricted runtime roles. Use the Docker runtime already configured.
- Create and check a candidate baseline using the task's pinned captures
  and invented fixtures. Preserve exact source numbers under the project's
  BIGINT/64-bit rule. A failed check leaves the existing baseline in place.
- Use ordinary PostgreSQL backup/restore. Copy only while workers are idle;
  verify the restored copy, including MDM IDs and source links. Keep the
  identity registry and accepted decisions with the data.
- Make the verified baseline available to new environments automatically.
  Existing environments retain their own data and selected starting copy.
  Serialize baseline updates so two agents cannot replace it concurrently.
- Stopping an environment preserves its data. Keep recoverable backups
  outside Docker volumes. Reports contain counts, never source values,
  credentials or database addresses.

## Run from your worktree

Use a repository checkout containing `infra/scripts/local-test-stores.py`.
Run `uv run --extra mdm python infra/scripts/local-test-stores.py --help`
to check that the implementation is present. From your own worktree:

```bash
docker pull postgres:16-alpine
uv run --extra mdm python infra/scripts/local-test-stores.py up codex-local-lab
uv run --extra mdm python infra/scripts/local-test-stores.py status codex-local-lab
```

`up` creates the shared server when it is missing and preserves its data when
it is already running. The procedure for that server is
`docs/local-agent-testing.md`.

MySQL and SQL Server are other engines on the same Docker context. They are
not databases inside PostgreSQL. MDM, RDM, Rules, Bookkeeping, Change Journal
and silver stay on PostgreSQL. Start MySQL when the task names MySQL. Start
SQL Server only when the task names SQL Server. Each password lives in a
private mode `0600` env file and is never printed or committed.

```bash
docker pull mysql:8
docker volume create edgartools-local-mysql-data
docker run -d --name edgartools-local-mysql \
  -p 127.0.0.1::3306 \
  --env-file <private-mysql-env> \
  -v edgartools-local-mysql-data:/var/lib/mysql \
  mysql:8
```

```bash
docker pull mcr.microsoft.com/mssql/server:2022-latest
docker volume create edgartools-local-sqlserver-data
docker run -d --name edgartools-local-sqlserver --platform linux/amd64 \
  -p 127.0.0.1::1433 \
  --env-file <private-sqlserver-env> \
  -v edgartools-local-sqlserver-data:/var/opt/mssql \
  mcr.microsoft.com/mssql/server:2022-latest
```

The MySQL file sets `MYSQL_ROOT_PASSWORD`. The SQL Server file sets
`ACCEPT_EULA=Y` and `MSSQL_SA_PASSWORD`. On Apple Silicon, SQL Server runs as
`linux/amd64`. Repeating `docker run` against an existing named container is
a conflict; start the existing container instead.

`up` creates empty migrated stores. Load the assigned data through qualified
readers and workers before treating the backup as a source-data baseline.
`backup --baseline` checks a restore before selecting it for future copies.
From another worktree, `copy <new-name>` uses that baseline; `stop <name>`
preserves the environment. Source the reported private environment file in
your terminal; keep its contents out of reports.

Read `docs/local-agent-testing.md` in that checkout for recovery and backup
details. Verify startup and the task's data checks before claiming readiness.
This policy adds no provider access or production deployment and never
supplies invented operator approval words for another workflow.
