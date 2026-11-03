# 181: The Mapping Document is in the catalog as a mapping, not as lineage

Priority: 181. Map: [Rebuild priorities](../map.md). Opened 2026-11-03 08:09 ET (operator, 2026-11-03: "mapping.xlsx must be in openmetadata atleast all the source to final mappings find the right spot for this information this is mapping document not lineage").

Type: task. Status: open. Blocked by: none. Related: `skills/openmetadata/SKILL.md` ("What the catalog holds for quality and mapping"), `skills/data-onboarding/CATALOG.md`, `edgar_warehouse/rules/catalog.py` (lines ~170-260 build the edges, ~1337 writes `columnsLineage`).

## Question

Today the catalog holds a mapping only as column-level lineage on the Gold or master kind table (the Lineage tab). The operator says a Mapping Document is a mapping, not lineage. Where in OpenMetadata does each source field to final field mapping live, so a steward finds it on the table page?

"Source to final" means every row of a source's `MAPPING.xlsx`: the source field or file path, each step that changes it, and the Silver column or master field it ends in.

## Operator ruling (2026-11-03 08:21 ET)

The operator said: "Treat the document as the integration specification; use lineage to represent the relationships described by it." They gave the placement:

| What | Where in OpenMetadata |
|---|---|
| The mapping covering an entire integration (the whole `MAPPING.xlsx` of one source) | A custom property on the pipeline, with links from the relevant target tables |
| A brief explanation of each transformation | The table or column description |
| The source → target relationships | The Lineage tab |

So lineage stays, as the picture of the relationships the document describes; the document itself is the specification and sits on the pipeline. The Question's wording "not lineage" means the document is not only lineage.

## Parts

- [ ] Read the Mapping Document sheets (`rules mapdoc`) and name what one row carries (source path, steps, target, quality rule), with the count of rows per source
- [x] Place chosen by the operator (2026-11-03 08:21 ET, table above); no question left
- [ ] Demonstrate on the running server and the pinned release that a pipeline custom property can hold a whole Mapping Document (size limit, type), that a table can link to it, and that table and column descriptions can hold the transformation text; record any capability gap and route it
- [ ] Publisher: `rules catalog plan` and `publish` write each source's Mapping Document as a custom property on its pipeline, link it from the target tables, put the brief transformation text in the table or column descriptions, and keep the source → target edges (with columns) on the Lineage tab; read all back. The plan lists them; `catalog check` compares them
- [ ] Change the skill lines in `skills/openmetadata/SKILL.md` and `skills/data-onboarding/CATALOG.md`
- [ ] Test: a plan for a fixture source holds one mapping per row of its Mapping Document; a mapping changed in the rules changes the plan
- [ ] Learning → skill: name the skill line this changes (the "What the catalog holds for quality and mapping" bullet in `skills/openmetadata/SKILL.md`)
