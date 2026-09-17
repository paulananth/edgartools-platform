# Handover — 2026-09-16, Claude → Codex

Session: https://claude.ai/code/session_014oAc1nXCnJEqHscRpK293F

> **Superseded in part.** This document remains the best record of the prod
> deploy — image digests, the five verification steps, and the six
> `deploy-aws-application.sh` gotchas. But its "Session close" section predates
> PR #652 and the final branch/worktree cleanup. For current state, read
> [`2026-09-16-codex-handoff-final.md`](./2026-09-16-codex-handoff-final.md);
> where the two disagree, that one wins.

## TL;DR

`main` is at `7e69e4e4`. Prod is deployed from `50d9a71d` and verified (the two
commits since are documentation only — nothing deployable changed). Nothing is
uncommitted. Worktrees, branches and stashes are cleaned up. The pipeline is
still down, but for a reason no code change can fix: **Snowflake billing**.

**See "Session close" at the bottom for the final state** — the Open items
section below was written mid-session and three of its entries are now done.

## State of `main`

Four PRs landed this session, all squash-merged, all CI-green:

| PR | Squash | What |
|---|---|---|
| #645 | `eb521c9d` | rename `silver_database_write` → `identity_refresh_run_manifest_write` |
| #646 | `a19aef04` | drop the dead `silver_root` parameter, name the bookkeeping gate |
| #647 | `91d5f0f8` | audit every CLAUDE.md deployment-status claim against the running image |
| #648 | `50d9a71d` | guard relationship-version closes against an illegal date interval |

No open PRs. All merged branches have zero unpushed commits.

## Prod deploy — done and verified

Built from `50d9a71d`, both roles, pushed to `edgartools-prod-images`:

- warehouse `sha256:b9e35e60ea2f9e7df10b7caa7fee5dd85b25dd448946c2b48f45c15554a42e53`
  (tags `warehouse-sha-50d9a71dd451`, `warehouse-prod`)
- mdm `sha256:01cc00a1d8c6ae1d81450806e9ce99a58ad987c8f2f48654ad04d547254ff370`
  (tags `mdm-sha-50d9a71dd451`, `mdm-prod`)

`uv.lock` and the Dockerfiles were unchanged since the previously deployed
commit, so the deps images were **not** rebuilt (`warehouse-deps-21b758564fc30552`,
`mdm-deps-1b3db75385592471` still current).

Task definitions, before → after:

| Task def | Was | Now |
|---|---|---|
| `edgartools-prod-large` | 304 / `37b0c68c` | **305** / `b9e35e60` |
| `edgartools-prod-medium` | 306 / `37b0c68c` | **307** / `b9e35e60` |
| `edgartools-prod-small` | 302 / `37b0c68c` | **303** / `b9e35e60` |
| `edgartools-prod-mdm-large` | 205 / `ef7f50c1` | **206** / `01cc00a1` |
| `edgartools-prod-mdm-medium` | 271 / `ef7f50c1` | **272** / `01cc00a1` |
| `edgartools-prod-mdm-small` | 273 / `ef7f50c1` | **274** / `01cc00a1` |

Ten state machines updated: `targeted-resync`, `gold-refresh`, `mdm`,
`load-history`, `daily-incremental`, `residual-holds-graph`,
`one-click-data-refresh`, `generation-build`, `seed`, `mdm-utility`.

Verification actually performed (not inferred from a zero exit code):

1. `DEPLOY_EXIT=0` read from the log body, not the task notification.
2. All six task defs re-queried and confirmed flipped off the baseline digests.
3. Task-def ARNs grepped out of **three** state machine definitions, all
   referencing the new revisions: `mdm` → `mdm-medium:272`, `mdm-small:274`,
   `medium:307`; `daily-incremental` → `large:305`, `medium:307`;
   `load-history` → `large:305`, `mdm-medium:272`, `medium:307`.
   **Not verified:** no state machine was found referencing
   `edgartools-prod-mdm-large:206`. That task def was registered on the new
   digest, but which machine (if any) consumes it was not established —
   `mdm-large` is the pinned residual-security profile per CLAUDE.md's
   Ticket 28, so confirm this before relying on it.
4. The fix proven present *inside* the MDM image before deploying:
   `docker run --entrypoint python … ` confirmed `close_relationship_version`
   contains the write-level guard, `pipeline.py` contains the caller guard,
   and the `still_open` (6) / `worker_session.rollback()` (3) marker counts
   match the worktree exactly.
5. The rollback-cleanup lock (`s3://edgartools-prod-warehouse-690839588395/warehouse/release/ecr_rollback_cleanup.lock`)
   confirmed released — only `ecr_rollback_registry.json` remains in that prefix.

Rollback anchor: the previous immutable tags are still in ECR, and the
pre-deploy manifest is preserved at
`infra/aws-prod-application.json.bak-20260915-predeploy` in the shared checkout.

