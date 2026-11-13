---
name: openmetadata
description: Write and read this platform's catalog on OpenMetadata. Use before rules catalog publish, a catalog reset, or any OpenMetadata API call. Business meaning stays in the data-catalog skill.
---

# OpenMetadata

This is the only place for OpenMetadata implementation. Business meaning, the
subject domains, the glossary words, and what a relationship type is stay in
the data-catalog skill. This skill says how that meaning is stored on
OpenMetadata 2.0.7. Normal publication uses `rules catalog publish`; scoped
repair of unsupported metadata relationships follows the procedure below.

The `/lineage` page is the service view. It is not the platform architecture
diagram: that page names Capture, Bookkeeping, workers, MDM, Silver and Gold.
This canvas shows one PipelineService per source or standalone pipeline, plus
the database service. Each service and pipeline has a short `displayName`; the
technical name stays the identity. Do not delete a service by hand; the
DatabaseService stays.

What belongs on a target's graph is the
[data-governance lineage skill](../data-governance/LINEAGE.md). This skill
stores that picture. Do not add a pipeline or an edge to force a task onto
the canvas.

For a target's exact graph, read
`GET /api/v1/lineage/pipeline/name/<URL-encoded-FQN>?upstreamDepth=0&downstreamDepth=1`.
Column-by-column table lineage is on the table's Lineage tab and at
`GET /api/v1/lineage/table/name/<URL-encoded-FQN>?upstreamDepth=1&downstreamDepth=1`.

Write a plain display name and a plain first sentence on every domain, table,
product, relationship type, PipelineService and Pipeline. The technical name
stays the identity. Do not open a description with a file path, a rules version,
or a JSON list. A person
should understand the first sentence without knowing the rules layout.

Read the target's running version from `GET /api/v1/system/version`. The local
service was verified on 2.0.7; the versioned schemas below match it. When a
target differs, check that release's schema and API behavior before publishing.
Treat rolling documentation as concept guidance, not proof of the installed
API. For the local instance, use its private `.env` login and PAT as described
in [Local server and rebuilds](LOCAL-SERVER.md); hosted instances use their
authorized bot credentials.

Run the repository initializer before using the local catalog. It clears all
active AI Governance entities through the native API and verifies zero active
entities on readback. The exact collection scope and soft-delete behavior are
documented in [Local server and rebuilds](LOCAL-SERVER.md). Do not skip this
step or recreate AI demo objects manually.

## Native objects and their connections

| Native object | Meaning and mapping |
|---|---|
| Domain | Subject ownership/organization, independent from service containment. Choose its required `domainType` from the versioned schema and configured governance policy, not from the entity's name. |
| Glossary / GlossaryTerm | Vocabulary container and concepts. A term FQN includes its glossary and parent path; a UUID and FQN are native identities, not portable business keys. |
| Classification / Tag | Category taxonomy and assigned categories. Use a configured taxonomy for processing layers; do not conflate its tags with glossary terms. |
| DatabaseService → Database → DatabaseSchema → Table → Column | Technical containment. A logical registration is metadata, not proof a physical database table exists. |
| PipelineService → Pipeline → Task | Declared processing and dependencies. Pipeline lineage association must be published in addition to tasks. A metadata-ingestion pipeline is a different workflow from the data pipeline it describes. |
| DataProduct | Configured consumer-facing asset collection, assigned to domains. Create one only when the data-catalog model says a product definition exists. |
| TestDefinition / TestCase / TestSuite | Reusable check definition, asset-specific configured check and grouping. Actual results are separate. |

The pinned domain types are `Source-aligned`, `Consumer-aligned` and `Aggregate`.
This required native attribute is not the logical subject identity.

Master-data subject domains use `Source-aligned`. The operator approved that
type for every domain `CONTEXT.md` names as a master-data domain.
Do not ask again for that type, and do not apply it to a source, a feed, a
pipeline or a storage folder. Ask again only for a subject that is not one of
those domains.

