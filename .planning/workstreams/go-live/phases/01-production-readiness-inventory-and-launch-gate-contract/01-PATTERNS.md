# Phase 1: Production Readiness Inventory And Launch Gate Contract - Pattern Map

**Mapped:** 2026-06-13
**Files analyzed:** 5
**Analogs found:** 5 / 5

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `01-LAUNCH-GATE-MATRIX.md` | config (gate/checklist doc) | batch (status table, no live execution) | `TODOS.md` (blocker entries) + `docs/aws-mdm-snowflake-postgres-cutover.md` (hazard sections) | role-match |
| `evidence/aws.md` | test/evidence (command-result log) | request-response (CLI/AWS command -> non-secret summary) | `.planning/workstreams/neo4j-snowflake/phases/03-hosted-graph-verification-and-e2e-cutover/03-LIVE-DEV-RUN.md` | exact |
| `evidence/snowflake.md` | test/evidence (command-result log) | request-response (dbt/SQL command -> non-secret summary) | `.planning/workstreams/neo4j-snowflake/phases/03-hosted-graph-verification-and-e2e-cutover/03-LIVE-DEV-RUN.md` | exact |
| `evidence/mdm-hosted-graph.md` | test/evidence (command-result log) | request-response (`mdm verify-graph` / Step Functions status -> non-secret summary) | `.planning/workstreams/neo4j-snowflake/phases/03-hosted-graph-verification-and-e2e-cutover/03-LIVE-DEV-RUN.md` | exact |
| `evidence/dashboard-security.md` | test/evidence (UAT notes) | request-response (dashboard inspection -> text UAT notes) | `.planning/workstreams/neo4j-snowflake/phases/04-dashboard-hosted-graph-migration/04-03-PLAN.md` (Task 2: `04-DASHBOARD-VERIFICATION.md` spec) + `examples/mdm_graph_dashboard/README.md` | role-match |

All five files are documentation/evidence artifacts (no application source code is created or
modified in this phase). The "closest analog" search therefore targeted prior workstream
evidence docs, hazard-documentation sections in `docs/`, and `TODOS.md` blocker-entry format,
which are the established conventions for this kind of artifact in this repo.

---

## Pattern Assignments

### `01-LAUNCH-GATE-MATRIX.md` (gate/checklist doc)

**Analogs:**
- `TODOS.md` lines 555-650 (blocker entry format: Status line, root cause, fix, follow-up)
- `docs/aws-mdm-snowflake-postgres-cutover.md` lines 91-148 (hazard call-out format: Symptom / Root cause / Fix applied / Recommended permanent fix)
- `.planning/workstreams/go-live/REQUIREMENTS.md` lines 64-89 (Traceability table format)
- `.planning/workstreams/go-live/ROADMAP.md` lines 123-131 (Progress table format)

**Status/owner table pattern** (`TODOS.md` lines 555-561, adapted):
```markdown
## EDGARTOOLS_DEV_DEPLOYER lacks direct SELECT on EDGARTOOLS_SOURCE — blocks `dbt run --full-refresh` for any gold dynamic table

**Status:** RESOLVED for dev 2026-06-13. Discovered while attempting T1 live
verification of the Stage 5 `financial_derived.sql` change (PR #66,
`claude/financial-derived-lag-tiebreaker`), but is generic to **any**
`EDGARTOOLS_GOLD` dynamic table, not specific to that PR.
```
Use this "Status: <BLOCKED|RESOLVED|WARNING> for <env> <date>. <context sentence>." idiom
for each matrix row's narrative cell, and the `## <imperative summary>` heading style for
any per-item detail sections.

**Traceability table pattern** (`.planning/workstreams/go-live/REQUIREMENTS.md` lines 64-83):
```markdown
| Requirement | Phase | Status |
|-------------|-------|--------|
| LIVE-01 | Phase 1 | Pending |
| SEC-01 | Phase 1 | Pending |
```
Use this column shape (`| Item | Owner/Phase | Status |`) as the skeleton for the
launch gate matrix, extended per D-12 to:
`| Gate | Owner/Source | Required Fix | Required Rerun Proof | Status |`
with `Status` constrained to `BLOCKED` / `PASS` / `WARNING` per D-05/D-06/D-12 (no `WAIVED`).

