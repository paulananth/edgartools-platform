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

Use logical stable keys from owning configuration and separate destination IDs.
Each association has an explicit type: containment, domain membership, term
annotation, classification, product membership, data lineage or control link.
A relationship between mastered records is another relationship type; it is
not evidence that one dataset was produced from another.

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
