# Phase 6: Production AWS Infrastructure And Application Deploy - Pattern Map

**Mapped:** 2026-06-19
**Files analyzed:** 5
**Analogs found:** 5 / 5

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `infra/terraform/accounts/prod/versions.tf` | config (Terraform version pin) | batch (one-time apply) | `infra/terraform/accounts/dev/versions.tf` | exact (same file, sibling account, already has the correct constraint) |
| `infra/terraform/accounts/prod/backend.hcl` (new, from `.example`) | config (backend state pointer) | file-I/O | `infra/terraform/accounts/prod/backend.hcl.example` (template) / `infra/terraform/accounts/dev/backend.hcl.example` (sibling shape) | exact (template-to-instance copy pattern) |
| `infra/terraform/accounts/prod/terraform.tfvars` (new, from `.example`) | config (variable overrides) | file-I/O | `infra/terraform/accounts/prod/terraform.tfvars.example` (template) / `infra/terraform/accounts/dev/terraform.tfvars.example` (sibling shape) | exact (template-to-instance copy pattern) |
| `.../01-LAUNCH-GATE-MATRIX.md` rows 12-17 | doc (status ledger row update) | transform (BLOCKED -> PASS/evidence-linked) | Phase 1 row 27 (`Dashboard README NEO4J_* cleanup`) — only row already flipped `BLOCKED` -> `PASS` with a concrete evidence citation | role-match (status-table row edit pattern) |
| `.../evidence/aws.md` (new sections appended) | doc (evidence log, command + result pairs) | event-driven (append-only log of executed commands) | `evidence/aws.md` "Phase 2 Read-Only Checks Actually Run" section (own file, prior phase's section) | exact (same file, established section convention) |

## Pattern Assignments

### `infra/terraform/accounts/prod/versions.tf` (config, D-09 bug fix)

**Analog:** `infra/terraform/accounts/dev/versions.tf` (already correct — this is the literal target state)

**Current buggy prod content** (`infra/terraform/accounts/prod/versions.tf` lines 1-14):
```hcl
terraform {
  required_version = "~> 1.14.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.39.0"
    }
  }

  backend "s3" {
    use_lockfile = true
  }
}
```

**Correct dev analog** (`infra/terraform/accounts/dev/versions.tf` lines 1-14, identical file shape, only line 2 differs):
```hcl
terraform {
  required_version = ">= 1.14.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.39.0"
    }
  }

  backend "s3" {
    use_lockfile = true
  }
}
```

**The fix:** change line 2 only, `~> 1.14.7` -> `>= 1.14.7`. Everything else in the file (provider pin, `backend "s3" { use_lockfile = true }`) is already correct and must be left untouched — `use_lockfile = true` (D-02) is **already present** in both prod and dev `versions.tf`, so no edit is needed there; only the `required_version` line changes.

**Root cause documented in evidence** (`evidence/aws.md` lines 117-120, Phase 2):
> `required_version = "~> 1.14.7"` (pessimistic `~>` constraint, accepts only `1.14.x`), which fails `terraform init` under the locally installed Terraform `1.15.5` until temporarily relaxed to `>= 1.14.7`... The dev-side equivalent already uses `>= 1.14.7`. This is a real, unfixed repo bug recorded here for a future task to fix permanently — Phase 2 did not fix it (Pattern 1, temporary edit-then-revert only).

Phase 2's temporary, reverted edit (`evidence/aws.md` lines 94-95, 109-110) used the exact same target string `>= 1.14.7` and reverted with `git checkout -- versions.tf`. Phase 6 makes this same edit but commits it permanently instead of reverting.

---

### `infra/terraform/accounts/prod/backend.hcl` (config, new file from template, D-01/D-02)

**Analog 1 — same-account template:** `infra/terraform/accounts/prod/backend.hcl.example` (lines 1-5, full file):
```hcl
bucket  = "edgartools-prod-tfstate"
key     = "accounts/prod/terraform.tfstate"
region  = "us-east-1"
encrypt = true
```

**Analog 2 — sibling dev shape (for comparison, same key names, different values):** `infra/terraform/accounts/dev/backend.hcl.example` (lines 1-5, full file):
```hcl
bucket  = "edgartools-dev-tfstate"
key     = "accounts/dev/terraform.tfstate"
region  = "us-east-1"
encrypt = true
```

**Pattern:** Both prod and dev `.example` templates follow the same `{bucket}-{key}-{region}-{encrypt}` 4-line shape; neither currently has a `use_lockfile` line.

**Flagged conflict — do not silently resolve, surface to planner/user:** D-02 explicitly instructs adding `use_lockfile = true` to `backend.hcl`. Confirmed by reading both `versions.tf` files above: `use_lockfile = true` is **already present** in the `backend "s3" { ... }` block inside `versions.tf` (both prod and dev, identical). Adding `use_lockfile = true` as a 5th line in `backend.hcl` per D-02 would therefore be redundant with the existing `versions.tf` declaration — but Terraform partial-backend-config merging means this is likely harmless (same value, no conflict) rather than an error. Planner should either (a) follow D-02 as written and add the line to `backend.hcl` for explicitness/parity with the decision text, or (b) confirm with the user that the existing `versions.tf` declaration already satisfies the D-02 locking requirement and `backend.hcl` can stay at 4 lines. Do not unilaterally drop the `use_lockfile` line from `backend.hcl` without one of those two resolutions — D-02 is a locked user decision.

**File status:** `backend.hcl` (without `.example`) does not exist for either dev or prod accounts in the repo — confirmed via `find`. This is a gitignored, locally generated file (consistent with no DynamoDB lock table reference anywhere and consistent with "never committed" framing in CONTEXT.md D-10). Phase 6 plan should create it as a local, non-committed file exactly as Phase 2's dry-run created (then reverted) `override.tf`.

---

### `infra/terraform/accounts/prod/terraform.tfvars` (config, new file from template, D-07/D-08)

**Analog 1 — same-account template:** `infra/terraform/accounts/prod/terraform.tfvars.example` (lines 1-11, full file):
```hcl
# The AWS prod root provisions passive infrastructure only:
# VPC/subnets/security groups, S3/KMS, ECR, ECS cluster/logs, RDS infrastructure
# when enabled, and empty secret containers. IAM roles, service-assumed runner roles, and
# Snowflake trust policies live in infra/terraform/access/aws/accounts/prod.

# Optional: point at an existing empty EDGAR identity secret container instead of
# letting this root create edgartools-prod-edgar-identity.
# edgar_identity_secret_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:edgartools-prod-edgar-identity"

# Optional MDM database shell:
```

**Analog 2 — sibling dev shape:** `infra/terraform/accounts/dev/terraform.tfvars.example` (lines 1-12, full file):
```hcl
# The AWS dev root provisions passive infrastructure only:
# VPC/subnets/security groups, S3/KMS, ECR, ECS cluster/logs, and empty secret
# containers. IAM roles, service-assumed runner roles, and Snowflake trust policies live in
# infra/terraform/access/aws/accounts/dev.

# Optional: point at an existing empty EDGAR identity secret container instead of
# letting this root create edgartools-dev-edgar-identity.
# edgar_identity_secret_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:edgartools-dev-edgar-identity"

# Enable for the AWS MDM data plane used by ECS MDM jobs.
# mdm_db_engine_version    = null
```

**Pipeline notification variables to set** (from `infra/terraform/accounts/prod/variables.tf` lines 55-62 — declared but absent from both `.example` files, so this is new ground, not copied from an existing commented-out line):
```hcl
variable "pipeline_notifications_enabled" {
  description = "Set to true to provision the pipeline_notifications SNS + EventBridge stack. Defaults to false so it is opt-in and does not affect existing terraform plan output."
}

variable "pipeline_failure_subscriber_email" {
  description = "Email address to receive pipeline failure notifications. Required when pipeline_notifications_enabled = true. No default — operator must supply explicitly."
}
```

**Pattern:** Per D-05, leave `edgar_identity_secret_arn` and any MDM secret-override lines commented out / absent (fresh-shell creation, no overrides). Per D-07/D-08, ADD two new lines not present in either `.example` file, following the same `key = value` flat HCL style as the rest of the file:
```hcl
pipeline_notifications_enabled    = true
pipeline_failure_subscriber_email = "thepaulananth@gmail.com"
```

**File status:** `terraform.tfvars` (without `.example`) does not exist for either dev or prod — gitignored, locally generated, never committed (D-10 reinforces this for the real values).

---

### `01-LAUNCH-GATE-MATRIX.md` rows 12-17 (doc, status ledger update)

**Analog — only existing row that already transitioned BLOCKED -> PASS with a concrete evidence citation** (`01-LAUNCH-GATE-MATRIX.md` line 27):
```markdown
| Dashboard README `NEO4J_*` cleanup (neo4j-snowflake Phase 4 `04-03-PLAN.md` closeout) | dashboard reviewer / release owner | Complete upstream dashboard docs/final evidence closeout so active setup no longer instructs external `NEO4J_*`, Bolt, Aura, or `check-connectivity --neo4j` paths. | [evidence/dashboard-security.md](evidence/dashboard-security.md) README Cleanup section: cleanup completed in go-live Phase 4 plan 04-01 (commit e5865ba); arch test `test_dashboard_foundation_boundaries.py` enforces new contract (24 passed). Documentation gate satisfied; no prod dependency. | PASS |
```

**Table column structure** (header, line 10):
```markdown
| Gate | Owner/Source | Required Fix | Required Rerun Proof | Status |
|---|---|---|---|---|
```

**Current BLOCKED rows to update** (lines 12-17, full current text — preserve "Owner/Source" column, rewrite "Required Fix"/"Required Rerun Proof" columns to point at Phase 6 evidence, flip "Status" column):

| Row | Current Status | Current evidence pointer |
|---|---|---|
| 12 `AWS passive infrastructure outputs` | `BLOCKED` | `evidence/aws.md` (Phase 2 plan-only) |
| 13 `Production bronze data reuse from dev bronze` | `BLOCKED` | `runbook/aws-deploy.md` section 3 |
| 14 `Production AWS application manifest` | `BLOCKED` | `evidence/aws.md` (absent) |
| 15 `AWS active application deploy` | `BLOCKED` | `runbook/aws-deploy.md` |
| 16 `Stale edgar-identity secret ARN mitigation` | `BLOCKED` | `runbook/aws-deploy.md` section 2 |
| 17 `ECR cleanup deleting in-flight image digest mitigation` | `BLOCKED` | `runbook/aws-deploy.md` section 4 |

**Pattern to follow when rewriting each row:**
1. Keep the `Owner/Source` column (`AWS operator`) unchanged.
2. Rewrite `Required Fix` to state what was actually run in Phase 6 (e.g. "Real `terraform apply` against the bootstrapped `edgartools-prod-tfstate` S3 backend completed; `versions.tf` `~>` bug fixed permanently in this phase.").
3. Rewrite `Required Rerun Proof` to point at the new Phase 6 evidence section instead of (or in addition to) `runbook/aws-deploy.md`/dry-run-only `evidence/aws.md` content — link to the specific new subsection added in `evidence/aws.md` (see next pattern below), per the established `[evidence/aws.md](evidence/aws.md)` relative-link convention used throughout the table.
4. Flip `Status` from `BLOCKED` to `PASS` (or to a more specific blocked state with new evidence, per CONTEXT.md, if a step genuinely fails) — mirror row 27's phrasing style: cite the concrete artifact (commit hash, test pass count, or here: resource counts / digest format / command exit codes) rather than a vague "done" claim.
5. Row 13's bronze-sync step is explicitly **out of scope beyond what's already documented** per CONTEXT.md domain section ("does not... run the dev-bronze-to-prod-bronze S3 sync beyond what the matrix's existing documented procedure specifies") — if Phase 6 does not execute the sync, leave row 13's status as `BLOCKED` or update only the prerequisite note (bucket now exists), do not mark `PASS` for a step not executed.
6. Rows 16 and 17 are a different gate *type* than 12/14/15: they are mitigation/documentation gates ("the runbook must require X"), not apply-result gates. The runbook text already exists (`runbook/aws-deploy.md` sections 2 and 4) and already satisfies the documentation requirement independent of whether Phase 6's real deploy succeeds. For these two rows, row 27's documentation-satisfied `PASS` model (lines 27: "Documentation gate satisfied; no prod dependency") is the better analog than the apply-based rows 12/14/15 — they can plausibly flip to `PASS` purely on documentation existing + non-secret proof that the explicit flag/ordering was followed during the real deploy, even if framed slightly differently from the resource-count-based proof used for rows 12/14/15.

---

### `evidence/aws.md` (doc, append-only evidence log)

**Analog — established section pattern from Phase 2** (`evidence/aws.md` lines 89-121, "Phase 2 Read-Only Checks Actually Run"):
```markdown
## Phase 2 Read-Only Checks Actually Run

\`\`\`bash
cd infra/terraform/accounts/prod
# ... exact commands run ...
\`\`\`

Result: succeeded. `Plan: 37 to add, 0 to change, 0 to destroy.`

- Resource-add count: ...
- Output names present in `infra/terraform/accounts/prod/outputs.tf` (22 total, names only): ...
- Revert confirmed: ...
- Required-fix note: ...
- This is plan-only context. It is not production proof — ...
```

**Header/preamble pattern** (lines 1-12, file top — already exists, do not duplicate, just append new sections below):
```markdown
# AWS Evidence - Phase 1 Production Readiness

Date: 2026-06-14 UTC
Environment: production required; dev rows are precedent only and require separate production proof.
AWS profile: production profile required; dev status check used `sec_platform_deployer`.
AWS account: production account label required; dev status check referenced the dev account only.

This artifact captures non-secret evidence only. It omits passwords, tokens, DSNs, full task logs, secret ARNs, and raw Native App job logs.
```

**Generated-JSON summary rule to apply to the new `infra/aws-prod-application.json` evidence section** (lines 166-176, exact rule text to reuse):
```markdown
## Generated-JSON Summary Rule

When `infra/aws-prod-application.json` exists, evidence must summarize only:

- file presence,
- top-level keys,
- state-machine name list,
- image-ref format (`@sha256:` digest vs mutable tag),
- relevant sanitized paths.

Do not paste the JSON body.
```

**Pattern for the new Phase 6 section(s):** Add a `## Phase 6 Production Apply` (or similarly named) section, following the exact `### <subsection>` -> fenced bash command block -> `Result: <succeeded|failed>. <one-line outcome>` -> bullet list of non-secret findings -> closing status-pointer bullet structure used in every prior section of this file. Specifically:
- Bucket bootstrap commands (`aws s3api create-bucket`, `put-bucket-versioning`, `put-bucket-encryption`, `head-bucket`) get their own `###` subsection, mirroring the "Image-Promotion Digest Capture (read-only)" subsection style (lines 123-141) — short, command + result + 2-3 bullets.
- `terraform plan`/`apply` get a subsection mirroring "Phase 2 Read-Only Checks Actually Run" but reporting the REAL (non-reverted) resource-add count and the 22 live output VALUES are NOT pasted — only names/format, consistent with D-10 and the existing Generated-JSON Summary Rule's spirit (extend the same non-secret-summary discipline to Terraform outputs, not just JSON).
- The `EDGAR_IDENTITY` secret `put-secret-value` step gets a one-line confirmation bullet ("value set, not pasted") — never the value itself (D-06/D-10).
- The active deploy step (`deploy-aws-application.sh --env prod`) gets a subsection following the exact `### <n>. <step name>` pattern already established in `runbook/aws-deploy.md` numbered-comment style (`# 1.`, `# 2.`, etc., lines 28-44, 91-105) for the command block, then a result/bullet block matching `evidence/aws.md`'s own style (not the runbook's prose style) for the evidence entry itself.
- Update the `## Not-Yet-Runnable Production Steps` list (lines 62-70) by removing rows that are now resolved and/or add a new `## Phase 6 Resolved Steps` list mirroring its bullet format (`- BLOCKED - see ... row ...` becomes `- PASS - see ... row ...` or stays `- BLOCKED` for anything not executed in Phase 6, e.g. row 13 per scope boundary above).