**Known-hazard call-out pattern** (`docs/aws-mdm-snowflake-postgres-cutover.md` lines 91-100, 122-139):
```markdown
### ⚠️ Known issue: stale `edgar-identity` secret ARN breaks ALL ECS task launches

**Symptom:** Every ECS task registered by this deploy ... fails to start with:
...
**Fix applied:** re-run the deploy passing `--edgar-identity-secret-arn`
explicitly with the *live* ARN (look it up fresh, don't trust the manifest):
```
Use this Symptom -> Root cause -> Fix/Required Mitigation shape for the two named
deploy hazards (stale `edgar-identity` ARN, ECR cleanup deleting an in-flight digest)
as `BLOCKED` rows per D-03, each requiring "go-live runbook has explicit required
mitigations and the checklist enforces those mitigations before deploy."

**Missing-artifact blocker pattern** (D-17, verified against repo state):
```bash
ls infra/aws-dev-application.json    # exists
ls infra/aws-prod-application.json   # does NOT exist -> BLOCKED row per D-17
```
Record this as a `BLOCKED` matrix row: Gate = "Production AWS application manifest",
Owner = AWS operator, Required Fix = "live discovery or successful prod deploy",
Required Rerun Proof = "non-secret summary of `infra/aws-prod-application.json`
presence + key fields (state machine names, image refs) per D-15".

**Dev-vs-prod distinction pattern** (D-18, from `03-LIVE-DEV-RUN.md` header lines 1-7):
```markdown
Date: 2026-06-12 UTC
Environment: dev
Snowflake connection: `snowconn`
Snowflake database: `EDGARTOOLS_DEV`
AWS profile: `sec_platform_deployer`
```
Every matrix row referencing Phase 3's dev hosted-graph proof should explicitly mark it
"dev precedent only — prod proof required separately" using this same environment-label
header convention, satisfying D-18.

---

### `evidence/aws.md` (evidence, request-response)

**Analog:** `.planning/workstreams/neo4j-snowflake/phases/03-hosted-graph-verification-and-e2e-cutover/03-LIVE-DEV-RUN.md` (full file, 209 lines)

**File header pattern** (lines 1-10):
```markdown
# Phase 3 Live Dev Run

Date: 2026-06-12 UTC
Environment: dev
Snowflake connection: `snowconn`
Snowflake database: `EDGARTOOLS_DEV`
AWS profile: `sec_platform_deployer`

This artifact captures non-secret evidence only. It omits passwords, tokens, DSNs,
full task logs, and raw Native App job logs.
```
Adapt to: `# AWS Evidence — Phase 1 Production Readiness`, with Date, Environment
(`prod` required per D-18, `dev` only as precedent), AWS profile/account, and the same
secret-safety disclaimer sentence (satisfies D-07).

**Command + result + non-secret summary pattern** (lines 90-109):
```markdown
\`\`\`bash
bash infra/scripts/run-aws-mdm-e2e.sh \
  --env dev \
  --aws-profile sec_platform_deployer \
  --status-only
\`\`\`

Result: succeeded.

Relevant non-secret Step Functions status:

| Workflow | Latest status | Latest execution name |
| --- | --- | --- |
| `mdm_migrate` | `SUCCEEDED` | `ci-fix-mdm-migrate-1780711962` |
```
This is the exact "exact command / environment / pass-fail / key counts or statuses /
sanitized links" shape required by D-10. Each command block in `evidence/aws.md` should
follow: fenced command -> `Result: <succeeded|failed>.` -> bullet or table of non-secret
observations. Only include commands that were actually run (D-13) — e.g. read-only
status checks such as `aws ecs list-task-definitions`, `aws stepfunctions
list-state-machines`, `aws secretsmanager describe-secret` (ARN/metadata only, never
`get-secret-value` output), and `infra/aws-prod-application.json` presence/summary
(D-15).

