# Make Seven-Day Production Log Retention Durable

Type: task
Status: resolved
Blocked by: none

## Question

Which deploy-script and infrastructure declarations must change so every
`edgartools-prod` CloudWatch log group remains at the confirmed seven-day
Operational Forensics Window after future provisioning and application
deployments?

The live groups were set to seven days on 2026-08-01. Remove every conflicting
30-day declaration, add drift regression coverage, and verify all scoped groups
without modifying unrelated account log groups. CloudWatch retention-driven
deletion, not whole-stream deletion, owns expiration of older events.

## Answer

Root-caused and fixed 2026-08-11. The map's "set to seven days on 2026-08-01"
claim was correct for the moment it was made, but that change was never made
durable — two independent code paths silently reverted it back to 30 days on
every subsequent run, which is exactly why [ticket 01](01-attribute-production-log-volume.md)
found live retention at 30 days ten days later.

**Root cause — two conflicting 30-day hardcodes, one per provisioning path:**

1. `aws_cloudwatch_log_group.ecs` (Terraform-managed; the *only* log group
   Terraform creates directly), `infra/terraform/modules/warehouse_runtime/main.tf:67`,
   declared `retention_in_days = 30`. Any `terraform apply` — including ones
   run for unrelated reasons, e.g. this same session's earlier ECR
   consolidation work in the same file — reset `/aws/ecs/edgartools-prod-warehouse`
   back to 30.
2. `ensure_log_group()` (`infra/scripts/deploy-aws-application.sh:1341`), the
   idempotent create-or-update helper `deploy-aws-application.sh` calls for
   the Step Functions log group, hardcoded `--retention-in-days 30`. Every
   deploy run — and this session alone ran `deploy-aws-application.sh --env prod`
   twice for unrelated fixes — reset `/aws/states/edgartools-prod-warehouse`
   back to 30.

**A third gap, found while tracing this, that the map hadn't identified:**
the Container Insights performance log group
(`/aws/ecs/containerinsights/edgartools-prod-warehouse/performance`) is
**not created by Terraform or the deploy script at all** — AWS auto-creates
it the first time a task runs on a cluster with `containerInsights = enabled`
(`aws_ecs_cluster.warehouse`, same Terraform file). Nothing reasserted its
retention; it was live at 7 days only because the 2026-08-01 change happened
to land there and nothing has touched it since. That's not durable either —
a cluster recreate or any future manual `put-retention-policy` call would
silently revert it to CloudWatch's default (never expire) with no code path
to catch or correct it.

**Fix:**

- Terraform: `retention_in_days = 30` → `7` on `aws_cloudwatch_log_group.ecs`,
  with a comment pointing at this map's Operational Forensics Window and the
  other two groups it must stay in sync with.
- Script: `ensure_log_group()` now takes `retention_days` as a **required**
  parameter (`"${2:?ensure_log_group requires retention_days}"`, no silent
  default) instead of hardcoding 30 internally — the only way a future call
  site can end up with the wrong retention now is by explicitly passing the
  wrong number, not by omission. New top-level constant
  `OPERATIONAL_FORENSICS_LOG_RETENTION_DAYS=7`. The existing Step Functions
  call site now passes it explicitly; a new call site does the same for the
  Container Insights performance group (name built from `$CLUSTER_NAME`,
  already resolved earlier in the script) — `ensure_log_group` is idempotent
  regardless of who created the group, so calling it unconditionally on every
  deploy is safe whether or not Container Insights has populated the group
  yet.
- Applied live immediately (not left to the next apply/deploy) via
  `aws logs put-retention-policy --retention-in-days 7` on the two drifted
  groups. Verified all three `edgartools-prod` log groups at 7 days via
  `aws logs describe-log-groups` after: `/aws/ecs/edgartools-prod-warehouse`,
  `/aws/states/edgartools-prod-warehouse`,
  `/aws/ecs/containerinsights/edgartools-prod-warehouse/performance`. No
  other account log groups touched.

**Drift regression coverage:** `tests/architecture/test_cloudwatch_log_retention.py`
(new, 5 tests, following the existing static-text-assertion convention in
`tests/architecture/test_ecr_image_retention.py`) — asserts the Terraform
resource's retention is 7 not 30; `ensure_log_group()`'s body has no
hardcoded 30-day retention-policy call and threads its `retention_days`
parameter through; both the Step Functions and Container Insights call sites
pass the shared `OPERATIONAL_FORENSICS_LOG_RETENTION_DAYS` constant; and a
final blanket regression guard that neither file contains a bare
`--retention-in-days 30` / `retention_in_days = 30` anywhere, not just at the
two sites this ticket fixed. `bash -n` and `terraform fmt -check` both clean.
Full repo suite green: 1991 passed, 4 skipped.

Not yet committed as of this entry — code, tests, and the live AWS retention
change are done; nothing has been committed/PR'd.
