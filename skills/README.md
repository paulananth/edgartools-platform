# Skills: which one to open

Each skill's own description says when it applies; this page shows how they fit
together. Start at **data-platform** when the task is data work and you do not
yet know which step you are on.

Install every skill for Claude, Codex and Grok from this checkout with
`bash skills/link.sh`, or name the skills to link. An installed command line
copies them instead: `edgar-warehouse skill install`.

## Lifecycle role map

Role names organize existing skills; they do not add authority. Follow each skill's trigger and handoff. Start at [data-platform](data-platform/SKILL.md) when the platform phase is unclear. This repository's exact store boundaries override generic Medallion labels: captured files are Bronze; MDM owns masters; RDM owns code sets; Silver holds source facts; consumers use the configured mirror and, when required, Gold transformations. See [aws-snowflake-operations](aws-snowflake-operations/SKILL.md).

The source order is capture, profile, model, approved configuration, then MDM/Silver load. Raw data is not loaded into MDM for discovery. The CDO role adds no new approval path; existing operators and skill owners retain their decisions.

### Stages 1–2: ingestion, storage, cleaning and modeling

**Data Architect — design and discovery**
- [data-platform](data-platform/SKILL.md) routes architecture, readiness and the next step.
- [data-profiling](data-profiling/SKILL.md) measures captured structure and can add portable NER mention evidence from local text; it does not resolve identities.
- [data-modeling](data-modeling/SKILL.md) decides approved domains, classes, master kinds, reference code sets and hierarchies, entity resolution and identity, relationships and time.
- [data-governance](data-governance/SKILL.md) and [data-catalog](data-catalog/SKILL.md) govern definitions, lineage and catalog meaning.
- [mdm-data-publication](mdm-data-publication/SKILL.md) selects and verifies exact governed MDM outputs for operational and analytical consumers, while keeping hub and reference-data administration internals private.

**Data Engineer — engineering and production**
- New source configuration and checks: [data-onboarding](data-onboarding/SKILL.md), [data-quality](data-quality/SKILL.md). Existing-rule refinement sits inside [MDM Engineering](mdm-engineering/SKILL.md#refining-rules); [refining-rules](refining-rules/SKILL.md) forwards to its procedure.
- Runtime and stores: [mdm-engineering](mdm-engineering/SKILL.md), [sql-writer](sql-writer/SKILL.md), [bookkeeping](bookkeeping/SKILL.md), [change-journal](change-journal/SKILL.md), [data-operations](data-operations/SKILL.md), [pipeline-orchestration](pipeline-orchestration/SKILL.md), [database-monitoring](database-monitoring/SKILL.md), [production-support](production-support/SKILL.md), [aws-snowflake-operations](aws-snowflake-operations/SKILL.md), [access-audit](access-audit/SKILL.md), [openmetadata](openmetadata/SKILL.md) and [openmetadata-deploy](openmetadata-deploy/SKILL.md) and [load-monitoring](load-monitoring/SKILL.md).

### Stage 3: BI and consumption

**Data Analyst — discovery and business questions**
- [auto-ontology-product-query](auto-ontology-product-query/SKILL.md) answers questions over configured products. No general analyst workflow skill is maintained here.

**BI Developer — production reporting**
- [mdm-data-publication](mdm-data-publication/SKILL.md), [semantic-views](semantic-views/SKILL.md), [auto-ontology](auto-ontology/SKILL.md) and [aws-snowflake-operations](aws-snowflake-operations/SKILL.md) cover governed product exposure, scoped semantic/query and Snowflake/dbt work; [data-catalog](data-catalog/SKILL.md) and [openmetadata](openmetadata/SKILL.md) cover catalog publication and readback. No generic dashboard-builder skill is maintained in this repository.

### Stage 4: advanced analytics and AI

**Data Scientist — exploratory and predictive modeling**
- [data-scientist](data-scientist/SKILL.md) teaches general exploration and prediction concepts; platform NER belongs to Data Profiling, not this stage.

**AI/ML Engineer — production AI**
- No end-to-end production ML/AI skill is maintained in this repository; production NER deployment is not covered. Semantic and query skills are not model-training, RAG or agent-deployment workflows.

### Domain and teaching routes

- [security-master](security-master/SKILL.md) and [company-financials](company-financials/SKILL.md) hold domain-specific rules.
- [data-engineering-fundamentals](data-engineering-fundamentals/SKILL.md) teaches general concepts; platform rules stay with their owner skills.

The role map is an entry point, not a substitute for a skill's own boundaries.

## What a skill holds

- The rule and the method, written for any reader. A ticket number, a pull
  request number, the date of a ruling or a run, and one run's counts or
  timings belong in the ticket. A limit the engine enforces is a rule and stays.
- A `SKILL.md` under 500 lines. A section only some tasks need moves whole to
  a sibling file, and its heading stays with one line saying when to read it:
  `python3 scripts/dev/move_skill_section.py`.
- A source, kind or identifier is named only under a heading that contains
  "Examples", except in the skills whose purpose is one domain or deployment.
- A new skill is a folder with a `SKILL.md`; add its route under the lifecycle role map or Domain and teaching routes above.
