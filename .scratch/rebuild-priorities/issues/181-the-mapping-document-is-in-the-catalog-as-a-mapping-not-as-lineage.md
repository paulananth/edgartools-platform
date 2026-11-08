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

The operator clarified: "bookkeeping is not a pipeline; it is part of the
pipeline." Bookkeeping defines the task stages of each configured target
Pipeline; it is not a separate Pipeline or PipelineService. The target's latest
status is published from Bookkeeping to that Pipeline. Bookkeeping keeps the
current run/work-item state and attempt count; a retry can replace the prior
error, so durable per-attempt failure history is not promised.

## Parts

- [x] Mapping Document sheets read (the 13 `MAPPING.xlsx` files, 2026-11-04 04:39 ET): a `Fields` row carries the Dataset, the MDM field, the Part, the Source path, what it is Used for and the Rules path; `Pipeline steps` rows carry the target, step, operation, requires, key, leases, checks and Rules path; `Data quality` rows carry the check id, what it does, what it reads and what happens when it fails. `Fields` rows per source: gleif 26, sec.company 14, iapd.adv 13, sec.ownership 13, sec.nport.security 12, sec.nport.registrant 7, openfigi 4, sec.thirteenf.securities 4, sec.nport.fund 1, sec.submissions.person 1, and 0 for the three silver-only sources (sec.company-facts, sec.registration, sec.thirteenf.filings): 95 rows, 492 rows on all sheets. Found: a silver-only source's `Fields` sheet is empty, so its source field to Silver column mapping is on no sheet of the document, which the operator's "source to final mappings" needs; the publisher part below has to read it from the source's `silver` tables

- [x] Place chosen by the operator (2026-11-03 08:21 ET, table above); no question left
- [ ] ~~Demonstrate on the running server and the pinned release that a pipeline custom property can hold a whole Mapping Document (size limit, type), that a table can link to it, and that table and column descriptions can hold the transformation text; record any capability gap and route it~~ deferred to Codex: operator, 2026-11-04 05:54 ET: "all openmetadata will be handled by Codex"
- [ ] ~~Publisher: `rules catalog plan` and `publish` write each source's Mapping Document as a custom property on its pipeline, link it from the target tables, put the brief transformation text in the table or column descriptions, and keep the source → target edges (with columns) on the Lineage tab; read all back. The plan lists them; `catalog check` compares them~~ deferred to Codex: operator, 2026-11-04 05:54 ET: "all openmetadata will be handled by Codex"
- [ ] ~~Change the skill lines in `skills/openmetadata/SKILL.md` and `skills/data-onboarding/CATALOG.md`~~ deferred to Codex: operator, 2026-11-04 05:54 ET: "all openmetadata will be handled by Codex"
- [ ] ~~Test: a plan for a fixture source holds one mapping per row of its Mapping Document; a mapping changed in the rules changes the plan~~ deferred to Codex: operator, 2026-11-04 05:54 ET: "all openmetadata will be handled by Codex"
- [ ] ~~Learning → skill: name the skill line this changes (the "What the catalog holds for quality and mapping" bullet in `skills/openmetadata/SKILL.md`)~~ deferred to Codex: operator, 2026-11-04 05:54 ET: "all openmetadata will be handled by Codex"
- [x] Updated scope: the operator deferred the Pipeline custom property and prioritized native lineage only. 2026-11-08 07:27 ET.
- [x] Qualified the 2.0.7 custom-property limit: `entity_extension.extension` is `varchar(512)`, every source workbook has 1,223–12,189 raw cell characters, and the Pipeline custom-property registry is empty. The operator deferred the property; no write was attempted. 2026-11-08 07:27 ET.
- [x] Implemented one PipelineService per source and per standalone pipeline owner; each configured target Pipeline keeps its Bookkeeping tasks. Migration uses the status endpoint to preserve latest status and retires the exact owned shared service only after per-source Pipeline and edge readback. Verified by `tests/unit/test_rules_catalog.py::test_pipeline_services_are_split_by_source_and_standalone_owner`, `tests/unit/test_rules_catalog.py::test_bookkeeping_steps_are_embedded_as_target_pipeline_tasks`, `tests/unit/test_rules_catalog.py::test_target_pipeline_lineage_includes_configured_silver_and_master_outputs`, and `tests/unit/test_rules_catalog_coverage.py::test_publication_migrates_shared_pipeline_service_to_per_source_services` (2026-11-08 12:06 ET).
- [x] Added `rules catalog status --bookkeeping-run RUN_ID`. Retryable Bookkeeping failures map to Pipeline `Pending` plus a Failed task; completed runs map to `Successful`. Status is latest-only; `items[].error` remains in Bookkeeping and is overwritten on retry. Verified by `test_bookkeeping_run_states_map_to_target_pipeline`, `test_catalog_status_reports_retryable_bookkeeping_failure_on_target_pipeline`, and `test_status_exposes_failed_attempt_steps_without_error_text` (re-claim clears `items[].error`/`failed_steps`, attempts become 2); 152 affected tests passed (2026-11-08 12:06 ET).
- [x] Updated OpenMetadata, data-onboarding and Bookkeeping skills. `tests/unit/test_profiling_genericity.py`: 99 passed; catalog plan CLI smoke: 22 Pipelines, 15 PipelineServices and 55 pipeline edges (32 source, 11 Silver, 12 MDM), every source-target Pipeline linked (2026-11-08 12:06 ET).
- [ ] Publish/read back the new 55 per-source pipeline edges and failure statuses. The prior live readback (30/32 matched, 2 missing, 2 stale) predates the Silver/MDM output projection. Current API identity has object-level `notAllow` for owned PipelineService `Create`/`Delete`/`EditAll`, Pipeline `EditLineage`/`EditStatus`, and Table `EditLineage`; no live writes were attempted. The Silver-only source-field→Silver-column map is also absent from current Rules (`Fields` sheets are empty); do not invent column edges.
- [x] Regression evidence: `test_publication_migrates_shared_pipeline_service_to_per_source_services` requires all planned per-source services after publish (`assert set(service["name"] for service in plan["pipeline_services"]) <= set(server.pipeline_services)`, assertion message: “publisher must create every per-source PipelineService before retiring the old service”). The old shared-service publisher does not create them; the green migration test verifies service, pipeline, status and lineage readback before retiring the old service (2026-11-08 12:06 ET).
- [x] Learning → skill: `skills/openmetadata/SKILL.md`, `skills/data-onboarding/CATALOG.md`, `skills/bookkeeping/SKILL.md` and `skills/bookkeeping/SPEC.md` document per-source services, Bookkeeping-as-stage, explicit status reporting and the retry-history boundary (2026-11-08 12:06 ET).
