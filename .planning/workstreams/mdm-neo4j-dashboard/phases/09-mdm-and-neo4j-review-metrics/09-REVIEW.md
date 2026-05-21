---
phase: 09-mdm-and-neo4j-review-metrics
reviewed: 2026-05-21T11:02:55Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - edgar_warehouse/mdm/dashboard_readonly.py
  - tests/mdm/test_dashboard_readonly.py
  - edgar_warehouse/mdm/graph_readonly.py
  - tests/mdm/test_graph_readonly.py
  - tests/architecture/test_dashboard_foundation_boundaries.py
  - examples/mdm_graph_dashboard/streamlit_app.py
  - examples/mdm_graph_dashboard/README.md
findings:
  critical: 2
  warning: 1
  info: 0
  total: 3
status: issues_found
---

# Phase 09: Code Review Report

**Reviewed:** 2026-05-21T11:02:55Z
**Depth:** standard
**Files Reviewed:** 7
**Status:** issues_found

## Summary

Reviewed the Phase 9 read-only MDM and Neo4j dashboard helpers, Streamlit shell, tests, and operator README. The implementation preserves read-only boundaries, and the scoped test command passed, but the Neo4j coverage path derives full graph queries from bounded MDM diagnostic samples. That makes operator-facing coverage incomplete and can produce false extra-graph diagnostics.

Verification run:

```bash
uv run pytest tests/mdm/test_dashboard_readonly.py tests/mdm/test_graph_readonly.py tests/architecture/test_dashboard_foundation_boundaries.py -q
# 35 passed in 14.16s
```

## Critical Issues

### CR-01: [BLOCKER] Neo4j coverage skips relationship types not present in bounded diagnostic samples

**File:** `examples/mdm_graph_dashboard/streamlit_app.py:49`

**Issue:** `_read_neo4j_metrics()` asks Neo4j for relationship types from `_relationship_types_from_diagnostics()`, which only returns keys from `known_mdm_edge_keys`. Those keys are built in `get_active_relationship_diagnostic_inputs()` from bounded `candidate_rows` rather than from the full active relationship registry. With the default `global_sample_limit=50`, any active relationship type outside the sampled rows is never queried in Neo4j. The coverage table then compares full MDM counts against an empty Neo4j payload for omitted types, so it can report false missing graph data and miss real extra graph data for registered types that have no sampled MDM row.

**Fix:**

Use the full MDM metrics registry or relationship-count keys for Neo4j relationship queries, and keep diagnostic inputs only for bounded sample lookup.

```python
@st.cache_data(ttl=60, show_spinner=False)
def _read_neo4j_metrics(
    mdm_metrics: Mapping[str, Any],
    mdm_diagnostic_inputs: Mapping[str, Any],
) -> dict[str, Any]:
    relationship_types = list(
        (mdm_metrics.get("relationship_counts") or {}).keys()
    )
    entity_labels = _entity_labels_from_registry(mdm_metrics)
    return graph_readonly.get_neo4j_graph_metrics(
        entity_labels=entity_labels,
        relationship_types=relationship_types,
        mdm_diagnostic_inputs=mdm_diagnostic_inputs,
    ).as_dict()
```

### CR-02: [BLOCKER] Extra graph samples compare full Neo4j counts against a bounded MDM key sample

**File:** `edgar_warehouse/mdm/graph_readonly.py:293`

**Issue:** `_needs_extra_samples()` returns `edge_count > len(known_edge_keys)`, but `known_edge_keys` comes from the bounded MDM diagnostic payload, not the complete set of active MDM edges. A healthy graph with 1,000 Neo4j edges and a 5-row diagnostic sample satisfies `1000 > 5`, so `_find_extra_graph_samples_with_session()` will label legitimate graph edges as "extra" simply because they were not in the small sampled key set. This creates false operator diagnostics even when MDM and Neo4j counts match.

**Fix:**

Only attempt extra-graph sampling when full counts prove Neo4j has more edges than MDM, and do not filter against a bounded key sample as if it were exhaustive. Pass the MDM active count into the graph metric path, or remove extra sample generation until an exhaustive MDM key source is available.

```python
mdm_active_count = _diagnostic_active_count(diagnostic_inputs, rel_type)
if (
    type_limit > 0
    and mdm_active_count is not None
    and edge_count > mdm_active_count
):
    extra_for_type = _find_extra_graph_samples_with_session(...)
```

## Warnings

### WR-01: [WARNING] Dashboard hard-codes Neo4j labels instead of using the active MDM graph registry

**File:** `examples/mdm_graph_dashboard/streamlit_app.py:56`

**Issue:** `_entity_labels_from_diagnostics()` always returns `["Company", "Adviser", "Person", "Security", "Fund"]`. The graph subsystem is registry-driven through `mdm_entity_type_definition.neo4j_label`; hard-coding labels in the dashboard means renamed labels or additional active entity types will be silently omitted from Neo4j node metrics. `dashboard_readonly._get_registry_details()` currently returns only entity type names, so the Streamlit layer has no authoritative labels to query.

**Fix:** Include active `neo4j_label` values in the MDM dashboard registry payload and derive `entity_labels` from that registry instead of the fixed list.

---

_Reviewed: 2026-05-21T11:02:55Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
