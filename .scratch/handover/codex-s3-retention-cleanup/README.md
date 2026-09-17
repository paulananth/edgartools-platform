# codex/s3-retention-cleanup — stashed work, checked in as a patch

Checked in 2026-09-16. **This is a preserved artifact, not a merge candidate.**

## What this is

`stash@{1}` in the local repo, created 2026-08-01 20:10 ET:

    On codex/s3-retention-cleanup: claude-handoff: direct Snowflake publication cutover

81 files, 587 insertions, 3330 deletions. The branch it was stashed on
(`codex/s3-retention-cleanup`) no longer exists locally or on the remote, so
the stash could not be popped back onto anything.

| | |
|---|---|
| stash sha | `ee3fa9a1c2a890719fa53db44d507bd3aa00f38e` |
| base commit | `b9df23d2` — "Chart production observability and image cost controls (#327)", 2026-08-01 |
| base on main? | yes, `b9df23d2` is an ancestor of `main` |
| `main` ahead of base | **737 commits** |

## Why it is a patch and not a commit of applied changes

`git stash apply` onto `main` at `50d9a71d` produced **31 conflicted files**
(full list in `conflicts-against-50d9a71d.txt`), including:

- `edgar_warehouse/application/warehouse_orchestrator.py`
- `edgar_warehouse/application/command_context_factory.py`
- `edgar_warehouse/infrastructure/warehouse_settings.py`
- `infra/scripts/deploy-aws-application.sh`
- `infra/snowflake/sql/bootstrap/04_refresh_wrapper.sql`
- the whole `infra/terraform/snowflake/modules/native_pull/` module

plus a modify/delete conflict on `infra/scripts/go-live.sh`, which `main`
renamed to `install.sh` (snowflake-account-cutover map, Ticket 05).

Committing that state would have written conflict markers into live source
files. The stash content is preserved here verbatim instead, losing nothing.
The original `stash@{1}` was applied with `apply`, never `pop`, and is still
present in the local repo.

## Read this before applying any of it

The patch **deletes infrastructure that is live in production today**:

- `infra/terraform/snowflake/modules/native_pull/` (main.tf, outputs.tf,
  variables.tf, versions.tf, and its three SQL procedures) — 553 lines of
  `main.tf` alone.
- `infra/snowflake/sql/bootstrap_native_pull.py` (253 lines).
- `infra/snowflake/sql/bootstrap/04_refresh_wrapper.sql` (249 lines).
- `tests/architecture/test_snowflake_native_pull_contract.py` (94 lines).

Per CLAUDE.md, `SNOWFLAKE_RUN_MANIFEST_TASK` must be STARTED in
`EDGARTOOLS_GOLD` and is central to the gold refresh path, and
`04_refresh_wrapper.sql` carries the documented fix for the Snowflake Scripting
multi-column cursor defect (`Unsupported: Scalar subquery with multi-column
SELECT clause`). Deleting these without a replacement path would break gold
refresh in prod.

The intent recorded in the stash subject — "direct Snowflake publication
cutover" — may well have been superseded by the silver-snowflake-migration and
dbt-gold-silver-rewiring work that landed across those 737 commits. Establish
that before treating any of this as work still to do.

## How to inspect it

    git apply --check .scratch/handover/codex-s3-retention-cleanup/codex-s3-retention-cleanup.patch   # will fail; see conflicts file
    git apply --3way  .scratch/handover/codex-s3-retention-cleanup/codex-s3-retention-cleanup.patch   # 3-way, expect conflicts

To see it in its original context instead, check out the base commit:

    git worktree add ../inspect-b9df23d2 --detach b9df23d2
    cd ../inspect-b9df23d2 && git apply .../codex-s3-retention-cleanup.patch

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014oAc1nXCnJEqHscRpK293F
