# Run `mdm.residual_security` Medium Canaries and the Unbounded `sync-graph` Canary

Type: task
Status: open
Blocked by: none

## Question

Run and record the outcome of two related, currently-unscheduled MDM canary
cohorts, both raised by [Decide the Machine Profile for Every Workflow Stage](16-decide-machine-profile-per-workflow-stage.md):

1. **`mdm.residual_security`→`mdm-medium` downgrade canaries.** Per Ticket
   09's standing policy, `mdm-large` stays the operational profile for
   residual-holds/security work until three current-image, representative
   `mdm-medium` canaries process non-zero 13F/residual-security data and
   pass the full correctness/parity/completeness/recovery/idempotency/
   zero-failure gate set. Zero of the three have run as of this ticket.
2. **The first unbounded `mdm sync-graph` run** (`--mdm-graph-limit 0`),
   per [Decide the Loop, Batch, and Concurrency Policy](15-decide-loop-batch-and-concurrency-policy.md)'s
   decision to raise the default from 200 for production runs. No execution
   at real (~193K-node) scale exists yet. Ticket 16 decided this first
   canary should run on `mdm-large`, not `mdm-medium`, given the complete
   absence of duration/memory evidence at this scale.

Both are MDM-runtime canaries blocked on the same kind of missing evidence
(a representative, non-zero-data, current-image execution) — grouped here
rather than split, since resolving one is likely to inform scheduling the
other. Record execution ARNs, task-bound CPU/memory peaks, duration, and
pass/fail against each cohort's own gate criteria (Ticket 03/09 for #1,
Ticket 15 for #2) on resolution.

## In progress (2026-08-13) — execution identities, recorded live

Neither existing generic single-command state machine
(`edgartools-prod-mdm-run`, `edgartools-prod-mdm-sync-graph`) could be
used directly: both pinned to stale task-def revision `mdm-medium:149`
(not current `158`), `mdm-run` hardcodes `--entity-type all` with no
override for `security`, and neither references `mdm-large` at all. Per
Ticket 04's own canary policy ("a canary must exercise the same
orchestration... as the covered production stage"), registered two
temporary, unscheduled Standard state machines instead — exact copies of
the real production definitions with only the candidate task-profile ARNs
swapped, nothing else:

- `canary-mdm-sync-graph-large-t25` — copy of `edgartools-prod-mdm-sync-graph`,
  all `mdm-medium:149` → `mdm-large:92`.
- `canary-residual-holds-medium-t25` — copy of `edgartools-prod-residual-holds-graph`,
  all 8 `mdm-large:92` references → `mdm-medium:158` (the 1 `mdm-small:158`
  verify-graph reference left untouched — not part of the candidate).

**Executions launched:**
- Sync-graph canary (`{"limit": 0}`, unbounded): `canary-sync-graph-unbounded-1`,
  started 2026-08-13T06:57:27-04:00.
- Residual-security canary attempt 1/3: `canary-residual-security-medium-1`,
  started 2026-08-13T06:57:42-04:00.

Both monitored to completion; results and pass/fail against each cohort's
gate criteria recorded below once terminal. Attempts 2/3 of the
residual-security cohort launch after attempt 1 completes.

## Current-image rerun (2026-08-29)

The 2026-08-13 executions above are historical attempts, not qualifying
Ticket 28 evidence. Both used image digest `sha256:ac245d...` and stale task
definitions; the sync execution failed, and the residual execution failed in
`MdmVerify` after the medium workload stages succeeded. Current-image evidence
was restarted from today's production definitions.

The dry-run-first canary builder in `scripts/ops/ecs_sizing_canary.py` pinned:

- image digest
  `sha256:5603ac3d1e787d77bc82b53517bf9213a1b2603aa25347eb176b94577b13bd6d`;
- residual workload states: `mdm-large:137` -> `mdm-medium:203` for exactly
  eight states, preserving `MdmVerify` on `mdm-small:203`;
- unbounded sync route: current MDM Utility Machine definition with exactly
  its five sync task references moved from `mdm-medium:203` to
  `mdm-large:137`; and
- no schedules, aliases, or production state-machine reference changes.

The live utility definition exposed a deterministic pre-launch gap: execution
input `{"limit":0}` routed to the Python CLI as `--limit 0`, but the current
CLI accepts only positive explicit limits. Ticket 28 now adds the canonical
state-machine translation from the zero sentinel to `mdm sync-graph` with no
limit flag. The temporary canary has the same explicit compatibility route so
the current-image run can proceed before the application branch is deployed.