## What is still broken, and why the deploy does not fix it

Execution `daily-incremental-ticket17-verify-1789514832` (started 2026-09-15
19:27 ET, FAILED 2026-09-16 07:59 ET, 12.5 h) had **two independent faults**:

1. The relationship bug — now fixed and deployed (#648).
2. **The Snowflake trial expired on `PRJEDJU-QJB05385`.** All warehouses are
   suspended, so `mdm mastering` dies in ~3 seconds. No image or task-def
   change affects this.

Until billing is restored, every MDM run will keep failing fast. Once it is:
that execution is `REDRIVABLE` with `redriveCount: 0`, so **redrive it rather
than starting a fresh execution** — a redrive resumes from the failure point,
a `start-execution` restarts from the start state and repeats the 12.5 hours.

## Open items

**Operator (human) only:**

- Restore Snowflake billing, then redrive the failed execution. **This is the
  only thing still blocking the pipeline.**

**Available to pick up:**

- **CLAUDE.md 5-whys entry for the zero-shares bug shape.** Not written. This
  is the 5th instance of the same shape in `pipeline.py` and `.scratch/` never
  ticketed the site. CLAUDE.md's own debugging discipline (step 4) asks for a
  documented chain when an issue is likely to recur. The full write-up already
  exists in PR #648's body — this is a copy, not new analysis.
- ~~Worktree/branch cleanup~~ — **done**, see Session close.
- ~~The shared checkout is on a stale branch~~ — **done**: it is on `main` at
  `7e69e4e4`, clean. The superseded `CLAUDE.md` was discarded; its one genuinely
  new datum (the 2026-09-16 cross-session checkpoint readback, 79,788 → 80,214
  across ten ECS tasks) survives as `claudemd-live-verification-evidence.patch`
  next to this file.
- **Three CLAUDE.md claims left unverified** by #647's audit: the
  `mdm_change_log` write-side diff, Ticket 101 filing-text strip, and the
  capped-restart watermark.

## Deploy gotchas — read before running `deploy-aws-application.sh`

Four attempts were needed. Three of the four failures were setup mistakes, not
platform problems. All four failed closed; attempts 1 and 2 mutated nothing.

1. **`--aws-account-id` is required** (validated at line 406) and is *not*
   derived from the environment.
2. **`--operator-alert-topic-arn` is mandatory with `--enable-mdm`** (line 5478,
   unconditional inside the MDM branch). It must be in the same
   region/account **and have ≥1 confirmed subscription**. The correct one is
   `arn:aws:sns:us-east-1:690839588395:sec-edgar-pipeline-alerts` — confirmed
   both by its subscription count and by grepping the deployed
   `daily-incremental` definition. (`edgartools-prod-snowflake-manifest-events`
   would also pass validation and is the wrong topic.)
3. **`MANIFEST_FILE` is derived from `REPO_ROOT`, not from `--output-file`**
   (line 527). The script *reads* `infra/aws-<env>-application.json` to
   discover the cluster ARN, role ARNs, bucket names and secret ARNs. A fresh
   worktree has no such file (it is gitignored), so the deploy fails with
   "could not resolve ECS cluster ARN". Copy the manifest in first.
4. **A fresh worktree needs `uv sync --extra s3 --extra mdm-runtime`.** The
   deploy runs `ecr_rollback_cli.py` under `uv`, which auto-creates a bare venv
   without boto3, failing at `import boto3`. **This failure is not clean:** by
   that point the script has already configured the S3 → SNS notification on
   `edgartools-prod-snowflake-export-690839588395` for the manifest prefix.
   The write is idempotent, but do not assume a failed deploy mutated nothing
   just because the task definitions are unchanged — that probe is too narrow.
5. **The rollback-cleanup lock never auto-expires** and its release is
   silenced (`>/dev/null 2>&1 || log "WARN: …"`). A successful deploy can still
   leave it held. Check
   `s3://edgartools-prod-warehouse-690839588395/warehouse/release/` and clear
   with `ecr_rollback_cli release-lock --force` only after confirming no deploy
   or cleanup is active.
6. **Background-task exit codes in the agent harness misreported five times
   this session.** Always write `echo "EXIT=$?"` into the log and read the log
   body; do not trust a completion notification's "exit code 0".

## The #648 fix, in one paragraph

`mdm_relationship_instance` has `ck_rel_instance_valid_interval`
(`valid_from_date IS NULL OR valid_to_date IS NULL OR valid_to_date >
valid_from_date` — strictly greater). `_deactivate_if_zero_shares` closed a
HOLDS version at a non-advancing date, and because that write goes through the
long-lived outer session, the failed flush poisoned it and every later
autoflush re-raised `PendingRollbackError` for ~5 hours. The invariant now
lives at the write (`close_relationship_version` refuses a close the constraint
would reject), covering all four previously unguarded call sites, plus an
explicit caller-side guard and rollback on three worker seams. Four new tests
in `TestZeroSharesDisposalGuard`, proven red on `origin/main` with the same
"raised as a result of Query-invoked autoflush" wording as the production
traceback, including a positive control and a NULL-`valid_from_date` case.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014oAc1nXCnJEqHscRpK293F

## Session close — final state

Appended after the body above was written. Where the two disagree, this wins.

### Repository

```
main              7e69e4e4   (shared checkout current, clean)
Local branches    main, codex/mdm-golden-copy-release1-wayfinder
Remote branches   4  — all unmerged or Codex's
Worktrees         2  — shared checkout + Codex's
Stashes           1  — Codex's fundamentals work (kept)
```

Six PRs landed: #645, #646, #647, #648 (the relationship-version guard, which
prod runs), then #649 and #650, both documentation only.