**Generated-JSON summary pattern** (D-15, no direct analog file exists yet but the
convention is implied by the "non-secret outcomes" bullet list style above): summarize
`infra/aws-*-application.json` as bullets — file presence, top-level keys present,
state machine name list, image ref format (digest vs tag) — never paste the JSON body.

---

### `evidence/snowflake.md` (evidence, request-response)

**Analog:** same as above, `03-LIVE-DEV-RUN.md`, plus `infra/scripts/deploy-snowflake-stack.sh` flags for command shapes.

**Command shape to mirror** (from `infra/scripts/deploy-snowflake-stack.sh` lines 10-14, 50-70):
```text
--env <dev|prod>           Target environment. Default: dev
--snow-connection <name>   SnowCLI connection used for all snow sql operations.
--run-validation           Run SnowCLI-based native-pull validation artifact generation.
--run-dbt                  Run dbt deps/run/test.
--upload-dashboard         Upload dashboard artifacts.
```
Evidence entries for dbt should follow the `03-LIVE-DEV-RUN.md` command/result/summary
shape, e.g.:
```markdown
\`\`\`bash
cd infra/snowflake/dbt/edgartools_gold
uv run --with dbt-snowflake dbt compile
\`\`\`

Result: succeeded.

- Models compiled: <count>
- `EDGARTOOLS_GOLD_STATUS` view present: yes/no
```
Only `dbt compile` (and other non-state-changing checks) belong here per D-21 unless a
production `dbt run`/`dbt test` was actually executed (D-13). Note the known
`EDGARTOOLS_DEV_DEPLOYER` / dynamic-table `--full-refresh` grant gap documented in
`TODOS.md` lines 555-650 — if the prod deployer role has the analogous gap, record it
as a `BLOCKED` row in the matrix (not in this evidence file) per D-04/D-17 reasoning.

---

### `evidence/mdm-hosted-graph.md` (evidence, request-response)

**Analog:** `.planning/workstreams/neo4j-snowflake/phases/03-hosted-graph-verification-and-e2e-cutover/03-LIVE-DEV-RUN.md` (full file — this is the canonical MDM/hosted-graph evidence shape)

**`verify-graph` non-secret payload summary pattern** (lines 50-71, 131-156):
```markdown
Non-secret verification payload summary:

- Overall status: `ok`
- Snowflake graph nodes: `15`
- Snowflake graph edges: `4`
- Node parity status: `ok`
- Relationship parity status: `ok`
- Missing/extra node diagnostics: none
- Missing/extra edge diagnostics: none
- Missing edge endpoint diagnostics: none
- Native App status: `ok`
- Native App compute pool: `CPU_X64_XS`
- Native App checks:
  - `app_installation`: `ok`
  - `compute_pool`: `ok` (`7` rows)
  - `graph_info`: `ok`
  - `bfs`: `ok`
  - `wcc`: `ok`
- `phase3_acceptance`: `true`
```
Reuse this exact field list/shape for prod `mdm verify-graph` evidence. Per D-22, Phase 1
requires the *local* `edgar-warehouse mdm verify-graph` against the target Snowflake
connection/database and Native App compute pool to be runnable — but the actual run
(and this summary) is Phase 3 work; Phase 1's `evidence/mdm-hosted-graph.md` should
record only commands actually run during Phase 1 (e.g. `--status-only` Step Functions
checks, D-13), with the `verify-graph` full-acceptance run referenced as a `BLOCKED`/
pending matrix row pointing to Phase 3.

**Relationship parity table pattern** (lines 74-89):
```markdown
| Relationship type | MDM active | Snowflake graph | Delta |
| --- | ---: | ---: | ---: |
| HOLDS | 1 | 1 | 0 |
| ISSUED_BY | 1 | 1 | 0 |
```
Reuse verbatim column shape for any parity evidence captured.

