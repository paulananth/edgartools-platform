# 01 — Define the single command→task-profile source of truth

**What to build:** Today, an ECS command's task memory/CPU profile is resolved
through three independent mechanisms that can silently disagree:
`infra/scripts/deploy-aws-application.sh`'s `workflow_profile()` case
statement (lines ~1332–1358, with dead cases for `daily_incremental` and
`bootstrap` that nothing ever calls), `write_warehouse_mdm_gold_definition`'s
hardcoded `wh_task_large_arn`/`wh_task_medium_arn` parameters (lines
~3053–3850), and `bootstrap-next`'s own special-cased hardcoded `"medium"`.
Build one mapping from command name → task profile that is the single source
of truth going forward, added *alongside* the existing three mechanisms
without switching any caller over yet (expand step — nothing behavioral
changes in this ticket). This is the prefactor that makes tickets 02–04 safe,
mechanical migrations instead of judgment calls.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] A single mapping (command name → task profile) exists and covers every
      command currently resolved by any of the three existing mechanisms
- [ ] A test asserts the new mapping matches each command's *current real*
      resolved profile today (i.e., it encodes today's live behavior,
      including the two dead `workflow_profile()` cases resolving to
      whatever `write_warehouse_mdm_gold_definition` actually hardcodes for
      them) — this is what makes tickets 02–04 provably behavior-preserving
- [ ] Nothing that currently calls `workflow_profile()`,
      `write_warehouse_mdm_gold_definition`'s hardcoded params, or
      `bootstrap-next`'s special case is changed to use the new mapping yet
