# OpenMetadata no-build control-plane fit

## Question and decision

Can the installed OpenMetadata deployment control the Rules catalog, data
engineering pipelines, and Bookkeeping operations with no custom build, while
remaining clear and uncluttered for end users?

**Decision: no for the full requirement.** OpenMetadata fits as the catalog and
can provide metadata governance. It can also run supported metadata-ingestion
and data-quality workflows when connected to their data sources and an
execution service. The checked deployment cannot run those workflows, and
OpenMetadata does not trigger this platform's Bookkeeping pipelines. The local
UI's visual clarity remains unverified under the repository's no-browser/no-GUI
rule.

## Current local evidence

The local API health endpoint reports OpenMetadata 2.0.2. The workstream records
a catalog-only reset, republish and authenticated API inventory earlier on
2026-11-04. The unauthenticated local `/swagger.json` schema was rechecked at
09:37 ET: catalog `Pipeline` exposes CRUD, status read/write, metrics, trends
and observability routes, but no run trigger. In contrast, `ingestionPipelines`
exposes trigger, deploy and kill routes; Apps and governance workflow definitions
also have their own trigger routes. Those routes execute their own workflow
types and do not trigger the platform's catalog `Pipeline` or Bookkeeping
targets.

| Catalog measure | Rules plan / prior inventory |
|---|---:|
| Domains | 8 |
| Glossaries | 8 |
| Glossary terms | 22 |
| Assets/tables | 65 |
| Configured quality definitions | 2 |
| Configured quality cases | 52 |
| Data products | 3 |
| Catalog pipelines | 20 |
| Planned table / pipeline / domain / glossary lineage | 30 / 30 / 51 / 22 |
| Total planned lineage edges | 133 |
| `Shared` domains / glossaries in the prior inventory | 0 / 0 |

These counts are not all covered by the CLI's automated readback. `verify()`
checks the database service, database and schema inventory, tables, pipelines
(including tasks), table lineage, profiles, selected table tags/certifications,
and quality results only when a results file is supplied. It does not verify
domain or glossary content and associations, products and their assets/input
ports, quality definitions/cases, domain lineage, pipeline-to-table lineage,
or every table annotation. The earlier API inventory recorded entity counts and
the absence of `Shared`; it does not establish field-by-field equality for all
those objects. Treat the plan/readback as confirmed only for the dimensions
actually checked.

The prior authenticated API checks after refresh found zero latest results for
the 52 configured quality cases and zero Data Contracts. The two configured
quality definitions use the `Other` platform and explicitly state that
OpenMetadata does not execute them. Of the 52 planned cases, 47 are checks and
5 are corrections, but both kinds become OpenMetadata test cases. This can make
the Test Cases surface imply that a correction is executable or has a
pass/fail result; the local UI presentation has not been visually inspected.
The database service is
`CustomDatabase` with no connection; the pipeline service is `CustomPipeline`
with no connection. The deployment has zero ingestion pipelines and sets
`PIPELINE_SERVICE_CLIENT_ENABLED=false`. Its compose file has the OpenMetadata
server, PostgreSQL, Elasticsearch and migration services, with no Airflow or
other ingestion runner.

There are seven installed applications, including an enabled
`DataContractValidationApplication` scheduled with cron `0 0 * * *`. Its API
descriptor says it does not support an ingestion runner. There are 19 governance
workflow definitions. Neither count establishes a runner for source capture,
MDM, RDM, Silver or Bookkeeping.

## Fit by requirement

