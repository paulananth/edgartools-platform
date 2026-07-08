# 06-03 Load Coverage Evidence

**Plan:** 06-03 (Wave 2, fix-pipelines)
**Status:** Task 1 (coordination + readiness gate) complete — operator typed "approved". Task 2
(trigger + monitor the bounded `load_history` run) was **NOT triggered** — a pre-flight
investigation (below) found the ~100-200 company bound (D-02) cannot be achieved through
`load_history`'s exposed interface given current dev MDM state, which is a Rule 4
(architectural) blocker, not a Rule 1-3 auto-fixable issue. Returning to operator for a
decision before any execution starts or any AWS spend is incurred. Task 3 depends on Task 2 and
has also not started.

---

## Task 1: Coordination + readiness gate — findings

### 1. 06-02 readiness verdict

Source: `06-02-BOOTSTRAP-FAILURE-FINDINGS.md`, "`load_history` Readiness — **GO**" section.

- Verdict text confirmed verbatim: **"Verdict: GO for 06-03's bounded `load_history` run"**.
- Root cause of the 2026-07-06 `bootstrap` failure (stale MDM Postgres Secrets Manager DSN from
  a non-atomic `go-live.sh` provisioning/secret-bootstrap sequencing gap) was external/
  operational, already self-resolved by an operator secret rotation on
  2026-07-06T12:30:44 ET — not a code defect requiring a fix in this repo.
- GO condition 1 (fresh `mdm-check-connectivity` re-verification before the 06-03 run) is
  recorded as **already satisfied**: execution `preflight-06-02-1783525375`
  (2026-07-08T11:42:57-04:00) SUCCEEDED.
- GO condition 2 (re-run secret bootstrap immediately after any future
  "Snowflake Postgres / graph prerequisites" `go-live.sh` stage, before 06-03 starts) is a
  standing procedural note only — no evidence of an intervening `go-live.sh` re-run between
  2026-07-08 (06-02 investigation) and now.
- **Automated grep check** (`grep -Eiq "GO" 06-02-BOOTSTRAP-FAILURE-FINDINGS.md`) — PASSES; the
  file contains the literal string "GO" multiple times, including the verdict heading itself.

**Conclusion: readiness verdict is GO, not NO-GO.**

### 2. Codex / `fundamental-factors-v2` overlap check

Source: `.planning/workstreams/fundamental-factors-v2/STATE.md` (last updated
2026-07-01T18:45:00.000Z — 7 days stale relative to today, 2026-07-08).

- Current position: Phase 03 (`cash-conversion-cycle`), status `executing`. `stopped_at`:
  "Phase 3 plans created (03-01 DSO, 03-02 DIO/DPO) and plan-checker verified. Ready for
  `/gsd-execute-phase 3`."
