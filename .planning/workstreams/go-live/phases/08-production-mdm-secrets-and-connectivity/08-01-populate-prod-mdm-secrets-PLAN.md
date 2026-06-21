---
phase: 08-production-mdm-secrets-and-connectivity
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - .planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/evidence/mdm-prod-secrets-and-connectivity.md
  - .planning/HANDOFF.json
autonomous: false
requirements: [MDM-02]
user_setup:
  - service: snowflake
    why: "Confirm the production Snowflake-hosted Postgres MDM instance exists and is ready before populating postgres_dsn"
    env_vars: []
    dashboard_config:
      - task: "Confirm prod Snowflake Postgres MDM instance exists (Snowsight or `snow sql DESCRIBE POSTGRES INSTANCE`)"
        location: "Snowsight (Snowflake console) or `snow` CLI with the prod connection"
  - service: aws
    why: "Populate the two prod MDM Secrets Manager values; requires prod admin credentials/profile (aws-admin-prod)"
    env_vars: []
    dashboard_config:
      - task: "Operator supplies real prod DSN and Snowflake credential values at execution time"
        location: "Operator shell with aws-admin-prod profile; values never committed/printed"

must_haves:
  truths:
    - "Operator has confirmed the production Snowflake Postgres MDM instance exists and is ready before any postgres_dsn write"
    - "edgartools-prod/mdm/postgres_dsn has an AWSCURRENT version (populated) without the DSN value ever being printed or committed"
    - "edgartools-prod/mdm/snowflake has an AWSCURRENT version (populated) without any credential value being printed or committed"
    - "Evidence records describe-secret metadata only (Name, ARN, LastChangedDate, VersionIdsToStages) for both secrets"
    - "HANDOFF.json blocker text clarifies neo4j and api_keys are NOT Phase 8 blockers (out of scope)"
  artifacts:
    - path: ".planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/evidence/mdm-prod-secrets-and-connectivity.md"
      provides: "Secret-safe presence evidence (describe-secret metadata) for both required secrets + instance-existence outcome"
      contains: "VersionIdsToStages"
  key_links:
    - from: "bootstrap-aws-mdm-secrets.sh --dsn-stdin"
      to: "edgartools-prod/mdm/postgres_dsn"
      via: "aws secretsmanager put-secret-value (region us-east-1)"
      pattern: "edgartools-prod/mdm/postgres_dsn"
    - from: "aws secretsmanager put-secret-value"
      to: "edgartools-prod/mdm/snowflake"
      via: "JSON --secret-string with 7 MDM_SNOWFLAKE_* keys (region us-east-1)"
      pattern: "edgartools-prod/mdm/snowflake"
---

<objective>
Populate the two required production MDM Secrets Manager containers
(`edgartools-prod/mdm/postgres_dsn`, `edgartools-prod/mdm/snowflake`) following the
already-authored v1.5 runbook, after first confirming the production Snowflake-hosted
Postgres MDM instance exists. Capture secret-safe presence evidence and clarify in
HANDOFF.json that `neo4j` and `api_keys` are out of scope for this phase.

Purpose: MDM-02 requires the operator to populate these two prod secrets without printing
any value. The downstream plan (08-02) cannot verify connectivity until these secrets exist.

Output: Populated `postgres_dsn` and `snowflake` secrets (AWSCURRENT versions); a new
evidence file with `describe-secret` metadata only; an updated HANDOFF.json blocker
description scoping out neo4j/api_keys.

