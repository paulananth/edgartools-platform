# 05 — Execute the live cutover in an approved operator window + verify

**What to build:** In a single approved operator window, apply the reviewed
plans from Ticket 04 back-to-back across both Terraform roots, so the ECS
write path and the Snowflake read path never disagree about which bucket is
current. Immediately after apply, write a real test manifest to the
canonical bucket and confirm `SNOWFLAKE_RUN_MANIFEST_TASK` (stream/task
chain) picks it up and `EDGARTOOLS_GOLD` refreshes. This is the actual
bucket-and-database cutover moment — de-risked by Tickets 03 and 04 so this
ticket is just "flip config + confirm," not discovery work.

**Blocked by:** 04 — Prepare and review the coordinated Terraform diff

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

---

**2026-07-19 — DONE.** Both Terraform roots applied back-to-back in the same
operator window (AWS task-def/SM redeploy happened before the Snowflake apply,
and nothing was running, so no cross-bucket disagreement window existed).
Pipe replacement completed; new pipe `RUNNING` with a fresh notification
channel; SNS topic policy re-applied for the new subscriber; S3→SNS bucket
notification verified on the canonical bucket (prefix
`warehouse/artifacts/snowflake_exports/manifests/`, suffix
`run_manifest.json`). GOLD dynamic tables rebuilt via
`dbt run --target prod --full-refresh` — PASS=17. Manifest task resumed
(`started`, warehouse `EDGARTOOLS_PROD_REFRESH_WH`).
**Test-manifest note:** the end-to-end synthetic-manifest check was
deliberately NOT run — `EDGARTOOLS_SOURCE` has never been loaded (verified
identical in the pre-rename clone: GOLD `COMPANY`=0 rows, zero graph tables;
the export bucket has never held a manifest). Injecting a synthetic manifest
would insert fake data into an empty production SOURCE. The first real
`gold-refresh` under Ticket 20 is the genuine end-to-end proof, and every
link it depends on (stage read, pipe, notification, task, DT build) was
verified individually. Rollback path (re-point to prodb buckets) documented
before start; unused.
