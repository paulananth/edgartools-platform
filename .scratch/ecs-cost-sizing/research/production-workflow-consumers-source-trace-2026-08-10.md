# Production Workflow and Consumer Inventory — Audit Draft

Date: 2026-08-10  
Status: Draft for operator audit; Ticket 11 remains open.  
Scope: Wayfinder Ticket 11; repository-owned primary sources plus a read-only live AWS reconciliation. No AWS mutations were made.

## Scope and method

`infra/scripts/deploy-aws-application.sh` is the inventory boundary. It creates or updates Standard Step Functions state machines with a deterministic environment-prefixed name and workflow tag (`infra/scripts/deploy-aws-application.sh:4352-4379`). Its registration blocks define 8 always-deployed workflows and, when MDM is enabled, 18 additional workflows, for 26 total (`infra/scripts/deploy-aws-application.sh:4392-4441`, `infra/scripts/deploy-aws-application.sh:4442-4481`, `infra/scripts/deploy-aws-application.sh:4483-4801`). This source-level inventory is reconciled below with all 26 live production definitions and their recent execution histories. A Step Functions terminal status is not treated as output-correctness or downstream-consumption proof.

Evidence labels used below:

- **Proven**: a repository source explicitly reads, invokes, or continues from the workflow's output.
- **Inferred**: repository prose or sequencing indicates an intended/manual handoff, but no automatic producer-to-consumer edge is implemented.
- **Unknown / no evidenced consumer**: no repository-owned reader or caller was found for the distinct output.

Trigger classification is similarly source-bound. A deployed standalone state machine is callable, but registration alone does not prove who invokes it. The only recurring repository schedule found is for `daily_incremental`: two EventBridge rules target that state machine with `daily` and `backstop` inputs (`infra/scripts/deploy-aws-application.sh:464-503`, `infra/scripts/deploy-aws-application.sh:507-544`), and architecture tests assert both cron expressions, target ARN, role, and payload (`tests/architecture/test_daily_incremental_schedule_controls.py:133-170`). Operator-trigger evidence comes from the shared trigger helper (`scripts/ops/trigger.sh:47-121`), the MDM end-to-end driver (`infra/scripts/run-aws-mdm-e2e.sh:219-229`), runbooks, or explicit comments/tests cited per row.

## Shared downstream consumer chains

These named chains avoid repeating the same long source trace in every workflow row.

### G — warehouse serving export to Snowflake, dbt, and dashboard: proven

The warehouse orchestration policy identifies gold-affecting commands and publishes gold only after successful commands (`edgar_warehouse/application/warehouse_orchestrator.py:83-115`). A successful gold publication builds table Parquet files, exports them to the Snowflake serving target, and writes a run manifest (`edgar_warehouse/application/warehouse_orchestrator.py:597-645`, `edgar_warehouse/application/warehouse_orchestrator.py:784-804`). The target describes itself as consumed by Snowflake native pull and maps source tables to export objects (`edgar_warehouse/serving/targets/snowflake.py:14-16`, `edgar_warehouse/serving/targets/snowflake.py:69-140`).

Snowpipe auto-ingests JSON manifests from the stage's `manifests/` path (`infra/snowflake/sql/bootstrap/01_source_stage.sql:63-82`, `infra/snowflake/sql/bootstrap/01_source_stage.sql:381-402`). A stream records new inbox rows (`infra/snowflake/sql/bootstrap/02_refresh_status.sql:15-38`); the loader procedure reads each manifest, copies named Parquet exports, merges them into source mirror tables, and marks the run ready for dbt (`infra/snowflake/sql/bootstrap/03_source_load_wrapper.sql:13-60`, `infra/snowflake/sql/bootstrap/03_source_load_wrapper.sql:181-205`, `infra/snowflake/sql/bootstrap/03_source_load_wrapper.sql:229-311`). The stream-processing task invokes loading and dynamic-table refresh, then resumes as a triggered task (`infra/snowflake/sql/bootstrap/04_refresh_wrapper.sql:197-255`).

dbt declares the native-pull source tables (`infra/snowflake/dbt/edgartools_gold/models/sources.yml:3-98`) and models consume them, including company, ticker reference, ownership activity, financial facts, and ADV fund-count reconciliation (`infra/snowflake/dbt/edgartools_gold/models/gold/company.sql:11-42`, `infra/snowflake/dbt/edgartools_gold/models/gold/ticker_reference.sql:1-8`, `infra/snowflake/dbt/edgartools_gold/models/gold/ownership_activity.sql:1-19`, `infra/snowflake/dbt/edgartools_gold/models/gold/financial_facts.sql:1-28`, `infra/snowflake/dbt/edgartools_gold/models/gold/adv_fund_count_reconciliation.sql:1-6`, `infra/snowflake/dbt/edgartools_gold/models/gold/adv_fund_count_reconciliation.sql:30-58`). The main Streamlit application reads the gold company/filing, financial, filing-activity, and ADV reconciliation objects (`infra/snowflake/streamlit/streamlit_app.py:196-220`, `infra/snowflake/streamlit/streamlit_app.py:491-524`, `infra/snowflake/streamlit/streamlit_app.py:636-646`, `infra/snowflake/streamlit/streamlit_app.py:1152-1181`).

### T — seed/ticker-reference consumers: proven

`seed-universe` writes a ticker-reference Parquet export and run manifest in addition to warehouse tracking state (`edgar_warehouse/application/warehouse_orchestrator.py:809-854`). The ticker artifact follows chain G into the dbt ticker model and dashboard subject resolution (`infra/snowflake/dbt/edgartools_gold/models/gold/ticker_reference.sql:1-8`, `infra/snowflake/streamlit/streamlit_app.py:386-398`). Its CIK batch manifest is also read by `bootstrap_batched`'s distributed map (`infra/scripts/deploy-aws-application.sh:1807-1839`).

### M — MDM relational export to dbt and dashboard: proven

