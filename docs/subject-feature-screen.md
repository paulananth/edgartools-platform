# Subject Feature Screen (ticket 10)

Multi-issuer ranking surface on the **Snowflake Decision Contract** (ADR 0001).

## Purpose

Let a trading agent **rank/filter** issuers in the Decision Subject Universe
without loading full Subject Bundle neighborhoods. Deep-dive remains ticket 11
(Subject Bundle Read).

## Contract object

| Concern | Rule |
| --- | --- |
| Universe | warehouse active ∩ MDM active (ticket 14) |
| Factors | As-Of: Primary Annual (FY) + Latest Interim **only if** `period_end` &gt; FY |
| Nulls | **null ≠ zero** — missing metrics stay null |
| Coverage | `present` / `empty` / `unavailable` / `not_applicable` on FY and interim sections |
| Market data | **Forbidden** — no price, PE, market cap (pure-SEC only) |
| Identity | `decision_contract_version` + Decision Watermark identity (ticket 09) |
| Agent-grade | Fail-closed via `evaluate_agent_grade`; screen may still list rows for audit |

## Code

| Layer | Location |
| --- | --- |
| Pure semantics (unit-tested) | `edgar_warehouse/serving/subject_feature_screen.py` |
| Snowflake view sketch | `infra/snowflake/sql/decision_contract/01_subject_feature_screen.sql` |
| Watermark gate | `edgar_warehouse/serving/decision_contract.py` |

## Usage (Python)

```python
from edgar_warehouse.serving.subject_feature_screen import build_subject_feature_screen

screen = build_subject_feature_screen(
    warehouse_active_ciks=warehouse_ciks,
    mdm_active_ciks=mdm_ciks,
    period_rows=gold_financial_period_rows,
    watermark_components={
        "business_date": "2024-06-30",
        "gold_run_id": "...",
        "graph_generation_id": "...",
        "silver_completeness_ok": True,
        "graph_parity_ok": True,
    },
)
if not screen["agent_grade"]:
    # abstain from trading decisions on this watermark
    ...
for row in screen["rows"]:
    ...
```

## Related

- Ticket 09 — Decision Watermark / agent-grade  
- Ticket 11 — Subject Bundle Read (issuer)  
- Ticket 13 — SiS Agent View / Explore over contract objects  
