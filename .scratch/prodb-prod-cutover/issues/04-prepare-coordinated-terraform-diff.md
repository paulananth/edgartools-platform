# 04 — Prepare and review the coordinated Terraform diff (plan only, no apply)

**What to build:** A reviewed, approved `terraform plan` spanning **both**
Terraform roots that must change together — AWS
(`infra/terraform/accounts/prod`: `module.runtime.snowflake_export_bucket_name`
→ canonical bucket) and Snowflake
(`infra/terraform/snowflake/accounts/prod`: the `native_pull` module's
`export_root_url`/`storage_role_arn` → canonical bucket, which forces the
pipe to be replaced via its `replace_triggered_by` lifecycle rule). No
`terraform apply` runs in this ticket. The output is the sign-off artifact
the operator window in Ticket 05 is approved against — the reviewer must be
able to see the exact combined diff before anyone touches live state.

**Blocked by:** 03 — Grant Snowflake IAM role read access to the canonical bucket

**Status:** ready-for-agent

- [ ] `terraform plan` output for the AWS root and the Snowflake root are
      both captured and reviewed together as one change set
- [ ] Plan output explicitly shows the Snowflake pipe replacement (not just
      an in-place update) so the operator isn't surprised by it during apply
- [ ] Plan is reviewed/approved by whoever owns the operator window (per
      `docs/prodb-to-prod-promotion.md`'s requirement for a separately
      approved operator window)
- [ ] No `terraform apply` is run against either root in this ticket
- [ ] The pending uncommitted `infra/terraform/accounts/prod/{main,outputs}.tf`
      diff (adding `module.storage_canonical`) is reconciled into this plan
      rather than left as a second, uncoordinated diff
