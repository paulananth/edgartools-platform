# Phase 3: MDM Hosted Graph E2E Acceptance - Pattern Map

**Mapped:** 2026-06-15
**Files analyzed:** 3 (2 new, 1 modified)
**Analogs found:** 3 / 3

This is an operational-acceptance phase. There is no application source code
to write — all "files" are planning/evidence/runbook Markdown documents. The
patterns below are document-structure, table-format, and masking conventions
extracted from Phase 1's evidence template and Phase 2's runbook/evidence
files, which the planner should reuse verbatim for Phase 3's new docs.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `.planning/workstreams/go-live/phases/03-mdm-hosted-graph-e2e-acceptance/evidence/mdm-hosted-graph.md` | evidence doc | batch (live CLI/script run capture) | `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/mdm-hosted-graph.md` (structure/template) + `.../evidence/aws.md` "Phase 2 Read-Only Checks Actually Run" section (precedent for how a later phase appends a new dated run-log section) | exact |
| `.planning/workstreams/go-live/phases/03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md` | runbook doc | batch (documentation-only command reference) | `.planning/workstreams/go-live/phases/02-aws-and-snowflake-production-deployment-dry-run/runbook/aws-deploy.md` | exact |
| `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md` | launch gate matrix (table update) | transform (row-level status/evidence-link edits) | same file, Phase 2's edits to rows 12-21 + "Required Production Identifiers" checklist (see `02-VALIDATION.md`/`02-VERIFICATION.md` for what Phase 2 actually changed — rows for MDM/hosted-graph, rows 22-25, are the Phase 3 targets) | exact |

## Pattern Assignments

### `evidence/mdm-hosted-graph.md` (evidence doc, batch run capture)

**Analog:** `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/mdm-hosted-graph.md` (full file, 107 lines — already read in full)

**Header/front-matter pattern** (lines 1-9):
```markdown
# MDM + Hosted Graph Evidence - Phase 1 Production Readiness

Date: 2026-06-14 UTC
Environment: production required; dev rows are precedent only and require separate production proof.
Snowflake connection: production connection required.
Snowflake database: production database required.
AWS profile: production profile required.

This artifact captures non-secret evidence only. It omits passwords, tokens, DSNs, full task logs, and raw Native App job logs.
```
For Phase 3, the new section(s) appended to this file should open with a
dated sub-header analogous to how `evidence/aws.md` and `evidence/snowflake.md`
added `## Phase 2 Read-Only Checks Actually Run` as a NEW top-level section
appended below the existing Phase 1 content — i.e. Phase 3 should add
`## Phase 3 Live Checks Actually Run` (or similarly named) rather than
rewriting Phase 1's sections. Each command block should restate environment
label (`dev` / `prod`), connection, database, and AWS profile inline, since
the file-level header only states "production required."

**"Read-Only Checks Actually Run" command-block + result pattern** (lines 20-44):
```markdown
## Phase 1 Read-Only Checks Actually Run

\```bash
bash infra/scripts/run-aws-mdm-e2e.sh \
  --env dev \
  --aws-profile sec_platform_deployer \
  --status-only
\```

Result: succeeded.

Relevant non-secret dev Step Functions status:

| Workflow | Latest status | Latest execution name |
| --- | --- | --- |
| `mdm_migrate` | `SUCCEEDED` | `aws-mdm-e2e-1781277675-migrate` |
| `mdm_run` | `SUCCEEDED` | `aws-mdm-e2e-1781277675-run` |
| `mdm_backfill_relationships` | `SUCCEEDED` | `aws-mdm-e2e-1781277675-backfill` |
| `mdm_sync_graph` | `SUCCEEDED` | `aws-mdm-e2e-1781277675-sync` |
| `mdm_verify_graph` | `SUCCEEDED` | `aws-mdm-e2e-1781277675-verify` |
| `mdm_counts` | `SUCCEEDED` | `aws-mdm-e2e-1781277675-counts` |
```
For Phase 3's D-09 dev rehearsal (fresh full E2E run), the planner should
add a `Started` column like the richer table in `03-LIVE-DEV-RUN.md` (see
below) since this is a fresh run with new timestamps, not just a status
check.

