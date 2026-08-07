# Confirm the AWS<->Snowflake storage_external_id/trust coupling needs no change for the new account

Type: task
Status: resolved

## Question

Quick confirmatory check, not expected to surface a real decision.

Per the snowflake-env-provisioning map's Ticket 04, `storage_external_id`
(the external ID the storage-integration IAM role's trust policy requires)
is coordinated between the AWS side and the Snowflake side purely by shared
naming convention keyed on the environment slug (e.g.
`edgartools-prod-snowflake-native-pull`), not a wired Terraform dependency.

Confirm: since this cutover keeps the environment slug `prod` (only the
underlying Snowflake account/org identifiers change, per this map's
Destination — bronze/silver/AWS infra are untouched), does
`storage_external_id` and the rest of the AWS-side trust relationship need
any change at all? The expectation is no — the slug-keyed convention should
be entirely account-identifier-agnostic — but verify directly against the
live `terraform plan` output for `access/aws/accounts/prod` (or equivalent)
rather than assuming, since a wrong assumption here breaks the storage
integration's auth silently.

## Notes

`task`-type (AFK). Expected to resolve quickly to "confirmed, no change
needed" — flagging as its own ticket rather than folding into Ticket 02
because it's a distinct, checkable claim with a real (if unlikely) failure
mode: if wrong, the storage integration silently fails auth, which is the
kind of confusing-error class Ticket 04's original answer specifically
called out.

## Answer

**`storage_external_id` itself: confirmed unaffected, exactly as
expected.** Ran a live `terraform plan` against
`access/aws/accounts/prod` (real AWS credentials, account `690839588395`,
via `sec_platform_deployer` — this is the AWS side, entirely separate
credentials from the Snowflake side blocked earlier this session). Traced
`local.storage_ext_id = coalesce(var.snowflake_storage_external_id,
try(local.snowflake.snowflake_storage_external_id, null),
"edgartools-${local.environment}-snowflake-native-pull")`
(`access/aws/accounts/prod/main.tf:37`) — the deterministic fallback is
keyed purely on `local.environment` (the slug, `"prod"`), never on any
Snowflake account identifier. `snowflake_storage_external_id`'s own
variable doc confirms this is the intended design: "Defaults to the
deterministic environment value." Live plan showed zero drift attributable
to this value.

**But a real, unanticipated finding: a *different* AWS↔Snowflake coupling
in the same trust relationship genuinely does need a follow-up apply, and
nothing in the current go-live sequence accounts for it.** The live plan
was not a no-op — `Plan: 0 to add, 1 to change, 0 to destroy` — and the
one change is directly relevant:
`module.runtime_access.aws_sns_topic_policy.snowflake_manifest_events`
gains a new statement, `AllowSnowflakeSubscribeToManifestTopic`, granting
`SNS:Subscribe` to `Principal.AWS =
"arn:aws:iam::437537458665:user/hsat1000-s"` — a **Snowflake-owned** AWS
IAM principal (account `437537458665`, not this platform's `690839588395`
and not any Snowflake account locator), sourced via
`local.subscriber_arn`, which reads `snowflake_manifest_subscriber_arn`
from **`data.terraform_remote_state.snowflake[0]`** — a live cross-state
read of the Snowflake provisioning root's own Terraform outputs
(`access/aws/accounts/prod/main.tf:20-36`, confirmed the Snowflake root
does output this at `infra/terraform/snowflake/accounts/prod/outputs.tf:36`).

**Why this matters:** that state file hasn't been re-applied against the
new account yet (only `terraform.tfvars` has been edited locally, per this
map's own Notes — the plan I ran is reading whatever the Snowflake root's
state *last actually contained*, i.e. the old account's real subscriber
ARN). This ARN is the AWS-side identity Snowflake's own Snowpipe
infrastructure uses to subscribe to the export bucket's SNS topic — the
exact mechanism Ticket 02 traced as the trigger for the entire
gold-population pipeline (`snowflake_pipe.manifest`'s `auto_ingest =
true`). **Once the Snowflake side is genuinely re-applied against
`pijjxma-ppb32800`, this output may resolve to a different ARN — and the
AWS access root must be re-planned/re-applied afterward to authorize
whatever that new ARN is, or Snowpipe can never subscribe to the SNS
topic and manifest auto-ingest silently never fires.**

**Sequencing gap this surfaces:** `go-live.sh`'s current stage order runs
"AWS: access roles/policies" (stage 4) *before* "Snowflake: native-pull
foundation" (stage 7) — correct for getting baseline IAM roles in place
before ECS needs them, but means the SNS subscribe grant is computed too
early to see the new account's real subscriber ARN. Confirmed this
degrades gracefully rather than erroring (`local.snowflake = try(...,
{})`, so a nonexistent/not-yet-applied Snowflake state key just yields an
empty map, `local.subscriber_arn` falls to `null`, and the SNS statement
is simply omitted on that first pass) — but the omission is silent, and
nothing re-runs this apply later in the sequence to add it back. **A
second "AWS: access roles/policies" apply, after the Snowflake native-pull
stage, is required** and is not currently in `go-live.sh` at all.

**Unrelated, pre-existing drift also visible in the same plan, noted so it
isn't confused with the finding above:** the plan also renames an existing
statement's `Sid` (`AllowS3BucketNotification` →
`AllowS3PublishFromSnowflakeExportBucket`) and adds an `aws:SourceAccount`
condition to it — this is the S3→SNS *publish* permission (unrelated to
Snowflake's *subscribe* permission above), reads like an already-pending
module hardening unrelated to which Snowflake account is targeted, not
something this cutover caused.

**Correction, made while resolving Ticket 06 (runbook assembly):** no second
stage is needed after all. The finding above was real, but the "handed to
Ticket 06 as a required new stage" conclusion was wrong — it was reasoning
from a bare, standalone `terraform plan`/`apply` run directly against
`access/aws/accounts/prod`, bypassing the script that stage 7 ("Snowflake:
native-pull foundation") actually calls. Reading
`infra/scripts/deploy-snowflake-stack.sh` in full (lines 379-418) shows it
already performs exactly this reconciliation internally, in one pass: (1)
apply `access/aws/accounts/{env}` with a permissive "bootstrap trust"
overlay (external ID only, no subscriber ARN yet); (2) apply
`snowflake/accounts/{env}`'s storage integration only, which emits the real
`snowflake_manifest_subscriber_arn` for *this* account; (3) **re-apply**
`access/aws/accounts/{env}` with a "reconcile" overlay carrying that real
ARN via an explicit `-var`; (4) apply the full Snowflake stack; (5) apply
`access/snowflake/accounts/{env}`. Confirmed step 3's explicit var wins over
the remote-state fallback I was reading before:
`access/aws/accounts/prod/main.tf:36` —
`local.subscriber_arn = try(coalesce(var.snowflake_manifest_subscriber_arn,
try(local.snowflake.snowflake_manifest_subscriber_arn, null)), null)`. So
the drift I observed live was this reconciliation simply not having run yet
for the new account — not a gap in `go-live.sh`'s stage sequence. No change
needed to the runbook for this.
