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

The local API reports OpenMetadata 2.0.2. Following the catalog-only reset and
refresh, the Rules plan, publisher readback and independent read-only check
matched. The unauthenticated local `/swagger.json` schema was also inspected
against the running server: catalog `Pipeline` exposes CRUD, status read/write,
metrics, trends and observability routes, but no run trigger. In contrast,
`ingestionPipelines` exposes trigger, deploy and kill routes; Apps and governance
workflow definitions also have their own trigger routes. Those routes execute
their own workflow types and do not trigger the platform's catalog `Pipeline`
or Bookkeeping targets.

| Catalog measure | Current count |
|---|---:|
| Domains | 8 |
| Glossaries | 8 |
| Glossary terms | 22 |
| Assets/tables | 65 |
| Configured quality definitions | 2 |
| Configured quality cases | 52 |
| Data products | 3 |
| Catalog pipelines | 20 |
| Table / pipeline / domain / glossary lineage | 30 / 30 / 51 / 22 |
| Total configured lineage edges | 133 |
| `Shared` domains / glossaries | 0 / 0 |

Independent API checks after refresh found zero latest results for the 52
configured quality cases and zero Data Contracts. The database service is
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
| Data catalog | **Fits as a projection.** | Rules publication, table/pipeline readback and the catalog-only rebuild succeeded. The configured Rules model remains authoritative. A catalog refresh does not execute the described pipelines. |
| Data engineering control | **Partial and integration-specific; does not fit this platform as deployed.** | The live 2.0.2 schema exposes catalog `Pipeline` status, metrics, trends and observability, but no run trigger. Ingestion-pipeline triggers run metadata workflows. OpenMetadata runs its own metadata and quality workflows through configured Airflow/Kubernetes runners. Current 2.0.x docs also say the dbt Cloud integration can execute models; dbt Core integration reads artifacts produced by a separate dbt run. This repository uses its Snowflake dbt project and has no dbt Cloud configuration. The local OpenMetadata instance has no ingestion runner configured. |
| Data operations control | **Does not fit without integration or replacement.** | The platform's source sequence executes through Bookkeeping workers. OpenMetadata has no connector or trigger for those run, merge, load, journal, retry and recovery operations. This is an inference from the configured execution path and the local API/runner inventory. |
| Data quality | **Native feature, not currently runnable here.** | OpenMetadata documents no-code tests and quality workflows, but this instance has no real database connection or ingestion runner; its 52 cases have no results. Definition presence is not execution evidence. |
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
  instance; evidence summarized above and in `TICKET.md`.
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
