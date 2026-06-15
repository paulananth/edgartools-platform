---
phase: 03
plan: 03-02-secrets-runbook-and-matrix
type: execute
wave: 2
depends_on: [03-01-live-mdm-graph-rehearsal]
files_modified:
  - .planning/workstreams/go-live/phases/03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md
  - .planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md
autonomous: true
requirements: [MDM-01, GRAPH-01, GRAPH-02, LIVE-03]

must_haves:
  truths:
    - "An operator has a non-secret runbook documenting how to populate the two prod MDM secrets (postgres_dsn, snowflake) with placeholder-only commands."
    - "The runbook documents describe-secret presence checks for both secrets and explicitly forbids pasting put-secret-value / get-secret-value output into evidence."
    - "The runbook annotates neo4j as legacy/not-required and api_keys as deferred — no population commands for either."
    - "01-LAUNCH-GATE-MATRIX.md rows 22-25 point operators at runbook/mdm-secrets.md and the Phase 3 evidence sections appended by plan 03-01, while staying BLOCKED."
    - "The Required Production Identifiers secret checklist is annotated per D-06 and references the new runbook."
  artifacts:
    - path: ".planning/workstreams/go-live/phases/03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md"
      provides: "MDM prod secret-population runbook (postgres_dsn + snowflake, placeholders only)"
      contains: "put-secret-value"
      min_lines: 60
    - path: ".planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md"
      provides: "Updated MDM/hosted-graph BLOCKED rows + Required Production Identifiers annotations"
      contains: "mdm-secrets.md"
  key_links:
    - from: "01-LAUNCH-GATE-MATRIX.md (rows 22-25, Required Fix cells)"
      to: "runbook/mdm-secrets.md"
      via: "cross-phase relative markdown link ../03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md"
      pattern: "03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md"
    - from: "01-LAUNCH-GATE-MATRIX.md (rows 22-25, Required Rerun Proof cells)"
      to: "evidence/mdm-hosted-graph.md ## Phase 3 Live Checks Actually Run (appended by 03-01)"
      via: "relative markdown link + named evidence section headings"
      pattern: "Phase 3 Live Checks Actually Run"
---

<objective>
Author the documentation-only deliverables that close the operator-facing loop for
Phase 3's MDM/hosted-graph BLOCKED rows: (a) a new `runbook/mdm-secrets.md` documenting
how to populate the two prod MDM secrets (`postgres_dsn`, `snowflake`) with
placeholder-only commands, and (b) in-place updates to `01-LAUNCH-GATE-MATRIX.md` rows
22-25 and the "Required Production Identifiers" secret checklist so they reference the
new runbook and the Phase 3 evidence appended by plan 03-01.

Purpose: an operator approaching go-live has the exact required-fix commands and a
concrete checklist of what "populated and passing" must look like — without any secret
value ever appearing in a committed file.

Output: `runbook/mdm-secrets.md` (new) and updated `01-LAUNCH-GATE-MATRIX.md` (rows
22-25 + Required Production Identifiers). No live commands are run by this plan — it is
documentation-only. The rows stay `BLOCKED` (they can only move to `PASS` after real
prod secrets are populated and a prod E2E succeeds, which is out of Phase 3 scope).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/workstreams/go-live/phases/03-mdm-hosted-graph-e2e-acceptance/03-CONTEXT.md
@.planning/workstreams/go-live/phases/03-mdm-hosted-graph-e2e-acceptance/03-RESEARCH.md
@.planning/workstreams/go-live/phases/03-mdm-hosted-graph-e2e-acceptance/03-PATTERNS.md
@.planning/workstreams/go-live/phases/03-mdm-hosted-graph-e2e-acceptance/03-VALIDATION.md

# Verbatim command/placeholder content source — copy these blocks into the runbook.
# 03-RESEARCH.md section "MDM Secret Population Runbook (D-05–D-08)" has the exact
# postgres_dsn (bootstrap-aws-mdm-secrets.sh --dsn-stdin), snowflake (raw
# put-secret-value with 7 keys), and describe-secret presence-check blocks.
# 03-PATTERNS.md section "runbook/mdm-secrets.md" gives the header disclaimer, the
# bootstrap-aws-mdm-secrets.sh flag inventory, the DSN-shape masking convention (D-07),
# and the References-section shape.

