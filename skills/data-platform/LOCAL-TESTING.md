# Local testing: independent copies

A baseline is a known starting copy of test data. Each agent gets its own
writable copy. Refresh the starting copy after checks pass; retain a backup
so it can be restored. This is local testing, not a production deployment.

## Agent rules

- Work automatically within the assigned task. The operator authorized no
  intermediate approval prompts for this local testing work on 2026-10-16.
  Ask only when agents would overlap or the requested scope is unclear.
- Use a dedicated worktree for code. The data-platform skill starts a test
  container or a production container. A production container stays. Do not
  remove it and do not remove its volume. `local-test-stores.py` is only for
  a worktree-owned test copy. Another agent's files and that copy are never
  an automatic cleanup target.
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

## Containers

The [data-platform skill](SKILL.md) starts the container. It selects a test
instance or a production instance. This page does not start those containers.
A production container stays. Do not remove it here.

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
