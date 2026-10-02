# Fresh Company, Person, and Relationship mastering

Status: incomplete — draft PR #780 published; PostgreSQL qualification and cleanup pending
Branch: `codex/mastering-rebuild-20261001`
Base: `542a9fa04f4359bed7e097b4cb1d5fa4b89ede15` (GitHub main verified 2026-10-02 08:12 ET, PR #779)

## Checklist

- [x] Synchronize the mastering branch against current GitHub main and verify retained changes before publishing the draft — clean rebase onto #779; range-diff confirms all six existing changes identical; original tip preserved by archive/mastering-rebuild-pre-sync-20261002; main refreshed through GitHub read connector using matching available local Git objects; 2026-10-02 08:13 ET.
- [x] Refresh the handoff and PR evidence after synchronization; retain explicit incomplete qualification gates — affected tests 13 passed in 9.10s; handoff delta and PR body retain dated full-suite evidence and pending PostgreSQL/database/memory gates; 2026-10-02 08:13 ET.
- [x] Document draft PR continuation ownership for Claude in the handoff and CLAUDE.md — scoped instruction pointer, source PR discovery/creation, separate Claude branch and replacement PR procedure, ready gates and blocker status; three local links verified and git diff --check passes; 2026-10-02 08:17 ET.
- [x] Write and verify Claude's continuation handoff with ownership, evidence and remaining gates — HANDOFF-to-claude-20261002.md checked against current main, branch, implementation, ticket and prerequisite failures; git diff --check; 2026-10-02 07:12 ET.
- [x] Publish the owned branch — git push succeeded through b35f8da3; 2026-10-02 07:13 ET.
- [x] Create a draft PR and verify its metadata — [PR #780](https://github.com/paulananth/edgartools-platform/pull/780), OPEN and draft, base main, head codex/mastering-rebuild-20261001 at 30c4f3c1; gh pr view verification; 2026-10-02 08:52 ET.
- [x] Refresh and publish the handoff with the verified PR URL and resolved sandbox prerequisites — f06a0889 pushed; PR #780 head and updated body verified with gh pr view; git diff --check passes; 2026-10-02 08:55 ET.
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
- [ ] Submit the authorized external memory cleanup — prepared note is not applied; Codex notes directory verified writable after permissions refresh, 2026-10-02 08:52 ET; inspect Claude memory targets before changes.
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
evidence; no deletion targets have been qualified.
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

## Draft preparation refresh (2026-10-02)

Operator agreed to publish only the mastering rebuild as a draft PR, preserving
the historical research branches. Rebased on GitHub main #779. Its five newer
commits changed research/ticket documents only; runtime code, tests and workflow
were unchanged. Range-diff matched every existing branch commit after rebase.
Affected checks passed again (13 in 9.10s); the previous full non-database
results above remain dated 2026-10-01, not a new complete gate result. The old
complete environment was removed by external workspace cleanup; this rerun
used the primary Python environment and cached ijson read-only, without changes
to another runtime's dependencies. PostgreSQL qualification remains incomplete.

## Prerequisite refresh (2026-10-02 08:52 ET)

The earlier sandbox blockers are resolved in the refreshed session. gh auth
status confirms paulananth and PR #780 was created and verified. colima status
confirms it is running; docker version reports server 29.5.2; docker image
inspect confirms postgres:16-alpine is available. The Codex memory notes
directory is writable. These prerequisite checks do not qualify mastering,
approve database removal or apply the prepared memory corrections. Claude owns
the continuation gates in the handoff.

This ticket remains incomplete until all unchecked parts have real evidence.