`mdm export` writes Snowflake gold tables and a Snowflake MDM mirror (`edgar_warehouse/mdm/cli.py:1847-1896`). dbt declares the direct MDM export separately from native-pull sources and enriches the company model from it (`infra/snowflake/dbt/edgartools_gold/models/sources.yml:100-117`, `infra/snowflake/dbt/edgartools_gold/models/gold/company.sql:11-42`); the resulting company object is read by the dashboard (`infra/snowflake/streamlit/streamlit_app.py:196-220`, `infra/snowflake/streamlit/streamlit_app.py:386-398`).

### I — daily-index cache/checkpoint consumers: proven

Loading a daily index writes the immutable bronze payload, merges parsed filing rows into silver, and records a successful checkpoint (`edgar_warehouse/application/warehouse_orchestrator.py:5630-5683`). Later loads read a successful checkpoint and cached rows instead of the network (`edgar_warehouse/application/warehouse_orchestrator.py:5551-5595`). `daily-incremental` calls the same loader and uses its impacted CIKs/accessions to select work (`edgar_warehouse/application/warehouse_orchestrator.py:1278-1339`), while catch-up starts after the last successful checkpoint and invokes the loader for each missing business date (`edgar_warehouse/application/warehouse_orchestrator.py:5924-5966`).

### R — graph-review/dashboard consumer: proven only for the active generation

`verify-graph` can publish generation-scoped review rows, but publication failure is deliberately non-fatal; without an explicit generation ID, publication resolves the currently active generation (`edgar_warehouse/mdm/cli.py:1531-1572`). The graph-review views join every result to `GRAPH_ACTIVE_POINTER` (`infra/snowflake/sql/graph_review/01_graph_review_contract.sql:99-136`), and the MDM dashboard queries those five views (`infra/snowflake/mdm_dashboard/streamlit_app.py:73-99`). The main dashboard also reports the active pointer, not an arbitrary candidate generation (`infra/snowflake/streamlit/streamlit_app.py:1045-1059`). Therefore R proves a consumer only after the relevant candidate has actually become active.

## Complete workflow inventory and consumer trace

### Warehouse-only and base workflows

| Workflow | Purpose and principal output/artifact | Repository trigger evidence | Downstream consumer and classification |
| --- | --- | --- | --- |
| `bootstrap_full` | Loads full filing history for tracked companies (`edgar_warehouse/cli.py:311-317`); its successful command is gold-affecting and emits chain G artifacts (`edgar_warehouse/application/warehouse_orchestrator.py:83-115`). | The single-workflow definition treats it as operator-triggered ad hoc and supports an optional CIK override (`infra/scripts/deploy-aws-application.sh:1433-1442`, `infra/scripts/deploy-aws-application.sh:1567-1586`). | **G — proven.** No automatic MDM or graph stage exists in this single-task state-machine shape (`infra/scripts/deploy-aws-application.sh:1433-1437`). |
| `targeted_resync` | Refreshes one reference, CIK, or accession scope (`edgar_warehouse/cli.py:429-493`), resolves matching reconciliation findings (`edgar_warehouse/application/warehouse_orchestrator.py:1680-1698`), and emits chain G artifacts because it is gold-affecting (`edgar_warehouse/application/warehouse_orchestrator.py:83-115`). | Explicitly operator-triggered ad hoc; its state input supplies `scope_type` and `scope_key` (`infra/scripts/deploy-aws-application.sh:1242-1248`, `infra/scripts/deploy-aws-application.sh:1433-1442`). | **G — proven; reconciliation repair — proven.** The resolved-finding rows are subsequently queryable from the silver finding store (`edgar_warehouse/silver_store.py:3640-3687`). |
| `full_reconcile` | Reconciles warehouse source/state completeness (`edgar_warehouse/cli.py:495-522`), persists `sec_reconcile_finding` rows (`edgar_warehouse/silver_store.py:544-565`, `edgar_warehouse/silver_store.py:3640-3687`), and emits chain G artifacts because it is gold-affecting (`edgar_warehouse/application/warehouse_orchestrator.py:83-115`). | No repository schedule or named caller was found; it is registered as a standalone one-task workflow (`infra/scripts/deploy-aws-application.sh:4397-4414`, `infra/scripts/deploy-aws-application.sh:1587-1592`). Trigger is therefore **unknown/operator-only** in source. | **G — proven; findings-to-targeted-resync — proven.** `targeted_resync` reads and marks applicable findings resolved (`edgar_warehouse/application/warehouse_orchestrator.py:1680-1698`). |
| `load_daily_form_index_for_date` | Loads one business date's SEC daily form index (`edgar_warehouse/cli.py:401-413`) and writes bronze, silver filing rows, and a checkpoint (`edgar_warehouse/application/warehouse_orchestrator.py:5630-5683`). | No repository schedule or named caller was found; the state input must provide `target_date` (`infra/scripts/deploy-aws-application.sh:1243-1248`, `infra/scripts/deploy-aws-application.sh:4397-4414`). Trigger is **unknown/operator-only** in source. | **I — proven.** There is no direct gold/Snowflake publication for this command; its evidenced value is the cache/checkpoint consumed by daily incremental and catch-up (`edgar_warehouse/application/warehouse_orchestrator.py:1278-1339`, `edgar_warehouse/application/warehouse_orchestrator.py:5924-5966`). |
| `catch_up_daily_form_index` | Loads missing daily form indexes through an optional end date (`edgar_warehouse/cli.py:415-427`) and writes the same bronze/silver/checkpoint artifacts through the shared loader (`edgar_warehouse/application/warehouse_orchestrator.py:5924-5966`). | No repository schedule or named caller was found; it is registered as a standalone one-task workflow (`infra/scripts/deploy-aws-application.sh:4397-4414`, `infra/scripts/deploy-aws-application.sh:1587-1592`). Trigger is **unknown/operator-only** in source. | **I — proven.** No direct gold/Snowflake consumer is evidenced (`edgar_warehouse/application/warehouse_orchestrator.py:83-115`). |
| `gold_refresh` | Rebuilds gold without new bronze capture and emits the Snowflake serving exports/run manifest (`edgar_warehouse/cli.py:956-962`, `edgar_warehouse/application/warehouse_orchestrator.py:597-645`, `edgar_warehouse/application/warehouse_orchestrator.py:784-804`). | The operator trigger helper exposes a `gold` action (`scripts/ops/trigger.sh:47-102`); it is also the terminal stage of multiple composite workflows (`infra/scripts/deploy-aws-application.sh:2917-2925`). | **G — proven.** |
| `seed_universe` | Refreshes SEC reference data and writes warehouse tracking, CIK batch, ticker-reference Parquet, and run-manifest artifacts (`edgar_warehouse/application/warehouse_orchestrator.py:1718-1730`, `edgar_warehouse/application/warehouse_orchestrator.py:809-854`). | It is callable standalone and embedded as the first stage of `bootstrap_batched` and `load_history` (`infra/scripts/deploy-aws-application.sh:4392-4414`, `infra/scripts/deploy-aws-application.sh:1807-1812`, `infra/scripts/deploy-aws-application.sh:2782-2792`). | **T — proven.** Both the distributed bootstrap map and Snowflake/dbt/dashboard consume distinct outputs (`infra/scripts/deploy-aws-application.sh:1830-1839`, `infra/snowflake/dbt/edgartools_gold/models/gold/ticker_reference.sql:1-8`). |
| `bootstrap_batched` | Seeds the universe, then runs parallel `bootstrap-batch` tasks over `cik_batches.jsonl`; the map ends after batch silver work (`infra/scripts/deploy-aws-application.sh:1807-1850`). | No repository schedule was found. `mdm_gold`'s own registration comment instructs operators to use it after BatchBootstrap (`infra/scripts/deploy-aws-application.sh:4483-4484`). | **Manual handoff to `mdm_gold` — inferred, not automatic.** This definition contains no MDM, gold refresh, or manifest publication after the map ends (`infra/scripts/deploy-aws-application.sh:1821-1850`). Its silver output has a plausible consumer, but this workflow alone does not complete G. |