### Unbounded sync canary -- passed execution-local gates

- Execution:
  `arn:aws:states:us-east-1:690839588395:execution:canary-ticket28-mdm-sync-graph-large:ticket28-sync-1-20260829T132646Z`
- ECS task: `61a940bb71bb4072a38c3f932791f207`, `mdm-large:137`, exit 0,
  no retry.
- Output: 226,197 nodes and 621,201 edges; both `limit` and
  `limit_per_type` were null, and `capped_below_available=false`.
- Duration: 32.190 seconds command time, 87.209 seconds image-pull-to-stop
  billable time, 128.626 seconds Step Functions end to end.
- On-demand Linux/x86 compute estimate: $0.002848384 using 88 rounded billed
  seconds and the 2026-08-29 us-east-1 AWS Fargate rates captured in the
  evidence file.
- Task-bound Container Insights (two one-minute samples): CPU max/p95
  19.38%/18.41%; memory max/p95 1.50%/1.43%; zero time in the 70/80/90%
  bands.
- Context: the task overlapped an unrelated `daily-incremental` warehouse
  task that was still in SEC bronze capture. The two exact task identities
  keep utilization task-bound, but the overlap remains recorded rather than
  silently treated as an idle-cluster duration sample.

Evidence: `.scratch/ecs-cost-sizing/evidence/ticket28/`.

### Residual-security cohort -- invalid preflight preserved; corrected series running

The first current-image execution is retained as a **non-counting preflight**:

`arn:aws:states:us-east-1:690839588395:execution:canary-ticket28-residual-holds-medium:ticket28-residual-1-20260829T133301Z`

All eight candidate workload stages ran once on exact `mdm-medium:203` and
exited 0. The worst medium memory peak was 10.13% (`MdmCompanyHolds`); the
worst medium CPU peak was 70.26% (`MdmInstitutionalHolds`). The execution then
failed after all three `MdmVerify` attempts returned the same correctness
result: the unchanged production `MdmSync` command capped each relationship
type at 200,000, while active `MANAGES_FUND` contained 563,638 rows. The
candidate generation was therefore short by exactly 363,638 edges and
`capped_below_available=true`. Its failed/retried compute estimate was
$0.148992521; it is not a successful-output cost sample.

This preflight does not prove or reject the medium profile: the completeness
failure is deterministic in the source orchestration and would be identical
on the large-profile control. It does prove that the old residual definition
cannot produce qualifying Ticket 28 evidence. Ticket 15 already decided that
production-scale graph sync is unbounded, so the deploy generator now keeps
the execution-scoped generation ID while omitting the legacy
`--limit-per-type 200000` cap. The canary builder applies that exact,
fail-closed compatibility overlay to today's live source.

The corrected definition is immutable and hash-qualified:

`canary-ticket28-residual-holds-medium-14dc90b8d0de`

Qualifying run 1/3 (execution attempt 2) launched at 2026-08-29 14:08 EDT:

`arn:aws:states:us-east-1:690839588395:execution:canary-ticket28-residual-holds-medium-14dc90b8d0de:ticket28-residual-2-20260829T180850Z`

It succeeded at 16:52 EDT with no retries or non-zero exits. The unbounded
candidate contained 226,197 nodes and 654,286 edges,
`capped_below_available=false`, and exact node/relationship identity parity.
Worst medium memory peak/p95 was 9.86%/9.82%; worst CPU peak/p95 was
57.68%/50.36%. End-to-end duration was 9,789.448 seconds and estimated
on-demand compute cost was $0.155314788.

Qualifying run 2/3 (execution attempt 3) launched at 2026-08-29 18:05 EDT:

`arn:aws:states:us-east-1:690839588395:execution:canary-ticket28-residual-holds-medium-14dc90b8d0de:ticket28-residual-3-20260829T220530Z`

Each corrected execution launches only after its predecessor is terminal and
its evidence is collected.
No existing production execution is a matched current-image control: the two
source-machine runs are failed July executions on older definitions. A
separate immutable corrected control therefore preserves all eight workload
states on `mdm-large:137` (zero task-reference changes) and applies the same
unbounded graph-completeness prerequisite:

`canary-ticket28-residual-holds-large-control-29134f504bbe`

The control launches only when no candidate execution is active so its
duration is not confounded by same-cluster canary contention. Ticket 28
remains open until three corrected current-image candidate executions, the
matched control, and the full correctness, parity, completeness, recovery,
idempotency, retry, duration, baseline, and cost gates are recorded.
