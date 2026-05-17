# Project: EdgarTools Platform

workstream: mdm-neo4j-dashboard
status: active
milestone: v1.2 MDM Neo4j Review Dashboard
updated: 2026-05-17

---

## Core Value

Deliver structured, business-ready SEC EDGAR data through a reliable AWS-focused pipeline, and give operators a practical way to inspect MDM relational state and Neo4j graph state before trusting downstream analytics or graph workflows.

---

## Current Milestone: v1.2 MDM Neo4j Review Dashboard

**Goal:** Build an isolated dashboard that lets operators review MDM entity and relationship data alongside Neo4j node and edge state, with clear mismatch diagnostics and no mutation of the MDM or graph pipelines.

**Target features:**

- Read-only MDM overview for entity counts, relationship counts, source freshness, and data quality warnings.
- Read-only Neo4j overview for node counts, edge counts by type, pending graph sync, and missing-edge diagnostics.
- Cross-store comparison that highlights MDM-to-Neo4j mismatches without modifying either store.
- Local/operator-friendly dashboard launch path that uses existing environment variables and avoids new deployment architecture.

---

## Scope Boundaries

- This workstream runs in `/Users/aneenaananth/gsd-workspaces/mdm-neo4j-dashboard/edgartools-platform` on branch `workspace/mdm-neo4j-dashboard`.
- Dashboard work must not edit the active `neo4j-pipe` workstream artifacts except through explicit reviewed merges.
- Keep the implementation AWS-focused and local/operator-friendly.
- Do not add non-AWS registries, storage targets, workflow engines, or secret-management paths.
- Do not mutate MDM rows or Neo4j graph data from the dashboard.
- Do not change generated deployment JSON.

---

## Relevant Existing Architecture

```text
Bronze/Silver SEC data
  -> MDM relational store
  -> MDM relationship rows
  -> Neo4j graph sync
  -> Review dashboard for operators
```

Primary source surfaces:

- `edgar_warehouse/mdm/database.py` for MDM SQLAlchemy models.
- `edgar_warehouse/mdm/pipeline.py` for entity and relationship derivation logic.
- `edgar_warehouse/mdm/graph.py` for Neo4j sync/query integration.
- `edgar_warehouse/mdm/cli.py` for existing `counts`, `verify-graph`, `sync-graph`, and connectivity behavior.
- `docs/neo4j.md` for Neo4j environment expectations.
- `examples/dashboard/` and `infra/snowflake/streamlit/` for existing dashboard patterns.

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition:**

1. Requirements invalidated? Move to Out of Scope with reason.
2. Requirements validated? Move to Validated with phase reference.
3. New requirements emerged? Add to Active.
4. Decisions to log? Add to Key Decisions.
5. Scope boundaries still accurate? Update if drifted.

**After this milestone:**

1. Review whether the dashboard is a local/operator tool or should become a deployable app.
2. Audit read-only guarantees.
3. Decide whether live AWS proof is needed.
4. Update documentation and runbooks.