### Composite production pipelines

| Workflow | Purpose and principal output/artifact | Repository trigger evidence | Downstream consumer and classification |
| --- | --- | --- | --- |
| `load_history` | Recommended full-history pipeline: seed, sequential bronze/silver windows, ADV/roster ingestion, MDM run/backfill/export/sync/verify, one gold refresh, and a run summary (`infra/scripts/deploy-aws-application.sh:1858-1871`, `infra/scripts/deploy-aws-application.sh:2753-2816`). | Explicitly operator-triggered ad hoc in architecture tests and available through the operator trigger helper (`tests/architecture/test_load_history_state_machine.py:955-958`, `scripts/ops/trigger.sh:47-102`). | **M and G — proven.** The run-summary is a terminal operator artifact. **New graph candidate — no proven active consumer:** its sync and verify calls carry no shared candidate ID (`infra/scripts/deploy-aws-application.sh:2908-2925`). |
| `bootstrap` | Loads recent filings, then MDM resolution/export/sync/verify and gold (`infra/scripts/deploy-aws-application.sh:4454-4460`, `infra/scripts/deploy-aws-application.sh:3077-3094`). | Operator helper action; the state machine accepts an optional CIK override (`scripts/ops/trigger.sh:47-102`, `infra/scripts/deploy-aws-application.sh:1253-1258`). | **M and G — proven.** **New graph candidate — no proven active consumer** for the same unbound sync/verify sequence (`infra/scripts/deploy-aws-application.sh:2908-2925`). |
| `daily_incremental` | Uses daily or weekly-backstop identity scope, captures bronze/silver plus ADV/roster updates, runs MDM export/sync/verify, then one gold refresh (`infra/scripts/deploy-aws-application.sh:3528-3583`); architecture tests assert exactly one gold stage (`tests/architecture/test_daily_incremental_state_machine.py:310-316`). | **Scheduled and proven:** Mon-Sat daily and Sunday backstop EventBridge rules with explicit payloads (`infra/scripts/deploy-aws-application.sh:528-544`, `tests/architecture/test_daily_incremental_schedule_controls.py:133-170`). | **I, M, and G — proven.** **New graph candidate — no proven active consumer** because the common MDM sequence does not bind candidate sync to verification/activation (`infra/scripts/deploy-aws-application.sh:2908-2925`). |
| `mdm_gold` | Runs MDM entity resolution, relationship backfill, relational export, graph sync/verify, and gold refresh without downloading submissions (`infra/scripts/deploy-aws-application.sh:4483-4484`, `infra/scripts/deploy-aws-application.sh:4512-4524`). | Documented manual continuation after `bootstrap_batched`; no schedule was found (`infra/scripts/deploy-aws-application.sh:4483-4484`). | **M and G — proven.** **Graph candidate — no proven active consumer:** `sync-graph` and `verify-graph` pass no common generation ID and there is no activation state (`infra/scripts/deploy-aws-application.sh:4516-4523`). |
| `ownership_mdm_gold` | Optionally parses ownership bronze, resolves persons, derives `IS_INSIDER`, exports MDM, syncs/verifies graph, and refreshes gold (`infra/scripts/deploy-aws-application.sh:4534-4536`, `infra/scripts/deploy-aws-application.sh:4575-4601`). | The operator trigger helper exposes `ownership`; no recurring schedule was found (`scripts/ops/trigger.sh:47-102`). | **M and G — proven.** **Graph candidate — no proven active consumer** because no candidate ID or activation is wired (`infra/scripts/deploy-aws-application.sh:4596-4600`). |
| `residual_holds_graph` | Builds residual security/HOLDS/COMPANY_HOLDS/INSTITUTIONAL_HOLDS state, exports it, then syncs and verifies one explicitly named candidate (`infra/scripts/deploy-aws-application.sh:4657-4664`, `infra/scripts/deploy-aws-application.sh:4688-4727`). | The release-readiness runbook gives an operator `start-execution` invocation and input (`docs/release-readiness/residual-holds-graph-pipeline.md:54-70`). | **M — proven. Candidate-to-active graph consumer — inferred/manual.** The definition explicitly leaves activation to an operator (`infra/scripts/deploy-aws-application.sh:4657-4658`), so R and active-graph dashboard consumers do not see this candidate until that separate action occurs (`infra/snowflake/sql/graph_review/01_graph_review_contract.sql:99-136`). |
| `silver_mdm_gold` | Runs silver processing followed by the common MDM export/sync/verify and gold chain; it is registered from the dedicated silver-to-MDM-to-gold definition (`infra/scripts/deploy-aws-application.sh:3588-3602`, `infra/scripts/deploy-aws-application.sh:4745-4753`). | The operator helper exposes `silver`; no recurring schedule was found (`scripts/ops/trigger.sh:47-102`). | **M and G — proven.** **Graph candidate — no proven active consumer** because the common chain uses unbound sync/verify and no activation (`infra/scripts/deploy-aws-application.sh:2908-2925`). |
| `bronze_seed_silver_gold` | Rebuilds from existing bronze through silver, MDM, and gold; its strict release branch additionally performs candidate sync, idempotency sync, candidate verification, activation, active verification, and gold (`infra/scripts/deploy-aws-application.sh:3915-3972`, `infra/scripts/deploy-aws-application.sh:4036-4112`). | A release-readiness runbook supplies an explicit production operator invocation for strict mode (`docs/release-readiness/ticket20-strict-bulk-load-resume.md:54-70`). | **M and G — proven. R — proven only in strict mode**, because strict mode explicitly verifies and activates the same execution-scoped generation (`infra/scripts/deploy-aws-application.sh:4076-4112`). The ordinary branch still has the unbound graph-candidate gap (`infra/scripts/deploy-aws-application.sh:4030-4034`). |
| `generation_build` | Plans an immutable MDM generation, writes `generation.json` and `partitions.jsonl`, builds partitions, fan-in verifies, retries failed partitions, and marks the MDM generation activated (`infra/scripts/deploy-aws-application.sh:4241-4251`, `infra/scripts/deploy-aws-application.sh:4253-4321`). | Its state-machine comment describes `{}` or versioned operator input; failed attempts require an operator retrigger (`infra/scripts/deploy-aws-application.sh:4306-4315`, `infra/scripts/deploy-aws-application.sh:4323-4346`). | **Unknown / no evidenced external consumer.** The deploy source says it is standalone and not yet chained into load/bootstrap/daily or wired to the shared Snowflake activation pointer (`infra/scripts/deploy-aws-application.sh:4770-4773`). Its `generation-activate` bookkeeping is therefore not evidence that R, the decision contract, Native App, or either dashboard consumes this generation. |