| PR | Squash | What |
|---|---|---|
| #649 | `928ac2c5` | this handover doc + two rescued wayfinder commits |
| #650 | `7e69e4e4` | the preserved s3-retention stash + its decision |

### Cleanup performed

- All Claude branches deleted, local and remote. Each deletion was gated on
  proving the content exists on `origin/main` by checking the **files**, not
  `git merge-base --is-ancestor` — squash merges make that check return false
  for genuinely merged branches (hit live on #645 this session).
- Four worktrees removed (`claude-claudemd`, `claude-silver-root`,
  `claude-zeroshares`, `claude-deploy-main`), plus the two created for the
  handover work. Only the shared checkout and Codex's remain.
- Shared checkout moved off `claude/mdm-tail-single-machine-wayfinder`
  (276 commits behind) onto `main`, then fast-forwarded to `7e69e4e4`.

### Stash dispositions

| Stash | Disposition |
|---|---|
| `codex/s3-retention-cleanup` (`ee3fa9a1`) | **dropped** — preserved on `main` by #650 first |
| `claude/ticket09-sqlite-port-survey` (`6f2992c5`) | **dropped** — 4 timestamp lines in `STATE.md`, nothing of substance |
| `codex/release-evidence-contract` | **kept**, now `stash@{0}` |

**Its index has shifted twice** (it was `stash@{2}`). It is the only stash left,
so a bare `git stash drop` would now destroy it. 14 files, +425/−41, touching
`bootstrap_fundamentals.py`, `fundamentals_ingest.py`, the CLI and 4
release-readiness ticket docs — the one stash that was never analysed for
unlanded value. That analysis is still available to do.

### Two commits rescued before their branch was deleted

`claude/mdm-tail-single-machine-wayfinder` held 2 commits that existed in no
remote branch and nowhere else: 200 insertions of
`.scratch/state-machine-consolidation` ticket docs. They are on `main` as
`git am`-ready patches in `.scratch/handover/wayfinder-mdm-tail-unmerged/`.

### The deploy manifest was lost, then rebuilt

`infra/aws-prod-application.json` is **gitignored**, and the post-deploy copy
lived only inside the `claude-deploy-main` worktree — so removing that worktree
destroyed the deploy record, leaving the shared checkout holding the *pre*-deploy
values (`small:302`, old digests). It was rebuilt from live AWS state:
`small:303`/`medium:307`/`large:305` on `b9e35e60`,
`mdm-small:274`/`mdm-medium:272`/`mdm-large:206` on `01cc00a1`.

This matters operationally: `deploy-aws-application.sh` **reads** that file to
discover the cluster ARN, role ARNs, bucket names and secret ARNs (gotcha 3
above). A missing or stale copy breaks or misinforms the next deploy. Do not
delete a worktree that holds the only copy.

### Deliberately left in place

- **Codex's worktree and its 2 remote branches** — protected under CLAUDE.md
  without an explicit handoff; 10 unmerged commits, active 2026-09-15.
- **`origin/claude/ticket05-row-level-parity-reverify`** — not stale: 2 unmerged
  commits, 482 insertions including `silver_parity.py` and a 192-line test file,
  last touched 2026-09-06. Needs a decision, not deletion.
- **`infra/aws-prod-application.json.bak-20260915-predeploy`** — untracked local
  backup, the rollback anchor for the previous deploy.

### Still open

1. **Restore Snowflake billing, then redrive**
   `daily-incremental-ticket17-verify-1789514832` (`REDRIVABLE`,
   `redriveCount: 0`). Redrive resumes from the failure point; a fresh
   `start-execution` repeats 12.5 hours. Operator only.
2. The CLAUDE.md 5-whys entry for the zero-shares shape (write-up already in
   #648's body).
3. The three CLAUDE.md claims #647 left unverified.
4. `origin/claude/ticket05-row-level-parity-reverify` — land or abandon.
5. Codex's `stash@{0}` — analyse for unlanded value.
6. `edgartools-prod-mdm-large:206` has no known state-machine consumer
   (verification step 3 above).
