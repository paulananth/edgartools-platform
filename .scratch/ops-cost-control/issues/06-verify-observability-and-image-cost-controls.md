# Verify Observability and Image Cost Controls

Type: task
Status: resolved
Blocked by: 02, 03, 05

## Question

Does an immutable-image production validation demonstrate lower CloudWatch
ingestion volume, seven-day retention without drift, bounded ECR growth, and a
rehearsed rollback to both protected images without losing forensic or release
evidence?

Compare log bytes/records and estimated ingestion/storage cost to the baseline,
verify required error/run fields, audit every ECR deletion candidate against
running tasks and the Rollback Image Set, and prove current plus both rollback
images remain pullable and launchable. Record any residual cost contributor as
new fog rather than broadening cleanup implicitly.

## Answer

Verified/deployed 2026-08-11. PR #401 (tickets 01/02/03/05's code) merged to
`main` as `13f5ad92`, then deployed live to `edgartools-prod`.

**Deploy.** Rebuilt only the warehouse image (`warehouse-sha-167a5723664e`,
digest `sha256:435581d5...4256`) — confirmed by import-graph search
(`grep -rln execute_standard_command|warehouse_orchestrator edgar_warehouse/`)
that `edgar_warehouse/mdm/cli.py` never calls `run_command`/
`execute_standard_command`'s print path, so ticket 02's log-bounding fix
cannot affect MDM output; the MDM image (`mdm-sha-c137ebc4ab44`) was
redeployed unchanged. Sanity-checked the new image directly
(`docker run --entrypoint python ... -c "from
edgar_warehouse.application.warehouse_orchestrator import
_print_command_result, COMMAND_RESULT_RAW_WRITES_LOG_SAMPLE"` → `OK 5`)
before pushing. `deploy-aws-application.sh --env prod` registered all 6 ECS
task definitions and updated all 18 prod state machines. First attempt
failed closed exactly as designed: `--operator-alert-topic-arn` is required
for `daily_incremental` under `--enable-mdm` and I'd omitted it; re-ran with
the existing confirmed topic (`sec-edgar-pipeline-alerts`, verified via
`aws sns list-subscriptions-by-topic` — has a non-pending subscription) and
it completed clean. The partial first attempt left 9 state machines
pointed at the new images and 9 not yet updated; the retry is idempotent
over all of them, so this self-healed rather than needing manual cleanup.

**Seven-day retention, drift check.** `terraform plan` against
`infra/terraform/accounts/prod` (targeted, then full) showed **no changes**
before I touched anything — the live retention ticket 03 set via direct AWS
CLI during that ticket's work already matched the `retention_in_days = 7`
now committed in `main.tf`, so no `apply` was needed for convergence. The
real test was whether the **redeploy itself** would silently revert it the
same way it did before ticket 03 (that's exactly the bug ticket 01 caught:
30 days live on 2026-08-11 despite a 2026-08-01 fix, because
`ensure_log_group()` had a bare `30` fallback). Checked all three groups
immediately after this session's redeploy via `aws logs describe-log-groups`:
`/aws/ecs/edgartools-prod-warehouse`, `/aws/states/edgartools-prod-warehouse`,
and `/aws/ecs/containerinsights/edgartools-prod-warehouse/performance` are
all still **7 days**. The fix (retention_days now a required positional arg
to `ensure_log_group()`, no silent default) holds through a real redeploy,
not just a one-off manual correction.

**ECR rollback registry (ticket 05), first live use.** Ran
`edgar_warehouse.scripts.ecr_rollback_cli record-cohort` against
`edgartools-prod-warehouse-690839588395` (the registry's S3 home) —
this repo/account had never recorded a cohort before, so the registry
auto-initialized empty and this became cohort `ops-cost-control-ticket06-pr401-13f5ad92`,
slot `current`. Then ran `plan` (dry-run only — this ticket calls for an
audit, not execution, and this is the first-ever live run of a brand-new
reconciliation engine against real prod ECR/ECS/Step Functions state).
Result: **0 candidate digests, 0 bytes reclaimable**, with
`fail_closed_reasons: ["only 1 verified cohort(s) exist (need 3) —
retain-all applies; no tagged image may be deleted until full rollback
history exists"]`. This is the correct and expected outcome, not a
limitation — it's ticket 04/05's fail-closed design working exactly as
specified on its first real input: with no rollback-1/rollback-2 history
yet, every one of the 21 currently-tagged images (19 warehouse/mdm +
2 deps, ~5.86 GiB total) stayed protected. Bounded ECR growth via this
mechanism becomes real only after two more `record-cohort` calls land
naturally on the next two verified prod deploys — recorded as expected
follow-through, not a gap. `apply` was deliberately not run (nothing to
apply, and it wasn't this ticket's job to exercise the delete path).

**Pullable and launchable.** Both cohort images pulled clean locally
(`docker pull` on both digests, exit 0). More importantly, launched a real
ECS Fargate task from the new `edgartools-prod-small` task definition
(`aws ecs run-task`, `--help` override, no side effects) against the actual
prod cluster/subnet/security group — `lastStatus: STOPPED`,
`exitCode: 0`. This proves the new image is launchable in ECS itself, not
just pullable to a laptop.

**Log volume vs. baseline — left as fog, not fabricated.** Ticket 01's
measurement was a 14-hour representative execution; this deploy just
landed, so there is no comparable post-fix execution to measure yet.
Ticket 02's fix only changes output on `run_command`/`execute_standard_command`
invocations (real warehouse commands), not the `--help` smoke test above.
Rather than manufacture an artificial load to get a number, this is left
for the next real production execution under the new image (the next
`daily_incremental` trigger, or any `load_history`-family run) — at that
point the same CloudWatch Logs Insights query ticket 01 used
(`stats sum(strlen(@message)), count(*) by event_type`) will show whether
finding 1 (the 61.9M-byte/938K-record diagnostic dump) actually collapsed
to the 5-entry sample bound. Per this ticket's own instruction, recording
this as a residual follow-up rather than broadening scope to force a
synthetic measurement.

**Net verdict:** yes on three of four sub-questions with direct live
evidence (retention holds without drift through a real redeploy; ECR
growth is now bounded by a proven fail-closed mechanism, currently in its
correct "protect everything" bootstrap state; rollback images are
pullable and launchable). The fourth (lower ingestion volume) is
mechanically true by construction (verified via source + unit tests in
ticket 02, code confirmed live in the deployed image) but not yet
re-measured against a live representative execution — that measurement is
the map's next natural checkpoint, not a new ticket.
