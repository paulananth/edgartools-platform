# Phase 4 Patterns: Dashboard Hosted Graph Migration

## Pattern 1: Streamlit As Renderer

Keep `examples/mdm_graph_dashboard/streamlit_app.py` as a rendering shell over helper payloads. It may format rows, filter rows, render Streamlit controls, clear Streamlit cache, and choose status copy. It must not own Snowflake SQL, Cypher, subprocess calls, credential parsing, CLI stdout parsing, mutations, or activation/repair actions.

## Pattern 2: Dataclass Helper Payloads

Follow `dashboard_readonly.py`: model helper results as dataclasses with `as_dict()` methods, timestamps, bounded samples, and safe unavailable states. Tests should exercise helper behavior with fake verifier/connection objects rather than live Snowflake, AWS, MDM Postgres, or Native App credentials.

## Pattern 3: Reuse Verify-Graph Semantics

Dashboard graph comparison should normalize the same conceptual payload that `edgar-warehouse mdm verify-graph` produces:

- node parity by entity type
- relationship parity by relationship type
- missing and extra graph nodes
- missing and extra graph edges
- missing edge endpoints
- Native App prerequisite and smoke check status

The dashboard is an inspection surface. It should not become the acceptance gate, and it should not weaken the CLI gate.

## Pattern 4: Failure-Only Native App Detail

Render Native App detail only when checks fail, are skipped, or are unavailable. Healthy `GRAPH_INFO`, `BFS`, `WCC`, and compute-pool checks may stay out of the primary dashboard view. Failure detail should include `Check`, `Status`, `Detail`, and `Remediation`, with no raw connector errors, DSNs, passwords, tokens, stack traces, or secret-bearing hostnames.

## Pattern 5: Architecture Tests As Safety Rails

Keep focused architecture tests around boundaries:

- route labels and sidebar controls are stable
- row limits remain bounded
- filters remain single-select
- dashboard files contain no mutation controls
- Streamlit contains no raw SQL, raw Cypher, subprocess, or stdout parsing
- active docs do not tell operators to configure external `NEO4J_*` credentials
- docs point to `verify-graph`, Native App prerequisites, and AWS hosted graph E2E as external commands only

## Pattern 6: Minimal Rename

Preserve the operator route label `Neo4j Overview`, but replace stale external-service wording in page copy, table labels, docs, helper tests, and failure states with Snowflake-hosted graph terminology. Internal names can remain only when changing them creates more risk than clarity, and tests must prove those names do not imply external Bolt/Aura configuration.

