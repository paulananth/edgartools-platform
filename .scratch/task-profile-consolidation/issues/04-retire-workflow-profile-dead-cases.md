# 04 — Retire workflow_profile()'s dead/superseded cases

**What to build:** With tickets 02 and 03 landed, every real caller resolves
task profile through the ticket 01 shared mapping. `workflow_profile()`
(`infra/scripts/deploy-aws-application.sh`, ~lines 1332–1358) is now either
fully dead or entirely redundant with the shared mapping. Delete it, or
reduce it to a thin pass-through over the shared mapping if any caller still
needs the `workflow_profile()` name/signature for now — either way, there
must be exactly one place task-profile resolution logic actually lives, with
no independent case statement able to silently drift from what callers do
(the failure mode that caused the original incidents).

**Blocked by:** 02, 03

**Status:** ready-for-agent

- [ ] `workflow_profile()`'s case statement no longer contains independent
      profile-resolution logic — it's deleted, or it's a direct pass-through
      to the ticket 01 shared mapping
- [ ] No remaining caller resolves a task profile any way other than through
      the ticket 01 shared mapping
- [ ] `grep` confirms no other reference to the old dead `daily_incremental`/
      `bootstrap` cases remains anywhere in the deploy script