**Step Functions status table pattern** (lines 169-178):
```markdown
| Workflow | Latest status | Latest execution name | Started |
| --- | --- | --- | --- |
| `mdm_migrate` | `SUCCEEDED` | `aws-mdm-e2e-1781277675-migrate` | `2026-06-12T11:21:17.727000-04:00` |
```
Use for `--status-only` evidence (D-21, read-only).

**`--status-only` / `--skip-preflight` flag semantics** (from `infra/scripts/run-aws-mdm-e2e.sh` lines 25-33):
```text
--snow-connection <name>    Snowflake connection for local verify-graph preflight.
--snowflake-database <db>   Snowflake database for local verify-graph preflight.
--skip-preflight            Skip local verify-graph preflight before AWS executions.
--status-only               Only report Step Functions status; do not start executions.
```
Per D-23, any `--skip-preflight` run must be labeled "emergency/debug — non-acceptance"
and must NOT appear as a passing gate in the matrix or evidence file.

---

### `evidence/dashboard-security.md` (evidence, UAT notes)

**Analogs:**
- `.planning/workstreams/neo4j-snowflake/phases/04-dashboard-hosted-graph-migration/04-03-PLAN.md` Task 2 spec (lines 79-97) — defines the intended `04-DASHBOARD-VERIFICATION.md` evidence shape (file does not yet exist; Phase 4 closeout is still pending per CONTEXT.md D-02/canonical refs).
- `examples/mdm_graph_dashboard/README.md` lines 1-80 — current dashboard docs (contains stale `NEO4J_*` assumptions flagged in CONTEXT.md as needing cleanup before go-live).

**Evidence-checklist intent pattern** (`04-03-PLAN.md` lines 87-96, must_haves D-12/D-14):
```markdown
- Checklist excludes DSNs, passwords, tokens, raw connector exceptions, full logs, and
  account-secret values.
- Documentation states bounded samples are diagnostics, not exhaustive exports.
```
`evidence/dashboard-security.md` should adopt this same "what NOT to include" preamble,
plus D-14's allowance: "Dashboard screenshots are optional if secret-safe. Text UAT
notes are sufficient for Phase 1."

**Read-only guarantee statement pattern** (`examples/mdm_graph_dashboard/README.md` lines 9-12):
```markdown
## Read-only guarantee

This dashboard does not run sync, repair, migrate, load, or write actions.
`Refresh metrics` only clears cached read-only dashboard data and rereads the
current helper payloads.
```
Reuse this framing in `evidence/dashboard-security.md` to state DASH-03/D-27: the
dashboard is inspection-only and does not define acceptance.

**Secret-loading-without-printing pattern** (`examples/mdm_graph_dashboard/README.md` lines 28-37):
```bash
export MDM_DATABASE_URL="$(
  aws secretsmanager get-secret-value \
    --profile sec_platform_deployer \
    --region us-east-1 \
    --secret-id edgartools-dev/mdm/postgres_dsn \
    --query SecretString \
    --output text
)"
```
Reference this command pattern (without ever pasting output) as the secret-safe loading
convention evidence notes should describe operators using.

**Known cleanup item (must be classified, not silently inherited):** the current
`examples/mdm_graph_dashboard/README.md` still documents `NEO4J_URI`, `NEO4J_USER`,
`NEO4J_PASSWORD`, `NEO4J_DATABASE`, `NEO4J_SECRET_JSON`, and `check-connectivity --neo4j`
as active setup steps (lines 18-21, ~80-106) — these are the "stale `NEO4J_*`
assumptions" called out in CONTEXT.md canonical refs. Per D-02, this is an incomplete
upstream workstream item (`neo4j-snowflake` Phase 4 Task 1/2, `04-03-PLAN.md`) that
affects dashboard operator docs and therefore blocks go-live until merged/rechecked —
record as a `BLOCKED` matrix row, not as a passed item in `evidence/dashboard-security.md`.

---

## Shared Patterns

