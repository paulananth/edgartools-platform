---
name: data-catalog
description: Model, qualify and publish understandable business domains, glossaries, assets and lineage through a replaceable catalog or visualization destination. Use for OpenMetadata catalog work, catalog portability and missing semantic or lineage coverage.
---

# Data catalog

Start with business meaning, not the destination's screens or object names.
Keep one configuration-derived description of the data; a catalog and a separate
visualization can project it at the same time. Changing a destination must not
change the business meaning, processing rules or stable logical identities.

## Know the data, then the catalog

The catalog is a projection of the data. It is not a second model. Read the
data before changing the catalog, and read the catalog before claiming it
already holds something.

- `CONTEXT.md` holds the words.
- [data-modeling](../data-modeling/SKILL.md) decides the class, the kind, the
  code set, the relationship, and which store each class lives in.
- The rules catalog plan is the list of assets, fields, lineage, and pipelines
  that configuration actually emits.
- The live catalog is what was stored. Read it back. A missing field is not
  proof a link is absent, and a successful write is not proof the read matches.

Three different facts, kept as different tags:

- A subject domain says what the data is about.
- A processing layer says which plan database holds it.
- A certification says how finished that store is. The built-in certification
  is a field on the asset, not a tag in the tag list, and it is mutually
  exclusive. Gold certifies the master store. Silver certifies the prepared
  store. The reference store and a captured source dataset stay uncertified.
  There is no gold database in the plan, so Gold is not a layer and not a
  subject. The server sets how long the certification lasts. Read that period
  and the expiry back. Do not invent a longer one.

A proposed table in the prepared store is still Silver certified and still has
no data class. Do not invent a class, a domain, or a certification the data
model does not name.

## Understand the model before publishing

Read [MODEL.md](references/MODEL.md) when organizing domains, layers, glossaries,
products, quality or lineage. These are different dimensions, not interchangeable
folders. Browse by business domain first; processing layer is a separate filter.

1. Discover the selected configuration, declared entity kinds, dataset grain,
   field definitions, transformations, checks, matching rules and dependencies.
   Each configured entity kind is a business domain, not each individual record.
   Reuse the same method for every source and kind; no entity/provider lists or
   rename dictionaries. Preserve the distinction between defined and qualified.
   Read the settled domain type, the multi-domain rule and the MDM, RDM and
   silver layer placement in [OPENMETADATA.md](references/OPENMETADATA.md)
   before asking the operator to choose a type again.
2. Identify the business subject, vocabulary, processing layer, physical location
   and responsible people independently. Use evidence-backed definitions and
   understandable display names. Persist reviewed meaning in its owning
   configuration. Propose uncertain meanings for review; do not invent them.
   Project the glossary and the classifications as
   [OPENMETADATA.md](references/OPENMETADATA.md) describes. Create a data product
   only when [MODEL.md](references/MODEL.md) says a product definition exists.
   Missing definitions go to profiling or onboarding; changes to existing
   definitions go through refining-rules.
3. Select the destinations and versions. Read only the applicable adapter
   reference: [OPENMETADATA.md](references/OPENMETADATA.md) for OpenMetadata;
   [PORTABILITY.md](references/PORTABILITY.md) for another catalog or renderer.
   State each capability as tested, documented-only or unsupported.
4. Map logical objects and relationships to native objects explicitly. Preserve
   ownership, review state, term associations, transformation meaning and quality
   failure actions. A native identifier belongs in the destination mapping,
   not in business identity. Unmapped meaning is a visible gap, not success.

## Use the skill that owns the decision

The catalog projects meaning. It does not author it. Before writing a term, a
class or a layer tag, read the owner and use its words:

- The words are `CONTEXT.md`. Changing a word is domain modeling.
- Class, kind, code set and relationship type are
  [data-modeling](../data-modeling/SKILL.md).
- A new feed or a new kind is [data-onboarding](../data-onboarding/SKILL.md).
- A change to a live mapping or a match is
  [refining-rules](../refining-rules/SKILL.md).
- A check or a fix is [data-quality](../data-quality/SKILL.md).
- Filed figures and fundamental measures are the financials skill. An
  instrument's identifiers and listings are
  [security-master](../security-master/SKILL.md).
- How a merge decides is [mdm-engineering](../mdm-engineering/SKILL.md).
- A load, a recovery or a resource limit is
  [data-operations](../data-operations/SKILL.md).

Do not copy those skills into this one. A term the owner has not written stays
unprojected. A class the data-modeling skill does not name stays untagged.

## Show the flow without operational clutter

Default to platform overview → pipeline → stage → field mappings. Show shared
steps once, referenced by all relevant pipelines. Keep field detail expandable.
Connect pipelines to their dataset lineage; a list of tasks alone is incomplete.
Keep data movement, transformation and control interactions visibly distinct.

- **Bookkeeping:** records successful artifact processing so work can resume from
  the last successful point.
- **Change Journal:** decides whether an artifact needs processing, avoiding
  unnecessary repeat work.

Give control links their own action labels; do not repeat data-stage names in
the control lanes. Derive those actions from configuration and verified behavior.
Show recorded evidence only when it exists and maps to the configured flow;
label an unexecuted definition honestly. Route mismatches, execution checks,
publication blocking, failures, retries, recovery and resource/log diagnostics to
`data-operations`. The catalog explains the work; it does not become its runner.

## Qualify one connected example first

Use APIs/CLI only. Never use computer use or browser automation on this project.
Use an existing authorized account and private credentials. Authorization to
publish metadata does not authorize provider requests, source processing,
deployment, account changes or pipeline activation.

Before publishing real metadata, test an isolated invented example that connects
the business model to technical assets and pipeline/field lineage. Read back
associations, fields and dependency direction through the actual native API;
verify identities and meanings, not just HTTP success or counts. Make an
incorrect expected mapping fail. Repeat publication to check stable identities
and relevant versions. A screenshot or renderer alone is not native API proof.

Track exact created identities. Remove test-owned objects in dependency order;
verify removal without recursive deletion of shared objects. An interrupted
cleanup needs explicit remaining-object accounting before another test starts.
Preserve other people's curation and assets. Reset only the reviewed task scope.

Then ask the operator to check the one understandable example before expanding
the presentation. Clearly distinguish tested native behavior, a separate visual
preview and pending implementation. Keep this first proof small.

## Completion

Report the configured inventory against native readback: domain/term membership,
layer classification, asset/field meaning, pipeline and column lineage, quality
definitions, actual ownership and review states. Publish quality definitions
without invented results. Catalog metadata ingestion is not source-data loading.

Retain counts, outcomes, configuration references, destination version and scope;
keep source records and credentials private. A future destination remains
unqualified until its own connected example passes. When all mappings and
readback pass, retain the neutral description and destination identity mapping
so the catalog and visualization can be rebuilt independently.
