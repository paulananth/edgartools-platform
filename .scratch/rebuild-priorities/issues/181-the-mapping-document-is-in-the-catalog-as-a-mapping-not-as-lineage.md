# 181: The Mapping Document is in the catalog as a mapping, not as lineage

Priority: 181. Map: [Rebuild priorities](../map.md). Opened 2026-11-03 08:09 ET (operator, 2026-11-03: "mapping.xlsx must be in openmetadata atleast all the source to final mappings find the right spot for this information this is mapping document not lineage").

Type: task. Status: open. Blocked by: none. Related: `skills/openmetadata/SKILL.md` ("What the catalog holds for quality and mapping"), `skills/data-onboarding/CATALOG.md`, `edgar_warehouse/rules/catalog.py` (lines ~170-260 build the edges, ~1337 writes `columnsLineage`).

## Question

Today the catalog holds a mapping only as column-level lineage on the Gold or master kind table (the Lineage tab). The operator says a Mapping Document is a mapping, not lineage. Where in OpenMetadata does each source field to final field mapping live, so a steward finds it on the table page?

"Source to final" means every row of a source's `MAPPING.xlsx`: the source field or file path, each step that changes it, and the Silver column or master field it ends in.

## Parts

- [ ] Read the Mapping Document sheets (`rules mapdoc`) and name what one row carries (source path, steps, target, quality rule), with the count of rows per source
- [ ] Find the native OpenMetadata place for it on the running server and the pinned release: table or column custom property, column description, a Data Contract, or a Knowledge Center page. Demonstrate each on the server; record which ones exist and which are absent (a capability gap is routed, not hidden)
- [ ] Recommend one place with the reasoning, and ask the operator one question
- [ ] Publisher: `rules catalog plan` and `publish` write the mapping to that place for every configured source, and read it back. The plan lists it; `catalog check` compares it
- [ ] Remove the mapping from lineage, or keep lineage as data flow only (the skill already says lineage is the data flow); change the skill lines in `skills/openmetadata/SKILL.md` and `skills/data-onboarding/CATALOG.md`
- [ ] Test: a plan for a fixture source holds one mapping per row of its Mapping Document; a mapping changed in the rules changes the plan
- [ ] Learning → skill: name the skill line this changes (the "What the catalog holds for quality and mapping" bullet in `skills/openmetadata/SKILL.md`)
