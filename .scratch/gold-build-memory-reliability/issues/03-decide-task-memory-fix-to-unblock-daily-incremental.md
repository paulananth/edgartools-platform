# Decide the task-memory fix to unblock the failed daily_incremental execution

Type: grilling
Status: claimed

## Question

`daily_incremental`'s first-ever prod execution (`daily-incremental-1785336584`) is now
terminally `FAILED` — all 3 retries OOM'd identically. Ticket 01 (streaming `build_gold`) is
the structural fix, but it's a real multi-file refactor that will take more than one session;
meanwhile there's a failed execution and no working `daily_incremental` path today.

Separately, this session's `/gof-refactor-reviewer` pass found that `large`
(`infra/scripts/deploy-aws-application.sh:936`, 2048 CPU) carries the **identical** 4096MB
memory ceiling as `medium` (1024 CPU) — only CPU differs. Commit `37c3171`'s stated intent for
moving `gold-refresh` to `large` back in May was explicitly more memory ("full-universe DuckDB
expands to several GB in the buffer pool during build_gold()"), but the actual change only
raised CPU, not memory. So `gold-refresh`'s own prior OOM fix may already be memory-ineffective
today, on top of `daily_incremental` never having gotten any equivalent fix at all.

This ticket decides the immediate tactical mitigation — not the structural fix (that's ticket
01) — so `daily_incremental` (and possibly `gold_refresh`, `bootstrap`, `full_reconcile`, the
other `medium`-profile `GOLD_AFFECTING_COMMANDS` members) has a working path forward now.

Questions to resolve with the user, one at a time:

1. Should `medium`'s memory be raised (e.g. 4096 → 8192MB, mirroring what `mdm-large` already
   uses), should `large`'s memory actually be raised past `medium`'s (restoring `37c3171`'s
   original intent), or should `daily_incremental` specifically move to a distinct profile?
   Recommended: raise `large`'s memory (e.g. to 8192MB) and move `daily_incremental` onto
   `large`, since `targeted_resync`/`bootstrap_full` already treat `large` as the "full-universe
   gold build" profile — this restores the fix `37c3171` intended rather than inventing a new
   profile.
2. Should this bump apply to all four `medium`-profile `GOLD_AFFECTING_COMMANDS` members
   (`daily_incremental`, `bootstrap`, `full_reconcile`, `gold_refresh`) now, or just
   `daily_incremental` (the one with confirmed live-incident evidence), deferring the other
   three until/unless they show the same failure? Recommended: apply to all four — they share
   the identical `build_gold()` call site, so the same failure is only a matter of when one of
   them runs at sufficient scale, and ticket 02 will enforce this floor going forward anyway.
3. Once the value is decided, should this ticket also drive the actual `deploy-aws-application.sh`
   edit + prod redeploy + a fresh `daily_incremental` execution to confirm it now succeeds, or
   should that execution be left to a separate follow-up? Recommended: this ticket drives it
   through to a confirmed-successful `daily_incremental` execution, since "decided but not
   applied" leaves the pipeline in the same failed state.

Blocked by: none. Independent of tickets 01/02 — this is the tactical bridge until 01 lands.