**`BLOCKED`-row cross-reference pattern** (lines 14-19, 98-106):
```markdown
For Phase 1, that strict production run is not recorded as a pass. It remains a matrix blocker:

- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `Strict edgar-warehouse mdm verify-graph`.
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `AWS MDM hosted graph E2E`.

...

## Not-Yet-Runnable Production Steps

- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `MDM Snowflake Postgres secret container and connectivity`.
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `edgar-warehouse mdm sync-graph hosted graph materialization`.
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `Strict edgar-warehouse mdm verify-graph`.
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `AWS MDM hosted graph E2E`.
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `Snowflake native S3 pull stack (infra/scripts/deploy-snowflake-stack.sh)`.

These planned production commands are not evidence entries because they were not run during Phase 1.
```
Phase 3's D-02 prod `--status-only` reproduction is exactly this pattern: a
new dated section documenting a command that fails with rc=1 before any AWS
call, with a `BLOCKED -- see 01-LAUNCH-GATE-MATRIX.md row ...` line pointing
at the MDM/hosted-graph rows. The MDM/hosted-graph rows themselves stay
`BLOCKED` per the "Dev Vs Prod Distinction" rule even after Phase 3's dev
rehearsal — only the dev-precedent text and runbook links change.

**Verify-Graph non-secret payload summary pattern** (lines 46-77 of Phase 1
template, fully realized in `03-LIVE-DEV-RUN.md` lines 133-156 and 52-77 —
already read in full):
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
  - `app_user_role_grant`: `ok`
  - `app_admin_role_grant`: `ok`
  - `database_role_to_application`: `ok`
  - `database_role_privileges`: `ok`
  - `compute_pool`: `ok` (`7` rows)
  - `graph_schema_sample`: `ok`
  - `graph_info`: `ok`
  - `bfs`: `ok`
  - `wcc`: `ok`
- `phase3_acceptance`: `true`
```
The Phase 1 template's version of this block (lines 46-71) uses
`pending production proof` placeholders for every field plus a relationship
parity table shape:
```markdown
Relationship parity table shape:

| Relationship type | MDM active | Snowflake graph | Delta |
| --- | ---: | ---: | ---: |
| pending production proof | pending production proof | pending production proof | pending production proof |
```
Per D-04, Phase 3 does NOT re-run `verify-graph` as a standalone
GRAPH-01/GRAPH-02 proof and instead **cites** `03-LIVE-DEV-RUN.md`'s
already-filled values (the "Dev Precedent Reconciliation" section of the
Phase 1 template, lines 79-96, already has these numbers — 15 nodes / 4
edges / `phase3_acceptance: true`). However, the D-09 fresh dev rehearsal
WILL run `mdm verify-graph` again as both the local preflight AND the
`mdm_verify_graph` AWS stage — so the planner should add a NEW payload-summary
block (same shape as above) with the rehearsal's own fresh numbers, clearly
labeled as "D-09 rehearsal payload (incidental to GRAPH-01/GRAPH-02, not a
re-proof)" to avoid confusion with the cited D-04 precedent.

**"Dev Precedent Reconciliation" pattern** (lines 79-96):
```markdown
## Dev Precedent Reconciliation

dev precedent only — prod proof required separately

The dev hosted graph evidence from `03-LIVE-DEV-RUN.md` shows:

- strict local `edgar-warehouse mdm verify-graph` eventually succeeded in dev,
- Snowflake graph nodes: `15`,
- Snowflake graph edges: `4`,
- node parity status: `ok`,
...
- dev `phase3_acceptance`: `true`,
- latest dev AWS MDM hosted graph E2E reached `mdm_migrate`, `mdm_run`, `mdm_backfill_relationships`, `mdm_sync_graph`, `mdm_verify_graph`, and `mdm_counts` with `SUCCEEDED` status.

Production still requires production Snowflake connection/database, production Native App app and compute-pool selector, production strict verify-graph proof, and production AWS MDM E2E proof.
```
This phrase "dev precedent only — prod proof required separately" is the
exact "Dev Vs Prod Distinction" boilerplate (see Shared Patterns below) and
must be reused verbatim on every dev-sourced evidence block in Phase 3.

---

### `runbook/mdm-secrets.md` (runbook doc, documentation-only)

**Analog:** `.planning/workstreams/go-live/phases/02-aws-and-snowflake-production-deployment-dry-run/runbook/aws-deploy.md` (full file, 283 lines — already read in full)

**Header pattern** (lines 1-15):
```markdown
# AWS Production Deploy Runbook

