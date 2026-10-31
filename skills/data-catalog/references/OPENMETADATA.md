# OpenMetadata adapter reference

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
| DataProduct | Configured consumer-facing asset collection, assigned to domains. Create one only when [MODEL.md](MODEL.md) says a product definition exists. |
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

`rules catalog publish` writes these domains, glossaries, and the Gold and
Silver certifications. A green publish that omits them is a publisher gap.
A domain relationship is one pinned relationship type. Read it from the code
set the data-modeling skill names, `mdm-relationship-types`, pinned in
`rules/merge/reference-pins.yaml`. Do not copy that list into this skill, and
do not invent a type.

- A code with no parent is one type and one catalog asset, under
  `mdm.relationships`. Its description is the code's definition, and it states
  the `from` ends, the `to` ends, and the capacities. The rules catalog plan
  already writes that description. Keep it.
- A child code is a capacity of its parent type. It is not another asset, not
  another domain, and not another relationship.
- The asset is a member of every endpoint domain. Map an endpoint code that is
  not a catalog domain name onto the approved catalog name. `venue` maps to
  `market_venue`. The other endpoint codes match the domain names. A domain
  with no kind file still receives the type when it is an endpoint.
- A profile on an end is a profile, not a domain and not a type.
- A prepared-store row that points at masters is a transaction. It is not a
  domain relationship. A lineage edge from a dataset to a type says that
  dataset declares the type. It is not a second relationship between subjects.
- Do not draw these types as `relatedTo` edges between glossary terms. A
  glossary term for a type uses the code's definition and is associated only
  with that type's table.

Place each profiled code set in `rdm.code_sets` and keep a proposed set labeled
proposed. A profiled identifier kind that is not a declared domain is not a new
domain. Code sets and profiled silver parts whose identifier kind is not a
declared domain are members of the domain that holds the instrument. A profiled
part that names no subject stays without a domain. Keep the plan description. A
display name may use the profiled part path when that path differs from the
table name. Publish lineage from each code set to the silver table that uses
it, and from each declaring dataset to its relationship type, when both ends
are registered.

An asset that fills or links more than one subject is a member of each of those
domains. The default entity rule "Multiple Domains are not allowed" rejects
that assignment. Disable that rule in `entityRulesSettings` before publishing
the asset. Do not drop a subject to satisfy the default, and do not copy the
asset so each domain has its own table.

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
analytics package in [MODEL.md](MODEL.md) is already three tables of that
subject, not one of these native objects.

## Glossary and classification

Project. Do not author a second glossary, and do not mark a term approved.

Read `CONTEXT.md`. Take the bold terms in **MDM identities and mastering** and
in **Data classes, reference data and agent context**. Leave the other sections
there until the skill that owns them asks for a term. The description is the
definition paragraph plus the Avoid line. Review state on an asset is
`Suggested`. Create no owners.

Give each published subject domain its own glossary. Its native name is the
domain name, and its display name is the domain's display name. A term whose
heading is that display name, or that display name plus " Identity", goes in
that glossary. Every other term from the two sections goes in one shared
glossary named `shared`. A shared spelling with a different definition stays a
different term.

Associate a term with a registered table only when the table name equals the
term heading, or when the term is that domain's own glossary entry and the
domain has a kind table. A domain with no kind table still has its glossary.
A proposed table is not a kind table.

The Relations Graph is the typed edges between terms. Read it from
`GET /glossaryTerms/{id}/relationsGraph`. A term that mentions another term is
not a relation. Do not add `relatedTo` from a definition, a display name, or an
Avoid line. Add an edge only when the operator names the two terms and the
relation type. The separate RDF glossary graph stays unused unless that
service is enabled.

Two classifications are created for this catalog. The built-in certification
is applied as well. Do not add another classification.

- `data_class`. One tag for each class the data-modeling skill names and this
  catalog can hold: master data on a kind table, reference data on a code-set
  table, relationship on a relationship-type table, transaction data on a
  registered prepared-store table. Copy the class sentence from `CONTEXT.md`
  where it has one, and from data-modeling where it does not. A proposed table
  in the prepared store has no data class. A source dataset has no data class:
  data-modeling does not name a source class. The metadata class stays unused
  until that store is in the catalog.
- `processing_layer`. One tag per database the rules catalog plan already
  emits. The tag name is that database name. It is a category. It is not a
  subject domain, and it does not follow from a folder name the plan does not
  use.
- Built-in `Certification`, which is mutually exclusive. It is the asset field
  `certification`, read with `fields=certification`. The screen reads
  `certification.tagLabel`. It is not a member of `tags`. A patch that adds
  `Certification.Gold` or `Certification.Silver` to `/tags` can echo the tag
  and leave the version unchanged; that did not certify the asset. Set
  `certification` itself. `Certification.Gold` on every table in the master
  store. `Certification.Silver` on every table in the prepared store, including
  a proposed table. Do not certify the reference store or a captured source
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

The native schema does not by itself prove a UI can render separate control
lanes, expandable stage detail or shared-step navigation. Preserve control-link
meaning as metadata and declare a separate renderer or a capability gap. Never
create fake dataset lineage to make a control lane appear.

## Quality publication

Use native test definitions/cases when supported, retaining configured semantics
and failure actions. An externally executed check is not a runnable native SQL
test. The `Other` platform is available in the pinned definition schema; select
the tested mapping rather than relabeling the existing execution engine.

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
