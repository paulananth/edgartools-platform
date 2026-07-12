# 06-03 Load Coverage Evidence

**Plan:** 06-03 (Wave 2, fix-pipelines)
**Status:** Task 1 complete (operator approved). Task 2's original Rule-4 blocker (no
CIK-scoping bound) was resolved via operator-selected Option B (`--total-cik-limit`, commits
`603fae3`/`e3c5fcb`). Two subsequent bounded executions ran: #1 failed fast on an
INLINE-vs-DISTRIBUTED Map bug (fixed, `e3c5fcb`); #2 ran Stage 1/1B + MdmRun/MdmBackfill to
success (~10.6h) but failed at `MdmExport` on a missing-target-table provisioning gap (fixed via
DDL, commit `caa9964`). Execution #3 (`load-history-06-1783726338`) is in flight after the fix —
see "Execution #3" below for status. Task 3 depends on Task 2's completed run.

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

## Task 2 (continued) — Option B resolution, executions #1 and #2, and the MdmExport provisioning fix

Operator selected **Option B** (add a real CIK-scoping input to `load_history`) from the
Rule-4 options table above, rather than Option A (mutate ~17,800+ rows of shared dev MDM
state) or Option C (run unbounded against the full 18,034-company universe).

### Option B implementation

- Commit `d0f20c0` — documents the Rule-4 blocker (this doc's prior section) and the operator's
  Option B decision.
- Commit `603fae3` — `feat(06-03): add --total-cik-limit CIK-scoping bound to load_history`.
  Adds `--total-cik-limit` to the `compute-windows` CLI subcommand (`edgar_warehouse/cli.py`) and
  `warehouse_orchestrator.py`, plus a new `$.total_cik_limit` Step Functions input field wired
  through `write_load_history_definition` in `infra/scripts/deploy-aws-application.sh`. Covered
  by `tests/unit/test_windowing.py`. Redeployed to dev (task-def revision bump reflected in
  `infra/aws-dev-application.json`).

### Execution #1 — `load-history-06-1783542242` — FAILED (~10 min)

Input: `{"total_cik_limit": 150}`. Failed fast (~10 min) with an INLINE-Map-cannot-use-ItemReader
error: the `WindowedBootstrap`/Stage1B `Map` states were declared `Mode: INLINE`, but
`ItemReader` (used to stream `cik_windows.jsonl` from S3) is only valid on `Mode: DISTRIBUTED`
Maps.

- **5-whys and fix:** commit `e3c5fcb` — `fix(06-03): load_history WindowedBootstrap/Stage1B
  Maps must use DISTRIBUTED mode`. All 4 affected `Map` states (`WindowedBootstrap`,
  `Stage1BEntityFacts`, `Stage1BPerFiling`, `Stage1BThirteenF`) switched from `INLINE` to
  `DISTRIBUTED`/`STANDARD` execution type in `write_load_history_definition`. Covered by
  `tests/architecture/test_load_history_state_machine.py`. Redeployed to dev (second task-def
  revision bump, also reflected in the committed `infra/aws-dev-application.json`).

### Execution #2 — `load-history-06-1783560365` — FAILED at MdmExport (after ~10.6h)

Input: `{"total_cik_limit": 150}`. **The `--total-cik-limit` bound worked as designed** — Stage 1
(bronze/silver bootstrap) and Stage 1B (fundamentals) ran to completion against the scoped
150-company subset, taking ~10.6 hours wall-clock (DISTRIBUTED Map concurrency, not the
sequential MaxConcurrency:1 shape flagged in the original Rule-4 blocker). `MdmRun` and
`MdmBackfill` both SUCCEEDED. The state machine then FAILED at `MdmExport`.

**Failure details** (CloudWatch, log group `/aws/ecs/edgartools-dev-warehouse`, stream
`mdm-mdm-medium/edgar-warehouse/54f1e894495542bc831f3037598b376d`):

```
snowflake.connector.errors.ProgrammingError: 002003 (42S02): Object
'EDGARTOOLS_DEV.EDGARTOOLS_GOLD.MDM_COMPANY' does not exist or not authorized.
```
Raised in `edgar_warehouse/mdm/export.py:252` (`cursor.execute(merge_sql)`, inside
`export_pending`). ECS task `edgartools-dev-mdm-medium:19` — `mdm export` — exit 1, 3 attempts,
all failed identically.

**5-whys:**
1. `MdmExport`'s ECS task exits 1 running `mdm export`.
2. The Snowflake `MERGE INTO MDM_COMPANY ...` statement fails because the target table doesn't
   exist in `EDGARTOOLS_DEV.EDGARTOOLS_GOLD`.
3. `edgar_warehouse/mdm/export.py`'s `DOMAIN_TO_TABLE` maps 5 domains (company/adviser/person/
   security/fund) to 5 Snowflake tables (`MDM_COMPANY`/`MDM_ADVISER`/`MDM_PERSON`/
   `MDM_SECURITY`/`MDM_FUND`) and `SnowflakeConnectorWriter.upsert()` assumes all 5 pre-exist —
   the only `CREATE` it issues is for a per-batch `TEMPORARY` staging table.
