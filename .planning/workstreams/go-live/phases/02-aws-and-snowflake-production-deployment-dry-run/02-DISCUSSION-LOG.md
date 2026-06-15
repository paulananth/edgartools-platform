# Phase 2: AWS And Snowflake Production Deployment Dry Run - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-14
**Phase:** 2-AWS And Snowflake Production Deployment Dry Run
**Areas discussed:** Dry-run scope, Snowflake validation without a prod connection, Production AWS account & image strategy, MDM flag in documented deploy command

---

## Area 1: "Dry run" scope

| Option | Description | Selected |
|--------|-------------|----------|
| 1. Document-and-validate only | Produce runbook + commands + BLOCKED rows; validate via terraform plan, dbt compile, script dry-checks; no real prod execution | ✓ |
| 2. Hybrid — provision passive AWS infra only | terraform apply for prod passive infra now; deploy/Snowflake DDL stay documented + BLOCKED | |
| 3. Full execute | terraform apply + deploy-aws-application.sh --env prod + Snowflake stack deploy + dbt against prod, now | |

**User's choice:** Option 1 (document-and-validate only).
**Notes:** Foundational decision — narrowed all subsequent areas toward "produce the runbook and capture what's safely checkable today" rather than standing up real prod infrastructure.

---

## Area 2: Snowflake validation without a prod connection

| Option | Description | Selected |
|--------|-------------|----------|
| 1. Validate dbt against existing dev target | dbt compile + run/test against dev as logic-validation proxy; document exact prod-target command as BLOCKED placeholder | ✓ |
| 2. Compile-only, no live connection | dbt compile only, no warehouse hit at all | |

**User's choice:** Option 1.
**Notes:** Answered together with areas 1, 3, 4 in a single batched turn ("1 for both, check it for area 3").

---

## Area 3: Production AWS account & image strategy

| Option | Description | Selected |
|--------|-------------|----------|
| 1. Confirm separate-account assumption | Build/push images to a separate prod AWS account's ECR | |
| 2. Same account — re-tag images | Re-tag existing :dev/sha-* images as :prod in the same ECR repos | ✓ (after verification) |

**User's choice:** Asked Claude to verify via `aws sts get-caller-identity --profile aws-admin-dev` and `--profile aws-admin-prod`. Both returned account `077127448006` / IAM user `cli-access` — same account confirmed. Option 2 selected based on this finding.
**Notes:** The initial framing (option 1 as "recommended") was based on the existence of a distinct `aws-admin-prod` profile and a separate Terraform root; live verification overturned that assumption.

---

## Area 4: MDM flag in the documented deploy command

| Option | Description | Selected |
|--------|-------------|----------|
| 1. Document deploy WITH --enable-mdm | Single documented prod deploy command includes --enable-mdm; MDM secret names listed as required-identifier BLOCKED items for Phase 3 | ✓ |
| 2. Document deploy WITHOUT --enable-mdm | Phase 2 documents base-warehouse-only deploy; Phase 3 documents its own MDM-enabling redeploy | |

**User's choice:** Option 1.
**Notes:** Answered in the same batched turn as areas 1-3.

---

## Claude's Discretion

None — all four areas were explicitly decided by the user.

## Deferred Ideas

None — discussion stayed within phase scope.
