# 2026-07-06 `bootstrap` Step Function Failure — 5-Whys Findings

**Investigated:** 2026-07-08 (Phase 06-02, D-01)
**Execution:** `sweep-bootstrap-1783349590`
**ARN:** `arn:aws:states:us-east-1:690839588395:execution:edgartools-dev-bootstrap:sweep-bootstrap-1783349590`
**State machine:** `arn:aws:states:us-east-1:690839588395:stateMachine:edgartools-dev-bootstrap` (dev, `690839588395`)
**Window:** 2026-07-06 10:53:16 ET (start) — 11:30:16 ET (`ExecutionFailed`), ~37 minutes

This is CLAUDE.md's "Debugging discipline: 5-whys" pass applied to D-01: root-cause this
failure BEFORE running `load_history` in 06-03, per the "Long-load 5-whys (resolved)"
template.

---

## Problem

The single `SeedUniverse` state (ECS task, command `seed-universe --run-id
sweep-bootstrap-1783349590`, task definition `edgartools-dev-medium:35`) failed on **all 4**
Step Functions retry attempts (10:53, 11:02, 11:11, 11:23 ET), each time with `StopCode:
EssentialContainerExited`, container `ExitCode: 1`. After the 4th retry exhausted, the
execution transitioned to `ExecutionFailed` with `error: States.TaskFailed`.

CloudWatch Logs for the last attempt (`log stream
warehouse-medium/edgar-warehouse/beeabce5644f49fa9b94b8d7bd573b7c`, `/aws/ecs/edgartools-dev-warehouse`)
show the process got through SEC bronze pulls (`company_tickers.json`,
`company_tickers_exchange.json` — both 200 OK) and then crashed with an unhandled Python
exception:

```
sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) connection to server at
"2mvgjthkubafxiu7vfyp3jd3di.ixkyqwk-yw12138.ca-central-1.aws.postgres.snowflake.app"
(15.157.80.139), port 5432 failed: Connection timed out
	Is the server running on that host and accepting TCP/IP connections?
```

Traceback: `edgar_warehouse/application/warehouse_orchestrator.py:1299`
(`_capture_bronze_raw`) → `warehouse_orchestrator.py:3101` (`_get_mdm_tracked_ciks`) →
`edgar_warehouse/mdm/universe.py:30` (`get_tracked_ciks`) → `session.execute(...)` → SQLAlchemy
connection pool → psycopg2 `connect()` → TCP connect timeout to the MDM Snowflake Postgres
instance's host. All 4 retries failed identically at this same call site.

## 5 Whys

1. **Why did the ECS task exit 1?** An unhandled `sqlalchemy.exc.OperationalError` propagated
   out of `get_tracked_ciks()` while `seed-universe` was resolving the MDM-tracked CIK universe
   for the bronze pull, and no exception handler caught it — the process crashed instead of
   retrying at the application level (retries happened only at the Step Functions/ECS level).

2. **Why did that query raise `OperationalError`?** The underlying `psycopg2` connection to
   `2mvgjthkubafxiu7vfyp3jd3di.ixkyqwk-yw12138.ca-central-1.aws.postgres.snowflake.app:5432`
   (the MDM Snowflake Postgres instance, resolved from the `MDM_DATABASE_URL` /
   `edgartools-dev/mdm/postgres_dsn` secret injected into the task) **timed out at the TCP
   level** — no SYN-ACK, not an authentication or "connection refused" error.

