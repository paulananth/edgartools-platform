---
phase: 08-production-mdm-secrets-and-connectivity
plan: 02
type: execute
wave: 2
depends_on: [08-01]
files_modified:
  - .planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/evidence/mdm-prod-secrets-and-connectivity.md
  - .planning/workstreams/go-live/milestones/v1.5-phases/01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md
autonomous: false
requirements: [MDM-02]
user_setup:
  - service: aws
    why: "Read postgres_dsn into the runtime env to run the MDM CLI verification; requires prod admin credentials/profile"
    env_vars: []
    dashboard_config:
      - task: "Operator runs the three CLI commands with prod credentials; MDM_DATABASE_URL is loaded from Secrets Manager and unset after"
        location: "Operator shell with aws-admin-prod profile"

must_haves:
  truths:
    - "MDM_DATABASE_URL is loaded from edgartools-prod/mdm/postgres_dsn into the runtime env without the DSN ever being printed"
    - "edgar-warehouse mdm check-connectivity returns connected:true, dialect:postgresql against prod"
    - "edgar-warehouse mdm migrate runs idempotently against prod (seeded result)"
    - "edgar-warehouse mdm counts returns non-zero table and relationship counts against prod"
    - "MDM_DATABASE_URL is unset after the three commands, and that fact is recorded in evidence"
    - "Launch gate matrix rows for MDM secret/container readiness are updated to PASS"
  artifacts:
    - path: ".planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/evidence/mdm-prod-secrets-and-connectivity.md"
      provides: "Sanitized JSON output of the three CLI commands + unset confirmation"
      contains: "check-connectivity"
  key_links:
    - from: "MDM_DATABASE_URL (env)"
      to: "edgar-warehouse mdm check-connectivity"
      via: "get_engine() reads os.environ[MDM_DATABASE_URL]"
      pattern: "check-connectivity"
    - from: "evidence/mdm-prod-secrets-and-connectivity.md"
      to: "01-LAUNCH-GATE-MATRIX.md (MDM rows)"
      via: "matrix row status flipped to PASS"
      pattern: "PASS"
---

<objective>
Verify the production MDM database path: load the prod DSN from Secrets Manager into the runtime
env (without printing it), run `edgar-warehouse mdm check-connectivity`, `migrate`, and `counts`
against production, unset the DSN, capture sanitized JSON evidence, and flip the relevant launch
gate matrix rows to PASS.

Purpose: MDM-02 requires connectivity/migration/counts to pass against the production MDM database
URL with no secret value printed. This is the functional half of MDM-02 (08-01 was population).

Output: Sanitized CLI JSON output appended to the shared evidence file; documented `unset` of
MDM_DATABASE_URL; updated launch gate matrix rows.

