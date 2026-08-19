# Map: Repopulate this product's Snowflake-side state on a brand-new account

Labels: wayfinder:map

## Destination

A documented, repeatable go-live procedure — driven by `infra/scripts/go-live.sh`
— for taking this product from "Terraform infra stood up on a brand-new
Snowflake account" to "fully live": source/gold/MDM/graph repopulated and
verified. Bronze (S3 Parquet) and silver (DuckDB on S3) are AWS-side
artifacts, entirely independent of which Snowflake account is in play — they
already exist and nothing needs to move for them. Gold, MDM, and the graph
are all *derived* from source/silver, so on a new account they get
**repopulated** by running existing pipeline tooling (native-pull → dbt gold
→ `mdm run` → `mdm sync-graph`), not migrated — no Snowflake-to-Snowflake
data copy. The live cutover from the trial-suspended `xcpclkf-kb19989`
account to the fresh `pijjxma-ppb32800` account is the first real exercise of
this capability; reaching the end of this map means the decisions are locked
and a documented, runnable go-live procedure exists that could take any
future brand-new account the same way.

Pure planning (per the user's explicit choice): tickets here resolve
decisions only. Implementation happens in later, explicit "implement ticket
NN" sessions, same pattern as the map below.

## Notes

- **Builds on ["One-shot brand-new-Snowflake-account → fully-live provisioning
  script"](../snowflake-env-provisioning/map.md), not a replacement for it.**
  That map's resolved decisions (account-agnostic Terraform generator,
  `--env-name <slug>` convention, the Neo4j Native App install stage, PR
  #367) are treated as prerequisite infrastructure — this map does not
  re-decide any of them. That map's own destination and scope boundary is
  "stand up an *empty*, prod-shaped infra shell"; its Out of scope section
  explicitly punts on "how the eventual warehouse compute gets pointed at
  this new account" — i.e. data/repopulation is deliberately not that map's
  job. This map picks up exactly there.
- **Ticket 07 on that map** ("Resolve graph grants running before the schema
  they grant on exists") was still open and squarely inside this
  destination — closed there with a pointer, reopened here as Ticket 01.
- **Ticket 06 on that map** ("Decide what 'fully live' is verified by") is
  already *resolved* (a standalone gold row-count verify CLI command,
  design locked) — not re-ticketed here, just cited directly below. Only
  its implementation is still pending, which belongs to the eventual
  "implement" pass, not a new decision ticket.
- **Live context this map exists because of:** `xcpclkf-kb19989` (the
  account this whole platform has run on per CLAUDE.md's documented
  history) is currently reporting a Snowflake free-trial-expired suspension.
  `pijjxma-ppb32800` has been confirmed (by the person driving this map) as
  a deliberate fresh start, not a revival target. `accounts/prod`'s and
  `access/snowflake/accounts/prod`'s local `terraform.tfvars` already point
  at `PIJJXMA`/`PPB32800` as of this map's creation; a `terraform plan`
  against that account shows `35 to add, 0 to change, 0 to destroy` — i.e.
  a genuinely empty account, consistent with "fresh start."
- Skills to consult per ticket: `/grilling` + `/domain-modeling` for
  architecture-shaped decisions; `/research` for anything needing primary
  Snowflake documentation.

## Decisions so far

- (inherited from the snowflake-env-provisioning map) [Decide what "fully live" is verified by](../snowflake-env-provisioning/issues/06-fully-live-verification.md) — a standalone `edgar-warehouse gold verify-live`-style CLI command, called from a new final go-live.sh stage, fails non-zero if any expected EDGARTOOLS_GOLD table is empty. Not yet implemented; implementation is this map's job, not a new decision.
- [Resolve graph grants running before the schema they grant on exists](issues/01-graph-grants-before-schema-ordering.md) — Move the grants SQL (unsplit) out of the "Snowflake Postgres / graph prerequisites" stage into the first line of the "MDM + graph: connectivity, migrations, sync, verification" stage. `mdm sync-graph` needs zero grants to create the schema itself; `mdm verify-graph`'s native-app checks need the grants present; splitting the file or having it self-create the schema were both rejected. Also surfaced that `bronze_seed_silver_gold`'s internal SFN chain creates the schema even earlier via a fault-tolerant sync/verify pair, which the new placement already accounts for.
- [Determine how EDGARTOOLS_GOLD actually gets populated end to end, and whether a brand-new account needs a historical-backfill trigger](issues/02-gold-population-mechanism-and-historical-backfill.md) — One pipeline, not two: Python `gold-refresh` computes gold-shaped Parquet + a manifest from current silver state; Snowpipe auto-ingests the manifest; `LOAD_EXPORTS_FOR_RUN` MERGEs into `EDGARTOOLS_SOURCE` mirror tables; `REFRESH_AFTER_LOAD` force-refreshes dbt-built `EDGARTOOLS_GOLD` dynamic tables, which do real transformation (e.g. MDM enrichment), not passthrough. No historical-backfill trigger needed — `gold-refresh` always reads current state, so the first run is already a complete population. CLAUDE.md's architecture diagram oversimplifies this as "native S3 pull," worth a doc fix later. Surfaced real, unanticipated drift: the Terraform-managed `REFRESH_AFTER_LOAD` template only refreshes 9 of ~20 gold tables (an already-fixed prod bug never backported into Terraform), and the whole `infra/snowflake/sql/bootstrap/` directory (8 files) is unwired from any repeatable deploy path — spawned as [Ticket 07](issues/07-reconcile-bootstrap-sql-drift-against-terraform.md), now blocking Tickets 05 and 06.
- [Find and document what actually provisions the Snowflake-hosted MDM Postgres instance](issues/03-mdm-postgres-instance-provisioning.md) — The provisioning SQL exists and is reusable (`mdm_create_network_policy.sql` + `mdm_create_instance.sql`, both Jinja-parameterized) but is not wired into `go-live.sh` — found dead scaffolding (`mdm_schema_name_q`/`mdm_network_policy_name_q`/`mdm_network_rule_name_q` computed at the top of the stage-plan function, never used) suggesting an abandoned wiring attempt. Surfaced a third, deeper gap neither SQL file's own comments mention: both require the `EDGARTOOLS_PROD.MDM` Snowflake schema to already exist, which Terraform's `account_baseline` module never creates (only `source`/`gold`) — a brand-new account has no `MDM` schema at all. Documented the exact 3-command sequence needed; left the "new go-live stage vs. documented manual step" placement choice to Ticket 06, which already covers that kind of decision.
- [Confirm the AWS<->Snowflake storage_external_id/trust coupling needs no change for the new account](issues/04-confirm-aws-snowflake-trust-coupling-unaffected.md) — `storage_external_id` itself confirmed unaffected (slug-keyed, live `terraform plan` against `access/aws/accounts/prod` showed zero drift on it). But the plan wasn't a no-op: found a real, unanticipated sibling gap — the SNS topic policy's grant letting Snowflake's own AWS principal (`arn:aws:iam::437537458665:user/hsat1000-s`) subscribe to the manifest-events topic is populated via a live cross-state read of the Snowflake root's own outputs, which will resolve to a different value once the Snowflake side is actually re-applied against the new account — and nothing in `go-live.sh`'s current stage order re-runs the AWS access-roles apply afterward to pick that up. Without a second apply, Snowpipe can never subscribe and manifest auto-ingest silently never fires. Handed to Ticket 06 as a required new stage, not spun into its own ticket.
- [Reconcile infra/snowflake/sql/bootstrap/*.sql manual prod patches against native_pull's Terraform templates](issues/07-reconcile-bootstrap-sql-drift-against-terraform.md) — Drift is larger than Ticket 02 found: 3 of 8 files (`01`, `03`, and the already-known `04`) are live, current procedure/table bodies more current than Terraform's stale templates — `01`/`03` add 9 EDGARTOOLS_SOURCE tables Terraform never creates at all, confirmed against Python's own `SNOWFLAKE_EXPORT_TABLES` dict as the real source of truth. 2 more (`07`, `08`) are genuinely required with no Terraform equivalent — `08` by explicit design (Terraform's own `account_access` module comments name it directly: object ownership isn't something that module can express). 3 (`02`, `05`, `06`) are confirmed dead. Decision: backport `01`/`03`/`04` into the Terraform templates (one source of truth); run `07`/`08` as new `go-live.sh` stages (Python-model-derived content and ownership transfers respectively, neither fits Terraform's remit); skip `02`/`05`/`06` entirely. Unblocks Tickets 05 and 06.
- [Decide the concrete repopulation sequence for this cutover](issues/05-repopulation-sequence-for-this-cutover.md) — `go-live.sh` (renamed `install.sh` going forward) already has the right sequence for a new-install-against-existing-S3-state: `bronze_seed_silver_gold` (stage 11) + standalone `gold-refresh` (stage 12), unchanged. `load_history` confirmed the wrong fit (its Stage 1 needlessly re-fetches from SEC). One real gap found and closed: neither existing stage ever calls `seed-universe`, needed as a new full/unscoped early step. (Corrected on Ticket 06: the reason is `bootstrap_pending` tracking-status completeness, not `TICKER_REFERENCE` — that table exports in full regardless of `--limit`.)
- [Assemble the documented go-live runbook, driven by go-live.sh](issues/06-assemble-go-live-runbook.md) — This map's terminal ticket. Final 18-stage sequence locked (was 15): new stages for unscoped `seed-universe`, `07_mdm_export_targets.sql`, and `08_loader_role.sql`; `gold verify-live` appended to the gold-refresh stage (fail-fast); Ticket 03's MDM schema/Postgres provisioning prepended to the Postgres-prereqs stage; the old bounded `seed-universe` line removed from the smoke-test stage. `docs/runbook.md` restructured in place (new "Quick Path — install.sh" section prepended, existing manual steps demoted to a reference section) rather than a second competing doc. Also corrected Ticket 04 in passing: `deploy-snowflake-stack.sh` already self-reconciles AWS↔Snowflake trust in one pass — no second AWS access-roles stage is needed after all. No tickets remain open; implementation is a future session.
- [6 empty gold tables blocking gold-verify-live, found during live Stage 15 execution](issues/08-six-empty-gold-tables-followup.md) — Post-implementation fog, ticketed live rather than at charting time. Disposition settled per-table: `ACCOUNTING_FLAGS`/`GUIDANCE_FACTS`/`EARNINGS_CALENDAR` all close automatically once task #35's full-universe `bootstrap-fundamentals` run happens; `CONSENSUS_ESTIMATES`/`TRANSCRIPT_EVENTS` are intentionally pilot-scoped — exclude from `gold-verify-live`'s required-table list; `ADVISER_DISCLOSURES` is a real gap (corrects this ticket's own earlier "no producer code" claim — a gold builder/model already exist, the gap is one layer upstream in silver) turned into an implementation-ready spec on the `adv-pipeline` map, its [ticket 09](../adv-pipeline/issues/09-office-disclosure-parser-extension-spec.md).

## Addendum (2026-08-17): second account swap, `pijjxma-ppb32800` → `prjedju-qjb05385`

`~/.snowflake/connections.toml` (`edgartools-prod`, `snowconn`) now resolves
to a **third** Snowflake account, `PRJEDJU`/`QJB05385` — confirmed live
(`snow sql --connection edgartools-prod -q "SELECT CURRENT_ACCOUNT_NAME(),
CURRENT_ORGANIZATION_NAME()"`) and confirmed empty (`SHOW DATABASES` /
`SHOW ROLES LIKE 'EDGARTOOLS%'`: zero EdgarTools objects, only Snowflake's
built-in databases plus a `NEO4J_GRAPH_ANALYTICS` application already
installed the same day). `pijjxma-ppb32800` — this map's original target,
against which Tickets 01-08 above and the bulk of this map's real
provisioning work already happened (18-stage install, MDM, graph, ~47
Terraform-tracked Snowflake resources) — is superseded, not this map's
target anymore; confirmed by direct user instruction, not inferred.

Terraform for both Snowflake roots (`infra/terraform/snowflake/accounts/prod`,
`infra/terraform/access/snowflake/accounts/prod`) updated:
`terraform.tfvars`' `snowflake_organization_name`/`snowflake_account_name`
point at `PRJEDJU`/`QJB05385`. Both roots' state moved to a **fresh** key
(`snowflake/prod-qjb05385/terraform.tfstate` and
`access/snowflake/prod-qjb05385/terraform.tfstate`, both still in the
existing `edgartools-prod-tfstate-690839588395` AWS S3 bucket — only the
key changed, not the bucket) rather than reusing `pijjxma-ppb32800`'s old
`snowflake/prod/terraform.tfstate` key: that state tracks 47 resources
which do not exist in the new, empty account, so reusing it would have
made Terraform try to reconcile against phantom resources instead of doing
a clean first-time apply. `pijjxma-ppb32800`'s old state pulled and backed
up locally (`~/edgartools-ppb32800-tfstate-backups/`, both roots,
gitignored — not committed, matches this repo's existing
`~/edgartools-077-tfstate-backups-FINAL` pattern for the AWS-side
precedent) before the backend key was changed, so it is not silently lost,
only superseded. `access/snowflake/accounts/prod/terraform.tfvars`'s
`provisioning_state_key` (a cross-state read of the main Snowflake root's
outputs) updated to match the new key — this cross-reference would
otherwise have silently kept reading `pijjxma-ppb32800`'s stale outputs
after only the main root's key moved.

AWS Terraform (`infra/terraform/accounts/prod`,
`infra/terraform/access/aws/accounts/prod`) is **unaffected** — this is a
Snowflake-account-only swap; AWS account `690839588395` and its existing
~44-resource `edgartools-prod-tfstate/accounts/prod` state are unchanged,
matching this map's own "AWS-side is an explicit precondition, not built
here" framing.

**Not yet done as of this entry:** the actual `install.sh` 18-stage
provisioning run against `prjedju-qjb05385` has not started. It requires a
one-time, per-organization ORGADMIN acceptance of the Snowflake Provider/
Consumer Terms in Snowsight for the Neo4j Graph Analytics Native App
(wayfinder snowflake-env-provisioning ticket 02 — no SQL/API equivalent
exists) — `SHOW DATABASES` already shows `NEO4J_GRAPH_ANALYTICS` installed
today, so this step may already be done for this account, but that has not
been separately confirmed. `install.sh doctor`/`install.sh deploy --apply`
against `--env-name prod --snow-connection edgartools-prod` is the next
step.

## Not yet specified

- Whether to dry-run this whole repopulation capability against a disposable
  throwaway Snowflake account before trusting it on the real cutover, or go
  straight at `pijjxma-ppb32800` once the tickets below resolve — depends on
  how confident Ticket 02/05's answers leave everyone, not yet sharp enough
  to ticket.
- What CLAUDE.md's account-map documentation needs to say once this cutover
  is real (mirroring the existing AWS-077 and Snowflake-DEV decommission
  note pattern) — content depends entirely on how the rest of this map
  resolves, not yet sharp enough to ticket.

## Out of scope

- Terraform root generation/structure, the `--env-name` slug convention, and
  Neo4j Native App installation scriptability — already decided by the
  snowflake-env-provisioning map; not re-litigated here.
- AWS-side infrastructure provisioning itself (S3 buckets, IAM roles, SNS
  topics, Step Functions/ECS compute) — a documented precondition per that
  same map's Ticket 04, unaffected by which Snowflake account is targeted.
- Whether `xcpclkf-kb19989` could be revived by adding billing — ruled out;
  the person driving this map confirmed `pijjxma-ppb32800` is a deliberate
  fresh start, not a fallback.