## Shared Patterns

### Non-secret evidence discipline (D-10, carried from Phase 1)
**Source:** `evidence/aws.md` lines 8, 12, 166-176 (Generated-JSON Summary Rule); CONTEXT.md D-10
**Apply to:** every new evidence subsection in `evidence/aws.md`, every matrix row update.
```markdown
This artifact captures non-secret evidence only. It omits passwords, tokens, DSNs, full task logs, secret ARNs, and raw Native App job logs.
```
Never paste: full `infra/aws-prod-application.json` body, Terraform state, secret ARNs/values, the `EDGAR_IDENTITY` string value, image digests as committed evidence (format only, per line 141: "Digest values themselves are not recorded here (non-secret but ephemeral/mutable-on-rebuild) — only the format was confirmed").

### Dev-vs-prod sibling-file diffing
**Source:** `infra/terraform/accounts/dev/*` vs `infra/terraform/accounts/prod/*`
**Apply to:** `versions.tf`, `backend.hcl`, `terraform.tfvars`
Every prod Terraform root file under `infra/terraform/accounts/prod/` has a structurally identical dev sibling under `infra/terraform/accounts/dev/` differing only in `dev`/`prod` name-prefix substitutions and the `versions.tf` `required_version` bug (now fixed to match). When in doubt about correct prod file shape, diff against the dev sibling first — this is the single highest-confidence analog in this phase.

