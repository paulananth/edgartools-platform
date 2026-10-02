# Fresh Company, Person, and Relationship mastering

Status: incomplete — PostgreSQL/Docker and external memory access blocked
Branch: `codex/mastering-rebuild-20261001`
Base: `5b59f72ff85bfac2eda9be014cb15d7e2aa8af77` (current GitHub main, PR #774)

## Checklist

- [x] Write and verify Claude's continuation handoff with ownership, evidence and remaining gates — HANDOFF-to-claude-20261002.md checked against current main, branch, implementation, ticket and prerequisite failures; git diff --check; 2026-10-02 07:12 ET.
- [ ] Publish the owned branch and create a draft PR; verify the remote head and PR metadata.
- [x] Create an isolated Codex branch and verify its base against current main — dedicated worktree; GitHub commit/blob/tree hashes verified; fast-forward to #774; 2026-10-01 22:52 ET.
- [x] Inventory active acquisition, rules, mastering, publication and tests; review code and change history — AST import inventory plus executable/skill/script searches and GoF review recorded in INVENTORY.md; 2026-10-01 23:10 ET.
- [x] Implement bounded integrated Company/Person/Relationship acceptance and fail-closed local runner — four normalized records pass; five new cases collect; missing image, timeout and skipped-PostgreSQL report checks pass; 2026-10-01 23:14 ET.
- [ ] Build and qualify Company mastering in fresh PostgreSQL 16 stores with restricted roles.
- [ ] Build and qualify Person mastering in fresh PostgreSQL 16 stores with restricted roles.
- [ ] Build and qualify Relationship mastering with real endpoint and publication checks.
- [ ] Execute fresh local qualification and verify physical outputs — operator selected local qualification only; Docker preflight failed, report qualified=false; no hosted deployment is in scope.
- [x] Delete unused code and tests only after checking executable callers and retained contracts; record the deletion inventory — three unreachable modules, five obsolete cases; active loader/boundary checks and full non-database suite pass; c936bd60; 2026-10-01 23:14 ET.
- [ ] Inventory unused databases, review exact targets and recoverability, delete authorized unused targets, and verify remaining stores.
- [x] Consolidate CLAUDE.md and AGENTS.md around current executable architecture and operator rules — shared guide plus Claude pointer and mastering operations reference; 1,796 always-loaded lines reduced to 140; inspected references and git diff --check; 2026-10-01 23:14 ET.
- [x] Prepare authorized Codex/Claude memory corrections — MEMORY-CLEANUP.md preserves operator decisions and identifies stale schema/skill references; 2026-10-01 23:10 ET.
- [ ] Submit the authorized external memory cleanup — Codex/Claude memory directories are outside the allowed writable roots; prepared note is not applied.
- [x] Verify all non-database cases and shell syntax — 1,132 passed in 107.90s; 25 shell scripts pass bash -n; 2026-10-01 23:14 ET.
- [x] Commit code cleanup and qualification on the owned branch — c936bd60 and d0733de7, clean staged diff checks; 2026-10-01 23:14 ET.
- [ ] Run PostgreSQL integration and the complete qualification gate — 292 cases collect; new acceptance errors at Docker image inspection; no prerequisite skips and no database qualification claimed.
- [ ] Run all required verification, commit the branch, and report exact completion and remaining blockers.

## Scope and decisions

The operator requested a fresh branch, fresh deployment of Company, Person,
and Relationship mastering, unused code/test/database removal, and cleanup
of memory and runtime instruction files. Existing unrelated work and rollback
artifacts in the shared checkout are protected. The operator selected **Local
qualification only**. Existing database deletion needs exact current no-use
evidence; Docker access is unavailable, so no deletion targets were qualified.
Additional Person/role/entity source feeds are not fabricated from names.

## Evidence

## Verification evidence

- Fresh run entry: `uv run python scripts/ops/qualify_local_mastering.py --output-root <new-directory>` after locked dependency setup and PostgreSQL 16 image provisioning.
- Local run `/private/tmp/mastering-qualification-20261001-2310/report.json`: Docker access failed in 0.403s; `qualified=false`; no databases were created or deleted.
- New PostgreSQL case: 1 setup error in 0.98s, from `docker image inspect postgres:16-alpine`; `/private/tmp/mastering-postgres.log`.
- First non-database run: 1,115 passes and 16 environmental failures in 148.61s. Missing openpyxl and network-blocked uv synchronization accounted for every failure; no test was skipped or weakened.
- Those files rerun in an existing complete environment with synchronization disabled: 25 passes in 32.83s.
- Final non-database gate in that environment: **1,132 passed in 107.90s**, `/private/tmp/mastering-final-nondatabase.xml` and `.log`. Cached environments were used read-only; dependencies in another runtime's worktree were not modified.
- Affected checks: 13 passes in 4.57s. Shell gate: 25 scripts, 0 syntax failures.
- Final collection: **1,424 cases** = 395 unit + 490 MDM + 247 architecture + 292 integration. Five obsolete cases removed, five qualification cases added; total case count is unchanged. No CI/gate speed improvement is claimed or measured.
- Shared checkout retains `.planning/workstreams/fix-pipelines/STATE.md` and the predeploy application JSON backup unchanged by this task.

## Remaining blockers

Colima is stopped and the session cannot access its Docker socket. Start Colima
and provide Docker access to run fresh PostgreSQL qualification and inventory
existing local databases. External memory folders need writable access before
the prepared cleanup note can be submitted. Shell network access is restricted.

This ticket remains incomplete until all unchecked parts have real evidence.