Scope guardrail: This plan populates EXACTLY two secrets. It MUST NOT populate, create, or
reference any write to `edgartools-prod/mdm/neo4j` or `edgartools-prod/mdm/api_keys` — those
are legacy/deferred and explicitly out of scope.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/workstreams/go-live/STATE.md
@.planning/workstreams/go-live/ROADMAP.md
@.planning/workstreams/go-live/REQUIREMENTS.md
@.planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/08-RESEARCH.md
@.planning/workstreams/go-live/milestones/v1.5-phases/03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md
@.planning/workstreams/go-live/milestones/v1.5-phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/mdm-hosted-graph.md
@CLAUDE.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Precondition — confirm prod Snowflake Postgres MDM instance exists</name>
  <files>.planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/evidence/mdm-prod-secrets-and-connectivity.md</files>
  <read_first>
    - .planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/08-RESEARCH.md (Open Question 1, Pitfall 1, Assumptions Log A1/A2)
    - infra/snowflake/postgres/mdm_create_instance.sql (confirm it is dev-only — creates EDGARTOOLS_DEV_MDM, no prod variant)
    - .planning/workstreams/go-live/phases/07-production-snowflake-native-pull-and-gold (Phase 7 BLOCKED-with-evidence precedent: stop rather than fabricate)
  </read_first>
  <action>
    Before any secret population, confirm the production Snowflake-hosted Postgres MDM instance
    exists and is ready. No Terraform resource or prod-targeted SQL script in this repo provisions
    it (mdm_create_instance.sql only creates EDGARTOOLS_DEV_MDM), so its existence is an external
    precondition that MUST be verified, not assumed. Use `snow sql` against the prod connection with
    a DESCRIBE POSTGRES INSTANCE query against the prod instance name (operator supplies the exact
    prod instance name, e.g. EDGARTOOLS_PROD_MDM — do not hardcode a guess), or Snowsight as a manual
    fallback if the `snow` CLI is unavailable. Create the evidence file
    evidence/mdm-prod-secrets-and-connectivity.md and record ONLY the non-secret outcome: instance
    name and ready/exists status (no host string, no credentials, no DSN). If the instance does NOT
    exist or is not ready, STOP — do not proceed to Task 2, do not fabricate a DSN. Record a new
    BLOCKED item in the evidence file and run a 5-whys root-cause pass per CLAUDE.md (the proximate
    cause being "no prod instance provisioned"; root cause being "no prod-automated instance
    provisioning exists in this repo"). This mirrors the Phase 7 precedent of stopping at secret-safe
    BLOCKED evidence rather than synthesizing placeholder production state.
  </action>
  <verify>
    <automated>test -f .planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/evidence/mdm-prod-secrets-and-connectivity.md && grep -qiE "instance|postgres instance" .planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/evidence/mdm-prod-secrets-and-connectivity.md</automated>
  </verify>
  <acceptance_criteria>
    - Evidence file exists and records the prod Postgres MDM instance existence/readiness outcome (exists+ready OR BLOCKED).
    - If instance exists and is ready: evidence states this in non-secret terms (no host, no credentials) and execution proceeds to Task 2.
    - If instance does NOT exist: a BLOCKED item with a 5-whys chain is recorded, Task 2 is NOT executed, and no DSN is fabricated or written.
    - No host string, DSN, credential, or raw connector error appears anywhere in the evidence file.
  </acceptance_criteria>
  <done>Prod Postgres MDM instance existence is verified and recorded; either confirmed-ready (proceed) or BLOCKED-with-5-whys (stop). No secret value printed or committed.</done>
</task>

<task type="auto">
  <name>Task 2: Populate both required prod MDM secrets + capture presence evidence</name>
  <files>.planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/evidence/mdm-prod-secrets-and-connectivity.md</files>
  <read_first>
    - .planning/workstreams/go-live/milestones/v1.5-phases/03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md (Sections 1, 2, 5, Security Note — authoritative population + presence-check procedure)
    - infra/scripts/bootstrap-aws-mdm-secrets.sh (DSN validation helper; supports --dsn-stdin and --dry-run)
    - .planning/workstreams/go-live/milestones/v1.5-phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/mdm-hosted-graph.md (D-07 DSN shape reference, D-08 describe-secret evidence pattern)
  </read_first>
  <action>
    Only execute if Task 1 confirmed the prod Postgres instance exists. Populate
    edgartools-prod/mdm/postgres_dsn via the validated helper bootstrap-aws-mdm-secrets.sh with the
    --dsn-stdin flag (DSN piped via stdin, never as a shell argument — avoids process-listing and
    shell-history leakage), passing --env prod --aws-profile aws-admin-prod --aws-region us-east-1.
    The DSN must satisfy the helper's invariants: host ends in .snowflake.app, database equals mdm,
    query string includes sslmode=require. Optionally run with --dry-run first to validate shape
    without writing. Then populate edgartools-prod/mdm/snowflake with a raw aws secretsmanager
    put-secret-value (--profile aws-admin-prod --region us-east-1 --secret-id
    edgartools-prod/mdm/snowflake) supplying a JSON --secret-string with exactly the 7 keys
    MDM_SNOWFLAKE_ACCOUNT, MDM_SNOWFLAKE_USER, MDM_SNOWFLAKE_PASSWORD, MDM_SNOWFLAKE_DATABASE,
    MDM_SNOWFLAKE_WAREHOUSE, MDM_SNOWFLAKE_SCHEMA (value EDGARTOOLS_GOLD, known — not a placeholder),
    and MDM_SNOWFLAKE_ROLE. Redirect put-secret-value output to /dev/null — its ARN/VersionId output
    must NEVER be pasted into evidence. Do NOT print, log, or commit any DSN, password, or secret
    value at any point. Then run aws secretsmanager describe-secret --profile aws-admin-prod --region
    us-east-1 for BOTH secret IDs with the query selecting only Name, ARN, LastChangedDate,
    VersionIdsToStages, and append that metadata-only output to the evidence file (this is the only
    output safe to commit, per the runbook Security Note / D-08). A populated secret shows an
    AWSCURRENT entry in VersionIdsToStages with an advanced LastChangedDate. CRITICAL: do NOT populate,
    create, or reference edgartools-prod/mdm/neo4j or edgartools-prod/mdm/api_keys — out of scope.
    Always pass --region us-east-1 explicitly (infra is us-east-1, not the AWS CLI default us-east-2).
  </action>
  <verify>
    <automated>grep -q "VersionIdsToStages" .planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/evidence/mdm-prod-secrets-and-connectivity.md && grep -q "edgartools-prod/mdm/postgres_dsn" .planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/evidence/mdm-prod-secrets-and-connectivity.md && grep -q "edgartools-prod/mdm/snowflake" .planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/evidence/mdm-prod-secrets-and-connectivity.md && ! grep -qiE "sslmode=require|password|snowflake\.app" .planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/evidence/mdm-prod-secrets-and-connectivity.md</automated>
  </verify>
  <acceptance_criteria>
    - describe-secret metadata (Name, ARN, LastChangedDate, VersionIdsToStages) for BOTH postgres_dsn and snowflake is recorded in the evidence file, each showing an AWSCURRENT version.
    - No DSN, host string, password, sslmode=require literal, or put-secret-value/get-secret-value SecretString output appears anywhere in the evidence file.
    - The evidence file contains NO mention of populating neo4j or api_keys.
    - All aws secretsmanager invocations used --region us-east-1 explicitly.
  </acceptance_criteria>
  <done>Both required secrets carry an AWSCURRENT version; evidence shows describe-secret metadata only; no value was printed or committed; neo4j/api_keys untouched.</done>
</task>

<task type="auto">
  <name>Task 3: Clarify neo4j/api_keys out-of-scope in HANDOFF.json</name>
  <files>.planning/HANDOFF.json</files>
  <read_first>
    - .planning/HANDOFF.json (the existing blocker entry listing all 4 MDM secret containers as un-populated)
    - .planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/08-RESEARCH.md (scope decision: only postgres_dsn + snowflake are Phase 8 / MDM-02; neo4j is legacy, api_keys is deferred)
  </read_first>
  <action>
    Edit the HANDOFF.json blocker whose description currently lists all four MDM secret containers
    (postgres_dsn, neo4j, api_keys, snowflake) as un-populated. Update its description text to clarify
    that ONLY edgartools-prod/mdm/postgres_dsn and edgartools-prod/mdm/snowflake are Phase 8 / MDM-02
    blockers, and that edgartools-prod/mdm/neo4j (legacy — replaced by the Snowflake-hosted graph) and
    edgartools-prod/mdm/api_keys (deferred — consumer is the MDM FastAPI auth layer, unrelated to this
    phase) are explicitly NOT Phase 8 blockers and are out of scope. Keep the JSON valid (parseable).
    Do not add or remove other blocker entries; only adjust this one description string. Do not write
    any secret value into HANDOFF.json.
  </action>
  <verify>
    <automated>python3 -c "import json; json.load(open('.planning/HANDOFF.json'))" && grep -qi "not Phase 8\|out of scope\|NOT Phase 8" .planning/HANDOFF.json</automated>
  </verify>
  <acceptance_criteria>
    - HANDOFF.json remains valid JSON (python json.load succeeds).
    - The MDM-secrets blocker description names postgres_dsn and snowflake as the only Phase 8 blockers and marks neo4j and api_keys as out of scope.
    - No other blocker entry was added or removed; no secret value was written.
  </acceptance_criteria>
  <done>HANDOFF.json blocker text scopes Phase 8 to the two required secrets and documents neo4j/api_keys as out of scope; JSON still valid.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| operator shell → AWS Secrets Manager | Real prod DSN/credentials cross here via put-secret-value; must never be printed/logged/committed |
| operator shell → Snowflake (prod) | Instance-existence check; connection details must not leak into evidence |
| evidence Markdown → git | Only describe-secret metadata may cross; secret values and raw connector errors must not |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-08-01 | Information Disclosure | DSN/credential value in committed evidence | mitigate | describe-secret metadata only; put-secret-value output to /dev/null; grep gate in verify blocks sslmode/password/host leakage |
| T-08-02 | Information Disclosure | DSN supplied as shell argument (process listing / history) | mitigate | postgres_dsn populated via bootstrap-aws-mdm-secrets.sh --dsn-stdin (stdin, not argv) |
| T-08-03 | Tampering | Wrong-region secret write creating shadow secret | mitigate | every aws secretsmanager call passes --region us-east-1 explicitly |
| T-08-04 | Denial of Service (self-inflicted) | postgres_dsn pointed at a non-existent prod Postgres instance | mitigate | Task 1 precondition verifies instance exists/ready before any write; STOP + BLOCKED if absent |
| T-08-SC | Tampering | npm/pip/cargo installs | accept | No packages installed this phase (uses existing AWS CLI + edgar-warehouse CLI); no install surface |
</threat_model>

<verification>
- evidence/mdm-prod-secrets-and-connectivity.md exists and records the instance-existence outcome.
- describe-secret metadata for both required secrets present (AWSCURRENT versions) — OR a BLOCKED item recorded if the prod Postgres instance does not exist.
- No DSN, password, host string, or put-secret-value/get-secret-value SecretString output anywhere in committed files.
- HANDOFF.json valid JSON with neo4j/api_keys marked out of scope.
- No write to neo4j or api_keys secrets occurred.
</verification>

<success_criteria>
Both required production secret names (postgres_dsn, snowflake) are populated by an operator
without printing values, OR a legitimate BLOCKED outcome is recorded with a 5-whys chain when the
prod Postgres instance does not yet exist. Evidence records only secret names and describe-secret
metadata. HANDOFF.json clarifies neo4j/api_keys are out of scope. (A legitimate BLOCKED outcome is a
valid verification result — it must never be resolved by fabricating a DSN or credential.)
</success_criteria>

<output>
Create `.planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/08-01-SUMMARY.md` when done.
</output>