# Style reference — follow this format exactly (header disclaimer, numbered
# "# N. <description>" command blocks, References section):
@.planning/workstreams/go-live/phases/02-aws-and-snowflake-production-deployment-dry-run/runbook/aws-deploy.md

# The file being edited in Task 2 — rows 22-25 + Required Production Identifiers:
@.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md

<interfaces>
<!-- Stable headings plan 03-01 appends to the EXISTING Phase 1 evidence file -->
<!-- .planning/workstreams/go-live/phases/01-.../evidence/mdm-hosted-graph.md -->
<!-- under a new top-level "## Phase 3 Live Checks Actually Run" section. Task 2's -->
<!-- "Required Rerun Proof" cells reference these by name: -->
<!--   ### Dev MDM Postgres Re-Verification (MDM-01, D-03) -->
<!--   ### Dev postgres_dsn Shape Reference (D-07 — for plan 03-02) -->
<!--   ### Dev Full E2E Rehearsal (LIVE-03/GRAPH-01/GRAPH-02, D-09/D-10) -->
<!--   ### Prod --status-only Blocker Reproduction (LIVE-03, D-02) -->

<!-- The snowflake secret JSON shape — 7 keys consumed by _snowflake_setting() in -->
<!-- edgar_warehouse/mdm/export.py:53-59 (call sites) / 181-189 (resolution): -->
<!--   ACCOUNT, USER, PASSWORD, DATABASE, WAREHOUSE, SCHEMA (defaults EDGARTOOLS_GOLD), ROLE -->
<!-- Written as uppercase MDM_SNOWFLAKE_<KEY> keys per Assumption A2 in 03-RESEARCH.md. -->
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Author runbook/mdm-secrets.md (postgres_dsn + snowflake population, placeholders only)</name>
  <files>.planning/workstreams/go-live/phases/03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md</files>
  <action>
Create the new file `runbook/mdm-secrets.md`, mirroring the Phase 2 `runbook/aws-deploy.md`
style (non-secret header disclaimer, numbered `# N. <description>` command blocks, closing
References section). Copy the verbatim command blocks from 03-RESEARCH.md section "MDM Secret
Population Runbook (D-05–D-08)" — do not paraphrase the commands.

Required sections, in order:

1. Header disclaimer (per 03-PATTERNS.md "Header pattern"): state this runbook documents
   `aws secretsmanager put-secret-value` commands for `edgartools-prod/mdm/postgres_dsn` and
   `edgartools-prod/mdm/snowflake` (per D-05/D-06); every value is a `<PLACEHOLDER>`; no real
   secret values, ARNs, or `put-secret-value` / `get-secret-value` output are pasted.

2. `postgres_dsn` population (per D-05/D-07): use `infra/scripts/bootstrap-aws-mdm-secrets.sh`
   as the vehicle (it already populates this secret and validates DSN shape) with `--env prod`,
   `--aws-profile`, `--aws-region`, and `--dsn-stdin` — placeholder DSN piped via `printf`.
   Note the `--dry-run` flag validates without writing. Include the D-07 shape reference
   (structure only, no values): `postgresql://<user>:<password>@<host>.snowflake.app:<port>/<database>?sslmode=require`,
   noting host must end `.snowflake.app`, database must equal `mdm`, query must include
   `sslmode=require` (enforced by `audit-mdm-snowflake-postgres-cutover.py`). State that the
   masked dev DSN structure captured by plan 03-01 under the evidence heading
   `### Dev postgres_dsn Shape Reference (D-07 — for plan 03-02)` is the format reference for
   what the prod value must look like — structure only, no values.