### Runbook-as-script-of-record
**Source:** `.planning/workstreams/go-live/phases/02-aws-and-snowflake-production-deployment-dry-run/runbook/aws-deploy.md`
**Apply to:** every state-changing AWS CLI/Terraform command Phase 6 executes.
Per CONTEXT.md: "Phase 6 executes what this runbook documented as dry-run; do not re-derive the command shape from scratch." Every command in Plan 06-01/06-02 should be a direct, unmodified copy of a command already present in this runbook (sections 1-4), with only the dry-run/reverted framing removed since these are now real.

### Approval-gate before destructive/irreversible apply (D-03/D-04)
**Source:** CONTEXT.md D-03/D-04; no prior code analog exists in this repo (first real prod apply) — this is a NEW process pattern, not copied from existing code.
**Apply to:** the `terraform plan -out=tfplan` / `terraform apply tfplan` sequence only.
```bash
terraform plan -out=tfplan
# show user: resource add/change/destroy counts + resource list
# WAIT for explicit user go-ahead message
terraform apply tfplan   # never `terraform apply` (fresh re-plan) at this step
```

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `infra/aws-prod-application.json` (generated, not authored) | config (generated manifest) | request-response (script output) | Not authored by the plan — produced automatically by `infra/scripts/deploy-aws-application.sh --env prod`; the existing `infra/aws-dev-application.json` is the runtime analog but is read-only generated output, not something to pattern-match for hand-authoring. Per D-10/Generated-JSON Summary Rule, only its summary (not its content) is committed, into `evidence/aws.md`. |

## Metadata

**Analog search scope:** `infra/terraform/accounts/{dev,prod}/`, `.planning/workstreams/go-live/phases/{01,02}-*/`, `infra/scripts/deploy-aws-application.sh` (referenced, not re-read — already fully documented in `runbook/aws-deploy.md`).
**Files scanned:** 16 Terraform account files (dev+prod), `01-LAUNCH-GATE-MATRIX.md` (108 lines), `evidence/aws.md` (176 lines), `runbook/aws-deploy.md` (283 lines), `variables.tf` (pipeline notification variable declarations).
**Pattern extraction date:** 2026-06-19
