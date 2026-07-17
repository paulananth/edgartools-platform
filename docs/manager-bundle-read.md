# Manager Subject Bundle — ADV sections (ticket 12)

Extends the issuer [Subject Bundle Read](subject-bundle-read.md) for
**adviser/manager** subjects. Pure issuers are unchanged (ADV remains
`not_applicable`).

## Agent-grade rules

| Rule | Detail |
| --- | --- |
| MANAGES_FUND / ADV funds | Agent-grade **only** when `source_system` is bulk IAPD (`bulk_iapd`, `iapd_bulk`, …) |
| Heuristic ADV parse | Never `agent_grade_edge=true` — listed under `non_agent_grade` |
| IS_ENTITY_OF | Included when **both** adviser CIK and company CIK resolve; sparse/zero is empty/unavailable, not a hard fail for issuers |
| ADV lag metadata | When agent-grade ADV rows exist, attach `adv_lag_metadata` (as-of date, lag_days, watermark_component `adv_bulk_iapd`) |

## Code

`edgar_warehouse/serving/manager_bundle_read.py`

```python
from edgar_warehouse.serving.manager_bundle_read import build_manager_subject_bundle

bundle = build_manager_subject_bundle(
    subject_cik=adviser_cik,
    watermark_components={...},
    manages_fund_edges=[...],  # bulk_iapd only for agent-grade
    is_entity_of_edges=[...],
    adv_lag_metadata={"adv_as_of_date": "2024-03-31", "lag_days": 90},
)
```

## Related

- Ticket 11 — issuer bundle (ADV not_applicable)  
- Ticket 13 — SiS Agent View / Explore  
