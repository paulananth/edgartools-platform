# 04 — Execute the live cutover in an approved operator window + verify

**What to build:** In a single approved operator window, apply the reviewed
plans from Ticket 03 back-to-back across both Terraform roots, so the ECS
write path and the Snowflake read path never disagree about which bucket is
current. Immediately after apply, write a real test manifest to the
canonical bucket and confirm `SNOWFLAKE_RUN_MANIFEST_TASK` (stream/task
chain) picks it up and `EDGARTOOLS_GOLD` refreshes. This is the actual
bucket-and-database cutover moment — de-risked by Tickets 02 and 03 so this
ticket is just "flip config + confirm," not discovery work.

**Blocked by:** 03 — Prepare and review the coordinated Terraform diff

**Status:** ready-for-agent

- [ ] Both Terraform roots are applied in the same operator window with no
      gap where AWS writes to one bucket and Snowflake reads from another
- [ ] Snowflake pipe replacement completes and the new stage/storage
      integration point at the canonical bucket
- [ ] A test manifest written to the canonical bucket post-apply is
      processed end-to-end (stream → task → stored procedure) with no
      manual intervention
- [ ] `EDGARTOOLS_GOLD` dynamic tables refresh successfully following the
      test manifest
- [ ] Rollback path (re-pointing back to the old `prodb` bucket) is known
      and documented before starting, in case verification fails mid-window
