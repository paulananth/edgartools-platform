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

- [x] Mapping Document sheets read (the 13 `MAPPING.xlsx` files, 2026-11-04 04:39 ET): a `Fields` row carries the Dataset, the MDM field, the Part, the Source path, what it is Used for and the Rules path; `Pipeline steps` rows carry the target, step, operation, requires, key, leases, checks and Rules path; `Data quality` rows carry the check id, what it does, what it reads and what happens when it fails. `Fields` rows per source: gleif 26, sec.company 14, iapd.adv 13, sec.ownership 13, sec.nport.security 12, sec.nport.registrant 7, openfigi 4, sec.thirteenf.securities 4, sec.nport.fund 1, sec.submissions.person 1, and 0 for the three silver-only sources (sec.company-facts, sec.registration, sec.thirteenf.filings): 95 rows, 492 rows on all sheets. Found: a silver-only source's `Fields` sheet is empty, so its source field to Silver column mapping is on no sheet of the document, which the operator's "source to final mappings" needs; the publisher part below has to read it from the source's `silver` tables
- [x] Place chosen by the operator (2026-11-03 08:21 ET, table above); no question left
- [ ] ~~Demonstrate on the running server and the pinned release that a pipeline custom property can hold a whole Mapping Document (size limit, type), that a table can link to it, and that table and column descriptions can hold the transformation text; record any capability gap and route it~~ deferred to Codex: operator, 2026-11-04 05:54 ET: "all openmetadata will be handled by codex"
- [ ] ~~Publisher: `rules catalog plan` and `publish` write each source's Mapping Document as a custom property on its pipeline, link it from the target tables, put the brief transformation text in the table or column descriptions, and keep the source → target edges (with columns) on the Lineage tab; read all back. The plan lists them; `catalog check` compares them~~ deferred to Codex: operator, 2026-11-04 05:54 ET: "all openmetadata will be handled by codex"
- [ ] ~~Change the skill lines in `skills/openmetadata/SKILL.md` and `skills/data-onboarding/CATALOG.md`~~ deferred to Codex: operator, 2026-11-04 05:54 ET: "all openmetadata will be handled by codex"
- [ ] ~~Test: a plan for a fixture source holds one mapping per row of its Mapping Document; a mapping changed in the rules changes the plan~~ deferred to Codex: operator, 2026-11-04 05:54 ET: "all openmetadata will be handled by codex"
- [ ] ~~Learning → skill: name the skill line this changes (the "What the catalog holds for quality and mapping" bullet in `skills/openmetadata/SKILL.md`)~~ deferred to Codex: operator, 2026-11-04 05:54 ET: "all openmetadata will be handled by codex"