### Standalone MDM utility workflows

All nine utilities are generated by the same one-task state-machine writer and registered in one loop (`infra/scripts/deploy-aws-application.sh:1598-1750`, `infra/scripts/deploy-aws-application.sh:4784-4801`). Except where an operational script is cited, no recurring trigger was found.

| Workflow | Purpose and principal output/artifact | Repository trigger evidence | Downstream consumer and classification |
| --- | --- | --- | --- |
| `mdm_migrate` | Applies MDM schema migrations and prints a result (`edgar_warehouse/mdm/cli.py:20-26`, `edgar_warehouse/mdm/cli.py:1307-1334`). | First step in the MDM end-to-end driver (`infra/scripts/run-aws-mdm-e2e.sh:224-229`). | **Later MDM commands — proven operational prerequisite** by that ordered driver; it has no end-user data artifact (`infra/scripts/run-aws-mdm-e2e.sh:224-229`). |
| `mdm_check_connectivity` | Checks configured MDM connectivity and prints status (`edgar_warehouse/mdm/cli.py:33-40`, `edgar_warehouse/mdm/cli.py:1307-1334`). | Required and invoked by the Snowflake Postgres cutover audit (`infra/scripts/audit-mdm-snowflake-postgres-cutover.py:176-186`, `infra/scripts/audit-mdm-snowflake-postgres-cutover.py:425-431`). | **Audit/operator — proven.** No durable downstream data consumer is evidenced. |
| `mdm_run` | Resolves selected entity types into MDM relational state and emits a terminal report (`edgar_warehouse/mdm/cli.py:27-32`, `edgar_warehouse/mdm/cli.py:765-810`). | Invoked by both the MDM end-to-end driver and cutover audit (`infra/scripts/run-aws-mdm-e2e.sh:224-229`, `infra/scripts/audit-mdm-snowflake-postgres-cutover.py:439-444`). | **Backfill/export chains — proven** by the ordered end-to-end driver and composite definitions (`infra/scripts/run-aws-mdm-e2e.sh:224-229`, `infra/scripts/deploy-aws-application.sh:2902-2913`). |
| `mdm_backfill_relationships` | Derives/backfills relationship instances in MDM (`edgar_warehouse/mdm/cli.py:369-392`, `edgar_warehouse/mdm/cli.py:1732-1754`). | Third step in the MDM end-to-end driver (`infra/scripts/run-aws-mdm-e2e.sh:224-229`). | **MDM export/sync — proven** by the composite chain ordering (`infra/scripts/deploy-aws-application.sh:2905-2916`). |
| `mdm_sync_graph` | Materializes a Snowflake graph candidate from the MDM mirror (`edgar_warehouse/mdm/cli.py:78-105`, `edgar_warehouse/mdm/cli.py:1337-1361`). With no `--generation-id`, it creates a fresh UUID and explicitly never activates it (`edgar_warehouse/mdm/cli.py:97-103`). | Fourth step in the MDM end-to-end driver (`infra/scripts/run-aws-mdm-e2e.sh:224-229`). | **Unknown / no evidenced consumer for the newly created candidate.** The next driver step runs bare `verify-graph`, which means “currently active” rather than this candidate (`edgar_warehouse/mdm/cli.py:304-309`, `infra/scripts/run-aws-mdm-e2e.sh:227-228`), and active-only views cannot consume an unactivated candidate (`infra/snowflake/sql/graph_review/01_graph_review_contract.sql:99-136`). |
| `mdm_verify_graph` | Verifies Snowflake graph parity/Native App execution and prints a result; it may publish graph-review rows (`edgar_warehouse/mdm/cli.py:289-324`, `edgar_warehouse/mdm/cli.py:1575-1623`). | Fifth step in the MDM end-to-end driver and exposed as `verify` in the operator helper (`infra/scripts/run-aws-mdm-e2e.sh:224-229`, `scripts/ops/trigger.sh:47-102`). | **R — proven for an explicit or already-active generation, but not fail-closed for review publication.** Publish failures do not change command success (`edgar_warehouse/mdm/cli.py:1531-1572`). |
| `mdm_counts` | Reads and prints MDM counts (`edgar_warehouse/mdm/cli.py:27-32`, `edgar_warehouse/mdm/cli.py:1307-1334`). | Final step in the MDM end-to-end driver and explicitly invoked by the cutover audit (`infra/scripts/run-aws-mdm-e2e.sh:224-229`, `infra/scripts/audit-mdm-snowflake-postgres-cutover.py:432-438`). | **Audit/operator — proven.** No durable downstream data consumer is evidenced. |
| `mdm_seed_universe` | Seeds MDM company/entity state from the tracked universe (`edgar_warehouse/mdm/cli.py:149-176`, `edgar_warehouse/mdm/cli.py:1395-1415`). | Embedded before compute/windows in `load_history`; standalone workflow also supports a limit override (`infra/scripts/deploy-aws-application.sh:2782-2792`, `infra/scripts/deploy-aws-application.sh:1287-1301`). | **Subsequent MDM resolution — proven** inside `load_history`, whose later states run MDM resolution and export (`infra/scripts/deploy-aws-application.sh:2809-2814`). Standalone invocation requires a manual continuation. |
| `mdm_seed_from_silver` | One-time compatibility/migration seed from silver tracking state (`edgar_warehouse/mdm/cli.py:178-194`, `edgar_warehouse/mdm/cli.py:1276-1290`). | No repository script, schedule, runbook invocation, or composite state was found; only its standalone registration and command mapping are evidenced (`infra/scripts/deploy-aws-application.sh:1289-1290`, `infra/scripts/deploy-aws-application.sh:4784-4801`). | **Inferred/manual.** Later MDM commands can use the seeded relational state, but no repository-owned automatic handoff or named caller proves that edge. |

