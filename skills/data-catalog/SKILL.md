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
- A certification says how finished that store is. Gold certifies the master
  and reference stores. Silver certifies the prepared store. A captured source
  dataset stays uncertified. Gold is not a layer and not a
  subject. How a destination stores that certification is in the
  [openmetadata](../openmetadata/SKILL.md) skill.

A proposed table in the prepared store is still Silver certified and still has
no data class. Do not invent a class, a domain, or a certification the data
model does not name.

A domain relationship is one pinned type. Its ends stay on that asset. They
are not extra links, and a dataset that declares a type is not lineage to that
type. The [openmetadata](../openmetadata/SKILL.md) skill is the only write of
this model into OpenMetadata. Do not publish it a second time by hand.

## Understand the model before publishing

Read [MODEL.md](references/MODEL.md) when organizing domains, layers, glossaries,
products, quality or lineage. These are different dimensions, not interchangeable
folders. Browse by business domain first; processing layer is a separate filter.

1. Discover the selected configuration, declared entity kinds, dataset grain,
   field definitions, transformations, checks, matching rules and dependencies.
   Each configured entity kind is a business domain, not each individual record.
   Reuse the same method for every source and kind; no entity/provider lists or
   rename dictionaries. Preserve the distinction between defined and qualified.
   Read the settled domain type in the
   [openmetadata](../openmetadata/SKILL.md) skill before asking the operator
   to choose a type again.
2. Identify the business subject, vocabulary, processing layer, physical location
   and responsible people independently. Use evidence-backed definitions and
   understandable display names. Persist reviewed meaning in its owning
   configuration. Propose uncertain meanings for review; do not invent them.
   Project the glossary as this skill describes. The OpenMetadata write is the
   [openmetadata](../openmetadata/SKILL.md) skill. Create a data product
   only when [MODEL.md](references/MODEL.md) says a product definition exists.
   Missing definitions go to profiling or onboarding; changes to existing
   definitions go through refining-rules.
3. Select the destinations and versions. Read only the applicable adapter
   reference: the [openmetadata](../openmetadata/SKILL.md) skill for
   OpenMetadata; [PORTABILITY.md](references/PORTABILITY.md) for another
   catalog or renderer.
   State each capability as tested, documented-only or unsupported.
4. Map logical objects and relationships to native objects explicitly. Preserve
   ownership, review state, term associations, transformation meaning and quality
   failure actions. A native identifier belongs in the destination mapping,
   not in business identity. Unmapped meaning is a visible gap, not success.

### Find source inventories at the right level

Distinguish configured source scopes from top-level source groups. A configured
scope is a `rules/sources/<folder>/source.yaml` and its `source:` identifier;
the catalog may show each scope as a schema. That inventory is not automatically
the top-level source list. When asked for top-level sources, use the explicit
source hierarchy or operator-approved grouping. Do not infer groups by splitting
identifiers on dots, matching provider display names, or reading catalog schema
names as roots. If no grouping is recorded, ask before reporting a top-level
count. List pipelines separately: some belong to a source group, and others are
standalone.

### Trace a source and domain through the pipeline

When asked how a source supplies a domain, trace the configured path end to
end. A domain tag or a source name alone does not establish a pipeline, and the
relationship is not necessarily one-to-one: one source can supply several
domains, and one domain can receive data from several sources.

1. Resolve the source to its exact `rules/sources/<folder>/source.yaml` and
   `source:` identifier. Read its `dataset_contracts` to find the datasets and
   declared kinds it supplies. Follow those kinds to
   `rules/merge/kinds/<kind>.yaml` and the applicable merge policy. Do not
   infer the source from a domain label or split a dotted identifier.
2. Trace execution from that source document's `bookkeeping.targets` and
   ordered `steps`: record each operation, prerequisite, input and output
   asset. Follow `rules/source-sequence.yaml` for the inventory target and
   preferred source order only. Its `after` entries are not Bookkeeping step
   dependencies and do not cause another source to run. An optional
   `catalog.pipelines.<target>.display_name` sets the catalog label while
   preserving the Bookkeeping target and its downstream references.
3. Trace reference data independently. Follow code sets declared by the
   source findings/contracts to their RDM definitions and catalog assets;
   identify which configured steps consume them. RDM is a distinct reference
   store, not an assumed stage in every source's Bookkeeping target.
4. Trace prepared outputs from each `rules/sources/<source>/silver-*.yaml`
   specification to its target table and link keys. Join these with the
   Bookkeeping steps that produce/register the output. Keep MDM masters,
   RDM reference data and Silver transaction/prepared data as distinct store
   paths; do not imply that every record passes through all three stores.
5. Cross-check the rules catalog plan for emitted assets, pipeline definitions
   and dataset/field lineage, then use read-only catalog check/readback for
   what the destination actually contains. The plan is configuration evidence;
   it is not run evidence.
6. Account for every source folder in both `rules/source-sequence.yaml` and
   its `source.yaml` Bookkeeping registration. A missing file, missing
   `bookkeeping` declaration or missing sequence entry is an unregistered
   source and a concrete gap. A sequence `target: null` means no source target
   is registered there; report it as not runnable through that declared
   target. For a runnable target, verify its steps and profiles against the
   Bookkeeping specification and implemented worker registry. Configuration
   alone does not prove a worker exists or that a run completed.

Report the trace as source → declared datasets/kinds → Bookkeeping steps →
MDM, RDM and/or Silver outputs, naming only the stores that configuration
actually connects. Include missing registrations, unsupported worker
profiles, absent lineage and unverified execution as separate gaps. Do not
call a catalog pipeline an operationally runnable or completed pipeline until
its Bookkeeping registration, worker support and run evidence are verified.

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

## Report publication as separate outcomes

Keep these stages distinct in every run report:

1. **Plan:** what the selected configuration describes. `rules catalog plan` is
   side-effect free. Count configured domains, glossaries and terms, assets,
   quality definitions, products, pipelines and lineage from its output.
2. **Publish:** what the publisher sent, including any removals inside the
   catalog's owned scope. The `publish` command runs a readback after sending;
   its structured result keeps the send and readback stages separate.
3. **Readback:** what the native API confirms. `rules catalog check` repeats
   the check independently and is read-only. Only a matching readback supports
   the status **confirmed** for the dimensions that check covers.

Use **pending** when only a plan exists, **partial** when a publish may have
partly applied or an API request/readback failed or drifted, **failed** when
planning or configuration prevented a publish attempt, and
**confirmed** only after a matching readback. Name the failed stage, summarize
the cause and state the next action. Do not call planned counts sent counts.
Report created and updated counts only when the publisher or API provides
reliable evidence for them; otherwise mark those counts unavailable.

Identify the destination by its host, never by a credential-bearing URL. Keep
tokens, user info, query strings, response bodies that may echo credentials, and
private endpoint paths out of reports. A shared glossary may be named `shared`;
`shared` is a glossary identity only, never a domain name, domain tag, or domain
assignment. Do not create a domain named `Shared`. Metadata publication describes
processing and does not load data, run a source pipeline, or activate one.

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