This runbook documents the production AWS active-application deploy
(`infra/scripts/deploy-aws-application.sh --env prod`) and the ECR
image-promotion procedure (D-05/D-06). It is non-secret: every value below is
a placeholder, a `<DIGEST>` slot, or a freshly-resolved-at-runtime expression.
No ARNs, secret values, account locators with embedded secrets, or compiled
output are included.

Per D-05, `aws-admin-dev` and `aws-admin-prod` resolve to the SAME AWS account
(`077127448006`, IAM user `cli-access`). "Prod" is a same-account,
prefix-distinguished resource set ...
```
For `runbook/mdm-secrets.md`, open with an equivalent non-secret disclaimer:
this runbook documents `aws secretsmanager put-secret-value` commands for
`edgartools-prod/mdm/postgres_dsn` and `edgartools-prod/mdm/snowflake`
(D-05/D-06), every value is a `<PLACEHOLDER>`, and no real secret values, ARNs,
or `put-secret-value` output are pasted (per D-08 / Pitfall in RESEARCH.md
"snowflake secret" command note about not pasting output).

**Numbered-step command block with inline comments** (lines 26-71, the
ECR digest-resolution + re-tag steps — representative of the "numbered
sequential commands with `# N. <description>` comments" convention):
```bash
# 1. Resolve current :dev image digests — read-only, no docker pull needed.
export ECR="077127448006.dkr.ecr.us-east-1.amazonaws.com"

WAREHOUSE_DEV_DIGEST=$(aws ecr describe-images --region us-east-1 \
  --repository-name edgartools-dev-warehouse \
  --image-ids imageTag=dev \
  --query 'imageDetails[0].imageDigest' --output text)
```
Apply this same `# N. <description>` numbering convention to the
`postgres_dsn` and `snowflake` secret-population command blocks from
RESEARCH.md's "MDM Secret Population Runbook (D-05-D-08)" section.

**"Required secret names" list pattern** (lines 132-147):
```markdown
### `--enable-mdm` required secret names

`--enable-mdm` requires all four MDM Secrets Manager secret ARNs to resolve
(via `${NAME_PREFIX}/mdm/<name>` lookup, where `NAME_PREFIX=edgartools-prod`),
or the script hard-fails with `--enable-mdm requires MDM secret ARNs; missing: ...`.
The four required secret names (names only — Terraform creates these as empty
containers; Phase 3/MDM-01 populates values):

- `edgartools-prod/mdm/postgres_dsn`
- `edgartools-prod/mdm/neo4j`
- `edgartools-prod/mdm/api_keys`
- `edgartools-prod/mdm/snowflake`

These four names are recorded as required-identifier `BLOCKED` items in
`evidence/aws.md` ("Required MDM Secret Names") and in
`01-LAUNCH-GATE-MATRIX.md` `## Required Production Identifiers`.
```
This is the exact precedent that names Phase 3's `postgres_dsn` and
`snowflake` secrets as "Phase 3/MDM-01 populates values" — `mdm-secrets.md`
is that population runbook. Follow the same "names only, no ARNs" framing,
but for Phase 3 only `postgres_dsn` and `snowflake` get population command
blocks (D-06); `neo4j` and `api_keys` get a one-line annotation each
(legacy/N/A and deferred respectively), not full commands.

**Full command + placeholder convention** — use RESEARCH.md's
"MDM Secret Population Runbook (D-05-D-08)" section verbatim as the
content source (it is already written in this exact runbook style):

```bash
# postgres_dsn — full command with placeholders (existing validated helper)
printf '%s' "postgresql://<APPLICATION_ROLE_USER>:<APPLICATION_ROLE_PASSWORD>@<PROD_SNOWFLAKE_POSTGRES_HOST>.snowflake.app:5432/mdm?sslmode=require" | \
  bash infra/scripts/bootstrap-aws-mdm-secrets.sh \
    --env prod \
    --aws-profile aws-admin-prod \
    --aws-region us-east-1 \
    --dsn-stdin
