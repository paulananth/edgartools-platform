---
name: openmetadata
description: Write and read this platform's catalog on OpenMetadata. Use before rules catalog publish, a catalog reset, or any OpenMetadata API call. Business meaning stays in the data-catalog skill.
---

# OpenMetadata

This is the only place for OpenMetadata implementation. Business meaning, the
subject domains, the glossary words, and what a relationship type is stay in
the data-catalog skill. This skill says how that meaning is stored on
OpenMetadata 2.0.2, and `rules catalog publish` is the only write.

The page at `/lineage` is the service view. It draws a line only when lineage
crosses from one service to another. Edges between tables in the same database
service do not appear there. `rules catalog publish` also writes a pipeline-to-dataset
edge for each source pipeline, so that page shows the pipeline service feeding
the database service. The column-by-column flow is on the table's own Lineage
tab, `GET /api/v1/lineage/table/name/{fqn}`.

Write a plain display name and a plain first sentence on every domain, table,
product, and relationship type. The technical name stays the identity. Do not
open a description with a file path, a rules version, or a JSON list. A person
should understand the first sentence without knowing the rules layout.

Read the running version from `GET /api/v1/system/version`. The API behavior
below was checked on 2.0.2; refresh the selected version's schema before another
deployment. Treat rolling documentation as concept guidance, not proof of the
installed API. Use the existing private endpoint and bot credentials.

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
type on 2026-10-30 for every domain `CONTEXT.md` names as a master-data domain.
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
domain, as a `Glossary` tag in the `Suggested` state (operator, 2026-11-01: "update
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
`rules catalog publish` also writes every configured check and every
registered prepared-table check as a quality case, and every configured fix
as a correction. A profile proposal is not a case. A case has a pass or fail only
when a silver load wrote a results file (`QUALITY_RESULTS_FILE`, or
`land(..., results=path)`) and `publish --results FILE` sent it. The definitions are `edgartools-configured-table-check` and
`edgartools-configured-column-check`, platform Other, and OpenMetadata does
not execute them. A case whose column is on the table uses
`<#E::table::{fqn}::columns::{column}>`. Any other case uses
`<#E::table::{fqn}>`. A green publish that omits them is a publisher gap.
A domain relationship is one pinned relationship type. Read it from the code
set the data-modeling skill names, `mdm-relationship-types`, pinned in
`rules/merge/reference-pins.yaml`. Do not copy that list into this skill, and
do not invent a type.

- A code with no parent is one type and one catalog asset, under
  `mdm.relationships`. Its description is the code's definition, and it states
  the `from` ends, the `to` ends, and the capacities. The rules catalog plan
  already writes that description. Keep it.
- A type that no file under `rules/sources/` reads, and no loaded link uses,
  stays an asset, because the pinned list is the source, and its description
  ends "(planned: no rule reads this type yet and no link is loaded)". It has
  no glossary term and no Relations Graph edge until a rule reads it (operator,
  2026-11-01).
- A child code is a capacity of its parent type. It is not another asset, not
  another domain, and not another relationship.
- The type is one asset. Do not place that asset on every endpoint domain.
  Each placement is stored as another relationship, so sixteen types become
  one link per end. The ends stay on the type. Map an endpoint code that is
  not a catalog domain name onto the approved catalog name when an end is
  read: `venue` maps to `market_venue`.
- A profile on an end is a profile, not a domain and not a type.
- A prepared-store row that points at masters is a transaction. It is not a
  domain relationship. Do not publish a lineage edge from a dataset to a
  relationship type. That edge is not the relationship, and it is counted
  again beside the type. Lineage is the data flow: a feed to the dataset that
  reads it, a dataset to the kind whose fields it fills, and a code set to the
  prepared table that uses it.
- Draw each type on the glossary Relations Graph as one typed edge from
  the identity term of the type's `from` end to that type's glossary
  term. The edge is the type (`issuedBy`, display name `Issued by`). Do
  not draw the `to` ends: those identities already star every type they
  belong to, so the graph walks through the type and paints every other
  subject's types onto this one. Register each type first with
  `PUT /system/settings` `glossaryTermRelationSettings`, keeping every
  system type. The API name is the pinned code in camelCase
  (`ISSUED_BY` → `issuedBy`); underscores are rejected. A reported
  position that is silver, not a mastered type, is the glossary term for
  that position, linked from the instrument identity as `heldBy`. Do not
  add a relation from a definition mention. A glossary term for a type
  uses the code's definition and is associated only with that type's
  table.

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
ends. Those edges are not types. Do not create them. If a publish finds a
domain-to-domain edge whose source is `ChildAssets`, delete it. Disable
"Multiple Domains are not allowed" (a rule in `entityRulesSettings`) only for an asset that itself is more than
one kind. Do not disable it to spread a relationship type.

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
local catalog had no native data products on 2026-10-30. The fundamental
analytics package in the data-catalog model is already three tables of that
subject, not one of these native objects.

## Glossary and classification

Project. Do not author a second glossary, and do not mark a term approved.

Read `CONTEXT.md`. A glossary holds only entity terms: the domain identity
terms, the kinds of one domain's identity, and the relationship types. The
description is the definition paragraph plus the Avoid line. Review state on
an asset is `Suggested`. Create no owners.

Give each published subject domain its own glossary. Its native name is the
domain name, and its display name is the domain's display name. A term whose
heading is that display name, or that display name plus " Identity", goes in
that glossary. There is no `shared` glossary (operator, 2026-11-01: "i dont
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
  (operator, 2026-11-01: "they are steps in the system and documentation, it
  can be part of lineage, not in glossary"). That covers a pipeline step or
  stage, a rules file and its parts, a store or a file. The catalog shows the
  steps as pipeline tasks on lineage, so a term would repeat them. Do not
  create a glossary named after a `CONTEXT.md` section, and do not copy these
  definitions into Articles.
- A data class is a `data_class` tag, a code-set grouping is text in the
  code-set descriptions, and a fact about a relationship (its capacity or its
  dated interval) is text in the relationship-type descriptions. The publisher
  writes these; do not edit the live catalog by hand.
- A silver field or a silver row set is not a glossary term. Its definition
  goes on the silver column or table. A `CONTEXT.md` entry that describes
  silver data is not published.
- An umbrella word with no real instance of its own is not a term. Remove it
  from `CONTEXT.md` instead of publishing it.

Publish a term only when real data backs it (operator, 2026-11-01: "the skill
must be intelligent, can not create fake domains"). A domain is real when a
rule reads it, an RDM code set holds it, or a mastered kind exists. A
relationship type is a glossary term only when a file under `rules/sources/`
uses its code. A type that `CONTEXT.md` or a ticket plans, with no rule that
creates it, is not published (`HAS_MARKET_OPERATOR` and
`IS_SEGMENT_OF_EXCHANGE`, removed 2026-11-01: no rule creates either link).
Test a domain by its own data before ruling it out: the market/venue domain
looked empty through those two links, but its MIC code set and the listing rules
make it real. Create a subject domain, its glossary or a term in
it only for a real domain; never create one to hold planned or invented terms.

## Context Center

OpenMetadata 2.0 replaced the Knowledge Center with the Context Center. A
glossary holds entity terms and a `data_class` tag holds a data class; a
platform word stays in `CONTEXT.md`. A process record that nothing else holds,
or a how-to, is an Article.
Articles are pages (found in the server's `/swagger.json`, tested 2026-11-01 on
version 2.0.2):

- Create with `POST /api/v1/contextCenter/pages`: `name`, `pageType`
  `"Article"` and `page` `{}` are required; the text goes in `description`,
  which the server stores HTML-escaped. Set `entityStatus` to `Draft`; do not
  mark an Article approved. The `page` object holds only `publicationDate` and
  `relatedArticles`.
- Read `GET .../pages/{id}`, list `GET .../pages`, and change the text with a
  JSON patch on `/description`. A short fact is a Memory
  (`/api/v1/contextCenter/memories`); an uploaded file is in
  `/api/v1/contextCenter/drive`.
- Not tested: how an Article looks in the screen, and whether an AI agent finds
  it. The documentation says the agent search reads only the facts extracted
  from uploaded files, not Articles or hand-written Memories.

Associate a glossary term with a table only when the term is one relationship
type and the table is that type. Do not tag the kind table with every term
whose heading starts with the domain name. A domain with no kind table but with
a rules file still has its glossary. A proposed table is not a kind table.

A domain has no `relationsGraph` endpoint. Its graph is lineage. Read it with
`GET /api/v1/lineage/domain/name/{domain}?upstreamDepth=1&downstreamDepth=1`.
Add one edge from the domain to the relationship-type table, for each end of
that type:

`PUT /api/v1/lineage/domain/name/{domain}/table/name/{typeFqn}`

with `{"description": "<type>: <definition>", "source": "Manual"}`. The node
on the graph is the type. Do not add an edge from domain to domain. One edge
per domain pair is overwritten by the next type, so the type disappears.
`rules catalog publish` writes these edges.

The glossary Relations Graph is a different API,
`GET /glossaryTerms/{id}/relationsGraph`. A domain glossary's Relations Graph
page starts at that domain's identity term.
A term that mentions another term is not a relation. Do not add an edge
from a definition, a display name, or an Avoid line.
`rules catalog publish` registers the types, then writes
`POST /glossaryTerms/{id}/relations` with
`{"relationType": "<issuedBy>", "term": {"id": "<type-term-id>", "type":
"glossaryTerm"}}` from the `from` end's identity term to each type that
names that end. Duplicate POST is idempotent. Remove a leftover `relatedTo`
or any other pair the plan does not name with
`DELETE /glossaryTerms/{id}/relations/{toTermId}?relationType=<that type>`.
The separate RDF glossary graph stays unused unless that service is enabled.

`rules catalog publish` applies the built-in certification and the `data_class`
tags below. It leaves each term's status to the server unless `--draft-terms` is given
(operator, 2026-11-02: "stop forcing Draft on the local catalog"). It writes the terms, tags and
descriptions this section names; edit none of them in the live catalog by hand.
A second write of mention edges or endpoint domain links is how overstatement
comes back. A relationship type that no file under `rules/sources/` names gets
"(planned: no rule reads this type yet and no link is loaded)" in its asset
description and no term. Each data product carries the identity term of its
domain, `Suggested`. The store of a table is its native Certification, not a custom
tag (operator, 2026-11-02: "rdm = Gold, MDM = Gold, Silver = Silver"). `check`
reports a table whose class tag or certification is missing.

- `data_class`. One tag for each class the data-modeling skill names and this
  catalog can hold: master data on a kind table, reference data on a code-set
  table, relationship on a relationship-type table, transaction data on a
  registered prepared-store table. Copy the class sentence from `CONTEXT.md`
  where it has one, and from data-modeling where it does not. A proposed table
  in the prepared store has no data class. A source dataset has no data class:
  data-modeling does not name a source class. The metadata class stays unused
  until that store is in the catalog.
- Built-in `Certification`, which is mutually exclusive. It is the asset field
  `certification`, read with `fields=certification`. The screen reads
  `certification.tagLabel`. It is not a member of `tags`. A patch that adds
  `Certification.Gold` or `Certification.Silver` to `/tags` can echo the tag
  and leave the version unchanged; that did not certify the asset. Set
  `certification` itself. `Certification.Gold` on every table in the master
  store and the reference store. `Certification.Silver` on every table in the
  prepared store, including a proposed table. Do not certify a captured source
  dataset. Do not put Gold on the prepared store or Silver on the master store.
  Bronze stays unused until a captured-source certification is configured.
  `assetCertificationSettings` supplies the validity period. On this server it
  is 30 days. Record the applied date and the expiry, and apply it again when
  it expires. Do not invent a longer window.

Leave every other built-in classification in place. A repeat put keeps the same
glossary, term, classification and tag identity. Read tags back on their own.
A glossary is global: resetting a database service does not remove it.

Pinned create schemas expose `domains` as FQN strings on applicable resources.
Table registration can also name `dataProducts`. Readback resolves these into
entity references. Request `fields=domains` on its own. The default table
payload omits domain membership, so a missing field is not proof the link is
absent. Compare returned domain FQNs as a set: the server does not keep the
submitted order. Do not compare an input string list directly to a returned
reference list.

## Readback and reconciliation traps

- Read column annotations with **both `fields=columns,tags`**. In 2.0.2, asking
  only for tags can return columns with empty tags despite stored annotations.
  Check domain/product fields separately in the same request when needed.
- Request `fields=tasks` when checking pipeline tasks and downstream dependencies.
- Native lineage edge `lineageDetails.pipeline` references the pipeline;
  `columnsLineage` names fully qualified upstream/downstream columns and the
  transformation. A registered pipeline with tasks alone does not supply that
  edge association. No transformation SQL is invented for a non-SQL process.
- Descriptions may have one transport layer of HTML entity escaping. Normalize
  Markdown fields once for comparison; keep identity, rule parameters and hashes
  exact. A genuine semantic difference must still fail.
- Bot PUT may retain curated descriptions. Compare the result, and patch only
  explicitly configuration-owned fields using JSON Patch when authorized.
  Check identity before and after; preserve other owners' labels and wording.
- List all pages and constrain ownership by exact service membership or an
  explicit ownership receipt. Domains, glossaries, terms and quality resources
  are global and are not assumed removed when a service is reset.

- A renamed source leaves its old tables behind. Such a table still holds its
  test cases, so `DELETE /tables/{id}?hardDelete=true` answers 400 "table is not
  empty"; the publisher deletes with `recursive=true` (2026-11-01, a
  source ID rename). A publish that names a
  renamed source creates its new pipelines, schema, tables and test cases and
  removes the old ones in the same run; do not delete them by hand.
- A glossary term has no status in its create body (`CreateGlossaryTerm`, 2.0.2).
  A put, a relation write and a tag on an asset all leave it `Approved`, and a
  patch of one term resets its related terms. With `--draft-terms` the publisher
  patches `/entityStatus` to `Draft` as its last write, reads each status back and
  patches again until none is left. Without it, a publish leaves the server's status.
- The server's `GlossaryTermApprovalWorkflow` approves any created or updated
  term that has no reviewer, a few seconds after the write. It keeps terms
  `Approved` whatever `--draft-terms` does. To see Draft on a server, suspend it:
  `PUT /api/v1/governance/workflowDefinitions/name/GlossaryTermApprovalWorkflow/suspend`
  (undo with `/resume`). Check `suspended` is true before a publish.
- What the catalog holds for quality and mapping: a quality case sits on the table
  it checks (source datasets and silver tables from their quality rules; a master
  kind table from its identifier limits: one case per `claim.forward` and
  `claim.reverse` of each identifier in `merge/kinds/<kind>.yaml`, none where the
  limit is null). The approved Mapping Document placement is a Markdown custom
  property on its pipeline, with relevant source, Silver and master tables
  linking to that pipeline. Silver-only mappings come from registered
  `silver-*.yaml` specs. The current main-branch plan, publisher and readback do
  not implement this projection, so do not report complete Mapping Documents as
  published. A field mapping shown in column lineage remains separate from the
  integration specification. A code list's edge maps its `code` to each column
  that holds those codes. A captured file feed's edge to its dataset stays table
  to table: a file has no columns.
  A page with an empty Quality tab is a table with no configured check.

- A profile has one native place, the table profile. `PUT /api/v1/tables/{id}/tableProfile`
  takes `{"tableProfile": {"timestamp": <ms>, "rowCount": n, "columnCount": n}}`; read it with
  `GET /api/v1/tables/{fqn}/tableProfile/latest` (the `profile` field); remove one with
  `DELETE /api/v1/tables/{fqn}/table/{timestamp}/profile`. The publisher writes it for every
  silver table of a source that has a `profile.yaml`: the profile date is the timestamp, and
  the counts are the part's rows and the silver table's columns, counts only. The source
  schema and each kind table say which profile feeds them, or "Not profiled yet". `catalog check`
  reads the latest profile back and reports "profile changed, publish again" for a table whose
  profile differs. Try the API on a throwaway table, never on a catalog table: a test value
  written to a real table must then be deleted by its timestamp.

## Operator outcome report

Keep configuration, send and confirmation as three separate facts:

1. `edgar-warehouse rules catalog plan --root <rules>` describes the configured
   inventory and makes no API request. Count domains, glossaries, terms,
   tables, products, quality definitions/cases, pipelines and each lineage
   family from this plan.
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
response and removals separately from readback. The current `check` verifies the service, database and
schema inventory, tables, pipelines (including tasks), and table lineage. It
does not verify every configured domain/glossary association, product
membership/input port, quality object, domain lineage edge, pipeline-to-table
edge, or all table annotations. Do not describe the entire catalog as confirmed
from that check alone; read the missing objects through the native API and
report any remaining gap as unverified until CLI coverage exists.

Do not create a shared glossary, a domain named `Shared`, or a `Shared` tag.

## Pipeline execution boundary

OpenMetadata's `Pipeline` and `ingestionPipeline` are different objects with
different jobs:

- A `Pipeline` describes a data workflow and its lineage. Its status API accepts
  externally reported run status through `PUT /api/v1/pipelines/{fqn}/status`;
  the API has no trigger for this object. A status record is run evidence only
  when the actual runner reported it and its output was verified.
- An `ingestionPipeline` runs a metadata connector through a configured
  pipeline-service client. `POST /api/v1/services/ingestionPipelines/trigger/{id}`
  triggers metadata ingestion. It does not start the platform's source capture,
  Bookkeeping steps, MDM merge, RDM publication or Silver loads.
- Other trigger routes are scoped to their own object: `/api/v1/apps/trigger/{name}`
  runs an installed OpenMetadata Application, and
  `/api/v1/governance/workflowDefinitions/name/{fqn}/trigger` starts a governance
  workflow. Neither route makes a catalog `Pipeline` runnable.
- OpenMetadata also has native Data Contracts. On 2.0.2,
  `POST /api/v1/dataContracts/validate` checks a draft request against existing
  entity metadata without creating a contract. This checks the contract shape and
  metadata constraints; it is not a test over stored rows or a pipeline run. The
  persisted contract's `POST /api/v1/dataContracts/{id}/validate` is a separate
  operation. The current Rules catalog plan does not publish Data Contracts, and
  contract validation does not run a source pipeline or Bookkeeping operation.

Before calling OpenMetadata a plug-and-play execution or operations control
plane, check the installed version's API schema for a trigger on the exact
object, count configured ingestion pipelines and their statuses, and inspect
the deployment for an enabled runner that is connected to the real workflow.
Require readback of both run status and verified output. A `Pipeline` entity,
task list, lineage edge, or successful catalog publish does not meet that bar.

The local `infra/openmetadata/docker-compose.yml` has no ingestion runner and
sets `PIPELINE_SERVICE_CLIENT_ENABLED` to false. In this deployment
OpenMetadata is a catalog projection; Bookkeeping retains data-operation run
ownership. Making OpenMetadata trigger and govern those operations requires an
orchestrator or a control-plane integration and is not a no-build catalog
configuration. Do not imply that changing catalog metadata changes the
execution path.

The native schema does not by itself prove a UI can render separate control
lanes, expandable stage detail or shared-step navigation. Preserve control-link
meaning as metadata and declare a separate renderer or a capability gap. Never
create fake dataset lineage to make a control lane appear.

## Quality publication

Use native test definitions/cases when supported, retaining configured semantics
and failure actions. An externally executed check is not a runnable native SQL
test. The `Other` platform is available in the pinned definition schema; select
the tested mapping rather than relabeling the existing execution engine.

A result is `POST /api/v1/dataQuality/testCases/testCaseResults/{caseFQN}` with
`timestamp`, `testCaseStatus` (`Success` or `Failed`), `testResultValue`,
`passedRows` and `failedRows`; read it as `testCaseResult` with
`fields=testCaseResult`. A failed result opens an incident. `check --results FILE`
reports "result changed, publish again". A silver load's file keeps the latest
report per check (`<table>.<check id>`). Only silver checks write one so far; the
source checks and the master identifier limits have no results file yet. Probe
the API with a throwaway case on a real table, never a real case, and delete the
case and its empty suite (`DELETE /dataQuality/testCases/{id}?hardDelete=true&recursive=true`,
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
- [Versioned create schemas](https://github.com/open-metadata/OpenMetadata/tree/2.0.2-release/openmetadata-spec/src/main/resources/json/schema/api)
- [Lineage schema](https://github.com/open-metadata/OpenMetadata/blob/2.0.2-release/openmetadata-spec/src/main/resources/json/schema/type/entityLineage.json)
- [Column-tag readback implementation](https://github.com/open-metadata/OpenMetadata/blob/2.0.2-release/openmetadata-service/src/main/java/org/openmetadata/service/jdbi3/TableRepository.java)

## Local server

Use the existing Docker context and the named volumes in
`infra/openmetadata/docker-compose.yml`:

```bash
docker compose -f infra/openmetadata/docker-compose.yml up -d
```

Check Docker first. If it is unreachable, report that blocker. Preserve other
users' containers and volumes. A cold start may take 10–20 minutes. The compose
file accepts `CATALOG_SERVER_HEAP_OPTS` and `CATALOG_SEARCH_HEAP_OPTS`.

A login token of the local account expires within the hour; a publish that
answers 401 needs a new one. Refresh it in the private terminal session, with
shell tracing off. Enter the local account password only at the hidden prompt;
the password is base64 encoded for the login API, and neither it nor the returned
token is printed:

```bash
set +x
set -euo pipefail
export OPENMETADATA_URL=http://127.0.0.1:8585
read -r -p 'OpenMetadata email: ' OM_LOGIN_EMAIL
read -r -s -p 'OpenMetadata password: ' OM_LOGIN_PASSWORD
printf '\n'
OM_LOGIN_PASSWORD_B64=$(printf '%s' "$OM_LOGIN_PASSWORD" | base64 | tr -d '\n')
OM_LOGIN_BODY=$(jq -cn --arg email "$OM_LOGIN_EMAIL" --arg password "$OM_LOGIN_PASSWORD_B64" \
  '{email:$email,password:$password}')
OPENMETADATA_TOKEN=$(printf '%s' "$OM_LOGIN_BODY" | curl -fsS \
  -H 'Content-Type: application/json' -X POST \
  --data-binary @- "$OPENMETADATA_URL/api/v1/users/login" | jq -er '.accessToken')
export OPENMETADATA_TOKEN
unset OM_LOGIN_EMAIL OM_LOGIN_PASSWORD OM_LOGIN_PASSWORD_B64 OM_LOGIN_BODY
```

Keep the variables in the private shell only. Never echo or save the token in
the repository. The URL passed to `catalog.connect` is the server root; that
function adds `/api/v1`.

A whole-service reset deletes the owned pipeline service, then the owned
database service:

1. `GET /api/v1/services/<type>/name/<exact-owned-name>`. Check the name and
   the fully qualified name.
2. `DELETE /api/v1/services/<type>/<returned-id>?recursive=true&hardDelete=true`.
3. Repeat the GET and require 404.

Domains, glossaries, and terms are global. Deleting a service does not remove
them.

## Catalog-only clean rebuild

`rules catalog publish` reconciles the plan; it is not a delete-and-recreate
reset. Use it alone for normal refreshes. For an explicitly requested clean
rebuild, preserve the OpenMetadata PostgreSQL and search volumes, users,
workflows, roles, and instance settings. Do not use `docker compose down -v`,
drop the OpenMetadata database, or clear search storage for a catalog reset.

Before deleting anything, read the current plan and list every API page for the
owned services and global objects. Establish exact ownership by comparing each
identity with the current plan and the publisher's ownership boundary. Stop if
an object cannot be shown to be owned; global domains, glossaries, terms,
products, and quality definitions can contain unrelated curation. Record the
IDs and counts for the reviewed scope.

Delete in dependency order: owned products, owned quality cases, owned custom
quality definitions, owned pipeline service, owned database service, owned
glossary terms, owned glossaries, owned domains, then owned custom tags. Remove
products and cases before their referenced tables. Delete the pipeline service
before the database service. For services, verify the exact service name and
FQN first, delete by returned ID with `recursive=true&hardDelete=true`, then
repeat the GET and require 404. For each other resource, use its native API and
returned ID; use recursive deletion only when the owned children are in the
reviewed scope. Keep built-in definitions, classifications, tags,
relationships, workflows, and settings unless the plan explicitly owns them. If
a delete fails or ownership becomes unclear, stop and account for remaining
objects before continuing.

Publish the current plan only after the reviewed scope is empty. Require the
publish result's readback to match, run `rules catalog check` independently,
and verify the exact domain and glossary inventories plus the absence of any
forbidden shared object. A zero-removal publish after the rebuild is expected;
it means the fresh catalog already matches the plan. Report deletion counts
separately from publication counts. A catalog reset does not reset the
OpenMetadata server or prove that metadata ingestion or data pipelines ran.
