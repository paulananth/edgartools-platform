# Local testing: independent copies

A baseline is a known starting copy of test data. Each agent gets its own
writable copy. Refresh the starting copy after checks pass; retain a backup
so it can be restored. This is local testing, not a production deployment.

## Agent rules

- Work automatically within the assigned task. The operator authorized no
  intermediate approval prompts for this local testing work on 2026-10-16.
  Ask only when agents would overlap or the requested scope is unclear.
- Use a dedicated worktree and PostgreSQL 16 container/volume per active
  agent environment. Check ownership before changing a resource. Another
  agent's files, database and volume are never an automatic cleanup target.
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

The skill states the rules; the local environment script must enforce them.
Its implementation is pending the local-agent-stores ticket. Do not invent
commands or claim a successful setup from this document alone. This policy
adds no provider access or production deployment and never supplies invented
operator approval words for another workflow.
