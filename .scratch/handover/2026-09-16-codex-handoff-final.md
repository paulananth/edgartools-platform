# Handoff → Codex — 2026-09-16, session end

Session: https://claude.ai/code/session_014oAc1nXCnJEqHscRpK293F

**This is the current, authoritative handoff.** The companion document
[`2026-09-16-codex-handover.md`](./2026-09-16-codex-handover.md) is still the
best record of the *prod deploy* (image digests, the five verification steps,
and six `deploy-aws-application.sh` gotchas) — read it for that. But its
"Session close" section predates #652 and the final cleanup, so **where the two
disagree, this document wins.**

## State in one screen

```
main              f3fe8beb   (shared checkout current, 0 behind, clean)
Local branches    main  — only
Remote branches   origin/main  — only
Worktrees         1  — the shared checkout; the worktrees dir is empty
Open PRs          none
Stashes           1  — Codex's fundamentals work (see below)
```

Eight PRs landed this session:

| PR | Squash | What |
|---|---|---|
| #645 | `eb521c9d` | rename `silver_database_write` → `identity_refresh_run_manifest_write` |
| #646 | `a19aef04` | drop the dead `silver_root` parameter, name the bookkeeping gate |
| #647 | `91d5f0f8` | audit every CLAUDE.md deployment-status claim against the running image |
| #648 | `50d9a71d` | **guard relationship-version closes against an illegal date interval** |
| #649 | `928ac2c5` | the deploy handover + two rescued wayfinder commits |
| #650 | `7e69e4e4` | the preserved s3-retention stash + its decision |
| #651 | `1bfa4828` | brought that handover current |
| #652 | `f3fe8beb` | **took over the Codex MDM-enrichment wayfinder branch, 10 commits** |

## Production, verified live at session end

| Task definition | Revision | Image |
|---|---|---|
| `edgartools-prod-small` | 303 | `sha256:b9e35e60…` |
| `edgartools-prod-medium` | 307 | `sha256:b9e35e60…` |
| `edgartools-prod-large` | 305 | `sha256:b9e35e60…` |
| `edgartools-prod-mdm-small` | 274 | `sha256:01cc00a1…` |
| `edgartools-prod-mdm-medium` | 272 | `sha256:01cc00a1…` |
| `edgartools-prod-mdm-large` | 206 | `sha256:01cc00a1…` |

Built from `50d9a71d`. The five commits on `main` since are documentation and
planning artifacts only — **nothing deployable changed, so no redeploy is
warranted.** The #648 fix was proven present *inside* the MDM image before
deploy (`docker run --entrypoint python`, checking the guard in
`close_relationship_version`, the caller guard in `pipeline.py`, and matching
`still_open` / `worker_session.rollback()` marker counts), not inferred from a
successful build.

## The one thing blocking the pipeline — operator only

Execution `daily-incremental-ticket17-verify-1789514832`, re-checked live at
session end:

```
status FAILED   redriveStatus REDRIVABLE   redriveCount 0
stopped 2026-09-16 07:59:15 ET
```