3. `snowflake` population (per D-05/D-06, Assumption A2): no helper script exists, so document
   a raw `aws secretsmanager put-secret-value --secret-id edgartools-prod/mdm/snowflake` with a
   placeholder JSON `--secret-string` containing exactly the 7 uppercase keys
   `MDM_SNOWFLAKE_ACCOUNT`, `MDM_SNOWFLAKE_USER`, `MDM_SNOWFLAKE_PASSWORD`,
   `MDM_SNOWFLAKE_DATABASE`, `MDM_SNOWFLAKE_WAREHOUSE`, `MDM_SNOWFLAKE_SCHEMA` (default value
   `EDGARTOOLS_GOLD`), `MDM_SNOWFLAKE_ROLE` — these mirror `_snowflake_setting()` in
   `edgar_warehouse/mdm/export.py`. Include the inline note that this command's output contains
   the secret ARN/VersionId and must NOT be pasted into evidence.

4. `neo4j` and `api_keys` annotations (per D-06): one line each, NO population command.
   `neo4j` — "not required — legacy graph container; the Snowflake-hosted graph does not use
   this secret" (Phase 2 framing). `api_keys` — "deferred — purpose unclear; revisit when the
   consumer is identified" (deferred in CONTEXT.md).

5. `describe-secret` presence-check block (per D-08): `aws secretsmanager describe-secret`
   for both `edgartools-prod/mdm/postgres_dsn` and `edgartools-prod/mdm/snowflake`, querying
   `{Name,ARN,LastChangedDate,VersionIdsToStages}` only — to confirm the secret containers
   exist but are not yet populated (a populated secret has a non-empty `AWSCURRENT` version).
   Note this `describe-secret` JSON output IS safe to record in evidence (it is the D-08
   "secret exists but not populated" proof); it contains no secret values.

6. Security note (covers all three threats in the threat model): the operator must NOT paste
   `aws secretsmanager get-secret-value --query SecretString` output, nor `put-secret-value`
   response output, into any evidence or planning file. Only `describe-secret` metadata (Name,
   ARN, LastChangedDate, VersionIdsToStages) is safe to record.

7. References section: cite `infra/scripts/bootstrap-aws-mdm-secrets.sh`,
   `infra/scripts/audit-mdm-snowflake-postgres-cutover.py`,
   `infra/terraform/modules/warehouse_runtime/main.tf`, `edgar_warehouse/mdm/export.py`
   (`_snowflake_setting`), and `01-LAUNCH-GATE-MATRIX.md` row "MDM Snowflake Postgres secret
   container and connectivity".

No `aws secretsmanager get-secret-value` invocation may appear anywhere in this file — it is
named only inside the prohibition prose of the security note.
  </action>
  <verify>
    <automated>test -f .planning/workstreams/go-live/phases/03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md && f=.planning/workstreams/go-live/phases/03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md; grep -q 'bootstrap-aws-mdm-secrets.sh' "$f" && grep -q -- '--dsn-stdin' "$f" && grep -q 'put-secret-value' "$f" && grep -q 'describe-secret' "$f" && for k in MDM_SNOWFLAKE_ACCOUNT MDM_SNOWFLAKE_USER MDM_SNOWFLAKE_PASSWORD MDM_SNOWFLAKE_DATABASE MDM_SNOWFLAKE_WAREHOUSE MDM_SNOWFLAKE_SCHEMA MDM_SNOWFLAKE_ROLE; do grep -q "$k" "$f" || { echo "MISSING $k"; exit 1; }; done && grep -qi 'neo4j' "$f" && grep -qi 'api_keys' "$f" && test "$(grep -cE 'get-secret-value[[:space:]]+--secret-id|secretsmanager get-secret-value --secret-id' "$f")" -eq 0 && echo PASS</automated>
  </verify>
  <done>
`runbook/mdm-secrets.md` exists with: postgres_dsn via bootstrap-aws-mdm-secrets.sh --dsn-stdin;
snowflake via raw put-secret-value with all 7 MDM_SNOWFLAKE_* keys; describe-secret presence
checks for both; neo4j (legacy/N/A) and api_keys (deferred) annotated with no population
command; D-07 shape reference citing 03-01's evidence heading; security note forbidding
get-secret-value / put-secret-value output in evidence; References section. No
`get-secret-value --secret-id` invocation anywhere (the string appears only in prohibition prose).
  </done>
</task>

