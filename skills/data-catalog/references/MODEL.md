# Keep the dimensions separate

| Concept | Question it answers | Relationship to other concepts |
|---|---|---|
| Business domain | What subject does this data describe? | Groups related meanings and assets. This project's declared entity kinds define the subject domains. |
| Glossary | What do the business words mean? | Holds terms; terms describe assets and fields across their technical locations. |
| Term | What does this concept mean in this context? | Can have a parent, synonyms and related concepts; shared spelling alone does not prove shared meaning. |
| Processing layer | At what stage of preparation is this data? | An independent configured classification. A subject may span several layers. |
| Service and technical hierarchy | Where is this asset represented? | A database service contains databases, schemas and tables; columns belong to tables. This containment is not a business-domain hierarchy. |
| Pipeline and stage | How is the data processed? | A pipeline has declared stages/dependencies and connects upstream/downstream assets. |
| Lineage | Where did this output come from and how did it change? | Directed asset edges plus field mappings and transformations, tied to the processing pipeline. |
| Control interaction | How is work resumed or unnecessary work avoided? | Separate links between processing stages and their control systems, not fake business datasets. |
| Classification and tag | What category or handling label applies? | A classification groups tags. A glossary term supplies meaning; a classification supplies a category. |
| Data product | What useful package of data is offered to consumers? | An explicitly defined collection with purpose/responsibility; not an automatic synonym for a table, pipeline, domain or layer. |
| Quality definition | What condition must the data satisfy? | Names inputs, parameters, failure action and execution owner. A correction is different from a check. |
| Quality result | What did an actual check observe? | Requires genuine corresponding execution evidence; the existence of a definition supplies none. |
| Ownership and review | Who is responsible, and what has been approved? | Independent from the ingestion bot and from technical publication success. |

Read this as a connected model: a domain has a vocabulary; its terms explain
datasets and fields; those assets have technical locations and processing-layer
classifications; pipelines transform them; lineage connects the inputs, outputs
and transformations. Products package explicitly selected assets for use.
Quality, responsibility and review add meaning to these objects without turning
their publication into an operational approval.

Use the configured layer vocabulary. Do not derive a layer from a database name
or create a business domain for every storage folder. Keep domain-first browsing
and a separate layer filter even when a destination's native hierarchy differs.
Do not create a physical asset twice just to place it under two browse headings.

A data product exists only when configuration names the package, its purpose
and the assets it contains. An owner is a separate fact. Do not invent one.

Fundamental analytics is that package. The rules name three silver tables and
the measure definitions: one holds every filed figure, one holds the standard
line items for a fiscal year, and one holds one fundamental measure for a
subject, a fiscal year and a window. The measure list is that source's
measures file, version `measures-2026-10-29.first-build`: margins, leverage
and per-share ratios, returns on the average balance and on the beginning
balance, and CAGR over 1, 3, 5 and 10 years. It belongs to the subject those
tables are already members of. It is not a new subject. The local catalog
already holds those three tables. The rules do not name a native data product,
and the catalog plan does not emit one. Do not create that native object until
the rules name it.

The older gold factor chain is a separate earlier factor table. It is not this
package. Do not publish it as the fundamental analytics package.

These are not that package:

- A subject domain, a processing layer, a table, or a pipeline.
- A provider publication. A delivery the provider calls a product is a source
  or a feed.
- A fund arrangement. A series under a fund registrant is a subject, not a
  selected set of catalog assets.
- The Agent Decision Surface, the Decision Graph Bundle, gold, or the Human
  Audit View. Those are a consumer contract, an analytics layer, and a screen.
  The Human Audit View is not the primary product surface. A destination enum
  such as decision support is not a product definition.

Do not create a Consumer-aligned domain to hold a product that has no definition.

Use logical stable keys from owning configuration and separate destination IDs.
Each association has an explicit type: containment, domain membership, term
annotation, classification, product membership, data lineage or control link.
A relationship between mastered records is another relationship type; it is
not evidence that one dataset was produced from another.

Glossary terms are a projection. The words stay in `CONTEXT.md`. The class
choice stays in the data-modeling skill. OpenMetadata storage of that
projection is the openmetadata skill. Do not keep a second copy here.

For semantic enrichment, read the definition, grain, field role, constraints,
relationships and transformation together. A technical identifier or title case
is insufficient evidence. Present an uncertainty as a proposal for review.

## Evidence and authority

Configured flow describes intended behavior. Recorded evidence, when available,
must point to the same logical steps and configured dependencies. Missing or
contradictory evidence remains visible; operational checks and enforcement are
owned by data-operations. A catalog graph must never rewrite evidence to appear
compliant.

The current project publisher and a future portable publisher are separate
capabilities. A skill can specify a portable mapping and identify a gap without
claiming that the runtime already exports a vendor-neutral manifest or supports
every destination.