## Live AWS reconciliation

The main audit performed a read-only capture on 2026-08-10 at repository
commit `4143f35d69e90682788d9ce129b09741d01d4ee0`. It described every live
production state machine, canonicalized and hashed each ASL definition,
resolved every ECS task reference, described the referenced task definitions,
listed parent executions, and fetched every parent execution history in the
30-day window from 2026-07-11 00:00 EDT through the capture. It also listed
EventBridge rules and EventBridge Scheduler schedules. The commands succeeded;
no AWS mutation API was called.

The raw AWS responses were kept out of the repository because they contain
environment-specific account, network, bucket, role, and task identities. The
portable evidence below records definition revisions and hashes, task family
revisions, immutable image digests, normalized command operations, and
aggregates without hardcoding operator identity or account-specific resource
names.

### Current runtime cohort

All 26 definitions reference exactly these six task definitions and two
immutable image digests:

| Runtime/profile | Task definition | CPU/memory | Immutable image digest |
| --- | --- | --- | --- |
| warehouse small | `edgartools-prod-small:168` | `512/1024` | `sha256:79d7e015cd98c67426a03d45a8a928e22f3e54d846c47cafdc7b048cd47246f4` |
| warehouse medium | `edgartools-prod-medium:173` | `1024/4096` | `sha256:79d7e015cd98c67426a03d45a8a928e22f3e54d846c47cafdc7b048cd47246f4` |
| warehouse large | `edgartools-prod-large:165` | `2048/8192` | `sha256:79d7e015cd98c67426a03d45a8a928e22f3e54d846c47cafdc7b048cd47246f4` |
| MDM small | `edgartools-prod-mdm-small:145` | `512/1024` | `sha256:9f55a0a7910cb55d1a88190c7642ccfc55b6c4f0210deccb956f6750c3711de2` |
| MDM medium | `edgartools-prod-mdm-medium:145` | `1024/4096` | `sha256:9f55a0a7910cb55d1a88190c7642ccfc55b6c4f0210deccb956f6750c3711de2` |
| MDM large | `edgartools-prod-mdm-large:79` | `2048/8192` | `sha256:9f55a0a7910cb55d1a88190c7642ccfc55b6c4f0210deccb956f6750c3711de2` |

The current standalone `seed-universe` and dormant `bootstrap-batched`
definitions still reference warehouse medium. The active composite
`bootstrap`, `load-history`, and `silver-mdm-gold` SeedUniverse states
reference warehouse large. Neither medium path has a post-fix execution in
this window, so its current definition is not successful sizing evidence.

### Live trigger evidence

- No current EventBridge rule with the production name prefix was present.
- No current EventBridge Scheduler schedule with the production name prefix
  was present.
- Repository code can create daily and backstop EventBridge rules for
  `daily-incremental`, but that capability was not configured at capture time.
- Of 114 parent execution inputs, 21 declared `trigger=operator`, three used a
  named release-readiness trigger, and 90 omitted trigger provenance.
- All 114 parent executions had `redriveCount=0`.

Therefore the current live portfolio has no proven recurring trigger. The 90
inputs without a trigger field establish direct API starts but do not prove
whether a human, script, CI job, or another external caller initiated them.
Caller attribution remains an audit gap.