3. **Why would the TCP connection time out rather than connect or get refused?** A silent
   timeout (vs. an immediate refusal) usually means the destination address was genuinely
   unreachable, not merely access-denied. IP allowlisting was ruled out as the mechanism:
   `infra/snowflake/postgres/mdm_create_network_policy.sql` intentionally uses a permissive
   `0.0.0.0/0` `POSTGRES_INGRESS` network rule (dev/prod ECS tasks have no NAT gateway and get
   ephemeral public IPs — see that file's own posture comment), so the policy was not blocking
   this task's IP.

4. **Why was the destination unreachable specifically during this ~37-minute window and not
   before or after?** AWS Secrets Manager version history for
   `edgartools-dev/mdm/postgres_dsn` shows the version active during the failure
   (`AWSPREVIOUS`, created **2026-07-02T10:52:46-04:00**) resolves to host
   `2mvgjthkubafxiu7vfyp3jd3di.ixkyqwk-yw12138.ca-central-1.aws.postgres.snowflake.app` —
   **exactly** the host in the crash traceback. A **new** secret version (`AWSCURRENT`) was
   created at **2026-07-06T12:30:44-04:00** — one hour after the last failed retry
   (11:30:16 ET) — pointing to a **different** host:
   `lml6ivyssferrau6blcozanmsm.xcpclkf-kb19989.ca-central-1.aws.postgres.snowflake.app`. The
   underlying Snowflake Postgres instance's endpoint hostname changed between the two secret
   versions.

5. **Root cause:** `go-live.sh`'s `"Snowflake Postgres / graph prerequisites"` stage
   (`mdm_create_instance.sql`, `CREATE POSTGRES INSTANCE ...` — no `IF NOT EXISTS` guard) and
   its following `"MDM + graph: secret bootstrap"` stage
   (`bootstrap-aws-mdm-secrets.sh --dsn-stdin`) are two separate, non-atomic steps: the first
   (re-)provisions/points at a Snowflake Postgres instance, the second writes that instance's
   DSN to Secrets Manager. Between 2026-07-02 (when the `AWSPREVIOUS` secret was created) and
   2026-07-06 (when the failure occurred), the MDM Snowflake Postgres instance was
   re-provisioned under a new hostname — most plausibly by a re-run of `go-live.sh`'s Snowflake
   Postgres stage as part of the same day's "dev Step Functions sweep" operator work (commit
   `ba367f7`, landed 2026-07-06T13:05:46-04:00, is independent evidence of active
   dev-environment remediation work that day; it fixes an unrelated orphaned-state-machine
   image issue found during the same sweep) — **before** the corresponding secret bootstrap
   step ran. `bootstrap` executed in that gap window, so `MDM_DATABASE_URL` still pointed at
   the old (by-then-decommissioned-or-unroutable) hostname. The secret was rotated to the
   current instance's DSN at 12:30:44 ET, closing the gap.

**Distinguishing code/config bug vs. transient/external:** This is an **external/operational
timing gap** (a manual multi-stage deploy sequence run out of atomic order), not a bug in
`edgar_warehouse` application code, and not a currently-live misconfiguration — the secret
already points at the correct, currently-live instance and has been exercised successfully
many times since. No code change in this repository would have prevented or would fix this
specific failure; the fix already landed operationally (secret rotation) before this
investigation started.

## Resolution

No code fix required in this repository — root cause is an already-resolved infra-provisioning
timing gap (see Why 5), not an application bug. The corrective action (Secrets Manager DSN
rotated to the current Snowflake Postgres instance endpoint) already happened at
2026-07-06T12:30:44-04:00, roughly 1 hour after the failure, via the standard `go-live.sh`
"MDM + graph: secret bootstrap" stage — no new commit is needed to reproduce that fix.

Evidence the fix is in effect and stable (all using the `AWSCURRENT` DSN, post-rotation):

| Time (ET) | State machine | Execution | Result |
|---|---|---|---|
| 2026-07-06 12:57–12:58 | `mdm-check-connectivity` | `exercise-mdm-check-connectivity-1783357058` | SUCCEEDED |
| 2026-07-06 13:09–13:13 | `mdm-run` | `exercise-mdm-run-1783357752` | SUCCEEDED |
| 2026-07-06 13:14 | `mdm-backfill-relationships` | `exercise-mdm-backfill-relationships-1783358039` | SUCCEEDED |
| 2026-07-06 14:46–14:57 | `mdm-sync-graph` | `exercise-sync-full-1783364261` / `exercise-sync-graph-retry3-...` | SUCCEEDED |
| 2026-07-05 16:15 (before, for contrast) | `mdm-check-connectivity` | `sweep-mdm-check-connectivity-1783282490` | SUCCEEDED (on the *old* DSN, before it went stale) |
| 2026-07-08 (Phase 5, GVER-03) | (ad hoc MDM Postgres queries) | — | "MDM Postgres already holds 15,285 nodes / 1,117 edges, confirmed stable across reruns" (06-CONTEXT.md D-02) |

