# Local testing: independent copies

A baseline is a known starting copy of test data. Each agent gets its own
writable copy. Refresh the starting copy after checks pass; retain a backup
so it can be restored. This is local testing, not a production deployment.

## Agent rules

- Work automatically within the assigned task. The operator authorized no
  intermediate approval prompts for this local testing work on 2026-10-16.
  Ask only when agents would overlap or the requested scope is unclear.
- Use a dedicated worktree for code. The shared database engines below have
  no agent and no worktree owner. Any checkout may start a missing engine
  and may use it. Leaving a worktree does not stop or delete an engine.
  `local-test-stores.py` is only for a worktree-owned test copy. Another
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

## Shared engines

Create these on the Docker context already configured. Leave `DOCKER_HOST`
unset. Do not pass a worktree path, an agent name, or an owner label. If a
named container already exists, start it. Do not create a second one. Each
password lives in a private mode `0600` env file and is never printed or
committed.

PostgreSQL 16 is the platform engine. MDM, RDM, Rules, Bookkeeping, Change
Journal and silver stay here.

```bash
docker pull postgres:16-alpine
docker volume create edgartools-local-postgres-data
docker run -d --name edgartools-local-postgres --restart unless-stopped \
  -p 127.0.0.1::5432 \
  --env-file <private-postgres-env> \
  -v edgartools-local-postgres-data:/var/lib/postgresql/data \
  postgres:16-alpine
```

The private file sets `POSTGRES_PASSWORD`.

MySQL and SQL Server are separate engines, not databases inside PostgreSQL.
Start MySQL when the task names MySQL. Start SQL Server Express when the task
names SQL Server. Express is the free edition and is limited to 10 GB per
database. Do not set `MSSQL_PID` to Standard or Enterprise.

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
`ACCEPT_EULA=Y`, `MSSQL_PID=Express`, and `MSSQL_SA_PASSWORD`. On Apple
Silicon, SQL Server runs as `linux/amd64`.

## Worktree-owned test copy

`infra/scripts/local-test-stores.py up <name>` attaches that environment to
the current worktree and refuses every other checkout. Use it only for a
private test copy, never for the shared engines above.

```bash
uv run --extra mdm python infra/scripts/local-test-stores.py up agent-test
uv run --extra mdm python infra/scripts/local-test-stores.py backup agent-test --baseline
```

`up` creates empty migrated stores for that copy. Load the assigned data
through qualified readers and workers before treating the backup as a
source-data baseline. `backup --baseline` checks a restore before selecting
it for future copies. From another worktree, `copy <new-name>` uses that
baseline; `stop <name>` preserves the copy. Source the reported private
environment file in your terminal; keep its contents out of reports.

Read `docs/local-agent-testing.md` in that checkout for recovery and backup
details. Verify startup and the task's data checks before claiming readiness.
This policy adds no provider access or production deployment and never
supplies invented operator approval words for another workflow.