### Thirty-day execution and retry distribution

`Runs S/F/A` reports total, succeeded, failed, and aborted parent executions.
Durations use terminal parent wall-clock time and nearest-rank p50/p95,
separated by successful and unsuccessful status. `Retry executions/attempts`
counts an exact `TaskFailed` event immediately followed by a `TaskScheduled`
event linked to that failed event. It does not count command-internal retries.

| Workflow | Runs S/F/A | Active days | Success p50/p95 | Unsuccessful p50/p95 | Retry executions/attempts | Latest |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `bootstrap-batched` | 0 0/0/0 | 0 | -/- | -/- | 0/0 | - |
| `bootstrap-full` | 0 0/0/0 | 0 | -/- | -/- | 0/0 | - |
| `bootstrap` | 1 1/0/0 | 1 | 4.2h/4.2h | -/- | 1/3 | 2026-07-30 |
| `bronze-seed-silver-gold` | 37 1/26/10 | 11 | 5.3h/5.3h | 48.7m/14.4h | 3/7 | 2026-08-08 |
| `catch-up-daily-form-index` | 0 0/0/0 | 0 | -/- | -/- | 0/0 | - |
| `daily-incremental` | 13 3/6/4 | 7 | 4.8h/7.1h | 3.8h/19.6h | 8/25 | 2026-08-04 |
| `full-reconcile` | 0 0/0/0 | 0 | -/- | -/- | 0/0 | - |
| `generation-build` | 1 1/0/0 | 1 | 6.6m/6.6m | -/- | 0/0 | 2026-07-22 |
| `gold-refresh` | 4 4/0/0 | 4 | 3.7m/4.2m | -/- | 0/0 | 2026-08-09 |
| `load-daily-form-index-for-date` | 0 0/0/0 | 0 | -/- | -/- | 0/0 | - |
| `load-history` | 13 2/8/3 | 4 | 1.1m/1.7m | 64.4m/11.1h | 4/10 | 2026-08-09 |
| `mdm-backfill-relationships` | 13 9/4/0 | 4 | 1.4m/99.4m | 7.6m/57.9m | 5/9 | 2026-08-09 |
| `mdm-check-connectivity` | 3 3/0/0 | 2 | 1.1m/1.4m | -/- | 0/0 | 2026-07-19 |
| `mdm-counts` | 2 2/0/0 | 2 | 1.2m/1.8m | -/- | 0/0 | 2026-08-09 |
| `mdm-gold` | 0 0/0/0 | 0 | -/- | -/- | 0/0 | - |
| `mdm-migrate` | 3 3/0/0 | 2 | 1.4m/1.4m | -/- | 0/0 | 2026-08-09 |
| `mdm-run` | 6 3/3/0 | 2 | 2.5m/22.2m | 10.3m/10.6m | 3/6 | 2026-08-09 |
| `mdm-seed-from-silver` | 0 0/0/0 | 0 | -/- | -/- | 0/0 | - |
| `mdm-seed-universe` | 0 0/0/0 | 0 | -/- | -/- | 0/0 | - |
| `mdm-sync-graph` | 6 4/2/0 | 3 | 1.4m/1.5m | 6.4m/7.2m | 2/4 | 2026-08-09 |
| `mdm-verify-graph` | 4 1/3/0 | 3 | 4.5m/4.5m | 15.2m/17.3m | 3/6 | 2026-08-09 |
| `ownership-mdm-gold` | 1 0/0/1 | 1 | -/- | 18.0m/18.0m | 0/0 | 2026-07-25 |
| `residual-holds-graph` | 2 0/2/0 | 1 | -/- | 9.7m/83.8m | 2/5 | 2026-07-25 |
| `seed-universe` | 1 1/0/0 | 1 | 6.7m/6.7m | -/- | 0/0 | 2026-07-31 |
| `silver-mdm-gold` | 0 0/0/0 | 0 | -/- | -/- | 0/0 | - |
| `targeted-resync` | 4 1/3/0 | 1 | 1.6m/1.6m | 20.2m/24.4m | 3/6 | 2026-08-04 |

Across the window, the portfolio recorded 114 parent executions: 39
`SUCCEEDED`, 57 `FAILED`, and 18 `ABORTED`. Thirty-four executions performed
81 Step Functions task retry attempts after 114 task failures. Nine live
workflows had no execution. These are orchestration outcomes only; catches,
partial output, stale active generations, and missing consumer freshness can
make a `SUCCEEDED` execution insufficient evidence of value.

### Current definition, task, and command binding

The table records the exact current Step Functions revision ID, SHA-256 of
canonicalized ASL, every referenced task-definition revision, and normalized
ECS command operations. Dynamic arguments and environment-specific resource
names are intentionally omitted; the source trace above cites their owning
builders and command implementations.

