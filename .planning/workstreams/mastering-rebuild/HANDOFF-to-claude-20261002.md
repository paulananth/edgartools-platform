# Claude continuation: fresh mastering

Prepared 2026-10-02 07:10 ET. Operator: "create pr and write handoff to claude".
Updated for the operator's "update the handoff and instructions to hand over
the draft pr to claude" (2026-10-02).
Status: implementation committed; PostgreSQL qualification and cleanup incomplete.
Scope: **local qualification only**. The operator selected this environment;
hosted deployment and merge are outside this handoff.

## Start here

The source branch is `codex/mastering-rebuild-20261001`, based on GitHub main
`542a9fa04f4359bed7e097b4cb1d5fa4b89ede15` (PR #779), reverified at rebase.
The rebased branch is pushed. **Source draft: [PR #780](https://github.com/paulananth/edgartools-platform/pull/780).**
Verified 2026-10-02 08:52 ET: OPEN, draft, base main, source head
`30c4f3c1a3d5253cc17ef88f1dae84c46d303e3e` at creation. Later documentation
commits update this handoff; verify the live head before continuation. GitHub
access now works after the session permissions refresh. The draft body is
PR-DRAFT.md beside this handoff. Claude owns review and qualification
continuation described below.
Original implementation commits:

- `c936bd60`: remove three unreachable modules and five obsolete cases.
- `d0733de7`: bounded mastering acceptance and local qualification runner.
- `a0e6b685`: consolidated agent guides and qualification evidence.

Claude owns continuation on a new `claude/mastering-qualification-20261002`
branch and dedicated worktree. Keep Codex's branch as the reviewable source.
From a writable Git checkout, fetch and create the continuation tree:

```bash
git fetch origin
git worktree add -b claude/mastering-qualification-20261002 \
  ../edgartools-platform-claude-mastering-qualification-20261002 \
  origin/codex/mastering-rebuild-20261001
```

Check branch, status, last commit and active-workstream before edits. Create
`.planning/workstreams/mastering-qualification-claude/` with a checklist for
every pending part below; link this source ticket and keep ET verification
timestamps. The copied `.planning/active-workstream` says `fix-pipelines`;
it is historical shared state, not this task's ownership assignment.

## Draft PR ownership and instructions

Claude owns review, qualification fixes, evidence updates and follow-through.
Codex's published branch remains the source snapshot. Claude's new commits
belong on its `claude/` continuation branch; the shared main checkout and
Codex's branch are protected.

1. Check for an existing source PR:

   ```bash
   gh pr list --repo paulananth/edgartools-platform --state all \
     --head codex/mastering-rebuild-20261001
   ```

   If it merged, refresh main and carry forward only still-missing work. If it
   is closed unmerged, inspect why before replacing it. If it is open, record
   its URL, head SHA, checks and review threads in the continuation ticket.

2. Verify the source PR metadata and retain it in the continuation ticket:

   ```bash
   gh pr view 780 --repo paulananth/edgartools-platform \
     --json url,state,isDraft,baseRefName,headRefName,headRefOid
   ```

   Continue from the verified current source head. If source state has changed,
   follow step 1 before carrying work forward.

3. Review Standards, Spec and GoF, then complete the pending local gates below
   on Claude's branch. Maintain a checklist and evidence, including the
   difference between fixture acceptance and actual source onboarding.

4. Publish Claude's branch and create a continuation draft against main that
   includes the source changes and Claude's fixes. Link both PRs and the
   handoff in the PR bodies using a body file. Verify the replacement retains
   the complete source diff before closing the Codex draft as superseded.
   Describe closure as supersession, never as successful qualification.

5. Mark the continuation ready only after all required local gates have real
   evidence, relevant CI checks pass and review findings are resolved.
   Any outstanding database or memory cleanup must remain explicitly
   incomplete in the task checklist. Merge or hosted deployment requires a
   separate operator instruction; neither is part of this handoff.

## Protected local state

At the original local check, the primary checkout was on main at `66ec4570`
with unrelated changes:
`.planning/workstreams/fix-pipelines/STATE.md` and
`infra/aws-prod-application.json.bak-20260915-predeploy`. Preserve both.
The current source worktree is `/private/tmp/edgartools-mastering-rebuild-20261001`;
its independent Git owner is `/private/tmp/edgartools-mastering-rebuild-20261001-owner`.
These temporary paths and evidence logs may not survive another machine/session.

## What exists and what it proves

Read `TICKET.md`, `INVENTORY.md`, `MEMORY-CLEANUP.md` in this directory and
`docs/agents/mastering-operations.md` for the exact inventory and boundaries.

- `scripts/ops/qualify_local_mastering.py` requires a new output directory,
  checks Docker and PostgreSQL 16, runs mastering plus all four pytest suites,
  checks shell syntax, and retains logs/JUnit. Failed prerequisites, PostgreSQL
  skips and timeouts leave `qualified=false`.
- `tests/support/fresh_mastering.py` loads unchanged Company/Person contracts
  and approved rules over a pinned four-record cohort: two Companies and two
  individual-filer Persons. It converts fixture fields; a full Person
  acquisition/preparation reader remains separate work.
- `tests/integration/test_fresh_mastering_postgres.py` exercises the common
  MergeStage, canonical endpoint bindings, restricted role denials, replay
  and physical local publication read-back. It has not passed PostgreSQL
  setup here. Its EMPLOYED_BY statement is synthetic and proves no employment
  fact. Local journal envelopes check the sink contract; existing integration
  tests separately qualify real Change Journal delivery and recovery.
- Existing GLEIF relationships, Company pagination, Rules authorization,
  Journal outages/recovery, leases/fencing, identity and release checks remain.
- Removed code: bronze daily-index and reference seed loaders, and the
  uncalled Security publisher. Exact five removed node IDs and caller proof
  are in INVENTORY.md. No duplicate-equivalence or CI speed claim was made.
- AGENTS.md is the shared guide; CLAUDE.md points to it. Always-loaded guidance
  decreased from 1,796 lines to 140. External memory updates are prepared only.

## Verified evidence

At 2026-10-01 23:14 ET, all non-database suites passed: **1,132 in 107.90s**.
All 25 shell scripts passed `bash -n`. Collection: **1,424 cases** (395 unit,
490 MDM, 247 architecture, 292 integration). Five cases removed and five
added: unchanged total. CI time was not measured.

Evidence on this Mac:

- `/private/tmp/mastering-final-nondatabase.xml` and `.log`.
- `/private/tmp/mastering-after-collection.txt`.
- `/private/tmp/mastering-qualification-20261001-2310/report.json`:
  `qualified=false`, Docker preflight failed; no databases created/deleted.
- `/private/tmp/mastering-postgres.log`: new acceptance had one setup error,
  no skip, at Docker image inspection.

The first test attempt had missing dependency/network-sync failures; all
non-database failures were resolved by rerunning in an existing complete
environment without changing that environment. Prefer a fresh locked
environment in Claude's worktree; do not modify another runtime's venv.

## Pending work, in order

### Rebase delta (2026-10-02 08:13 ET)

Source branch now bases on GitHub main `542a9fa04f4359bed7e097b4cb1d5fa4b89ede15`
(#779), reverified through GitHub. Main's five newer commits changed documents
only. A clean rebase retained all existing changes (verified by range-diff).
Affected checks passed again: 13 in 9.10s. The earlier 1,132-case result is
dated 2026-10-01; a new full PostgreSQL/local qualification gate remains pending.
The original commit IDs above are preserved by local tag
`archive/mastering-rebuild-pre-sync-20261002`; use the latest remote branch
head for continuation. Person and relationship activation remains subject to
the operator's paired switch-on and relationship-rule requirements in current
main's platform-validation ticket 06. Synthetic acceptance is no rule approval.

### Continuation checklist

- [x] Publish and verify the source draft — PR #780 is OPEN and draft against
  main, head 30c4f3c1 at creation; gh pr view; 2026-10-02 08:52 ET. Record its
  current URL and head again in Claude's continuation ticket.
- [x] Establish Docker access — colima status confirms running, Docker server
  29.5.2 and postgres:16-alpine image inspection succeed; 2026-10-02 08:52 ET.
  Recheck these prerequisites in Claude's session before acceptance.
- [ ] Review Standards, Spec and GoF for the implementation before changes.
  Pay attention to the unexecuted new integration case and timeout behavior:
  killing pytest can bypass fixture teardown and leave its temporary container.
  Inventory exact run-owned leftovers after a timeout; preserve other containers.
- [ ] Run the new mastering acceptance first; fix demonstrated failures.
  Require real PostgreSQL 16 migrations, restricted runtime roles, canonical
  Company/Person endpoint IDs, publication read-back and replay assertions.
- [ ] Run the complete local gate and inspect physical outputs and JUnit.
  Each suite has a 300-second budget. An integration timeout is incomplete,
  even if smaller affected subsets pass; record it and resolve the cause.
- [ ] Inventory existing local databases: exact container/database, schemas,
  connections, callers, retention and recovery. Remove only operator-authorized
  targets with current no-use evidence and recoverability; verify remaining
  stores. No existing database or Docker volume has been deleted by this task.
- [ ] Apply authorized memory corrections. The Codex notes directory is writable
  in the refreshed session (2026-10-02 08:52 ET); corrections remain unapplied.
  Submit one Codex note under `~/.codex/memories/extensions/ad_hoc/notes/`; use the prepared
  MEMORY-CLEANUP.md. Scope Claude corrections to stale implementation references
  and retain the operator's relationships-with-MDM and governance decisions.
- [ ] Update the continuation checklist, commit on Claude's branch, create a
  continuation PR, and link this draft. Close or supersede this draft only once
  the full changes are preserved in the reviewed continuation. Any unchecked
  part means the original task remains incomplete.

Commands from Claude's worktree after prerequisites are ready:

```bash
colima start
docker pull postgres:16-alpine
uv sync --frozen --extra s3 --extra mdm
uv run pytest tests/integration/test_fresh_mastering_postgres.py -q --tb=short
uv run python scripts/ops/qualify_local_mastering.py \
  --output-root /tmp/mastering-qualification-claude-20261002-<unique-run>
```

Replace `<unique-run>` with a new identifier. Success requires the runner to
exit zero, every required step to pass and `report.json` to say `qualified=true`.
No hosted cutover, real-world relationship coverage, database cleanup or
external memory application may be inferred from the non-database results.