4. No DDL anywhere in `infra/snowflake/sql/` (grep-confirmed against all of
   `infra/snowflake/sql/bootstrap/`) ever created these 5 tables.
5. `MdmExport` was added to `load_history` to resolve a data-architecture ordering issue
   (export must precede `mdm-sync-graph`; see `deploy-aws-application.sh` comments ~L1772,
   ~L1915) but had **zero prior dev executions** before this plan — the missing-target gap was
   never exercised until this run reached it, ~10.6h in.

**Root cause:** a provisioning gap — target-table DDL was never written for the MDM Snowflake
export path, distinct from (and downstream of) the earlier INLINE/DISTRIBUTED Map bug.

### Fix — idempotent DDL for the 5 MDM_* export targets

Commit `caa9964` — `fix(06-03): provision missing MDM_* Snowflake export targets`.

- New file `infra/snowflake/sql/bootstrap/07_mdm_export_targets.sql`: `CREATE TABLE IF NOT
  EXISTS` for `MDM_COMPANY`, `MDM_ADVISER`, `MDM_PERSON`, `MDM_SECURITY`, `MDM_FUND`. Column
  shapes derived from the SQLAlchemy models in `edgar_warehouse/mdm/database.py` (`MdmCompany`,
  `MdmAdviser`, `MdmPerson`, `MdmSecurity`, `MdmFund`) — the same models `export.py`'s
  `MDMExporter._serialize()` reads rows from.
- **Type choices validated live** against dev Snowflake before finalizing the DDL (not assumed
  from memory): built a smoke-test MERGE reproducing `SnowflakeConnectorWriter.upsert()`'s exact
  shape — a temp table with all columns `VARIANT`, populated via `SELECT PARSE_JSON(column1),
  ... FROM VALUES (%s, ...)`, then `MERGE ... WHEN MATCHED / WHEN NOT MATCHED` referencing bare
  `source.<col>`. Confirmed Snowflake implicitly coerces `VARIANT` source values into `VARCHAR`,
  `NUMBER`, `BOOLEAN`, and `TIMESTAMP_TZ` target columns with no explicit cast required, and that
  `PARSE_JSON('null')` (export.py's JSON encoding of a Python `None`) coerces to a real SQL
  `NULL` on the target column rather than a JSON-null literal. JSON-typed SQLAlchemy columns
  (`MdmPerson.name_variants`/`role_titles`) are kept as Snowflake `VARIANT`. This means **no
  export.py changes or Docker image rebuild were needed** — this is a pure Rule 1-3
  provisioning fix, not a Rule 4 architectural change.
- Applied directly to `EDGARTOOLS_DEV.EDGARTOOLS_GOLD` via `snow sql --connection snowconn`.
  Verified: `SHOW TABLES LIKE 'MDM_%' IN SCHEMA EDGARTOOLS_DEV.EDGARTOOLS_GOLD` → `MDM_ADVISER`,
  `MDM_COMPANY`, `MDM_FUND`, `MDM_PERSON`, `MDM_SECURITY` (all 5 present).
- Sanity-checked the exporter's actual dev identity against the connection used to apply the
  DDL: `aws secretsmanager get-secret-value --secret-id edgartools-dev/mdm/snowflake` →
  `MDM_SNOWFLAKE_ACCOUNT=xcpclkf-kb19989`, `MDM_SNOWFLAKE_USER=ANANP11`,
  `MDM_SNOWFLAKE_ROLE=ACCOUNTADMIN`, `MDM_SNOWFLAKE_DATABASE=EDGARTOOLS_DEV`,
  `MDM_SNOWFLAKE_SCHEMA=EDGARTOOLS_GOLD` — identical to the `snowconn` SnowCLI connection used
  to apply the DDL (same account/user/role). No role/ownership mismatch risk for this run.
- **Follow-up (not built now, out of this plan's Rule 1-3 scope):** an exporter-side
  auto-ensure (`CREATE TABLE IF NOT EXISTS` issued by `export.py` itself before the first
  `MERGE`) would make this self-healing for future environments/schemas instead of relying on
  bootstrap DDL being applied out-of-band. Recorded here for a future phase, not implemented in
  06-03.

### Execution #3 — re-trigger after the fix

Command:
```
aws stepfunctions start-execution --region us-east-1 \
  --state-machine-arn arn:aws:states:us-east-1:690839588395:stateMachine:edgartools-dev-load-history \
  --name load-history-06-1783726338 \
  --input '{"total_cik_limit": 150}'
```
- **Execution ARN:** `arn:aws:states:us-east-1:690839588395:execution:edgartools-dev-load-history:load-history-06-1783726338`
- **Start:** 2026-07-10T19:32:19.894000-04:00
- **Input:** `{"total_cik_limit": 150}` — same bound as executions #1/#2 (D-02, ~100-200
  companies). No `--force` anywhere (DEC-009).
- Stage 1/1B bronze/silver artifacts from execution #2 were already captured for this 150-CIK
  scope before that run failed downstream at MdmExport; SEC idempotency (DEC-009: loaders skip
  already-captured files by default) means this re-run is expected to skip re-fetching those
  artifacts and move materially faster through Stage 1/1B than the ~10.6h observed in execution
  #2. Observed behavior recorded in the monitoring section below.

## Execution #3 outcome — FAILED (OOM in gold build), 2026-07-12

Execution #3 ran ~29h then FAILED at **2026-07-12T05:10:09Z** with
`States.ExceedToleratedFailureThreshold`. Root cause (5-whys):

1. Execution FAILED → `States.ExceedToleratedFailureThreshold`.
2. Its single WindowedBootstrap map child (`a497f830…`, cmd `bootstrap-next --cik-limit 150
   --cik-offset 0 --tracking-status-filter active,bootstrap_pending`) FAILED → `States.TaskFailed`.
3. The ECS container (task `a82ced…`, `edgartools-dev-medium:39`) exited **137**, reason
   **`OutOfMemoryError: container killed due to memory usage`**.
4. It OOM'd while building the **`sec_financial_fact`** gold table (`gold_table_started`
   05:09:37Z, killed ~3s later; many prior gold tables completed OK — e.g.
   `fact_ownership_transaction` 32,317 rows).