A declared domain with a kind file is qualified and receives the mastered kind,
the datasets whose records become that kind or fill its fields, and the
registered silver tables whose links name that kind. A declared domain with no
kind file is created from its definition and receives no kind table and no
dataset. Use the kind code as the native name when configuration has one
(`branch`, `government`). International Organization and Market/Venue have no
kind code. Their approved catalog names are `international_organization` and
`market_venue`. Those names are destination identities, not kind codes.

MDM, RDM and silver are processing layers: databases `mdm`, `rdm` and `silver`
on the rules service. They are not subject domains. Do not create a domain
named after a layer.

`rules catalog publish` writes these domains, glossaries, the Gold and
Silver certifications, and the three named data products. A product's domain
must be a domain of every asset it contains. Assets are added after the
product exists. Input ports are a second assignment, not the asset list.
Add them with `PUT /api/v1/dataProducts/{name}/inputPorts/add` and the same
bulk asset body. Read them with `GET /api/v1/dataProducts/name/{fqn}/inputPorts`.
A product carries its domain and the glossary term "<Domain> Identity" of that
domain, as a `Glossary` tag in the `Suggested` state (operator: "update
data products with domains and glossary"). The tag is on the product, not on its
assets, and a product's domain still equals every asset's domain.
A mastered package takes the source datasets that fill it as input ports.
The fundamental-measures package takes the filed-figure table and the line-item
table as input ports. The measure table is an asset, not an input port.
When auditing `GET /dataProducts/{id}/assets`, compare `type=table` references
to the configured table assets. The local 2.0.2 API also returned `testCase`
references for some products; match those separately to configured quality
cases, and do not count them as table assets. Their rendered UI presentation
has not been verified.
`rules catalog publish` also writes every configured check and every registered
prepared-table check as a quality case, and every configured fix as a
correction. A profile proposal is not a case. A case has a published result
only when an external check supplies one through the legacy latest-only
`--results FILE` input or verified completed Bookkeeping receipts via
`--bookkeeping-run RUN_ID`. When both are present, `--bookkeeping-run` is used
and `--results` is ignored. The
definitions are `edgartools-configured-table-check` and
`edgartools-configured-column-check`, platform Other; OpenMetadata does not
execute them. A case whose column is on the table uses
`<#E::table::{fqn}::columns::{column}>`. Any other case uses
`<#E::table::{fqn}>`. A green publish that omits them is a publisher gap.
Relationship vocabulary comes from the pinned RDM code set
`mdm-relationship-types`. For the authority and attribute locations, read
[data-modeling](../data-modeling/SKILL.md#what-the-platform-already-says).
Do not copy that list into this skill or invent a type.

- A code with no parent is one type and one catalog asset, under
  `mdm.relationships`. Its description is the code's definition, and it states
  the `from` ends, the `to` ends, and the capacities. The rules catalog plan
  already writes that description. Keep it.
- The configuration-only publisher retains type assets and definitions even
  without confirmed links. It does not read live relationship evidence and
  emits no domain-to-type or glossary identity-to-type fact edges. For any
  separate fact projection, apply data-catalog's **Confirm relationships before
  showing them**; unknown evidence omits affected fact edges, not other metadata.
- A child code is a capacity of its parent type. It is not another asset, not
  another domain, and not another relationship.
- The type is one asset. Its allowed ends stay on its description, not domain
  memberships that turn possibilities into graph edges. Map an endpoint code
  that is not a catalog domain name onto the approved catalog name when an end
  is read: `venue` maps to `market_venue`.
- A profile on an end is a profile, not a domain and not a type.
- A prepared-store row that points at masters is a transaction. It is not a
  domain relationship. Do not publish a lineage edge from a dataset to a
  relationship type. That edge is not the relationship, and it is counted
  again beside the type. Lineage is the data flow: a feed to the dataset that
  reads it, a dataset to the kind whose fields it fills, and a code set to the
  prepared table that uses it.
- Do not draw identity-to-type edges from a type's permitted `from` or `to`
  kinds. Those are possible relationships. A glossary term for a type uses
  the code's definition and is associated only with the type's table.
  Transaction rows remain transaction data; do not turn their master links
  into inferred mastered relationships.

### Repair unsupported relationship edges

Inventory the selected domain and glossary graphs through the native API.
Use data-catalog's **Confirm relationships before showing them** to distinguish
actual facts from configured possibilities; an empty mastered relationship
table alone is insufficient. Identify exact publisher-inferred endpoint/type
edges separately from genuine dataset/pipeline lineage and curated fact edges.
Unknown evidence is not permission to delete an edge.
Keep a private before-state of the catalog-owned edges selected for removal.

For an operator-authorized repair, use the native lineage or glossary relation
DELETE endpoint for each exact unsupported, catalog-owned edge. Preserve type
definitions, masters, source records, unrelated curation and other domains.
Do not recursively delete objects. Read both graphs back and verify the
unsupported edges are absent and unrelated metadata is preserved. A repeated
repair must find no further removals. If ownership or evidence is uncertain,
leave the edge unconfirmed and report it.

The corrected configuration-only publisher publishes vocabulary and genuine
metadata lineage without inferred fact edges; live relationship evidence is
not a prerequisite for that publication. A skill update alone is not a runtime
guard: an older publisher that still infers endpoint/type edges must be
corrected and tested before reusing that path. Normal publication is not
authorization for unrelated or uncertain edge cleanup.

Place each profiled code set in `rdm.code_sets` and keep a proposed set labeled
proposed. A profiled identifier kind that is not a declared domain is not a new
domain. Code sets and profiled silver parts whose identifier kind is not a
declared domain are members of the domain that holds the instrument. A profiled
part that names no subject stays without a domain. Keep the plan description. A
display name may use the profiled part path when that path differs from the
table name. Publish lineage from each code set to the prepared table that
uses it. Do not publish lineage from a dataset to a relationship type.

A dataset is a member of the kind it becomes. A relationship type is not a
member of its endpoint domains. Putting the type on each end stores one link
per end and makes the server draw a domain-to-domain edge for every pair of
ends. Those edges are not types. Do not create them. Handle an unsupported
`ChildAssets` edge through the scoped, operator-authorized repair above; its
source label alone is not authority to delete it. Disable "Multiple Domains are
not allowed" (a rule in `entityRulesSettings`) only for an asset that itself is
more than one kind. Do not disable it to spread a relationship type.

Domains and glossaries are independent native resources; assigning one does not
create the other. Term annotation uses a tag label whose `source` is `Glossary`;
classification annotation uses `Classification`. Keep label state, term review
state and execution state separate. Never infer approval from creation.

On 2.0.2 a data product create requires `name`, `description` and `domains`.
Assets are a separate assignment. Read product membership with
`fields=dataProducts` on its own. On the local server the default rule
"Multiple Data Products are not allowed" is disabled, so an asset may belong
to more than one real product. "Data Product Domain Validation" stays enabled:
a product on an asset must match that asset's domains. Do not disable it to
force a product onto an asset in another domain. Do not invent owners. The
local catalog had no native data products at first. The fundamental
analytics package in the data-catalog model is already three tables of that
subject, not one of these native objects.

## Glossary and classification

Project. Do not author a second glossary, and do not mark a term approved.

Read `CONTEXT.md`. A glossary holds only entity terms: the domain identity
terms, the kinds of one domain's identity, and the relationship types. The
description is the definition paragraph plus the Avoid line. New terms start
as `Suggested`. Create no owners; preserve existing review status and curation.

Reuse the corrected publisher's glossary-term update path: GET the existing
identity, then PATCH only `displayName` and `description`; PUT creates a missing
term. On 2.0.7, a full native PUT without `relatedTerms` can erase existing
curation. Preserve unrelated term relations and status; remove a relation only
through the scoped, authorized repair above.

Give each published subject domain its own glossary. Its native name is the
domain name, and its display name is the domain's display name. A term whose
heading is that display name, or that display name plus " Identity", goes in
that glossary. There is no `shared` glossary (operator: "i dont
want any shared"), no domain named `Shared`, and no `Shared` tag. Place every
other entity term by its kind:

- A kind of one domain's identity, such as a registration that shares that
  identity, goes in that domain's glossary. Name it by the kind itself. Never
  add "Profile" to a term's name (an audit firm is an audit firm, not an audit
  firm profile).
- A relationship type goes in the glossary of the domain its `from` list names
  first in the pinned list. A type whose `from` list names several domains
  still has that one home.
- A platform word is not a glossary term, and `CONTEXT.md` is its one home
  (operator: "they are steps in the system and documentation, it
  can be part of lineage, not in glossary"). That covers a pipeline step or
  stage, a rules file and its parts, a store or a file. The catalog shows the
  steps as pipeline tasks on lineage, so a term would repeat them. Do not
  create a glossary named after a `CONTEXT.md` section, and do not copy these
  definitions into Articles.
- A data class is a `data_class` tag; a code-set grouping is text in the
  code-set descriptions. A type's allowed capacities belong in its description,
  while an actual link's capacity and dated interval remain fact evidence, not
  type-level claims. The publisher writes the metadata; do not edit the live
  catalog by hand.
- A silver field or a silver row set is not a glossary term. Its definition
  goes on the silver column or table. A `CONTEXT.md` entry that describes
  silver data is not published.
- An umbrella word with no real instance of its own is not a term. Remove it
  from `CONTEXT.md` instead of publishing it.

Publish a subject term only when real data backs it (operator: "the skill
must be intelligent, can not create fake domains"). A domain is real when a
rule reads it, an RDM code set holds it, or a mastered kind exists.
Relationship vocabulary has a separate inclusion rule: publish every root
type in the pinned `mdm-relationship-types` version as a glossary term, whether
or not a source mapping mentions it or any link is loaded. Use its RDM label
and definition without invented planned/no-link-loaded status text. Its term
annotation belongs on the type asset; this creates no identity-to-type fact
edge.
Qualify each domain from its own data and code sets, not whether its relationship
types have loaded links. Create a subject domain, its glossary or a term in it
only for a real domain; never create one to hold planned or invented terms.

## Context Center

Read [CONTEXT-CENTER.md](CONTEXT-CENTER.md) before writing or reading a Context Center record, or deciding whether a word belongs in a glossary, a tag or `CONTEXT.md`.

## Readback and reconciliation traps

Read [READBACK.md](READBACK.md) before trusting any read from the API as proof of what is stored, and before reconciling a publish against the plan.

## Operator outcome report

Keep configuration, send and confirmation as three separate facts:

1. `edgar-warehouse rules catalog plan --root <rules>` describes the configured
   inventory and makes no API request. Count domains, glossaries, terms,
   tables, products, quality definitions/cases, pipelines, PipelineServices and
   each lineage family from this plan.
2. `edgar-warehouse rules catalog publish --root <rules>` sends the plan and
   reconciles only its owned scope, then runs a readback. Its report keeps the
   send and confirmation stages distinct. A successful HTTP response alone
   does not confirm publication.
3. `edgar-warehouse rules catalog check --root <rules>` repeats the readback
   independently and is read-only. A matching readback is required before
   calling the checked scope confirmed.

The CLI writes one concise status line to stderr and structured JSON to stdout.
For an interactive terminal, append `>/dev/null` to show only the status line;
leave stdout available when an automation needs the JSON. A plan's JSON includes
the full configured catalog and can be thousands of lines.

Use **pending** for plan-only work, **partial** when a send may have occurred
but confirmation is absent or an API request/readback reports failure or drift,
**failed** when planning or configuration prevented a publish attempt, and
**confirmed** only when
the relevant native readback matches.
For failures, name the stage, give a short cause, and state the next action.
Show the destination as scheme and host only. Never include user info, tokens,
query strings, or raw response bodies in an operator report.
Plan counts and confirmation apply only to the exact rules revision checked. After
a rebase or rules change, rerun plan and check; a previously confirmed catalog can
be stale against the newer configuration.

The current CLI does not provide trustworthy per-object created-versus-updated
counts; do not infer these from plan counts or a successful PUT. Mark them
unavailable unless a later publisher receipt or API evidence distinguishes
them. The structured `publish` result reports configured counts, the publisher
response and removals separately from readback. The current `check` verifies the
service, database and schema inventory, tables, Pipelines (including tasks),
native Pipeline-to-table lineage and table-to-table lineage. It does not verify
every domain/glossary association, product membership/input port, quality
object, domain-lineage edge, Pipeline run status, or every table annotation.
The separate `rules catalog status --bookkeeping-run` command verifies the
latest Bookkeeping outcome on its target Pipeline. Do not describe the entire
catalog as confirmed from `check` alone; read the missing objects through the
native API and report any remaining gap as unverified until CLI coverage exists.

Do not create a shared glossary, a domain named `Shared`, or a `Shared` tag.

## Pipeline execution boundary

OpenMetadata's `Pipeline` and `ingestionPipeline` are different objects with
different jobs:

- A `Pipeline` represents one configured source target in this catalog. Bookkeeping
  is the control/run-evidence stage within that target pipeline, not a separate
  Pipeline or PipelineService. Report its execution outcome on the matching
  target Pipeline; do not create a Bookkeeping Pipeline.
  `edgar-warehouse rules catalog status --bookkeeping-run RUN_ID` resolves the
  run's frozen source and target to the configured Pipeline, writes
  `PUT /api/v1/pipelines/{fqn}/status`, and reads `pipelineStatus` back. Publish
  the catalog plan first if the target Pipeline does not exist.
  The status API requires effective Pipeline `EditStatus`. Select the runtime
  through [Data Platform connection setup](../data-platform/SKILL.md#connection-urls-and-environment)
  and verify connectivity. Publish only a real run's status
  returned by Bookkeeping; never synthesize a failure to populate the catalog.
  This is an explicit status publication, not a Bookkeeping callback or a
  pipeline trigger; invoke it after the run transition that needs catalog
  visibility.
  Running, waiting and blocked Bookkeeping runs map to `Pending`; a retryable
  failed work item marks its task `Failed` with a generic safe summary.
  A complete run maps to `Successful`. Bookkeeping has no terminal failed state;
  never map a retryable attempt to overall `Failed`.
  OpenMetadata stores only the latest Pipeline status. Bookkeeping holds the
  current run/work-item state and attempt count, but a retry can replace its
  prior error, so neither store promises durable per-attempt failure history.
  The command never copies raw work-item errors or source records into OpenMetadata.
- An `ingestionPipeline` runs a metadata connector through a configured
  pipeline-service client. `POST /api/v1/services/ingestionPipelines/trigger/{id}`
  triggers metadata ingestion. It does not start the platform's source capture,
  Bookkeeping steps, MDM merge, RDM publication or Silver loads.
- Execution support is integration-specific, not a generic property of a
  catalog `Pipeline`. Current 2.0.x documentation says the dbt Cloud integration
  can execute models directly and track executions; dbt Core integration reads
  artifacts from storage that a separate dbt run produced. This is documented
  behavior, not verified against the local 2.0.2 deployment. It does not execute
  the platform's Bookkeeping targets or make arbitrary catalog pipelines
  runnable. Verify the exact connector, account/job and run path before calling
  a workflow controlled by OpenMetadata.
- Other trigger routes are scoped to their own object: `/api/v1/apps/trigger/{name}`
  runs an installed OpenMetadata Application, and
  `/api/v1/governance/workflowDefinitions/name/{fqn}/trigger` starts a governance
  workflow. Neither route makes a catalog `Pipeline` runnable.
- OpenMetadata also has native Data Contracts. On the local 2.0.2 server,
  `POST /api/v1/dataContracts/validate` validated a draft request against
  existing entity metadata without creating a contract. This checks the request
  and metadata; it does not run tests against stored rows. A persisted contract's
  `POST /api/v1/dataContracts/{id}/validate` is a different operation: current
  2.0.x documentation says it checks schema and semantics and, when quality
  expectations are attached, triggers the contract's test-suite pipeline. That
  behavior has not been exercised on this 2.0.2 instance. The
  `DataContractValidationApplication` is installed and enabled locally with a
  daily schedule, but there are no contracts to validate. The Rules catalog
  currently has no Data Contracts.
- A contract does not make every policy enforceable. The 2.0.x contract guide
  says security, terms of use and SLA values document expectations; security and
  SLA are not evaluated by a contract run. Do not present them as access control
  or operational enforcement.

Before calling OpenMetadata a plug-and-play execution or operations control
plane, check the installed version's API schema for a trigger on the exact
object, count configured ingestion pipelines and their statuses, and inspect
the deployment for an enabled runner that is connected to the real workflow.
Require readback of both run status and verified output. A `Pipeline` entity,
task list, lineage edge, or successful catalog publish does not meet that bar.

The local `infra/openmetadata/docker-compose.yml` has no ingestion runner and
sets `PIPELINE_SERVICE_CLIENT_ENABLED` to false. Live API readback also finds no
ingestion pipelines and no connection on the `CustomDatabase` service. The
installed Data Contract Validation app reports `supportsIngestionRunner=false`;
there are 52 configured quality cases but zero latest results. OpenMetadata's
no-code test UI still needs a usable source connection and workflow executor;
catalog cases alone are not run tests. In this deployment OpenMetadata is a
catalog projection; Bookkeeping retains data-operation run ownership. Making
OpenMetadata trigger and govern those operations requires an orchestrator or a
control-plane integration and is not a no-build catalog configuration. Do not
imply that changing catalog metadata changes the execution path.

The native schema does not by itself prove a UI can render separate control
lanes, expandable stage detail or shared-step navigation. Preserve control-link
meaning as metadata and declare a separate renderer or a capability gap. Never
create fake dataset lineage to make a control lane appear.

## Quality publication

Use native test definitions/cases when supported, retaining configured semantics
and failure actions. An externally executed check is not a runnable native SQL
test. The `Other` platform is available in the pinned definition schema; select
the tested mapping rather than relabeling the existing execution engine.

The Rules catalog currently publishes its configured checks and corrections as
two custom test definitions on the `Other` platform. Their descriptions state
that OpenMetadata does not execute them. The resulting cases are metadata only:
adding a database connection or ingestion runner does not make these cases
runnable. Before claiming native quality execution, map each supported rule to
an executable OpenMetadata definition or connect an external executor that
actually runs the rule, then read back real results. Do not relabel `Other` as a
database platform to make the cases appear executable.

Keep a correction distinct from a test. Do not publish a configured correction
as an OpenMetadata test case unless it is itself an executable assertion;
otherwise the Test Cases surface can imply that the correction runs or has a
pass/fail result. Keep the correction in its owning Rules configuration and
describe it as a planned action when projecting it as metadata.

The legacy `--results FILE` path is latest-only: a silver load's file keeps the
latest report per check (`<table>.<check id>`). It is not per-load Bookkeeping
history. `publish` and `check` confirm either input through the exact timestamp
history readback in
[Quality result history](references/QUALITY-RESULT-HISTORY.md). `check` reports
"result changed, publish again" when that readback differs. A failed result
opens an incident. Only silver checks write this legacy file so far; the source
checks and master identifier limits do not.

For per-load results from a completed Bookkeeping run, use
`edgar-warehouse rules catalog publish --bookkeeping-run RUN_ID`. That command
also reconciles the configured catalog plan.

Probe the API with a throwaway case on a real table, never a real case, and
delete the case and its empty suite (`DELETE /dataQuality/testCases/{id}?hardDelete=true&recursive=true`,
then `DELETE /dataQuality/testSuites/basic/name/{suite}?hardDelete=true&recursive=true`).

A PUT of a case on a table auto-creates that table's basic suite
`{tableFQN}.testSuite` and attaches the case. Do not create a second suite for
the same table.

The Summary page at `/data-quality` defaults to Last 30 days. It counts a table
as Covered only when a case on that table has `testCaseResult.timestamp` in
that window. The query is `GET /dataQuality/testSuites/dataQualityReport` with
`index=testCase` and
`aggregationQuery=bucketName=entityWithTests:aggType=cardinality:field=originEntityFQN`,
plus a `range` on `testCaseResult.timestamp`. A definition-only case has no
result, so Covered stays 0 and Not Covered is every table. The Test Cases tab
counts distinct `originEntityFQN` of published cases and does not apply that
range. Do not POST test-case results to fill the Summary donut. Real results
come from executing the checks.

A logical suite is a metadata grouping, not an executable/basic suite. Verify
the native API for creating it and linking cases. Do not call result endpoints
to populate a definition-only catalog. A populated glossary or check list is
not an approval, switch-on or operational qualification.

## Qualification and references

One connected invented API proof checked domain assignment, a glossary
parent/child link, field glossary/classification annotations with their supplied
Suggested state, product membership, task dependency and a field-lineage edge
associated with a pipeline. It used no source records or quality results and
removed its exact test objects. This is not proof of every object above, native
control-lane rendering or cross-vendor support. Keep the current execution
receipt and any additional qualification in the task record, not this skill.

- [Glossary concepts](https://docs.open-metadata.org/v2.0.x/how-to-guides/data-governance/glossary)
- [Domains](https://docs.open-metadata.org/v2.0.x/how-to-guides/data-marketplace/domains)
- [Data products](https://docs.open-metadata.org/v2.0.x/how-to-guides/data-marketplace/data-products)
- [Classification](https://docs.open-metadata.org/v2.0.x/how-to-guides/data-governance/classification)
- [Data Contracts: validation and enforcement limits](https://docs.open-metadata.org/v2.0.x/how-to-guides/data-contracts/spec)
- [Ingestion execution options](https://docs.open-metadata.org/v2.0.x/deployment/ingestion)
- [Data Quality](https://docs.open-metadata.org/v2.0.x/how-to-guides/data-quality-observability/quality)
- [Versioned create schemas](https://github.com/open-metadata/OpenMetadata/tree/2.0.7-release/openmetadata-spec/src/main/resources/json/schema/api)
- [Lineage schema](https://github.com/open-metadata/OpenMetadata/blob/2.0.7-release/openmetadata-spec/src/main/resources/json/schema/type/entityLineage.json)
- [Column-tag readback implementation](https://github.com/open-metadata/OpenMetadata/blob/2.0.7-release/openmetadata-service/src/main/java/org/openmetadata/service/jdbi3/TableRepository.java)

## Local server

Read [LOCAL-SERVER.md](LOCAL-SERVER.md) before starting, upgrading or checking the local server, handling `.env` credentials, excluding bundled demo lineage, or clearing AI Governance during initialization.

## Catalog-only clean rebuild

`rules catalog publish` reconciles the plan; it is not a reset. Read [LOCAL-SERVER.md](LOCAL-SERVER.md), "Catalog-only clean rebuild", only when the operator asks for a clean rebuild of the catalog.

## Full local instance rebuild

This removes the local instance's volumes, users and settings. Read [LOCAL-SERVER.md](LOCAL-SERVER.md), "Full local instance rebuild", only when the operator asks for it.
