# Project: EdgarTools Platform

workstream: neo4j-snowflake
status: active
milestone: v1.3 Neo4j Snowflake Native App Migration
updated: 2026-05-25

---

## Core Value

Deliver structured, business-ready SEC EDGAR graph data through the existing AWS and
Snowflake platform while moving Neo4j graph analytics from an external Neo4j runtime into
Snowflake through the Neo4j Graph Analytics Native App.

---

## Current Milestone: v1.3 Neo4j Snowflake Native App Migration

**Goal:** Replace the external Neo4j graph target with the Snowflake Marketplace Neo4j
Graph Analytics Native App, while keeping `edgar-warehouse` as the owner of graph sync
commands and preserving end-to-end MDM graph verification.

**Target features:**

- Prove and document the Snowflake Marketplace Native App installation, permissions, and
  runtime model for Neo4j Graph Analytics.
- Adapt `edgar-warehouse mdm sync-graph` so graph sync targets Snowflake-hosted Neo4j
  graph tables/projections instead of an external Neo4j service.
- Move graph connection/configuration expectations into Snowflake-managed application and
  role configuration, not external `NEO4J_*` runtime credentials.
- Preserve full validation coverage: matching node/edge counts, exact relationship parity,
  query-level traversal checks, dashboard comparison, and an end-to-end AWS pipeline run.
- Update the MDM Neo4j review dashboard to inspect the Snowflake-hosted graph target.

Developer-facing success metric: Given an already-loaded AWS MDM dataset, operators can run
the existing graph sync and verification workflow against the Snowflake-hosted Neo4j Native
App path, prove parity with MDM relationship state, inspect the result in the dashboard, and
avoid any dependency on an external Neo4j Aura/Bolt target.

---

## Scope Boundaries

- This workstream is isolated under `.planning/workstreams/neo4j-snowflake/`.
- Keep AWS as the active platform path; do not add non-AWS registries, workflow engines,
  storage targets, or secret-management paths.
- Reuse the existing Snowflake source/gold model as much as possible; create graph-ready
  tables/views only where needed for the Neo4j Native App contract.
- `edgar-warehouse` continues to own graph sync and verification commands.
- Do not keep external Neo4j as a parallel validation target for this milestone.
- Do not mutate generated deployment JSON unless an explicit rollout artifact is requested.

---

## Relevant Architecture

```text
SEC EDGAR API
  -> edgar-warehouse CLI on AWS ECS
  -> S3 bronze / warehouse storage
  -> Snowflake source + gold tables
  -> MDM entity and relationship state
  -> Snowflake graph-ready node and edge tables/views
  -> Neo4j Graph Analytics Native App in Snowflake
  -> MDM Neo4j review dashboard
```

The verified Native App assumption for this milestone is that Neo4j Graph Analytics is
installed from Snowflake Marketplace, operates over Snowflake tables/views, runs in Snowflake
using Snowpark Container Services, and can write graph analytics results back to Snowflake
tables.

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition:**

1. Requirements invalidated? Move to Out of Scope with reason.
2. Requirements validated? Move to Validated with phase reference.
3. New requirements emerged? Add to Active.
4. Decisions to log? Add to Key Decisions.
5. Native App assumptions still accurate? Update from current Snowflake/Neo4j docs.

**After this milestone:**

1. Decide whether external Neo4j support should be removed, deprecated, or retained only for local development.
2. Promote Snowflake Native App runbook steps into operator documentation.
3. Audit dashboard and verification docs for obsolete `NEO4J_*` credential assumptions.