- Pending Todos explicitly record that Phase 3 execution has **not been started**: "Run
  `/gsd-execute-phase 3` — Phase 3 (cash conversion cycle) is planned and plan-checker-verified
  ... expect the execution to pause there [at 03-02's blocking checkpoint]." No session activity
  is recorded past plan-creation/verification.
- Milestone Context constraint (Codex's own stated scope boundary): "Extends the V1
  accounting-only `FINANCIAL_FACTORS` gold model ... under an explicit constraint: **no new
  loader, no new SEC fetch path, only silver/gold changes**." Phase 3 (cash-conversion-cycle)
  needs "one new silver parser field but still no new loader, since it reads from data the
  existing loader already fetches" — confirmed by 06-CONTEXT.md's independent read of the same
  file: Phase 3 does not touch `bootstrap_fundamentals.py`, `accounting_flags.py`,
  `proxy_fundamentals.py`, or `thirteenf.py`.
- No `Blockers` or `Pending Todos` entry indicates an in-progress dev fetch/loader task at the
  time of this check.

**Conclusion: Codex is not mid-flight on a fundamentals loader/fetch task in dev.** STATE.md
shows Phase 3 plans exist but execution has not been triggered, and even when it is, Phase 3 is
gold-dbt-layer-only by explicit workstream constraint — no file overlap with the Stage1B
fundamentals fetch paths (`bootstrap_fundamentals.py`, `accounting_flags.py`,
`proxy_fundamentals.py`, `thirteenf.py`) that 06-03's `load_history` run will exercise.

### 3. In-flight dev `load_history` execution check

Command run (2026-07-08, live):

```
aws stepfunctions list-executions --region us-east-1 \
  --state-machine-arn arn:aws:states:us-east-1:690839588395:stateMachine:edgartools-dev-load-history \
  --status-filter RUNNING
```

Result:

```json
{
    "executions": []
}
```

`aws sts get-caller-identity` confirmed the query ran against the correct dev account
(`690839588395`, `arn:aws:iam::690839588395:user/admin-user`), consistent with `load_history`'s
zero-prior-executions state noted in `06-02-BOOTSTRAP-FAILURE-FINDINGS.md`.

**Conclusion: no RUNNING dev `load_history` execution is in flight.**

---

## Coordination outcome

| Check | Result |
|---|---|
| 06-02 readiness verdict | **GO** |
| Codex (`fundamental-factors-v2`) mid-flight on a dev fundamentals loader/fetch task | **No** — Phase 3 execution not yet triggered per its own STATE.md; even once run, Phase 3 is gold-dbt-layer-only (no loader/fetch file overlap) |
| RUNNING dev `load_history` execution | **None** (`list-executions --status-filter RUNNING` → empty) |

**All three preconditions hold.** No overlap or NO-GO blocker was found.

**This checkpoint does not self-approve.** Per the plan's `gate="blocking"` on Task 1, execution
stops here. Task 2 (triggering a real, cost-bearing `load_history` execution against dev account
`690839588395`) and Task 3 (per-type coverage capture) require explicit operator approval before
proceeding — see the `<resume-signal>` in `06-03-PLAN.md`: type "approved" to proceed with the
bounded load, or describe the overlap/NO-GO blocker.

---

## Task 2 (Trigger + monitor the bounded `load_history` execution) — BLOCKED (Rule 4)

Operator approval received ("approved") for this checkpoint. Before starting a real,
cost-bearing execution, a pre-flight bounding check was run (read-only) to confirm the
~100-200 company bound (D-02) is achievable. It is not, without either mutating a large amount
of pre-existing shared MDM state or a code+redeploy change — both out of Task 2's stated scope
("trigger + monitor"). No `load_history` execution was started. No mutating action was taken.

### 1. Read-only pre-flight checks performed

- `aws stepfunctions list-executions --status-filter RUNNING` for `load_history` — empty (no
  concurrent run before this check, and none after — confirmed again at the end of this
  investigation).
- `aws ecs list-tasks --desired-status RUNNING` on the warehouse cluster — only two pre-existing,
  unrelated `daily-incremental` scheduled tasks were running (`family:edgartools-dev-medium`,
  `startedBy: AWS Step Functions`, created 2026-07-07/08 06:30 ET) — not started by this
  investigation, not touched.
- `mdm counts` (via the `edgartools-dev-mdm-counts` state machine, read-only): current dev MDM
  state already has **`mdm_company: 18034`**, `mdm_entity: 18080`, and
  `relationships_by_type` including `AUDITED_BY: {active: 0}` and
  `INSTITUTIONAL_HOLDS: {active: 0}` (the two EDGE-10/EDGE-11 targets), consistent with 06-02's
  "15,285 nodes / 1,117 edges" figure from GVER-03 (close but not identical — likely counts more
  node types or has grown slightly since).
- Direct read-only SQL query against the dev MDM Postgres instance (DSN pulled from
  `arn:aws:secretsmanager:us-east-1:690839588395:secret:edgartools-dev/mdm/postgres_dsn-AempIg`
  via `aws secretsmanager get-secret-value`; connection is reachable directly — the
  `POSTGRES_INGRESS` network rule is intentionally `0.0.0.0/0`, per
  `infra/snowflake/postgres/mdm_create_network_policy.sql` — using
  `uv run --with psycopg2-binary python -c "..."`, a transient read-only tool install, no
  project dependency change):
  ```sql
  SELECT tracking_status, COUNT(*) FROM mdm_company GROUP BY tracking_status ORDER BY 2 DESC;
  ```
  Result: `active: 11914`, `bootstrap_pending: 6120` — **sum = 18,034 = 100% of `mdm_company`**.

### 2. Why this breaks the D-02 bound

`load_history`'s deployed Step Functions definition (`write_load_history_definition` in
`infra/scripts/deploy-aws-application.sh`) has no CIK-scoping input:

- The state machine's only recognized SM input field is `$.window_size` (optional; a `Choice`
  state injects the default `500` when absent — this is why `--input '{}'` is documented as
  valid in CLAUDE.md). `window_size` controls **CIKs per window**, not **total CIKs processed**.
- `ComputeWindows` runs `compute-windows --window-size <N> --run-id <execution-name>`. The
  `compute-windows` CLI subparser (`edgar_warehouse/cli.py` ~L597-612) accepts only
  `--window-size` and `--run-id` — **no `--tracking-status-filter`, `--cik-list`, or `--limit`
  flag exists on this subcommand.**
