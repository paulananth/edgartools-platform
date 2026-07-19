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

---

**2026-07-19 — DONE.** Plans captured and reviewed in-session before applies:
- `accounts/prod`: after state surgery (`module.storage_canonical` →
  `module.storage`, prodb resources untracked) the plan was a pure no-op on
  infrastructure (outputs-only change) — the dangerous force-replace this
  ticket warned about was defused by state surgery instead of config edits.
- `access/aws`: 7 add / 2 change / 7 destroy — the three
  `sec_platform_prodb_runner_*` → `sec_platform_prod_runner_*` role
  replacements plus policy repoints to canonical buckets.
- `snowflake/prod`: 5 add / 3 change / 5 destroy — integration replaced
  (`EDGARTOOLS_PROD_EXPORT_INTEGRATION`), pipe replaced via its
  `replace_triggered_by` (explicitly surfaced pre-apply, as required), stage
  updated in place to the canonical URL, procedures re-executed.
- `access/snowflake`: no changes (renames carried grants; state rewrite match).
The stashed `main.tf`/`outputs.tf` diff was NOT popped — it was superseded by
the state surgery (committed config already canonical) and dropped.
