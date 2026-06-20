# Phase 2: AWS And Snowflake Production Deployment Dry Run - Pattern Map

**Mapped:** 2026-06-14
**Files analyzed:** 5 edit targets (1 matrix file edited in place, 2 evidence files
appended, 1 terraform file temporarily edited+reverted, N new runbook docs)
**Analogs found:** 5 / 5 (all from Phase 1 in the same workstream)

This is a documentation/runbook phase. There is no application source code to pattern
match — every "pattern" below is a markdown structure, table format, or shell-command
idiom to replicate exactly from Phase 1's artifacts (the direct predecessor and primary
analog for everything Phase 2 produces).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|-----------------|----------------|
| `.planning/workstreams/go-live/phases/01-.../01-LAUNCH-GATE-MATRIX.md` (in-place row edits) | config/doc (matrix) | transform (BLOCKED row → documented/PASS row) | itself (Phase 1, rows 1-9) | exact |
| `.../01-.../evidence/aws.md` (append entries) | doc (evidence log) | event-driven (command-run → entry) | itself (Phase 1 structure) | exact |
| `.../01-.../evidence/snowflake.md` (append entries) | doc (evidence log) | event-driven (command-run → entry) | itself (Phase 1 structure) | exact |
| `.../02-.../runbook/aws-deploy.md` (new) | doc (runbook) | request-response (command + expected behavior) | `docs/runbook.md` Steps 7-8 + CLAUDE.md "Manual AWS build and deploy" | role-match |
| `.../02-.../runbook/snowflake-native-pull.md` (new) | doc (runbook) | request-response | `docs/runbook.md` dbt section + `infra/scripts/deploy-snowflake-stack.sh` flag shape | role-match |
| `.../02-.../runbook/dbt-gold.md` (new) | doc (runbook) | request-response | `docs/runbook.md` lines 420-512 (dbt prod commands, verbatim precedent) | exact |
| `infra/terraform/accounts/prod/versions.tf` (temporary edit+revert) | config (terraform) | transform (edit → plan → revert, zero net diff) | RESEARCH.md "Pattern 1" procedure (already fully specified) | exact |
| `infra/terraform/accounts/prod/override.tf` (temporary create+delete) | config (terraform) | transform (create → init/plan → delete) | RESEARCH.md "Pattern 1" procedure | exact |

## Pattern Assignments

### `01-LAUNCH-GATE-MATRIX.md` row edits (config/doc, transform)

**Analog:** `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md` lines 8-27 (the `## Gate Matrix` table itself)

**Table header + column format** (line 10-11):
```markdown
| Gate | Owner/Source | Required Fix | Required Rerun Proof | Status |
|---|---|---|---|---|
```

**Row format to follow exactly** — example of a row Phase 2 will touch (line 12,
the "AWS passive infrastructure outputs" row):
```markdown
| AWS passive infrastructure outputs | AWS operator | Confirm production Terraform outputs for buckets, ECS cluster, subnets, security group, KMS, ECR, log group, runner roles, and empty secret containers. | Non-secret output summary in [evidence/aws.md](evidence/aws.md): output names present, environment label, and account label only. | BLOCKED |
```

**How Phase 2 edits this row:** Per RESEARCH.md's matrix-row disposition table (row 1
disposition), this row stays a single-line table row but the `Required Fix` /
`Required Rerun Proof` / `Status` cells change. The pattern is:
- `Status` may move from `BLOCKED` to something like `BLOCKED (plan validated)` or a
  new intermediate label — **check CONTEXT.md/Phase 1 D-06 ("no waiver status")
  before inventing a new status value**. The matrix only formally defines `BLOCKED`
  and `PASS` (see row 27: `Evidence secret-safety scrub | release owner | ... | PASS`).
  If Phase 2 cannot fully resolve a row to `PASS`, keep `BLOCKED` and add the new
  evidence/required-fix detail in the cell text and in `evidence/aws.md` — do not
  invent a third status word without an explicit CONTEXT.md decision.
- `Required Fix` cell gets appended/refined text noting what Phase 2 discovered (e.g.,
  the `versions.tf` `~>` constraint bug as a "required fix" note for row 1).