No `bootstrap`/`load_history`-blocking regression test was added, because there is no code
path to regression-test: the failure was a stale credential value at a point in time, not a
reproducible code defect. The durable mitigation is procedural (documented below under
readiness conditions), not a code change.

## `load_history` Readiness — **GO**

- **Zero prior executions confirmed:** `aws stepfunctions list-executions` for
  `arn:aws:states:us-east-1:690839588395:stateMachine:edgartools-dev-load-history` returns an
  empty list — this will be `load_history`'s first-ever execution in dev, as stated in
  06-CONTEXT.md D-01.
- **Wiring correctness is independently proven**, not just assumed: `Stage1Parallel →
  Stage1BEntityFacts → Stage1BPerFiling → Stage1BThirteenF → MdmRun` sequential ordering is
  asserted by `tests/architecture/test_load_history_state_machine.py::
  test_branch_b_modes_run_sequentially_after_stage1_parallel` (and the per-stage command-shape
  tests around it), generated from the real `deploy-aws-application.sh` function source, not a
  hand-maintained copy. This is a never-run-at-scale gap, not a missing-integration gap,
  confirming 06-CONTEXT.md's framing.
- **Root cause does not recur by construction for this run:** the failure was caused by a
  stale Secrets Manager value from a prior deploy sequencing gap, not by anything
  `load_history` itself does differently. The secret has pointed at the live, correct instance
  continuously since 2026-07-06T12:30:44 ET (2+ days and 5+ independent successful MDM Postgres
  operations as of this writing, 2026-07-08), so `load_history`'s own `SeedUniverse`/
  `ComputeWindows`/`MdmRun` stages will read the same already-verified-working DSN.
  `_get_mdm_tracked_ciks()` (the exact call site that crashed on 07-06) is exercised
  successfully every time `mdm-run`/`bronze_seed_silver_gold` have run since the rotation.
- **Known operational mitigations already in place for the run itself** (per CLAUDE.md):
  `bootstrap-batch` is confirmed NOT in `GOLD_AFFECTING_COMMANDS`; `BOOTSTRAP_BATCH_CONCURRENCY`
  defaults to `3` in `infra/scripts/deploy-aws-application.sh` (within the recommended 2–5
  range); the in-process SEC rate limiter enforces 9 req/sec/task.
- **Conditions on the GO:**
  1. Before starting the 06-03 `load_history` run, re-verify MDM Postgres reachability with a
     fresh `mdm-check-connectivity` execution (cheap, ~1 minute) as a final live check — the
     same secret is still expected to be current, but this is a free, fast confirmation given
     the exact failure mode observed here was credential/endpoint staleness.
     **Already satisfied as of this investigation:** execution
     `preflight-06-02-1783525375` (started 2026-07-08T11:42:57-04:00) SUCCEEDED, confirming
     MDM Postgres is reachable on the current DSN immediately ahead of 06-03.
  2. If any future `go-live.sh` re-run touches the "Snowflake Postgres / graph prerequisites"
     stage before 06-03 runs, the "MDM + graph: secret bootstrap" stage must be re-run
     immediately after it in the same session (not deferred) to avoid reintroducing this exact
     gap.

**Verdict: GO for 06-03's bounded `load_history` run** — condition 1 is already satisfied by a
fresh, successful `mdm-check-connectivity` execution run as part of this investigation;
condition 2 is a standing procedural note for any future re-deploy before 06-03 starts.
