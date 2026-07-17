# Decision Watermark and Agent-Grade gate

Ticket 09 / ADR 0001. Code: `edgar_warehouse.serving.decision_contract`.

## Purpose

An **Agent-Grade Read** is only valid when a composite **Decision Watermark** is
complete and aligned. Missing or conflicting components **fail closed** — the
agent must not trade on best-effort joins.

## Decision Contract Version

`DECISION_CONTRACT_VERSION` (currently `"1"`) is returned on every evaluation so
agents can pin schema semantics.

## Required components

| Field | Meaning |
| --- | --- |
| `business_date` | Business date for current-at-watermark semantics |
| `gold_run_id` | Gold / feature export run identity |
| `graph_generation_id` | Hosted graph generation / relationship generation id |
| `silver_completeness_ok` | Published claim that silver completeness for the subject/window passed |
| `graph_parity_ok` | verify-graph (or equivalent) parity passed |

## Blocking conditions

- Any required identity field empty
- `silver_completeness_ok` or `graph_parity_ok` false
- `high_severity_reconcile_open` true **unless** `reconcile_waived` true
- `bronze_persist_used` true but no `bronze_content_hashes` (and the inverse)

## Usage

```python
from edgar_warehouse.serving.decision_contract import evaluate_agent_grade

result = evaluate_agent_grade({
    "business_date": "2024-06-01",
    "gold_run_id": "…",
    "graph_generation_id": "…",
    "silver_completeness_ok": True,
    "graph_parity_ok": True,
})
if not result.agent_grade:
    # abstain — result.reasons explains why
    ...
```

Snowflake / contract builders project these fields. Subject Feature Screen
(ticket 10) attaches watermark identity via
`edgar_warehouse.serving.subject_feature_screen`. This module remains the
fail-closed validator for those projections.