# Writes to: edgartools-prod/mdm/postgres_dsn
# --dry-run flag available to validate without writing.
```

```bash
# snowflake secret — full command with placeholders (no existing helper; raw put-secret-value)
aws secretsmanager put-secret-value \
  --profile aws-admin-prod \
  --region us-east-1 \
  --secret-id edgartools-prod/mdm/snowflake \
  --secret-string '{
    "MDM_SNOWFLAKE_ACCOUNT": "<ORGNAME-ACCOUNTNAME>",
    "MDM_SNOWFLAKE_USER": "<PROD_MDM_SNOWFLAKE_USER>",
    "MDM_SNOWFLAKE_PASSWORD": "<PROD_MDM_SNOWFLAKE_PASSWORD>",
    "MDM_SNOWFLAKE_DATABASE": "<EDGARTOOLS_PROD>",
    "MDM_SNOWFLAKE_WAREHOUSE": "<EDGARTOOLS_PROD_REFRESH_WH>",
    "MDM_SNOWFLAKE_SCHEMA": "EDGARTOOLS_GOLD",
    "MDM_SNOWFLAKE_ROLE": "<EDGARTOOLS_PROD_DEPLOYER>"
  }'
# Output text only — do NOT paste this output into evidence (contains ARN/VersionId).
```

**`bootstrap-aws-mdm-secrets.sh` confirmed flag inventory** (from
`infra/scripts/bootstrap-aws-mdm-secrets.sh` usage text, lines 9-35):
```
--env <dev|prod>              Environment. Required.
--aws-profile <profile>       AWS CLI profile. Default: AWS_PROFILE env var or instance role.
--aws-region <region>         AWS region. Default: us-east-1.
--name-prefix <prefix>        Resource prefix. Default: edgartools-<env>.
--secret-id <id-or-arn>       Secret to write. Default: <name-prefix>/mdm/postgres_dsn.
--dsn <dsn>                   Full PostgreSQL DSN. Prefer --dsn-stdin for credentials.
--dsn-stdin                   Read the full PostgreSQL DSN from stdin.
--host <host>                 Snowflake Postgres host when constructing a DSN.
--port <port>                 PostgreSQL port. Default: 5432.
--database <name>             PostgreSQL database. Default: mdm.
--username <user>             Snowflake Postgres application role/user.
--password-stdin              Read the application password from stdin when constructing a DSN.
--expected-host-suffix <suf>  Required host suffix. Default: .snowflake.app.
--dry-run                     Validate and print the masked DSN without writing.
```

**DSN shape reference convention (D-07)** — masking pattern to follow
(structure only, no values), modeled on the "Generated-JSON Summary Rule"
masking discipline used throughout Phase 1/2 evidence:
```
postgresql://<user>:<password>@<host>.snowflake.app:<port>/<database>?sslmode=require
```
The dev MDM Postgres DSN re-verified live in D-03 should be presented in this
same `<user>:<password>@<host>...` placeholder form — never the real dev DSN
— with a one-line note that the prod secret must satisfy the same
`<host>.snowflake.app` / `database=mdm` / `sslmode=require` invariants
enforced by `audit-mdm-snowflake-postgres-cutover.py`'s
`validate_snowflake_postgres_dsn()`.

**`describe-secret` presence-check pattern (D-08)**:
```bash
aws secretsmanager describe-secret \
  --profile aws-admin-prod --region us-east-1 \
  --secret-id edgartools-prod/mdm/postgres_dsn \
  --query '{Name:Name,ARN:ARN,LastChangedDate:LastChangedDate,VersionIdsToStages:VersionIdsToStages}'
```
A populated secret has a non-empty `VersionIdsToStages` entry with stage
`AWSCURRENT`; an empty/never-populated Terraform-created container does not.
This command's OUTPUT (the JSON describe-secret result, which contains no
secret values) is safe to paste into `evidence/mdm-hosted-graph.md` — unlike
`put-secret-value` output, which must not be pasted.

**References section pattern** (lines 270-283, closing "References" list
citing source files read):
```markdown
## References

- `infra/scripts/deploy-aws-application.sh` — read in full for flag inventory,
  resolution order, and hard-fail identifiers (Phase 2 research session).
- ...
- `01-LAUNCH-GATE-MATRIX.md` rows "AWS passive infrastructure outputs", ...
- `evidence/aws.md` — Phase 2 Pattern 1 terraform-plan evidence and
  image-digest-format capture.
