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
| DataProduct | Configured consumer-facing asset collection, assigned to domains. Only create one when a real product definition exists. |
| TestDefinition / TestCase / TestSuite | Reusable check definition, asset-specific configured check and grouping. Actual results are separate. |

The pinned domain types are `Source-aligned`, `Consumer-aligned` and `Aggregate`.
This required native attribute is not the logical subject identity. If the
governance configuration does not select a type, ask for that mapping decision
before real publication; do not infer it from a source name or silently copy the
type used by a synthetic test.

Domains and glossaries are independent native resources; assigning one does not
create the other. Term annotation uses a tag label whose `source` is `Glossary`;
classification annotation uses `Classification`. Keep label state, term review
state and execution state separate. Never infer approval from creation.

Pinned create schemas expose `domains` as FQN strings on applicable resources.
Table registration can also name `dataProducts`. Readback resolves these into
entity references; compare the intended associations using returned IDs/FQNs.
Do not compare an input string list directly to a returned reference list.

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
