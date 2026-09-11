# Agent Decision Contract

Label: `wayfinder:map`

## Destination

An implementation-ready, decision-complete plan for the remaining Snowflake
Decision Contract: composite Decision Watermark and agent-grade gate, Subject
Feature Screen, issuer Subject Bundle Read, and Streamlit-in-Snowflake Agent
View versus Explore, consistent with ADR 0001 and ADR 0006.

## Notes

- Repo: `edgartools-platform`. Planning only unless a later Notes override
  carries implementation into the map (change-propagation style). Produce
  decisions, not PRs, until the way is clear.
- AWS-only. Do not introduce another cloud, registry, workflow engine, storage
  target, or secret-management path.
- Skills every session should consult: `/grilling` (one question at a time),
  `/domain-modeling`, `/grill-with-docs`, ADR 0001, ADR 0006,
  `docs/doctrine-data-plane.md`, `CONTEXT.md` Agent decision support.
- Predecessor maps and indexes are inputs, not questions to reopen:
  - [Agent Decision Data Plane](../agent-decision-data-plane/spec.md) tickets
    01–14: closed. Agent-contract answers (watermark shape, issuer bundle,
    universe intersection, SiS modes) are inputs. Bronze-off / persist-only
    bronze-hash answers are not followed.
  - [Incremental Change Propagation](../change-propagation/map.md): ingest,
    mandatory Bronze evidence, PostgreSQL Source Fetch Decision, silver
    authority. Do not chart a second ingest map.
- Scope locked 2026-09-10 during destination and frontier grilling:
  - Manager ADV / MANAGES_FUND / IS_ENTITY_OF agent-grade sections are out of
    this map. Issuer bundles keep ADV `not_applicable`.
  - Human Audit View Agent View vs Explore is in destination.
  - Decision Watermark always includes Bronze evidence identity, plus silver
    completeness, graph generation id, gold/feature as-of, and business date.
  - Agent-grade fail-closed applies to `EDGARTOOLS_DECISION` contract reads
    only. Gold refresh, Explore, and ordinary MDM/gold pipelines keep running.
  - Decision Subject Universe is warehouse-active ∩ MDM-active.
  - Agent-grade requires a generation-scoped active graph pointer (or
    equivalent published generation id). No pointer, no agent-grade rows.
- Current-head sketches (not agent-grade): Python serving modules under
  `edgar_warehouse/serving/` (`subject_feature_screen`, `subject_bundle_read`,
  `watermark_aggregator`, `decision_contract`, `dashboard_modes`) plus
  `infra/snowflake/sql/decision_contract/`. Feature-screen SQL is close;
  issuer-bundle SQL still sketches auditor from SOURCE; dashboard SQL
  fail-closes on `DECISION_CONTRACT_PUBLICATION` + `GRAPH_ACTIVE_POINTER`.
- Ask the operator one grilling question at a time.

## Decisions so far

- [Inventory live Decision Contract objects](issues/01-inventory-live-decision-contract-objects.md) — Prod `EDGARTOOLS_DECISION` exists and is empty (no publication table/views; no READY rows). `GRAPH_ACTIVE_POINTER` points at `a573ebba-5820-49f2-8c40-43a4f538a79b` (activated 2026-08-22). MDM-active gold `COMPANY` tracking is a copied MDM column (63,197 active CIKs 1:1). Feature screen and issuer bundle are absent. [research](research/01-live-decision-contract-objects.md)
- [Inventory in-repo contract semantics versus SQL sketches](issues/02-inventory-in-repo-contract-semantics.md) — Python serving is canonical; SQL sketches disagree (MDM-only universe, `GOLD_UPDATED_AT` vs `gold_run_id`, no neighborhood bundle, persist-only bronze, no Agent View modes). [research](research/02-in-repo-contract-semantics.md)
- [Locate issuer neighborhood evidence tables](issues/08-locate-issuer-neighborhood-evidence.md) — Features/13F/ownership gold exist; auditor and subsidiary evidence are 0 rows; graph `AUDITED_BY`/`HAS_PARENT_COMPANY`/`INSTITUTIONAL_HOLDS` are 0; holders sketch columns do not match live gold. [research](research/08-issuer-neighborhood-evidence.md)
- [Encode Bronze evidence identity in the Decision Watermark](issues/03-encode-bronze-in-decision-watermark.md) — Required bronze identity is a digest of ordered unique content-addressed hashes as a typed column; concatenated token is logs-only; missing digest ⇒ not READY / not agent-grade; gold, Explore, and MDM keep running.
- [Inventory JSON and MongoDB as an end-user agentic data plane](issues/10-json-mongodb-as-agentic-data-plane.md) — Not for v1: agents stay on the Snowflake Decision Contract (ADR 0001). JSON is the Python bundle *shape*, not a document SoE. No MongoDB in repo or Terraform. [research](research/10-json-mongodb-agentic-data-plane.md)
- [Define the warehouse-active predicate for Decision Subject Universe](issues/04-define-warehouse-active-universe-predicate.md) — Warehouse-active is bookkeeping `sec_company_sync_state.tracking_status = 'active'`. Universe is a watermark-aligned ∩ snapshot in `EDGARTOOLS_DECISION`; one-sided CIKs excluded; empty ∩ is not READY.
- [Lock issuer v1 agent-grade bundle sections](issues/05-lock-issuer-v1-agent-grade-sections.md) — Agent-grade: features + `IS_INSIDER` + `EMPLOYED_BY`. Holders/auditor/parent keys stay `unavailable`. Section flags do not fail the bundle. Graph-keyed insiders/employment; FY/interim coverage follows glossary/Python.
- [Lock v1 As-Of Decision Feature keys against gold](issues/11-lock-v1-feature-keys-against-gold.md) — Keep 19 Python keys; alias `return_on_equity`/`return_on_assets`; pass through derived `ebitda`/`eps_diluted`/`ebitda_margin`; no `operating_margin`→`ebitda_margin`.
- [Bind v1 feature keys to gold FINANCIAL_FACTORS](issues/12-bind-v1-feature-keys-to-gold-financial-factors.md) — Python alias + gold passthrough + SQL 01/03 19-key projection. Needs dbt `--full-refresh` of `financial_factors` in prod.

## Not yet specified

- Who writes `DECISION_CONTRACT_PUBLICATION` and when it becomes READY.
- Whether dbt or bootstrap SQL owns the long-term contract views.

## Out of scope

- Ingest, bronze capture, PostgreSQL ledger, edgartools gateway cutover
  (change-propagation + ADR 0006).
- Reopening Agent Decision Data Plane tickets 01–07 capture/skip/bronze-off.
- Manager bundle ADV / private-fund agent-grade sections (closed predecessor
  ticket 12; later effort).
- Trading execution, market prices, product OAuth.
- Filing text / NLP as Decision Features.
- Greenfield rewrite, new microservice, external Neo4j, DuckDB replacement.
- MongoDB or a JSON document store as the v1 Agent Decision Surface (ADR 0001 Snowflake-only; S3/API remains optional later, not this map).
- Public SaaS packaging.