```
`runbook/mdm-secrets.md` should close with an analogous References section
citing `infra/scripts/bootstrap-aws-mdm-secrets.sh`,
`infra/scripts/audit-mdm-snowflake-postgres-cutover.py`,
`infra/terraform/modules/warehouse_runtime/main.tf` (secret resource
definitions), `edgar_warehouse/mdm/export.py` (`_snowflake_setting` key
resolution), and `01-LAUNCH-GATE-MATRIX.md` row "MDM Snowflake Postgres secret
container and connectivity".

---

### `01-LAUNCH-GATE-MATRIX.md` (matrix update, row edits)

**Analog:** the same file's own rows 22-25 (current state, already read in
full — 108 lines) — Phase 3 edits these rows in place, following the exact
column structure already established.

**Current row structure to preserve** (columns: `Gate | Owner/Source |
Required Fix | Required Rerun Proof | Status`), e.g. row 22:
```markdown
| MDM Snowflake Postgres secret container and connectivity | MDM operator | Confirm production MDM DSN secret name exists and runtime connectivity/migration/counts checks pass without printing the DSN. | [evidence/mdm-hosted-graph.md](evidence/mdm-hosted-graph.md) records exact commands, pass/fail, and counts only. | BLOCKED |
```
Phase 3 should update the **"Required Fix"** cell to point to the new
`runbook/mdm-secrets.md` (relative path:
`../03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md`, following the
same cross-phase relative-link convention Phase 1 used for Phase 2's
`runbook/aws-deploy.md` at
`../02-aws-and-snowflake-production-deployment-dry-run/runbook/aws-deploy.md`),
and the **"Required Rerun Proof"** cell to reference the new evidence
sections in `evidence/mdm-hosted-graph.md`. The **Status** column stays
`BLOCKED` for all four MDM/hosted-graph rows (22-25) per the "Dev Vs Prod
Distinction" rule (line 41-43) — Phase 3 dev rehearsal evidence does not
flip these to `PASS`.

**Cross-phase relative link convention** (already used in row 13, 18, 20-21):
```markdown
[runbook/aws-deploy.md](../02-aws-and-snowflake-production-deployment-dry-run/runbook/aws-deploy.md)
[evidence/snowflake.md](evidence/snowflake.md)
```
Note the asymmetry: links to files WITHIN the Phase 1 directory (where the
matrix lives) are relative (`evidence/...`), while links to files in OTHER
phase directories use `../<phase-dir>/...`. Phase 3's new
`evidence/mdm-hosted-graph.md` and `runbook/mdm-secrets.md` live in the
**Phase 3** directory, so links from `01-LAUNCH-GATE-MATRIX.md` (in the Phase
1 directory) to them must use
`../03-mdm-hosted-graph-e2e-acceptance/evidence/mdm-hosted-graph.md` and
`../03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md` — NOT the bare
`evidence/mdm-hosted-graph.md` relative link currently in rows 22-25 (which
points at Phase 1's own `evidence/mdm-hosted-graph.md`). The planner must
decide whether Phase 3 evidence is appended to the EXISTING
`01-.../evidence/mdm-hosted-graph.md` (mirroring how Phase 2 appended
sections to `01-.../evidence/aws.md` and `01-.../evidence/snowflake.md` in
place — see Shared Patterns) or written to a NEW
`03-.../evidence/mdm-hosted-graph.md` (per this phase's stated file list).
**If the planner follows the Phase 2 precedent** (append to the existing
Phase 1 evidence file in place), the matrix row links do NOT need to change
at all — only the row content/status text changes. **If a new
`03-.../evidence/mdm-hosted-graph.md` is created instead**, the matrix row
links must be updated to the cross-phase `../03-.../evidence/...` form. This
is the single most important structural decision for the planner — flag it
explicitly in the plan.

**"Required Production Identifiers" checkbox pattern** (lines 77-82):
```markdown
- [ ] MDM Secrets Manager secret names for Postgres DSN, API keys, Snowflake settings, and any legacy/empty graph containers by name only:
  - [ ] `edgartools-prod/mdm/postgres_dsn`
  - [ ] `edgartools-prod/mdm/neo4j`
  - [ ] `edgartools-prod/mdm/api_keys`
  - [ ] `edgartools-prod/mdm/snowflake`
