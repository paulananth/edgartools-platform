# 181: The Mapping Document is in the catalog as a mapping, not as lineage

Priority: 181. Map: [Rebuild priorities](../map.md). Opened 2026-11-03 08:09 ET (operator, 2026-11-03: "mapping.xlsx must be in openmetadata atleast all the source to final mappings find the right spot for this information this is mapping document not lineage").

Type: task. Status: claimed. Blocked by: none. Related: `skills/openmetadata/SKILL.md` ("What the catalog holds for quality and mapping"), `skills/data-onboarding/CATALOG.md`, `edgar_warehouse/rules/catalog.py` (lines ~170-260 build the edges, ~1337 writes `columnsLineage`).

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
- [ ] Qualify the Mapping Document representation on the 2.0.7 server. `entity_extension.extension` is `varchar(512)`; all 13 source workbooks contain 1,223–12,189 raw cell characters, and the Pipeline custom-property registry is empty. Full embedding cannot fit. Current login/PAT edit permissions are conditional; pre-upgrade checks on all 22 pipelines returned `notAllow`. No write was attempted. An operator-approved link/document target and authorized writer are required before proving table/column writes.
- [ ] Implement a generic rules-driven `catalog.plan`/`publish` projection for the approved representation, target-table links, transformation descriptions and native lineage; verify it with `catalog.check`. New pipelines must not require per-source code. Blocked until the representation and writer are available.
- [x] Updated the OpenMetadata and data-onboarding skills with config-driven pipeline discovery, the 512-character Mapping Document limit, the 2.0.7 upgrade sequence and service-versus-table lineage verification; documentation checks: 99 genericity tests and 2 guide-path tests. 2026-11-07 21:18 ET.
- [ ] Test: a fixture plan contains every source-to-final mapping row in the approved representation and changes when a mapping rule changes.
- [x] Learning → skill: `skills/openmetadata/SKILL.md` documents the 2.0.7 upgrade/rollback/reindex path and 512-character storage limit; `skills/data-onboarding/CATALOG.md` documents configuration-driven pipeline discovery. 2026-11-07 21:18 ET.