- `Required Rerun Proof` cell keeps the same `[evidence/aws.md](evidence/aws.md)` /
  `[evidence/snowflake.md](evidence/snowflake.md)` relative-link format — **reuse this
  link syntax exactly**, it's a relative markdown link from the matrix file's directory
  to `evidence/<file>.md`.

**9 rows Phase 2 may touch** (rows 12, 13, 14, 15, 16, 17, 18, 19, 20 in the current
file — "AWS passive infrastructure outputs" through "`EDGARTOOLS_GOLD_STATUS` and
dynamic-table freshness"). Each row's current full text is already quoted in
01-LAUNCH-GATE-MATRIX.md lines 12-20 — edit these specific lines, do not rewrite the
table.

**Surrounding structural sections that may also need small additions** (same file):
- `## Blocker Classification Rules` (lines 29-38) — D-01 through D-08, referenced by
  number; Phase 2 should cite these (e.g., D-08 "rerun + non-secret pass summary") in
  new evidence entries rather than restating them.
- `## Dev Vs Prod Distinction` (lines 40-42) — the exact phrase `"dev precedent only —
  prod proof required separately"` is the required label string (used verbatim in both
  evidence files already — see below). Reuse this exact string for any dev-target dbt
  result Phase 2 records.
- `## Required Production Identifiers` (lines 64-76) — a checklist (`- [ ] ...` items).
  If Phase 2 resolves any of these (e.g., confirms the AWS account/profile identity
  per D-05), check the box (`- [x]`) and add a one-line note, following the existing
  unchecked-checkbox list format.

---

### `evidence/aws.md` entry additions (doc/evidence-log, event-driven)

**Analog:** `.planning/workstreams/go-live/phases/01-.../evidence/aws.md` (full file, 98 lines)

**File header format** (lines 1-8) — reuse verbatim header style (do not duplicate
the header in Phase 2's additions; append new sections under the existing header):
```markdown
# AWS Evidence - Phase 1 Production Readiness

Date: 2026-06-14 UTC
Environment: production required; dev rows are precedent only and require separate production proof.
AWS profile: production profile required; dev status check used `sec_platform_deployer`.
AWS account: production account label required; dev status check referenced the dev account only.

This artifact captures non-secret evidence only. It omits passwords, tokens, DSNs, full task logs, secret ARNs, and raw Native App job logs.
```
Phase 2 should add a new dated section (or update the `Date:`/`AWS profile:`/`AWS
account:` header lines if D-05's confirmed account identity — `077127448006`,
`cli-access` — changes the "production account label required" placeholder to an
actual value).

**"Read-Only Checks Actually Run" entry format** (lines 14-25) — THIS is the exact
shape for Phase 2's terraform-plan and ECR describe-images evidence:
```markdown
## Phase 1 Read-Only Checks Actually Run

\`\`\`bash
ls -l infra/aws-dev-application.json infra/aws-prod-application.json
\`\`\`

Result: failed for production manifest presence; succeeded for dev manifest presence.

- `infra/aws-dev-application.json`: present.
- `infra/aws-prod-application.json`: absent.
- Production app summary gate remains blocked until live discovery or a successful production deploy creates equivalent evidence.
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `Production AWS application manifest (infra/aws-prod-application.json)`.
```

Pattern to copy for Phase 2's `terraform plan` (Pattern 1) result:
1. A fenced ` ```bash ` block with the exact command(s) run.
2. A `Result: <succeeded|failed> ...` line summarizing pass/fail.
3. Bulleted non-secret facts (counts, names, presence/absence) — NEVER raw output.
4. If still blocked, a `BLOCKED - see \`01-LAUNCH-GATE-MATRIX.md\` row \`<exact row
   name>\`.` line using the exact row name string from the matrix table.

For the second checks block (lines 27-38), note the additional pattern of a labeled
sub-list "Non-secret dev manifest summary:" — Phase 2's terraform plan summary should
follow this shape:
```markdown
Non-secret <subject> summary:

- <fact 1>.
- <fact 2>.
- This is <dev precedent|plan-only> context. It is not production proof.
```

**"Not-Yet-Runnable Production Steps" list format** (lines 62-71) — bulleted list of
`BLOCKED - see \`01-LAUNCH-GATE-MATRIX.md\` row \`<row name>\`.` lines, one per
still-blocked matrix row, followed by a one-sentence caveat:
```markdown
## Not-Yet-Runnable Production Steps

- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `AWS passive infrastructure outputs`.
...
Planned production deploy commands and full E2E commands are not evidence entries here because they were not run during Phase 1.
```
Phase 2 should update this list — remove rows that move to documented/plan-validated
status (if any), keep the rest verbatim.

**"Dev Precedent Reconciliation" format** (lines 73-86) — required verbatim phrase
`dev precedent only — prod proof required separately` as a standalone line, followed
by a short paragraph and a "Production still requires:" bullet list. Reuse this exact
phrase for any Phase 2 dev-target result (D-03's dev dbt run, if executed).

**"Generated-JSON Summary Rule" format** (lines 88-98) — closing section listing
exactly what may be summarized (file presence, top-level keys, state-machine name
list, image-ref format, sanitized paths) and the rule "Do not paste the JSON body."
Reuse this section's structure if Phase 2 adds any new generated-artifact summary
rules (e.g., for `terraform plan` output or ECR `describe-images` JSON — see
RESEARCH.md Anti-Patterns).

---

### `evidence/snowflake.md` entry additions (doc/evidence-log, event-driven)

**Analog:** `.planning/workstreams/go-live/phases/01-.../evidence/snowflake.md` (full file, 88 lines)

Same overall structure as `evidence/aws.md` — header, "Phase 1 Read-Only Checks
Actually Run", "Not-Yet-Runnable Production Steps", "Dev Precedent Reconciliation",
closing summary-rule section. Two additional sections specific to this file are
directly reusable analogs:

**"Known Grant Gap" section format** (lines 55-61) — directly reusable for matrix row
7 (Snowflake deployer direct grants):
```markdown
## Known Grant Gap

`TODOS.md` records that `EDGARTOOLS_DEV_DEPLOYER` lacked direct `SELECT` on `EDGARTOOLS_SOURCE`, which blocked `dbt run --full-refresh` for any gold dynamic table until an ad-hoc dev grant was applied. If `EDGARTOOLS_PROD_DEPLOYER` has the analogous direct-grant gap, production dynamic-table refresh can fail even when ad-hoc queries work through secondary roles.

This is recorded as a matrix blocker, not a pass:

- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `Snowflake deployer direct grants for gold dynamic tables`.
```
Phase 2 should add the documented `SHOW GRANTS TO ROLE EDGARTOOLS_PROD_DEPLOYER;`
check command (RESEARCH.md row 7 disposition) as a "required-fix command" sub-bullet
under this same section, following the same "recorded as a matrix blocker, not a
pass" framing if it cannot be run live.

**"Gold Status And Freshness Summary Shape" table format** (lines 77-84) — THE exact
table header Phase 2's evidence/snowflake.md must reuse for any dev-precedent or
future prod freshness result:
```markdown
## Gold Status And Freshness Summary Shape

To be filled only after production checks actually run:

| Model/Table | Status | Last refresh |
| --- | --- | --- |
| `EDGARTOOLS_GOLD_STATUS` | pending production proof | pending production proof |
| dynamic tables | pending production proof | pending production proof |
```
If D-03's dev-precedent dbt run executes successfully and the gold status query is
run against dev (per RESEARCH.md Open Question 2's "dev-precedent freshness sample"
option), Phase 2 should add a SECOND table with this same header but labeled
`(dev-precedent)`, e.g.:
```markdown
| Model/Table | Status | Last refresh (dev-precedent) |
| --- | --- | --- |
| `EDGARTOOLS_GOLD_STATUS` | <value> | <value> |
```

---

### New runbook docs (`runbook/aws-deploy.md`, `runbook/snowflake-native-pull.md`, `runbook/dbt-gold.md`) (doc, request-response)

**Analog 1 — command block formatting:** `CLAUDE.md` "Manual AWS build and deploy —
complete recipe (macOS Colima)" section. Pattern: numbered steps (`# 1. ...`, `# 2.
...`), each step is a fenced ` ```bash ` block with inline `#` comments explaining
*why*, followed by a "NOTE:"/"If X fails" callout in plain text immediately after the
block when there's a known gotcha. Phase 2's `aws-deploy.md` should mirror this
numbered-step-with-comments style for the image-promotion + deploy sequence (Pattern
2/3 from RESEARCH.md), e.g.:

```markdown
# 1. Resolve current :dev image digests (read-only, registry API).
\`\`\`bash
WAREHOUSE_DEV_DIGEST=$(aws ecr describe-images --region us-east-1 \
  --repository-name edgartools-dev-warehouse \
  --image-ids imageTag=dev \
  --query 'imageDetails[0].imageDigest' --output text)
\`\`\`

# 2. Re-tag as :prod within the same repo (state-changing — operator-executed at cutover, not during Phase 2).
\`\`\`bash
...
\`\`\`
```

**Analog 2 — prod placeholder env-var blocks:** `CLAUDE.md` "Required env vars for
`dbt run`/`dbt compile` against Snowflake" block and `docs/runbook.md` lines 426-441
(`export DBT_SNOWFLAKE_ACCOUNT="ORGNAME-ACCOUNTNAME"` etc.) — use this exact
`export VAR="<placeholder-description>"` style for all prod-target placeholder
commands (D-04). RESEARCH.md's "Pattern 4" block already has the full content ready to
drop into `runbook/dbt-gold.md` verbatim (both the dev-precedent block and the
prod-target placeholder block).

**Analog 3 — known-issue/gotcha framing:** `CLAUDE.md` "Known gap blocking
`--full-refresh` (dev, as of 2026-06-13)" paragraph — bold lead-in sentence stating the
gap, then a paragraph explaining root cause, then a pointer to `TODOS.md`. Use this
exact framing for documenting Pitfall 2 (SNOW-01 `backend.hcl` die) and Pitfall 4
(`dbt compile` needs live creds) in `runbook/snowflake-native-pull.md` and
`runbook/dbt-gold.md` respectively — RESEARCH.md's Pitfall sections already contain
this prose, ready to be lightly adapted.

**Analog 4 — `docs/runbook.md` dbt section (lines 420-512)**: exact prod env-var
names (`DBT_SNOWFLAKE_ACCOUNT`, `DBT_SNOWFLAKE_USER`, `DBT_SNOWFLAKE_PASSWORD`,
`DBT_SNOWFLAKE_ROLE`, `DBT_SNOWFLAKE_DATABASE`, `DBT_SNOWFLAKE_WAREHOUSE`), the `dbt
deps && dbt run --target prod && dbt test --target prod` sequence, the "creates 10
objects" object-list, the `TARGET_LAG = DOWNSTREAM` note, and the final gold-status
verification query — all directly reusable verbatim in `runbook/dbt-gold.md`'s
prod-target section.

---

### Pattern 1: Terraform `versions.tf` temporary edit + `override.tf` + revert (the one executable task)

**Analog:** RESEARCH.md "Architecture Patterns → Pattern 1" (lines 227-285) — this is
already a complete, copy-paste-ready procedure. No further searching needed; this is
the literal script to execute. Key exact values confirmed live in
`infra/terraform/accounts/prod/versions.tf` (read this session, lines 1-14):

```hcl
terraform {
  required_version = "~> 1.14.7"   # <- this line, change to ">= 1.14.7" temporarily

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.39.0"          # <- do NOT touch this, exact pin unaffected
    }
  }

  backend "s3" {
    use_lockfile = true
  }
}
```

**Exact procedure to follow (from RESEARCH.md, verified working this session):**
```bash
cd infra/terraform/accounts/prod

# 1. Temporary edit: "~> 1.14.7" -> ">= 1.14.7" in versions.tf (do NOT commit)

# 2. Add local-backend override (NOT committed)
cat > override.tf <<'EOF'
terraform {
  backend "local" {
    path = "/tmp/edgartools-prod-plan/terraform.tfstate"
  }
}
EOF

# 3. Init and plan
terraform init -input=false -no-color
terraform plan -input=false -no-color

# 4. Revert everything
git checkout -- versions.tf
rm -rf override.tf .terraform .terraform.lock.hcl terraform.tfstate* /tmp/edgartools-prod-plan
git status --short   # MUST be clean
```

Expected/previously-observed result: `Plan: 37 to add, 0 to change, 0 to destroy`
against real account `077127448006`. Record ONLY the resource count + output-name
list (from `outputs.tf`) in `evidence/aws.md`, per the Generated-JSON Summary Rule
analog above — never paste the full plan body.

**Verification that the revert worked** — use the same `git status --short` check
already shown in the procedure; this doubles as the "no source edits left behind"
proof for Phase 2's read-only constraint.

## Shared Patterns

### "BLOCKED row reference" string format
**Source:** `evidence/aws.md` lines 64-69, `evidence/snowflake.md` lines 47-51
**Apply to:** Any evidence-file bullet that still points at a BLOCKED matrix row
```markdown
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `<exact row name copied verbatim from the Gate column>`.
```
The row name string must match the `Gate` column cell text in
`01-LAUNCH-GATE-MATRIX.md` EXACTLY (including parentheses/backticks inside the name,
e.g. `` `AWS active application deploy (infra/scripts/deploy-aws-application.sh)` ``).

### "dev precedent only" label
**Source:** `01-LAUNCH-GATE-MATRIX.md` line 42 (`## Dev Vs Prod Distinction`),
reused verbatim in both evidence files (`evidence/aws.md` line 75,
`evidence/snowflake.md` line 65)
**Apply to:** Any D-03 dev-target dbt result Phase 2 records
```markdown
dev precedent only — prod proof required separately
```
Use this exact phrase as a standalone line before the dev-result paragraph.

### Secret-safety / generated-output summarization rule
**Source:** `evidence/aws.md` lines 88-98 ("Generated-JSON Summary Rule"),
`evidence/snowflake.md` lines 86-88
**Apply to:** `terraform plan` output, `aws ecr describe-images` JSON, dbt compiled
SQL, any `infra/aws-*-application.json` reference
```markdown
Any generated <X> artifact referenced by go-live evidence must be summarized only as
path, existence, top-level purpose/key list, count, and pass/fail result. Do not paste
raw logs, compiled SQL containing sensitive values, Terraform state, or full generated
JSON bodies.
```

### Command-evidence block structure (D-10)
**Source:** `evidence/aws.md` lines 16-25, 27-38; `evidence/snowflake.md` lines 16-30
**Apply to:** Every new evidence entry Phase 2 adds
```markdown
\`\`\`bash
<exact command>
\`\`\`

Result: <succeeded|failed> <one-line summary>.

- <non-secret fact 1>.
- <non-secret fact 2>.
- <BLOCKED reference OR "context only, not production proof" caveat, if applicable>.
```

## No Analog Found

None — Phase 1's matrix and evidence files, plus `docs/runbook.md` and `CLAUDE.md`,
together cover every file/edit Phase 2 needs to produce. RESEARCH.md's Pattern 1-4
blocks are themselves already-drafted content ready for direct reuse in the new
runbook docs.

## Metadata

**Analog search scope:**
- `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/` (01-LAUNCH-GATE-MATRIX.md, 01-CONTEXT.md, evidence/aws.md, evidence/snowflake.md)
- `docs/runbook.md` (dbt/Snowflake/dashboard sections, lines 420-520)
- `CLAUDE.md` (Image management, dbt smoke-test, manual AWS build-and-deploy sections)
- `infra/terraform/accounts/prod/versions.tf` (live-read to confirm exact current constraint string)
- `.planning/workstreams/go-live/phases/02-.../02-RESEARCH.md` (Architecture Patterns Pattern 1-4, already contain ready-to-use command blocks)

**Files scanned:** 6
**Pattern extraction date:** 2026-06-14
