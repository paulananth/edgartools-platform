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


## Updated operator ruling (2026-11-08 07:27 ET)

The operator directed: "defer document but publish lineage." Keep `MAPPING.xlsx`
in the rules repository; do not write or truncate it as a Pipeline custom
property. Publish native pipeline-to-table and rule-derived table/column lineage.

The `/lineage` page is the aggregate service view. Its two entries are shared
catalog services, not the per-source pipeline edges. Deleting those service
entities would remove catalog assets, not expose per-source lineage; no deletion
was attempted. Per-source lineage is read from each Pipeline/Table graph.

## Parts

- [x] Mapping Document sheets read (the 13 `MAPPING.xlsx` files, 2026-11-04 04:39 ET): a `Fields` row carries the Dataset, the MDM field, the Part, the Source path, what it is Used for and the Rules path; `Pipeline steps` rows carry the target, step, operation, requires, key, leases, checks and Rules path; `Data quality` rows carry the check id, what it does, what it reads and what happens when it fails. `Fields` rows per source: gleif 26, sec.company 14, iapd.adv 13, sec.ownership 13, sec.nport.security 12, sec.nport.registrant 7, openfigi 4, sec.thirteenf.securities 4, sec.nport.fund 1, sec.submissions.person 1, and 0 for the three silver-only sources (sec.company-facts, sec.registration, sec.thirteenf.filings): 95 rows, 492 rows on all sheets. Found: a silver-only source's `Fields` sheet is empty, so its source field to Silver column mapping is on no sheet of the document, which the operator's "source to final mappings" needs; the publisher part below has to read it from the source's `silver` tables
- [x] Updated scope: the operator deferred the Pipeline custom property and prioritized native lineage only. 2026-11-08 07:27 ET.
- [x] Qualified the 2.0.7 custom-property limit: `entity_extension.extension` is `varchar(512)`, every source workbook has 1,223–12,189 raw cell characters, and the Pipeline custom-property registry is empty. The operator deferred the property; no write was attempted. 2026-11-08 07:27 ET.
- [ ] Reconcile the generic source-pipeline-to-table lineage in `rules catalog publish` and verify it in `rules catalog check`. Plan: 32 edge pairs; live API: 30 matched, 2 missing and 2 stale. The new readback/reconciliation code is tested; live writes require effective `EditLineage` permission.
- [x] Updated the OpenMetadata and data-onboarding skills with the deferred-document ruling, service-view aggregation and per-source API readback; documentation checks: 99 genericity tests and 2 guide-path tests. 2026-11-08 07:27 ET.
- [x] Regression tests cover missing pipeline lineage readback and stale owned pipeline-edge removal; `tests/unit/test_rules_catalog.py`: 55 passed. 2026-11-08 07:36 ET.
- [x] Learning → skill: `skills/openmetadata/SKILL.md` documents the deferred property, aggregate service view, and native lineage readback. 2026-11-08 07:27 ET.
