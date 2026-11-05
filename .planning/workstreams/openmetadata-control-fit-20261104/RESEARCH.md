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

## Earlier local evidence (2026-11-04 morning snapshot)

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
5 are corrections, but both kinds become OpenMetadata test cases. They are
attached to 23 assets (maximum 8 cases on one asset), with corrections on two
assets. This can make the Test Cases surface imply that a correction is
executable or has a pass/fail result; these counts describe plan density, not
the rendered UI, which has not been visually inspected.
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

## Post-reset baseline before publish (2026-11-04 evening)

The local instance was fully reset and redeployed from the repository's compose
file. PostgreSQL, Elasticsearch and the OpenMetadata server are healthy on
version 2.0.2. The fresh authenticated API inventory has 0 domains, glossaries,
terms, database services, pipeline services, products and test cases; 25
built-in test definitions remain, and no domain named `Shared` exists. The
current Rules plan has 8 domains, 8 glossaries, 22 terms, 66 assets, 2 quality
definitions, 55 cases (50 checks and 5 fixes), 3 products, 21 catalog pipelines
and 134 planned lineage edges. These are configured counts; the plan has not
been published to this fresh instance. The independent read-only `rules catalog
check` found 216 differences, returned `partial`, and exited 1; its report says
`publish: not_run`. It covers the database service, databases, schemas, tables,
pipelines and table lineage, not every configured domain, glossary, product,
quality object or lineage family.

The first configured token could read inventory but had no catalog write role.
The first `rules catalog publish` request was rejected with HTTP 403 before any
write completed. This was the pre-publish baseline; the successful administrator
login and subsequent verification are recorded below.

## Post-publish verification (2026-11-04 21:43 ET)

The skill login flow created a local administrator access token in the current
process; API readback confirmed `isAdmin=true`. The token was not printed or
saved. At 21:43 ET, `rules catalog publish --root rules` issued 480 write
requests and returned `confirmed`: publisher readback matched, with 0 removals.
The result does not report created/updated counts
(`created_updated_counts: unavailable`). The independent read-only
`rules catalog check --root rules` returned `confirmed`, found 0 differences,
and exited 0.

At 21:48 ET, independent native API inventory matched the configured catalog: 8 domains,
8 glossaries, 22 terms, 1 database service, 1 pipeline service, 3 products,
66 tables, 21 pipelines, 2 configured test definitions (plus 25 built-ins),
and 55 test cases. There is no domain, glossary or tag named `Shared`. Domain
names and types, glossary names and domain assignments, term FQNs, and all 18
table-domain memberships match the plan. Product memberships match exactly: 13
table assets and 10 input ports across the 3 products. Readback confirmed 22
glossary relations, 51 domain-to-table edges and 31 pipeline-to-table edges;
the publisher and independent check confirmed all 30 table-lineage edges. All
134 planned lineage edges are accounted for. No quality-results file was
supplied; these metadata test cases do not execute the Rules checks or fixes.

This confirms catalog publication and configured lineage, not execution of the
described pipelines. The fresh 2.0.2 schema still separates catalog `Pipeline`
metadata from runnable ingestion workflows. The compose stack contains no
ingestion runner, and a repository scan finds no OpenMetadata references in
Bookkeeping or worker modules. OpenMetadata therefore cannot control this
platform's data operations without an integration or a change to its execution
path. Visual UI clarity remains unverified because repository instructions
prohibit browser and GUI interaction.

## Fit by requirement

| Requirement | Finding | Evidence and limit |
|---|---|---|
| Data catalog | **Fits as a projection; current publish is confirmed.** | Publisher readback and independent check both matched. Native API comparisons also matched exact domains/types, glossaries/domain links, term FQNs, 18 table-domain memberships, all product assets/input ports and every lineage family (30 table, 31 pipeline, 51 domain, 22 glossary edges). No `Shared` domain, glossary or tag exists. The publisher does not report created/updated counts, and Rules remains the source of truth; catalog refresh does not execute described pipelines. |
| Data engineering control | **Partial and integration-specific; does not fit this platform as deployed.** | The live 2.0.2 schema exposes catalog `Pipeline` status, metrics, trends and observability, but no run trigger. Ingestion-pipeline triggers run metadata workflows. OpenMetadata runs its own metadata and quality workflows through configured Airflow/Kubernetes runners. Current 2.0.x docs also say the dbt Cloud integration can execute models; dbt Core integration reads artifacts produced by a separate dbt run. This repository uses its Snowflake dbt project and has no dbt Cloud configuration. The local OpenMetadata instance has no ingestion runner configured. |
| Data operations control | **Does not fit without integration or replacement.** | The platform's source sequence executes through Bookkeeping workers. A repository scan finds OpenMetadata references only in the Rules catalog adapter/CLI, with none in the Bookkeeping or worker packages. OpenMetadata has no existing handoff into those run, merge, load, journal, retry and recovery operations. This is supported by the configured execution path, the code scan and the local API/runner inventory. |
| Data quality | **Native feature exists, but these Rules cases are metadata, not runnable checks.** | The current plan and API inventory contain 55 cases (50 checks, 5 fixes) and 2 configured `Other` definitions; their descriptions say OpenMetadata does not execute them. The latest-results API returned HTTP 204 with no result body, and publication supplied no results file. The `CustomDatabase` service has no connection config and the local deployment has no ingestion runner. A supported executable definition or external executor is required to run checks and publish results. |
| Data contracts | **Partial governance capability.** | A draft request validation was tested without creating a contract. Current official 2.0.x docs describe persisted validation and quality-test execution; that persisted path has not been tested on this 2.0.2 server. It currently has zero contracts. Security and SLA sections document expectations; they are not enforced by contract runs. |
| No custom build | **Fails for the full objective.** | Some supported workflows can be configured without a custom connector, including OpenMetadata metadata/quality workflows and the documented dbt Cloud integration. They require their supported runner, service connection, artifacts or existing dbt Cloud jobs. None provides a no-build trigger for this platform's Bookkeeping operations. Controlling those operations requires an integration or moving the execution path to a supported orchestrator. |
| Clear, uncluttered end-user experience | **CLI output is concise; UI clarity is unverified.** | On 2026-11-04, `plan --root rules >/dev/null` and `check --root rules >/dev/null` each produced one concise status line while hiding structured JSON. This is a scannable terminal path, not proof the rendered UI is visually clear. Repository instructions prohibit browser automation and GUI interaction, so the local UI has not been reviewed. |

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
  instance. Post-reset baseline, confirmed publication, independent readback,
  full object-family comparisons and the remaining control/UI limits are
  recorded in `.planning/workstreams/openmetadata-sync-20261104/TICKET.md`.
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