| Workflow | Definition revision / ASL SHA-256 | Task definitions | ECS command operations |
| --- | --- | --- | --- |
| `bootstrap-batched` | `ca87bc25-248b-4637-9718-9f0c03c86a4a` / `6c0a59ada1be544551ba4668458769bef79ea0f47462f470708d6b1ef7822e4d` | `edgartools-prod-medium:173` | `bootstrap-batch`, `seed-universe` |
| `bootstrap-full` | `4bd208a1-033e-4b85-8f27-6f3c1d1be589` / `0c8edc0cc7dff2834bac3a7a5c75905403230af526d8ea4c8f3633fe5aa1ef03` | `edgartools-prod-large:165` | `acquire-sec-fetch-lease`, `bootstrap-full`, `release-sec-fetch-lease` |
| `bootstrap` | `ccef84cc-d965-4a43-ae5d-ce554c7c4de0` / `f0e0042547ee83d48f18cfef2eb2a3729c9c4e1cc1ecd4ca31c3d77796e80d43` | `large:165`, `medium:173`, `mdm-medium:145`, `mdm-small:145` | `acquire/release-sec-fetch-lease`, `seed-universe`, `bootstrap`, `mdm run/backfill/export/sync/verify`, `gold-refresh` |
| `bronze-seed-silver-gold` | `e993e08a-1dd4-4585-9bbc-967fed886a59` / `a37ff042656f35d18d1a6cf57a4093ce934998ce6669baae10d76a854b8e8d63` | `large:165`, `medium:173`, `mdm-medium:145`, `mdm-small:145` | `seed-bronze-batches`, `bootstrap-batch`, `compute-remaining-batches`, `mdm run/backfill/export/sync/verify/activate`, `verify-insider-coverage`, `reconcile-relationship-release`, `gold-refresh` |
| `catch-up-daily-form-index` | `ece86ae1-c8d2-4d6e-8866-4703cdb3c1c0` / `e92e9283eaf8d6444063df9ad64f63b4eeaa26a26d3a42ebcb7154b8eefcfc64` | `small:168` | `catch-up-daily-form-index` |
| `daily-incremental` | `ef06a003-db96-4d29-bfe2-ece5345d69a4` / `85f34e83ad20b4656dc5b64d4de5433abdd85e9d7047da8b5d7bc9a79e702b9e` | `large:165`, `medium:173`, `mdm-medium:145`, `mdm-small:145` | identity/sec leases, identity windows, `bootstrap-fundamentals`, `daily-incremental`, ADV/roster fetch and ingest, `mdm run/backfill/export/sync/verify`, `gold-refresh` |
| `full-reconcile` | `2f9e5512-46d2-4779-95cd-b48348fde22e` / `9888c389dbac347d148aa0d563c82add5540eefbd8fecf6c188e33baa41e8f96` | `large:165` | `full-reconcile` |
| `generation-build` | `06aecf6e-729c-424e-b73f-8f73a38b3957` / `224ee74938c0303a9988e1078749542de9933b6b90f05fd64e7fbae70011e0ef` | `mdm-medium:145`, `mdm-small:145` | `mdm generation-plan/build-partition/fan-in/retry-failed-partitions/activate` |
| `gold-refresh` | `e815418b-e83a-458e-b9b4-94f5ff5157e1` / `bdf22844a63fd9520c7a63ba8dc0cb346479e5585fd729f873a89d29c310cd42` | `large:165` | `gold-refresh` |
| `load-daily-form-index-for-date` | `93164d1b-0e25-4761-a36d-b7673c11469c` / `a2a439b8559c9808a54a6b1db87bb60604c14e20440604e43ed344dc8e2ec950` | `small:168` | `load-daily-form-index-for-date` |
| `load-history` | `9858e4fa-8e1f-45f0-bb65-f2669414549a` / `8d1134ac71578ab2e6160b79411cf3501789c4c4f43c917f5bb30afae202892c` | `large:165`, `medium:173`, `mdm-medium:145`, `mdm-small:145` | sec lease, `seed-universe`, `mdm seed-universe`, windows and four bootstrap modes, ADV/roster fetch and ingest, `mdm run/backfill/export/sync/verify`, `gold-refresh`, run summary |
| `mdm-backfill-relationships` | `84d6cc09-c7ff-4ea7-9d7a-a897f5853f0a` / `25b96b6e9d93a93503a4185676ca77a526a302697b2ba25e063da5c409a93c57` | `mdm-medium:145` | `mdm backfill-relationships` or `derive-relationships` |
| `mdm-check-connectivity` | `24c0144d-3345-4e13-820a-b8cf3efd885a` / `7dd46b0aac7dc06e504a502321680feb85cbe6f5727e2f143023b9def5b27959` | `mdm-small:145` | `mdm check-connectivity` |
| `mdm-counts` | `e3c1b106-a69b-4938-b681-5986286c3af3` / `c417ccb7e37a5c6aee863866656bac2cbacb3eba6b1bced00133a54751457efb` | `mdm-small:145` | `mdm counts` |
| `mdm-gold` | `113bb1eb-7841-4f3e-bd12-f3ae62402e10` / `05cd45b3a55ec741ef081ce081d5fdb4014b82b28456f9a7876a1ced0ce02c98` | `large:165`, `mdm-medium:145`, `mdm-small:145` | `mdm run/backfill/export/sync/verify`, `gold-refresh` |
| `mdm-migrate` | `c93d7be6-519a-4c48-ba29-d322b1baeae0` / `2d3ffbaad9d20813d3596aa7a8f4b69bd3d4d966b7d6f23b41741f43637a89c9` | `mdm-small:145` | `mdm migrate` |
| `mdm-run` | `f7e64615-3423-4aa3-a23e-4aa82d1e5d8d` / `b73edb3e7f7db35e2f6006df8308f26da7ae1e718047f6313280bff791476ac4` | `mdm-medium:145` | `mdm run` |
| `mdm-seed-from-silver` | `3cd22451-0fb8-4fe4-8f6b-0eebe1541fcf` / `c5a776d9df3dff48e91c4cd678ae1a5eed0b5705071d7f468492d5b3745d6255` | `mdm-small:145` | `mdm seed-from-silver` |
| `mdm-seed-universe` | `2ba17e93-e21b-4eab-9284-8fdda38d732a` / `61a5d50a802f84b905ff8309f4cf6392f001ac016936aafbbd62839f92e634f4` | `mdm-small:145` | `mdm seed-universe` |
| `mdm-sync-graph` | `08e47dd4-07e9-4dd5-a2ca-9dfd1446d359` / `d4d1556de6b7e094f95f99e2be8cfc73cb8c1ad6885abeb198b5d5553c631627` | `mdm-medium:145` | `mdm sync-graph` |
| `mdm-verify-graph` | `bc764d66-6f1c-4f5e-80d5-2374a54d1072` / `a2683fcf970c000a1010b3800642349b1a298130f350258dbb087911e2165b06` | `mdm-small:145` | `mdm verify-graph` |
| `ownership-mdm-gold` | `aa72757b-d0ff-433d-9a1a-81dbaf7014fd` / `6c3fdf0648098f408b1ff0f4400c3559249dbfaa28c9f858cbc13eeed0a295f5` | `large:165`, `medium:173`, `mdm-medium:145`, `mdm-small:145` | `parse-ownership-bronze`, person and insider MDM stages, export/sync/verify, `gold-refresh` |
| `residual-holds-graph` | `c01c4f13-3903-4e7f-bc0d-6dbf3b2955b3` / `f73ef47ed5de9698328b2ab862d29d308cce02a45c826b5b65405bcefc8ae811` | `mdm-large:79`, `mdm-small:145` | security/person MDM, four relationship types, export, generation-scoped sync/verify |
| `seed-universe` | `a66aca41-2574-4a73-b0c4-7ac5b96b4e9e` / `3cbbf63940c69fb830e350404bd2f9db46ef3bba88b9b48b28f26302c260993a` | `medium:173` | `seed-universe` |
| `silver-mdm-gold` | `2933c309-3c59-4236-ad76-60c58f0f9823` / `2b27b28801df00237f68ecc0a175f6a6f6a4fe55c0364319121a65fe14f5182a` | `large:165`, `medium:173`, `mdm-medium:145`, `mdm-small:145` | `seed-universe`, `seed-silver-batches`, `bootstrap-batch`, `mdm run/backfill/export/sync/verify`, `gold-refresh` |
| `targeted-resync` | `bf348f67-2a71-4b23-9b9c-cab33efe4dee` / `7961d9d261ff9163257d74156fd6aae56cfa0b3060929bb06fb1e363ca8ff471` | `large:165` | sec lease and `targeted-resync` |