It had **two independent faults**. The relationship bug is fixed and deployed
(#648). The second is that **the Snowflake trial expired on `PRJEDJU-QJB05385`**
— all warehouses suspended, so `mdm mastering` dies in about 3 seconds
regardless of which image runs. No code or infrastructure change affects this.

1. Restore Snowflake billing.
2. **Redrive** that execution — do **not** `start-execution`. A redrive resumes
   from the failure point; a fresh execution restarts from the start state and
   repeats the 12.5 hours.

## Open work, ready to pick up

1. **CLAUDE.md 5-whys entry for the zero-shares bug shape.** Not written. This
   is the 5th instance of the same shape in `mdm/pipeline.py`, and `.scratch/`
   never ticketed the site — which is how it shipped. The complete write-up is
   already in PR #648's body; this is a copy, not new analysis.
2. **Codex's `stash@{0}`** — `codex/pre-pr325-merge-follow-on-20260801`, 14
   files, +425/−41, touching `bootstrap_fundamentals.py`,
   `fundamentals_ingest.py`, `cli.py`, `warehouse_orchestrator.py`,
   `deploy-aws-application.sh`, `CONTEXT.md` and 4 release-readiness ticket
   docs. **The only artifact this session never analysed for unlanded value.**
   Its branch no longer exists, so it cannot be popped back onto anything.
   Analyse it the way the others were (see "How to judge stale work" below)
   before dropping it.
3. **Three CLAUDE.md claims #647 left unverified**: the `mdm_change_log`
   write-side diff, the Ticket 101 filing-text strip, and the capped-restart
   watermark.
4. **`edgartools-prod-mdm-large:206` has no known state-machine consumer.** It
   is registered on the new digest, but grepping the definitions of
   `edgartools-prod-mdm`, `daily-incremental` and `load-history` found no
   reference to it. `mdm-large` is the pinned residual-security profile per
   CLAUDE.md's Ticket 28, so establish which machine consumes it before relying
   on that profile.

## How to judge stale work — read this before deleting anything

Four artifacts were handed over this session. **The commit count was wrong about
three of them.**

| Artifact | `ahead` said | Reality |
|---|---|---|
| s3-retention stash | 81 files of work | superseded **and never finished** — its orchestrator hunk imports `snowflake_direct`, a module absent from `main` that the stash itself never adds |
| `claude/ticket05-row-level-parity-reverify` | ahead=2 | merged via **#555**; its one genuinely unmerged commit patches `silver_parity.py`, which `72e033cf` (#626) deliberately deleted |
| `codex/ecs-cost-sizing-ticket29-…` | ahead=2 | already on `main` as `bf7a4fa9`/`4142e8aa` (re-applied, hence new SHAs). Merging it would have **reverted ten days** of Ticket 29 work |
| `codex/mdm-golden-copy-release1-wayfinder` | ahead=10 | **genuinely unlanded** — landed as #652 |

`git rev-list --count origin/main..<branch>` counts *commits*, not content, and
returns non-zero for anything cherry-picked, re-applied, or squash-merged.
`git merge-base --is-ancestor` fails the same way — it returns false for
squash-merged branches (hit live on #645).

**What actually works:** check whether the *files and their contents* are on
`main`. Compare blob SHAs per path; where they differ, check whether `main` is
ahead (line counts, `git log` on the file) and whether `main`'s own history
contains the branch's commit *subjects* under different SHAs.

One worked example, because it nearly went wrong: deleting the Codex branch in
#652's takeover, the content gate flagged `CONTEXT.md` as differing. That could
have meant the rebase silently dropped a hunk. Chasing it showed `main`'s own
`b00c7bcb` had edited the same file, and a line-level check confirmed every
Codex addition *and* every `main` addition survived — both at 788 lines. **The
gate failing was the useful signal.** Do not delete on an unexplained one.

## Operational traps confirmed live this session

- **The deploy manifest is gitignored and is an input, not just an output.**
  `deploy-aws-application.sh` reads `infra/aws-<env>-application.json` from
  `REPO_ROOT` (line 527 — *not* from `--output-file`) to discover the cluster
  ARN, role ARNs, bucket names and secret ARNs. A fresh worktree has no copy, so
  the deploy fails with "could not resolve ECS cluster ARN". Worse: the
  post-deploy copy lived only inside a worktree that was later removed, which
  **destroyed the deploy record**. It was rebuilt from live AWS state. Never
  delete a worktree holding the only copy.
- **`infra/aws-prod-application.json.bak-20260915-predeploy`** is untracked (the
  ignore rule covers `infra/aws-*-application.json`, not the `.bak` suffix) and
  is deliberately kept as the previous deploy's rollback anchor.
- **The rollback-cleanup lock never auto-expires** and its release is silenced
  (`>/dev/null 2>&1 || log "WARN: …"`), so a *successful* deploy can still leave
  it held. Check
  `s3://edgartools-prod-warehouse-690839588395/warehouse/release/` and clear
  with `ecr_rollback_cli release-lock --force` only after confirming no deploy
  or cleanup is active.
- **A fresh worktree needs `uv sync --extra s3 --extra mdm-runtime`** before any
  deploy: the script runs `ecr_rollback_cli.py` under `uv`, which auto-creates a
  venv without boto3 and fails at `import boto3` — *after* it has already
  configured the S3 → SNS notification, so that failure is not clean.
- **Background-task exit codes in the agent harness misreported five times this
  session.** Always write `echo "EXIT=$?"` into the log and read the log body; a
  completion notification claiming "exit code 0" sat on top of a real `1` and a
  real `2`.
- **`stash@{0}`'s index has shifted twice.** It is the only stash left, so a
  bare `git stash drop` would destroy it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014oAc1nXCnJEqHscRpK293F