- `ComputeWindows` queries MDM for **all** CIKs with `tracking_status IN ('active',
  'bootstrap_pending')` (by design — this is documented in the SM generator's own comment as
  intentional, so a fresh environment's `bootstrap_pending` backlog gets processed) and writes
  every one of them into `cik_windows.jsonl`, chunked into `window_size`-sized windows.
- `WindowedBootstrap` (Branch A) is a `Map` over **all** windows in `cik_windows.jsonl` with
  `MaxConcurrency: 1` — i.e. **sequential**, not the "parallel N×10 ECS batches" pattern CLAUDE.md
  documents for the separate `bootstrap-batch`/`silver_mdm_gold` pipeline. The three Stage1B
  fundamentals `Map`s (`Stage1BEntityFacts`/`Stage1BPerFiling`/`Stage1BThirteenF` — the exact
  artifact classes EDGE-09/10/11 evidence depends on) are also sequential, `MaxConcurrency: 1`,
  over the same full window set.
- **Consequence:** because 100% of the current 18,034 tracked companies already have
  `tracking_status IN ('active', 'bootstrap_pending')`, triggering `load_history` via its
  documented interface (`--input '{}'` or `{"window_size": N}` for any `N`) does not select a
  ~100-200 company subset — it processes the **entire 18,034-company tracked universe**,
  sequentially, one `bootstrap-next` window at a time. There is no supported flag anywhere in
  the deployed pipeline (SM input, `compute-windows` CLI, or `bootstrap-next`'s window-scoped
  invocation inside the SM) that narrows this to an arbitrary N-company subset at trigger time.
- This directly conflicts with the plan's `<threat_model>` entry `T-06-02` (Denial of Service —
  cost / SEC rate-limit ban, **severity: high**, disposition: mitigate, mitigation: "Bound to
  ~100-200 companies (D-02)... gate behind 06-02 GO verdict") and with `<acceptance_criteria>`
  ("The run was bounded to ~100-200 companies... not the full active universe"). CLAUDE.md's
  documented "~15 min for 100 companies via parallel ECS batches" figure describes a different,
  parallel pipeline shape (`bootstrap-batch`) and does not apply to `load_history`'s sequential
  `MaxConcurrency: 1` windows — 06-02 independently flagged `load_history` as "never-run-at-scale"
  for exactly this reason. No reliable time estimate exists for an 18,034-company sequential run
  under this shape; conservatively it is many hours to well over a day, and it would issue SEC
  API calls (subject to the 9 req/sec per-task limiter) for essentially the full company
  universe rather than a scoped 100-200 sample — a materially different cost/risk profile than
  what Task 1's coordination checkpoint and the threat model were gated on.

### 3. Options identified (none are Rule 1-3 auto-fixable)

| Option | Description | Trade-off |
|---|---|---|
| A — Temporarily bound via MDM state mutation | Set `tracking_status='paused'` on all but a deliberately chosen ~100-200 CIKs (broadest DEF 14A / 13F / XBRL coverage), run `load_history`, optionally restore afterward. No existing CLI does a bulk "pause all except N" operation — would need a new one-off script/SQL against the live dev MDM Postgres. | No code/infra redeploy needed, but mutates ~17,800+ rows of shared dev MDM state (used by Phase 5 GVER-03 tests and referenced by other workstreams) — a broad, semi-reversible write outside this plan's declared file scope. |
| B — Add a real CIK-scoping input to `load_history` | Extend `compute-windows` (and the SM's `ComputeWindows` command expression) to accept an optional `--cik-limit`/`--tracking-status-filter` argument sourced from SM input, then redeploy via `infra/scripts/deploy-aws-application.sh`. | Clean, reusable, matches the plan's original intent — but is a genuine code + infra-redeploy change, larger than Task 2's stated scope ("trigger + monitor"), and touches files outside this plan's declared `files_modified`. |
| C — Run unbounded against the full 18,034-company universe | Trigger `load_history` as-is. | Violates D-02 and `T-06-02`'s explicit "high severity, mitigate" disposition; unknown multi-hour-plus runtime; full-universe SEC fetch volume with no scoped-sample checkpoint — not recommended. |

**No option was applied.** This is returned to the operator as a `checkpoint:decision` per the
deviation-rules priority (Rule 4: architectural change — ask), rather than either silently
running the full-universe load or silently mutating thousands of rows of shared dev MDM state.

## Task 3 (Per-type artifact-coverage evidence for EDGE-09/10/11) — NOT STARTED

Depends on Task 2's completed run. Not started.