| Requirement | Finding | Evidence and limit |
|---|---|---|
| Data catalog | **Fits as a projection; full object-level confirmation remains incomplete.** | Rules publication and catalog-only rebuild succeeded. The automated readback confirms tables, pipelines/tasks and table lineage, but not every domain, glossary, product, quality object or lineage family. The prior authenticated inventory recorded counts and no `Shared` domain/glossary. The configured Rules model remains authoritative; a catalog refresh does not execute described pipelines. |
| Data engineering control | **Partial and integration-specific; does not fit this platform as deployed.** | The live 2.0.2 schema exposes catalog `Pipeline` status, metrics, trends and observability, but no run trigger. Ingestion-pipeline triggers run metadata workflows. OpenMetadata runs its own metadata and quality workflows through configured Airflow/Kubernetes runners. Current 2.0.x docs also say the dbt Cloud integration can execute models; dbt Core integration reads artifacts produced by a separate dbt run. This repository uses its Snowflake dbt project and has no dbt Cloud configuration. The local OpenMetadata instance has no ingestion runner configured. |
| Data operations control | **Does not fit without integration or replacement.** | The platform's source sequence executes through Bookkeeping workers. A repository scan finds OpenMetadata references only in the Rules catalog adapter/CLI, with none in the Bookkeeping or worker packages. OpenMetadata has no existing handoff into those run, merge, load, journal, retry and recovery operations. This is supported by the configured execution path, the code scan and the local API/runner inventory. |
| Data quality | **Native feature exists, but the current 52 Rules cases are not executable by OpenMetadata.** | The publisher uses two custom `Other` test definitions whose descriptions explicitly say OpenMetadata does not execute them. Of the cases, 47 are checks and 5 are corrections; publishing corrections as test cases risks confusing metadata with an executable action. The instance also has no real database connection or ingestion runner and no latest results. A connection alone is insufficient: each rule needs a supported executable definition or an external executor that runs it and publishes results. |
| Data contracts | **Partial governance capability.** | A draft request validation was tested without creating a contract. Current official 2.0.x docs describe persisted validation and quality-test execution; that persisted path has not been tested on this 2.0.2 server. It currently has zero contracts. Security and SLA sections document expectations; they are not enforced by contract runs. |
| No custom build | **Fails for the full objective.** | Some supported workflows can be configured without a custom connector, including OpenMetadata metadata/quality workflows and the documented dbt Cloud integration. They require their supported runner, service connection, artifacts or existing dbt Cloud jobs. None provides a no-build trigger for this platform's Bookkeeping operations. Controlling those operations requires an integration or moving the execution path to a supported orchestrator. |
| Clear, uncluttered end-user experience | **Unverified.** | Repository instructions prohibit browser automation and GUI interaction. API counts and CLI summaries do not prove that the local UI is visually clear. The plan command also emits thousands of lines of JSON after its status line. |

### Data Contract detail

The local `POST /api/v1/dataContracts/validate` test checked a draft contract
against existing metadata and left the contract inventory empty. Current
OpenMetadata 2.0.x documentation distinguishes this from a persisted contract
run: persisted validation checks schema and semantics and starts a test-suite
pipeline when the contract has quality expectations. That run behavior is
documented, not verified on the local 2.0.2 server. No contract or quality
pipeline was created or triggered for this review.

OpenMetadata's 2.0.x contract specification also says security expectations are
not enforced, and SLA values are not evaluated by a contract run. This prevents
the contract feature from serving as a complete operational policy or SLA
enforcement layer.

## Recommendation

Use OpenMetadata for discovery, domains, glossary, products, lineage and
governance. Consider its no-code data-quality experience only after a real
source connection and compatible runner are in place and a test result is read
back. Keep Bookkeeping as the owner of platform run state unless the operator
explicitly approves building an integration or replacing that execution path.

Do not approve the full requirement as “plug and play”: the data-engineering and
data-operations control requirement is contradicted by the live deployment
state. Do not claim the UI is clear or uncluttered until a permitted visual
review is completed.

## Sources

- Local version and catalog/API readback: OpenMetadata API at the local 2.0.2
  instance; earlier authenticated inventory and reset evidence are summarized
  in `TICKET.md`. Fresh authenticated inventory is pending because this session
  has no `OPENMETADATA_TOKEN`.
- Local execution API schema: the running instance's `/swagger.json`; catalog
  Pipeline has status and observability routes but no run trigger, while
  ingestion, app and governance workflow types expose their own trigger routes.
- Local runner configuration: [`infra/openmetadata/docker-compose.yml`](../../../infra/openmetadata/docker-compose.yml).
- Local OpenMetadata capability and execution boundaries:
  [`skills/openmetadata/SKILL.md`](../../../skills/openmetadata/SKILL.md).
- Platform execution sequence: the configured source targets and ordered steps
  in Rules, executed through Bookkeeping workers.
- [OpenMetadata 2.0.2 release](https://github.com/open-metadata/OpenMetadata/releases/tag/2.0.2-release).
- [OpenMetadata 2.0.x data-quality guide](https://docs.open-metadata.org/v2.0.x/how-to-guides/data-quality-observability/quality).
- [OpenMetadata 2.0.x ingestion execution options](https://docs.open-metadata.org/v2.0.x/deployment/ingestion).
- [OpenMetadata 2.0.x dbt workflow](https://docs.open-metadata.org/v2.0.x/connectors/database/dbt/configure-dbt-workflow) and [dbt Cloud configuration](https://docs.open-metadata.org/v2.0.x/connectors/database/dbt/dbt-cloud-api-guide). These describe an integration-specific dbt Cloud execution path; they do not show it is configured locally.
- [OpenMetadata 2.0.x Pipeline API](https://docs.open-metadata.org/v2.0.x/api-reference/data-assets/pipelines) lists create, read, update and delete operations for catalog pipeline entities; it does not document a run trigger for those entities.
- [OpenMetadata 2.0.x Data Contract specification](https://docs.open-metadata.org/v2.0.x/how-to-guides/data-contracts/spec).

The 2.0.x documentation references describe that documentation line; persisted
Data Contract execution was not verified on the local 2.0.2 server.