Scope note: This plan functionally verifies postgres_dsn ONLY. The snowflake secret is consumed by
_snowflake_setting() in export.py (Phase 9's sync-graph/export path), NOT by these three CLI
commands — it is presence-verified only (08-01's describe-secret), never claimed as
connectivity-verified here.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/workstreams/go-live/STATE.md
@.planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/08-RESEARCH.md
@.planning/workstreams/go-live/milestones/v1.5-phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/mdm-hosted-graph.md
@.planning/workstreams/go-live/milestones/v1.5-phases/01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md
@CLAUDE.md

<interfaces>
<!-- MDM CLI handlers (edgar_warehouse/mdm/cli.py) — executor uses these directly, no exploration needed. -->
<!-- get_engine() (edgar_warehouse/mdm/database.py) reads url from os.environ["MDM_DATABASE_URL"]. -->

check-connectivity -> prints JSON: {"sql": {"connected": true, "dialect": "postgresql", "missing_tables": []}}
migrate            -> prints JSON: {"dialect": "postgresql", "seeded": true}  (idempotent)
counts             -> prints JSON: table row counts (~19 tables) + "relationships_by_type"
                      with active / pending_graph_sync subtotals (IS_INSIDER, HOLDS, ISSUED_BY, COMPANY_HOLDS)

Invocation: uv run --extra mdm-runtime edgar-warehouse mdm <command>
None of these handlers echo MDM_DATABASE_URL (confirmed in research) — operator must not add debug output that would.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Run prod MDM connectivity, migrate, and counts; unset DSN</name>
  <files>.planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/evidence/mdm-prod-secrets-and-connectivity.md</files>
  <read_first>
    - .planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/08-RESEARCH.md (Pattern 3 load-DSN-without-printing; Pitfall 3 unset; Code Examples expected output shapes)
    - .planning/workstreams/go-live/milestones/v1.5-phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/mdm-hosted-graph.md (D-03 dev precedent: exact command sequence + expected non-secret JSON shapes + the "MDM_DATABASE_URL unset after all three commands" evidence line)
    - .planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/evidence/mdm-prod-secrets-and-connectivity.md (confirm 08-01 populated postgres_dsn — AWSCURRENT present; do not run if 08-01 recorded BLOCKED)
  </read_first>
  <action>
    Only proceed if 08-01 confirmed postgres_dsn is populated (AWSCURRENT present) and the prod
    Postgres instance exists. Ensure the mdm-runtime extra is installed (uv sync --extra mdm-runtime)
    if not already. Load the DSN into the runtime env by exporting MDM_DATABASE_URL from the output of
    aws secretsmanager get-secret-value --profile aws-admin-prod --region us-east-1 --secret-id
    edgartools-prod/mdm/postgres_dsn --query SecretString --output text, in-shell only. NEVER echo,
    print, log, or commit MDM_DATABASE_URL or the get-secret-value output. Then run, in order:
    uv run --extra mdm-runtime edgar-warehouse mdm check-connectivity, then mdm migrate, then mdm
    counts. Capture each command's stdout JSON (these handlers do not echo the DSN). Immediately
    after the third command, run unset MDM_DATABASE_URL to remove the DSN from the environment.
    Append to the shared evidence file: the sanitized JSON output of all three commands (connectivity
    result, migrate seeded result, counts table+relationship counts) and an explicit line recording
    that MDM_DATABASE_URL was unset after all three commands (replicating the D-03 dev precedent's
    evidence line item). Do not paste the export/get-secret-value command line with any real value
    into evidence. If check-connectivity returns a connection error instead of connected:true, STOP,
    run a 5-whys root-cause pass per CLAUDE.md (do not blindly retry), record a BLOCKED item, and
    ensure no raw connector error string (which can leak host/credential fragments) is committed —
    sanitize to a non-secret description of the failure class.
  </action>
  <verify>
    <automated>grep -q "check-connectivity" .planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/evidence/mdm-prod-secrets-and-connectivity.md && grep -qi "unset" .planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/evidence/mdm-prod-secrets-and-connectivity.md && ! grep -qiE "sslmode=require|snowflake\.app|password" .planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/evidence/mdm-prod-secrets-and-connectivity.md</automated>
  </verify>
  <acceptance_criteria>
    - Evidence contains sanitized JSON for check-connectivity (connected:true, dialect:postgresql), migrate (seeded), and counts (non-zero table + relationship counts) — OR a sanitized BLOCKED item with a 5-whys chain if connectivity failed.
    - Evidence contains an explicit line stating MDM_DATABASE_URL was unset after the three commands.
    - No DSN, host string, password, sslmode literal, or raw connector error appears in committed evidence.
    - The snowflake secret is NOT described as connectivity-verified anywhere in this evidence.
  </acceptance_criteria>
  <done>The three MDM CLI commands pass against prod (or a sanitized BLOCKED 5-whys is recorded); DSN unset and that fact recorded; no secret value or raw connector error committed.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 2: Operator confirms evidence is secret-safe, then flip launch gate matrix rows</name>
  <files>.planning/workstreams/go-live/milestones/v1.5-phases/01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md</files>
  <read_first>
    - .planning/workstreams/go-live/milestones/v1.5-phases/01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md (the MDM secret/container readiness rows, ~rows 22-25, and the Secret-Safety Rules section)
    - .planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/evidence/mdm-prod-secrets-and-connectivity.md (the evidence produced by 08-01 and 08-02 Task 1)
  </read_first>
  <what-built>
    08-01 populated postgres_dsn and snowflake (describe-secret metadata evidence) and 08-02 Task 1
    ran check-connectivity/migrate/counts against prod and recorded sanitized JSON + the DSN unset.
    The launch gate matrix MDM secret/container readiness rows now need to be flipped to PASS, but
    only after a human confirms the evidence file contains no secret value, DSN, host string,
    password, or raw connector error.
  </what-built>
  <how-to-verify>
    1. Open .planning/.../08-.../evidence/mdm-prod-secrets-and-connectivity.md and scan for any
       DSN, host ending in .snowflake.app, password, sslmode=require literal, put-secret-value
       ARN/VersionId output, or raw connector error string. There must be none.
    2. Confirm describe-secret metadata (Name/ARN/LastChangedDate/VersionIdsToStages) is present for
       both required secrets and the three CLI commands' sanitized JSON is present (or a legitimate
       BLOCKED 5-whys is recorded).
    3. If clean: instruct the executor to flip the MDM secret/container readiness rows (~22-25) in
       01-LAUNCH-GATE-MATRIX.md to PASS, cross-referencing this evidence file. Do not flip rows whose
       gate (e.g., snowflake functional verification or hosted graph E2E) belongs to Phase 9.
  </how-to-verify>
  <action>
    After operator approval, update the MDM secret/container readiness rows in 01-LAUNCH-GATE-MATRIX.md
    to PASS, referencing evidence/mdm-prod-secrets-and-connectivity.md. Only flip rows whose acceptance
    is satisfied by Phase 8 (secret population + postgres connectivity/migrate/counts). Do NOT flip
    rows whose acceptance requires snowflake functional verification or hosted graph E2E — those are
    Phase 9. If 08-02 Task 1 recorded BLOCKED, do not flip to PASS; record the blocked status instead.
  </action>
  <verify>
    <automated>grep -qi "mdm-prod-secrets-and-connectivity" .planning/workstreams/go-live/milestones/v1.5-phases/01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md</automated>
  </verify>
  <acceptance_criteria>
    - Operator has confirmed the evidence file is secret-safe (no DSN/host/password/connector error).
    - The Phase 8 MDM secret/container readiness rows in the launch gate matrix reference the evidence file and reflect PASS (or BLOCKED if Task 1 blocked).
    - No Phase 9 row (snowflake functional / hosted graph E2E) was prematurely flipped to PASS.
  </acceptance_criteria>
  <resume-signal>Type "approved" after confirming evidence is secret-safe, or describe what to redact.</resume-signal>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Secrets Manager → runtime env | postgres_dsn loaded into MDM_DATABASE_URL; must not be printed, and must be unset after use |
| MDM CLI → evidence Markdown | only sanitized JSON output may cross; raw connector errors (host/credential fragments) must not |
| evidence → launch gate matrix → git | only PASS/BLOCKED status + evidence reference cross; no secret value |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-08-05 | Information Disclosure | MDM_DATABASE_URL printed/echoed during verification | mitigate | load in-shell only, never echo; CLI handlers do not echo it; grep gate blocks DSN fragments in evidence |
| T-08-06 | Information Disclosure | MDM_DATABASE_URL left in env after use | mitigate | unset MDM_DATABASE_URL immediately after the three commands; record the unset in evidence |
| T-08-07 | Information Disclosure | raw connector error (host/credential) committed on connectivity failure | mitigate | on failure, sanitize to a non-secret failure-class description + 5-whys; never paste the raw error |
| T-08-08 | Repudiation | launch gate flipped PASS without proof / on a Phase 9 row | mitigate | human checkpoint confirms secret-safety + scope before any PASS flip; Phase 9 rows excluded |
| T-08-SC | Tampering | npm/pip/cargo installs | accept | only existing extra (uv sync --extra mdm-runtime) installed from the locked uv.lock; no new package surface |
</threat_model>

<verification>
- Evidence shows sanitized JSON for check-connectivity/migrate/counts (or a sanitized BLOCKED 5-whys).
- Evidence records MDM_DATABASE_URL was unset.
- No DSN, host, password, or raw connector error committed.
- Launch gate matrix Phase 8 MDM rows reference the evidence file and reflect PASS/BLOCKED correctly; no Phase 9 row flipped.
</verification>

<success_criteria>
check-connectivity, migrate, and counts pass against the production MDM database URL with no value
printed; the DSN is unset afterward; evidence records only secret names, command status, and
sanitized counts; the launch gate matrix MDM secret/container readiness rows are updated. A
legitimate connectivity BLOCKED outcome (recorded with a 5-whys, sanitized) is a valid result and
must never be resolved by fabricating connectivity success.
</success_criteria>

<output>
Create `.planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/08-02-SUMMARY.md` when done.
</output>