```
Per RESEARCH.md "Launch Gate Matrix Integration", Phase 3 updates this list
with annotations (not checkmarks, since population itself is not done):
`edgartools-prod/mdm/postgres_dsn` and `.../snowflake` stay `[ ]` with a note
"population runbook documented in `runbook/mdm-secrets.md`, not yet executed
against real prod values"; `edgartools-prod/mdm/neo4j` gets annotated
"not required / legacy" (D-06); `edgartools-prod/mdm/api_keys` gets annotated
"deferred, consumer unclear" (D-06).

## Shared Patterns

### "Dev Vs Prod Distinction" boilerplate
**Source:** `01-LAUNCH-GATE-MATRIX.md` lines 41-43 (rule definition);
applied verbatim in `evidence/mdm-hosted-graph.md` lines 79-96 and
`evidence/snowflake.md` lines 80-93, 153.
**Apply to:** every evidence block in Phase 3 that cites dev-only results
(D-03 dev Postgres re-verify, D-04 cited `03-LIVE-DEV-RUN.md` precedent, D-09
dev rehearsal).
```markdown
dev precedent only — prod proof required separately
```
Every such block must end with a sentence enumerating what production still
requires (mirroring the "Production still requires: ..." bullet lists in
`evidence/aws.md` lines 80-87 and `evidence/snowflake.md` lines 86-92).

### Non-secret evidence disclaimer
**Source:** every Phase 1/2 evidence file's second paragraph, e.g.
`evidence/mdm-hosted-graph.md` line 9:
```markdown
This artifact captures non-secret evidence only. It omits passwords, tokens, DSNs, full task logs, and raw Native App job logs.
```
**Apply to:** the header of any new Phase 3 evidence/runbook section.

### "Result: succeeded/failed" + structured summary, never raw logs
**Source:** pervasive in `evidence/aws.md`, `evidence/snowflake.md`,
`evidence/mdm-hosted-graph.md`, `03-LIVE-DEV-RUN.md` — every command block is
followed by `Result: succeeded.` or `Result: failed (...).` and then a
bulleted/tabular non-secret summary, never a pasted raw log.
**Apply to:** all five Phase 3 evidence categories (dev rehearsal, prod
`--status-only` repro, dev Postgres re-verify, GRAPH precedent citation,
secret presence checks).

### `BLOCKED -- see 01-LAUNCH-GATE-MATRIX.md row '<exact row name>'.` cross-reference
**Source:** `evidence/mdm-hosted-graph.md` lines 17-18, 100-104;
`evidence/aws.md` lines 25, 64-70; `evidence/snowflake.md` lines 47-51.
**Apply to:** every Phase 3 evidence section that documents a still-BLOCKED
prod item (the D-02 prod `--status-only` reproduction, the unpopulated
`postgres_dsn`/`snowflake` secrets).
Row names must match the matrix EXACTLY (e.g. `MDM Snowflake Postgres secret
container and connectivity`, not an abbreviation).

### Secret-loading-without-printing convention
**Source:** `01-LAUNCH-GATE-MATRIX.md` "Secret-Safety Rules" (line 57):
```markdown
Secrets may be loaded into runtime environment variables with `aws secretsmanager get-secret-value ... --query SecretString --output text`, but the value must never be printed, pasted, logged, or committed.
```
**Apply to:** D-03's dev MDM Postgres re-verification — `MDM_DATABASE_URL` is
exported from Secrets Manager but never echoed; mask any host display with
`sed 's/:[^:@]*@/:***@/'` per RESEARCH.md's Security Domain section.

## No Analog Found

None. All three Phase 3 files have exact-match analogs from Phase 1/2 — this
is a documentation-pattern-replication phase, not a new-pattern phase.

## Metadata

**Analog search scope:**
- `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/` (full: `01-LAUNCH-GATE-MATRIX.md`, `evidence/*.md`)
- `.planning/workstreams/go-live/phases/02-aws-and-snowflake-production-deployment-dry-run/` (full: `runbook/*.md`)
- `.planning/workstreams/neo4j-snowflake/phases/03-hosted-graph-verification-and-e2e-cutover/03-LIVE-DEV-RUN.md` (full, 208 lines)
- `infra/scripts/bootstrap-aws-mdm-secrets.sh` (usage text, lines 9-35)

**Files scanned:** 8 (all read in full or near-full; no re-reads of
overlapping ranges)

**Pattern extraction date:** 2026-06-15