5. **Root cause:** the `edgartools-dev-medium` task def is **2 GB** and the in-memory gold build
   of `sec_financial_fact` at 150-CIK scale exceeds it. This gold stage had never executed
   before exec #3 — first run, first OOM (the exact "never-run stage harbors latent bugs"
   prediction from `.continue-here.md`).

No orphaned tasks/cost remained (task reaped). **The load did not complete green**, but Stage-1
silver was fully captured before the gold OOM — sufficient for Task 3 evidence per the plan's own
"load run is instrumental, not the deliverable" note. The OOM is tracked as a separate hardening
fix (bump gold-stage task memory).

## Task 3 (Per-type artifact-coverage evidence for EDGE-09/10/11) — COMPLETE 2026-07-12

**Method (READ-ONLY, no silver publish):** pulled the canonical dev silver
`s3://edgartools-dev-warehouse/warehouse/silver/sec/silver.duckdb` (635 MiB, last modified
2026-07-10T23:39Z) to a scratch copy and queried it read-only (`duckdb 1.5.2`,
`read_only=True`). Bronze-artifact presence read from the silver filing feed / attachment tables
(captured-filing form-type counts), not an S3 bronze crawl. No `edgartools-dev-mdm-counts` run
needed. No write/publish command executed.

**Per-type coverage:**

| EDGE type | Relationship | Silver table | Bronze artifact present? | Silver rows | Classification |
|-----------|-------------|--------------|--------------------------|-------------|----------------|
| EDGE-09 | EMPLOYED_BY | `sec_executive_record` (from DEF 14A) | **YES** — 11 `DEF 14A` + 12 `DEFA14A` in `sec_filing_attachment` | **0** | **ARTIFACT PRESENT, SILVER EMPTY** (parser gap) |
| EDGE-10 | AUDITED_BY | `sec_accounting_flag.auditor_pcaob_id` (from companyfacts entity-facts) | **YES** — companyfacts loaded (`sec_financial_fact` = 2,729,147 rows from the same source) | **0** | **ARTIFACT PRESENT, SILVER EMPTY** (parser gap) |
| EDGE-11 | INSTITUTIONAL_HOLDS | `sec_thirteenf_holding` (from 13F-HR) | **YES** — 61 `13F-HR` in the captured filing feed | **0** | **ARTIFACT PRESENT, SILVER EMPTY** (parser gap) |

**Headline for Wave 3:** all three are the *same* class — the bronze artifact class is present
for the loaded universe, but the fundamentals silver parser did not populate the target table.
None is "ARTIFACT MISSING" (no fetchability triage needed); none is "ARTIFACT+SILVER PRESENT"
(none ready to populate as-is). Wave 3 (06-04/05/06) is therefore a **parser/pipeline
root-cause** effort for each, not an exclusion or a fetch problem. Corroborating signal: the
companyfacts source parses successfully into `sec_financial_fact` (2.7M) and
`sec_financial_derived` (28,552) but not into `sec_accounting_flag` — so the gap is per-parser,
not a wholesale source-ingestion failure.

**EDGE-10 Codex / `fundamental-factors-v2` coordination note (carried from 06-CONTEXT.md):**
`sec_accounting_flag`/`auditor_pcaob_id` derives from the same companyfacts entity-facts fetch
that the fundamentals workstream owns. As of the 2026-07-11 consolidation, `fundamental-factors-v2`
was merged into this workstream (unified Phase 10; Codex→Claude hand-off), so the earlier
"coordinate to avoid overlap" constraint is now an intra-workstream sequencing concern rather
than a cross-runtime one — but the accounting-flag parser still shares
`bootstrap_fundamentals.py`/`accounting_flags.py` surface and should be touched with that in mind.

**Provenance caveat:** counts are from the current canonical dev silver (accumulated across prior
loads incl. exec #2/#3 Stage-1), not a single isolated 150-CIK run. That does not change the
classifications — a present artifact with a zero silver table is a parser gap regardless of which
run captured the artifact.
