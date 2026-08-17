# 02 — Route write_warehouse_mdm_gold_definition through the shared profile

**What to build:** `daily_incremental` and `bootstrap`'s `RunWarehouseTask`
ARN currently comes from hardcoded parameters inside
`write_warehouse_mdm_gold_definition` (`infra/scripts/deploy-aws-application.sh`,
~lines 3053–3850) — the exact gap that caused two real production OOM
incidents (`gold_refresh` in May 2026, `daily_incremental` in July 2026,
same root cause, missed twice because this function never consulted
`workflow_profile()`). Switch `write_warehouse_mdm_gold_definition` to
resolve every command's task profile from ticket 01's shared mapping instead
of its own hardcoded params.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] `write_warehouse_mdm_gold_definition` resolves task profile via the
      shared mapping from ticket 01 for every command it handles, not
      hardcoded `wh_task_large_arn`/`wh_task_medium_arn` parameters
- [ ] Generated ASL for `daily_incremental` and `bootstrap` references the
      task-definition ARN the shared mapping specifies
- [ ] Deploying (or a dry-run generation of) the state machine definitions
      produces byte-identical ASL to before this change for every other
      command already handled correctly today (no regression for commands
      that weren't part of the original bug)