## Material gaps and cost-sizing implications

1. **Seven ordinary MDM composite paths produce a graph candidate with no proven active consumer.** `load_history`, `bootstrap`, `daily_incremental`, `mdm_gold`, `ownership_mdm_gold`, `silver_mdm_gold`, and the ordinary `bronze_seed_silver_gold` branch call bare `sync-graph`, then bare `verify-graph`, and contain no `graph-activate` state (`infra/scripts/deploy-aws-application.sh:2908-2925`, `infra/scripts/deploy-aws-application.sh:4516-4523`, `infra/scripts/deploy-aws-application.sh:4596-4600`, `infra/scripts/deploy-aws-application.sh:4030-4034`). Bare sync creates a fresh, unactivated UUID (`edgar_warehouse/mdm/cli.py:97-103`), while bare verification/review resolves the active generation (`edgar_warehouse/mdm/cli.py:304-309`, `edgar_warehouse/mdm/cli.py:1548-1560`). The strict bronze release path is the source-proven exception (`infra/scripts/deploy-aws-application.sh:4085-4112`).

2. **`generation_build` has no evidenced bridge to production graph consumers.** Its source explicitly says the workflow is standalone and not wired to the shared Snowflake activation pointer (`infra/scripts/deploy-aws-application.sh:4770-4773`). Its internal generation files/status may be useful for future work, but the present repository does not prove a consumer.

3. **`residual_holds_graph` deliberately stops before activation.** It proves candidate production and candidate verification, but activation is operator-driven (`infra/scripts/deploy-aws-application.sh:4657-4658`). Active-only graph review, decision-contract, and dashboard views cannot consume the candidate before that handoff (`infra/snowflake/sql/graph_review/01_graph_review_contract.sql:99-136`, `infra/snowflake/sql/decision_contract/03_dashboard_contract.sql:39-45`, `infra/snowflake/sql/decision_contract/03_dashboard_contract.sql:78-84`).

4. **`bootstrap_batched` is not an end-to-end publishing workflow.** Its definition ends at parallel bootstrap batches (`infra/scripts/deploy-aws-application.sh:1821-1850`); `mdm_gold` is only a documented manual continuation (`infra/scripts/deploy-aws-application.sh:4483-4484`). Cost/value analysis should not attribute Snowflake/dbt/dashboard delivery to a `bootstrap_batched` execution unless the continuation is separately evidenced.

5. **Three utility workflows are primarily control-plane evidence.** `mdm_check_connectivity` and `mdm_counts` have proven audit/operator consumers but no durable business-data consumer (`infra/scripts/audit-mdm-snowflake-postgres-cutover.py:425-444`). `mdm_migrate` is a proven prerequisite in the E2E sequence, not a direct data product (`infra/scripts/run-aws-mdm-e2e.sh:224-229`). They should be valued as safety/operability gates rather than dashboard-data producers.

6. **`mdm_seed_from_silver` has no evidenced caller, and several standalone warehouse repair/index workflows have no source-proven schedule.** Their definitions establish capability, but repository sources do not establish production frequency or current necessity (`infra/scripts/deploy-aws-application.sh:4397-4414`, `infra/scripts/deploy-aws-application.sh:4784-4801`).

7. **Live execution status does not prove usable output.** The read-only pass now
   establishes current definitions, task/image identities, starts, recency,
   terminal status, duration, and Step Functions task retries. It does not yet
   bind each successful execution to its S3 manifest, Snowflake load, dbt
   freshness, active graph pointer, dashboard visibility, or operator receipt.
   Those output-level checks remain required before Ticket 11 can resolve.

## Coverage statement

All 26 state-machine registrations in `deploy-aws-application.sh` and all 26
live production definitions are represented above. The trace covers their
current task/image bindings, recent parent executions, Step Functions retries,
CLI/application commands, warehouse and MDM artifacts, Snowflake manifest
ingestion and triggered refresh, dbt source/model reads, both Streamlit
consumer surfaces, repository schedules, operator scripts/runbooks, and
structural tests. Consumer classification is intentionally artifact-specific:
a workflow can have proven relational/gold consumers while its graph candidate
remains unconsumed. Final acceptance remains pending the audit gates recorded
in Ticket 11.
