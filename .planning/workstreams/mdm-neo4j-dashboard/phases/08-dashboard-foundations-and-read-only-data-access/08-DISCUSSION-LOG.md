# Phase 8: Dashboard Foundations And Read-Only Data Access - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-17  
**Phase:** 8-Dashboard Foundations And Read-Only Data Access  
**Areas discussed:** Dashboard home, MDM read-only contract, Neo4j read-only contract, Startup behavior

---

## Dashboard Home

| Option | Description | Selected |
|--------|-------------|----------|
| New operator dashboard path | Create a separate path so MDM/Neo4j review does not mix with the Snowflake gold dashboard. | ✓ |
| Extend `examples/dashboard` | Add MDM/Neo4j review near the existing Streamlit app; simpler discovery but mixes concerns. | |
| Package under `edgar_warehouse` | Treat as a first-class app module from day one. | ✓ |

**User's choice:** 1 and 3.
**Notes:** Captured as a hybrid: new operator dashboard path for the Streamlit app and docs, with reusable tested query/helper code under `edgar_warehouse`.

Follow-up decision:

| Option | Description | Selected |
|--------|-------------|----------|
| Streamlit | Fastest path and consistent with existing examples. | ✓ |
| CLI HTML report | Static output, less interactive. | |
| Lightweight web app | More flexible but heavier foundation. | |

**User's choice:** Streamlit.

---

## MDM Read-Only Contract

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated read-only query helpers | Structured SELECT-style helpers for dashboard use and safety tests. | ✓ |
| Reuse CLI internals directly | Less code, but handlers mix printing, sessions, and command behavior. | |
| Direct SQLAlchemy queries inside Streamlit | Fastest to build, but weaker safety boundary. | |

**User's choice:** Dedicated read-only query helpers.
**Notes:** Helpers should return structured data and avoid mutation surfaces such as `MDMPipeline`, resolver writes, migrations, and graph sync.

---

## Neo4j Read-Only Contract

| Option | Description | Selected |
|--------|-------------|----------|
| Review-only wrapper around existing client | Reuse `Neo4jGraphClient` connection conventions and add explicit read helpers. | ✓ |
| Use Neo4j driver directly in Streamlit | Fewer layers but duplicates connection handling. | |
| Shell out to `edgar-warehouse mdm verify-graph` | Reuses current behavior but poor fit for interactive dashboard filtering. | |

**User's choice:** Review-only wrapper around existing client.
**Notes:** Helpers should validate dynamic Cypher pieces and tests should guard against write operations.

---

## Startup Behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Partial availability | Launch with either MDM or Neo4j and show per-source status. | |
| Require MDM, Neo4j optional | MDM is source of truth; graph can be disconnected. | ✓ |
| Require both | Fail unless both stores connect. | |

**User's choice:** Require MDM, Neo4j optional.
**Notes:** If MDM is missing, fail with actionable non-secret config/error message. If Neo4j is missing, launch in MDM-only mode and show graph as disconnected/not configured.

## the agent's Discretion

- Choose exact file names and module boundaries within the locked structure.
- Choose fixture and mock test strategy, provided no live credentials are required.

## Deferred Ideas

- Managed AWS deployment for the dashboard.
- Drill-through graph visualization.
- Full metric and mismatch views beyond the foundation are Phase 9.