<task type="auto">
  <name>Task 2: Update 01-LAUNCH-GATE-MATRIX.md rows 22-25 + Required Production Identifiers</name>
  <files>.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md</files>
  <action>
Edit `01-LAUNCH-GATE-MATRIX.md` in place. Read the current row content (rows 22-25 and the
"Required Production Identifiers" secret checklist) before editing — preserve the existing
column structure (`Gate | Owner/Source | Required Fix | Required Rerun Proof | Status`) and do
not touch any other rows. All four rows stay `BLOCKED` (the "Dev Vs Prod Distinction" rule,
lines 41-43 — Phase 3 dev rehearsal evidence does not flip these to PASS).

Link-path discipline (the single most important structural decision per 03-PATTERNS.md):
- Plan 03-01 appends its evidence to the EXISTING Phase 1 `evidence/mdm-hosted-graph.md`, which
  lives in the SAME directory as this matrix. So evidence links stay the bare relative form
  `[evidence/mdm-hosted-graph.md](evidence/mdm-hosted-graph.md)` — do NOT rewrite them to a
  cross-phase path.
- The new runbook lives in the Phase 3 directory, so links to it MUST be cross-phase:
  `[runbook/mdm-secrets.md](../03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md)`
  (mirroring how Phase 1 links Phase 2's runbook via `../02-.../runbook/aws-deploy.md`).

Row edits (use 03-RESEARCH.md "Launch Gate Matrix Integration" as the per-row mapping):
- Row 22 "MDM Snowflake Postgres secret container and connectivity": "Required Fix" cell adds a
  link to the new runbook for the exact secret-population steps (postgres_dsn + snowflake
  put-secret-value commands and the describe-secret presence check). "Required Rerun Proof"
  cell references the Phase 3 evidence section `### Dev MDM Postgres Re-Verification (MDM-01, D-03)`
  (dev precedent refresh) and `### Dev postgres_dsn Shape Reference (D-07 — for plan 03-02)`.
- Row 23 "edgar-warehouse mdm sync-graph hosted graph materialization": "Required Rerun Proof"
  cell references `### Dev Full E2E Rehearsal (LIVE-03/GRAPH-01/GRAPH-02, D-09/D-10)` (the
  rehearsal's mdm_sync_graph stage), keeping the "dev precedent only — prod proof required
  separately" framing.
- Row 24 "Strict edgar-warehouse mdm verify-graph": "Required Rerun Proof" references the same
  `### Dev Full E2E Rehearsal ...` section (preflight + mdm_verify_graph stage) plus the cited
  `03-LIVE-DEV-RUN.md` precedent; dev-precedent-only framing preserved.
- Row 25 "AWS MDM hosted graph E2E": "Required Rerun Proof" references `### Dev Full E2E
  Rehearsal (LIVE-03/GRAPH-01/GRAPH-02, D-09/D-10)` for the dev rehearsal and
  `### Prod --status-only Blocker Reproduction (LIVE-03, D-02)` for the WHY-still-blocked proof
  (missing `infra/aws-prod-application.json`).

Required Production Identifiers secret checklist (lines ~77-82) — annotate, do NOT check boxes
(population itself is out of scope):
- `edgartools-prod/mdm/postgres_dsn` — stays `[ ]`; annotate "population runbook documented in
  ../03-.../runbook/mdm-secrets.md, not yet executed against real prod values".
- `edgartools-prod/mdm/snowflake` — same annotation.
- `edgartools-prod/mdm/neo4j` — annotate "not required / legacy" (D-06).
- `edgartools-prod/mdm/api_keys` — annotate "deferred, consumer unclear" (D-06).

Reference only runbook section descriptions and evidence section headings in the matrix cells —
never raw secret ARNs or DSN values (Information Disclosure threat).
  </action>
  <verify>
    <automated>f=.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md; grep -q '03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md' "$f" && grep -q 'Dev Full E2E Rehearsal' "$f" && grep -q 'Prod --status-only Blocker Reproduction' "$f" && grep -q 'not required / legacy' "$f" && grep -q 'deferred, consumer unclear' "$f" && test "$(grep -cE 'BLOCKED' "$f")" -ge 4 && echo PASS</automated>
  </verify>
  <done>
Rows 22-25 reference the new runbook (cross-phase link) and the four Phase 3 evidence section
headings appended by 03-01, while remaining BLOCKED. Required Production Identifiers checklist:
postgres_dsn and snowflake annotated with the runbook reference (boxes still unchecked), neo4j
annotated "not required / legacy", api_keys annotated "deferred, consumer unclear". No other
rows changed; no raw ARNs/DSNs introduced.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| operator shell → committed Markdown | Secret values resolved at runtime (DSNs, snowflake creds, secret ARNs) must never cross into runbook/evidence/planning files committed to git. |
| AWS Secrets Manager → evidence file | `describe-secret` metadata (Name, ARN, LastChangedDate, VersionIdsToStages) is safe to record; `get-secret-value`/`put-secret-value` output is not. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-03-01 | Information Disclosure | `runbook/mdm-secrets.md` put-secret-value / bootstrap command blocks | mitigate | All DSN/JSON values are `<PLACEHOLDER>` tokens only; D-07 shape reference is structure-only; header disclaimer states no real values/ARNs/output are pasted. Verify in Task 1: no `get-secret-value --secret-id` invocation appears; values are placeholders. |
| T-03-02 | Information Disclosure | operator pasting `put-secret-value` / `get-secret-value` output into evidence | mitigate | Runbook security note explicitly forbids pasting `put-secret-value` responses and `get-secret-value --query SecretString` output into any evidence or planning file; only `describe-secret` metadata is recordable (D-08). |
| T-03-03 | Information Disclosure | `01-LAUNCH-GATE-MATRIX.md` row + Required Production Identifiers updates | mitigate | Matrix cells reference runbook section descriptions and evidence section headings only — never raw secret ARNs or DSN values. Existing matrix Secret-Safety Rules (lines 45-63) remain in force. |
| T-03-SC | Tampering | npm/pip/cargo installs | N/A | No packages installed in this phase — 03-RESEARCH.md "Package Legitimacy Audit" confirms zero new external packages; this plan is documentation-only. No supply-chain checkpoint required. |
</threat_model>

<verification>
- `runbook/mdm-secrets.md` exists and passes the Task 1 automated grep gate (postgres_dsn via
  bootstrap helper, snowflake raw put-secret-value with all 7 keys, describe-secret presence
  checks, neo4j/api_keys annotations, no `get-secret-value --secret-id` invocation).
- `01-LAUNCH-GATE-MATRIX.md` passes the Task 2 automated grep gate (cross-phase runbook link,
  evidence section headings, D-06 annotations, rows still BLOCKED).
- Manual cross-check against 03-VALIDATION.md: this plan produces no live commands; its
  verification is "confirm section/content present in the authored file" (the doc-only analog
  of the Manual-Only Verifications table, whose live-command methods belong to plan 03-01).
- Secret-safety scrub: no DSNs, passwords, tokens, or secret ARNs appear in either authored
  file (only `<PLACEHOLDER>` tokens and structure references).
</verification>

<success_criteria>
- `runbook/mdm-secrets.md` documents placeholder-only population for `postgres_dsn`
  (via `bootstrap-aws-mdm-secrets.sh --dsn-stdin`) and `snowflake` (raw `put-secret-value`,
  7 `MDM_SNOWFLAKE_*` keys), with `describe-secret` presence checks for both, neo4j/api_keys
  annotated as not-required/deferred, a D-07 shape reference citing 03-01's evidence heading,
  and a security note forbidding get-secret-value/put-secret-value output in evidence.
- `01-LAUNCH-GATE-MATRIX.md` rows 22-25 reference the new runbook (cross-phase link) and the
  four Phase 3 evidence section headings, stay BLOCKED, and the Required Production Identifiers
  secret checklist is annotated per D-06.
- No secret values, DSNs, or secret ARNs appear in either file.
- `<threat_model>` present covering the three Information-Disclosure threats.
</success_criteria>

<output>
Create `.planning/workstreams/go-live/phases/03-mdm-hosted-graph-e2e-acceptance/03-02-SUMMARY.md` when done.
</output>