### Non-secret evidence header/disclaimer
**Source:** `.planning/workstreams/neo4j-snowflake/phases/03-hosted-graph-verification-and-e2e-cutover/03-LIVE-DEV-RUN.md` lines 1-10
**Apply to:** all four `evidence/*.md` files
```markdown
Date: <YYYY-MM-DD> UTC
Environment: <dev|prod>
<Relevant connection/profile labels>

This artifact captures non-secret evidence only. It omits passwords, tokens, DSNs,
full task logs, and raw Native App job logs.
```

### Command/Result/Summary block
**Source:** `03-LIVE-DEV-RUN.md` lines 12-21, 90-97
**Apply to:** all four `evidence/*.md` files
```markdown
\`\`\`bash
<exact command actually run>
\`\`\`

Result: <succeeded|failed>.

<bullet list or table of non-secret key counts/statuses>
```

### BLOCKED matrix row shape
**Source:** synthesized from `.planning/workstreams/go-live/REQUIREMENTS.md` traceability
table (lines 64-83) + `docs/aws-mdm-snowflake-postgres-cutover.md` hazard sections
(Symptom/Root cause/Fix)
**Apply to:** `01-LAUNCH-GATE-MATRIX.md`
```markdown
| Gate | Owner/Source | Required Fix | Required Rerun Proof | Status |
|---|---|---|---|---|
| Production AWS application manifest (`infra/aws-prod-application.json`) | AWS operator | Live discovery or successful prod deploy | Non-secret summary: file presence, state machine names, image refs | BLOCKED |
| Dashboard README `NEO4J_*` cleanup (neo4j-snowflake Phase 4 closeout) | dashboard reviewer / release owner | Land `04-03-PLAN.md` Task 1/2 | Re-check README for absence of `NEO4J_*` setup steps | BLOCKED |
| Stale `edgar-identity` secret ARN mitigation | AWS operator | Runbook requires `--edgar-identity-secret-arn` with freshly looked-up ARN before every deploy | Deploy dry-run shows explicit flag passed, no manifest fallback | BLOCKED |
| ECR cleanup-deletes-in-flight-digest mitigation | AWS operator | Runbook requires re-resolving digests immediately before deploy, after any cleanup step | Deploy dry-run shows fresh digest resolution step in sequence | BLOCKED |
```
Per D-06, no `WAIVED` status value exists — only `BLOCKED`, `PASS`, or `WARNING` (D-05
restricts `WARNING` to cleanup with no launch impact).

### Owner roles vocabulary
**Source:** CONTEXT.md D-29
**Apply to:** `01-LAUNCH-GATE-MATRIX.md` Owner/Source column and the Phase 1 data-issue
triage table (D-25)
```text
AWS operator | Snowflake operator | MDM operator | dashboard reviewer | release owner
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| Phase 1 data-issue triage table (D-25; likely embedded in `01-LAUNCH-GATE-MATRIX.md` or a sibling doc) | config (reference table) | batch | No existing per-layer triage table exists yet in this repo; closest precedent is the hazard/5-whys narrative format in `docs/aws-mdm-snowflake-postgres-cutover.md` and `TODOS.md`, but those are single-issue write-ups, not a symptom->layer->owner routing table. Planner should design the table structure fresh using the column set from D-25 (symptom, likely source, evidence to check, owner, blocker status, next action) and the owner vocabulary from D-29. |

## Metadata

**Analog search scope:**
- `.planning/workstreams/neo4j-snowflake/phases/03-hosted-graph-verification-and-e2e-cutover/`
- `.planning/workstreams/neo4j-snowflake/phases/04-dashboard-hosted-graph-migration/`
- `.planning/workstreams/go-live/` (PROJECT.md, REQUIREMENTS.md, ROADMAP.md, STATE.md)
- `TODOS.md`
- `docs/aws-mdm-snowflake-postgres-cutover.md`, `docs/aws-mdm-source-to-mdm.md`
- `examples/mdm_graph_dashboard/README.md`
- `infra/scripts/run-aws-mdm-e2e.sh`, `infra/scripts/deploy-aws-application.sh`, `infra/scripts/deploy-snowflake-stack.sh`
- `infra/aws-*-application.json` (presence check)

**Files scanned:** 12
**Pattern extraction date:** 2026-06-13
