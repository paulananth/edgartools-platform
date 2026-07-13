---
phase: 08
slug: neo4j-native-app-verification-gaps
date: 2026-07-12
status: draft
---

# Phase 08 Validation Strategy

- Unit: current API SQL renderers, job-error parsing, and failure-domain classification.
- Integration: fake Snowflake cursor exercises readiness, parity, capability, and combined failures.
- Live dev: GRAPH_INFO and BFS current calls, LIST_GRAPHS exact external reproduction, app version,
  cleanup, and operator-readable verify-graph payload.

Commands:

```bash
uv run pytest tests/mdm/test_snowflake_graph_migration.py tests/mdm/test_cli_snowflake_graph.py
SNOW_CONNECTION=snowconn SNOWFLAKE_CONNECTION=snowconn \
DBT_SNOWFLAKE_DATABASE=EDGARTOOLS_DEV \
uv run --extra snowflake edgar-warehouse mdm verify-graph
```

