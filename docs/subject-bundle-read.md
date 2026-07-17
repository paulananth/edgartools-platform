# Subject Bundle Read — issuer (ticket 11)

Single-subject **Decision Graph Bundle** for an issuer on the Snowflake Decision
Contract (ADR 0001). Complements the multi-issuer [Subject Feature Screen](subject-feature-screen.md)
(ticket 10).

## Purpose

Deep-dive Trading-Relevant Neighborhood for one Bundle Subject (CIK) at a
Decision Watermark: insiders, employment, dual 13F sections, auditor, optional
parent, subject features, and ADV `not_applicable` for pure issuers.

## Section contract

| Section | Agent-grade rule | Coverage |
| --- | --- | --- |
| `insiders` | Graph `IS_INSIDER` **and** gold ownership source accession | present / empty / unavailable |
| `employment` | `EMPLOYED_BY` with `source_system` `proxy_def14a` or `item_5_02`; pay from gold proxy | present / empty / unavailable |
| `holders_of_subject` | 13F holders of the issuer; Latest Complete Holdings Period + lag | present / empty / unavailable |
| `subject_as_manager_portfolio` | Issuer’s own 13F book (separate name) | present / empty / unavailable |
| `auditor` | Prefer auditor evidence + PCAOB id | present / unavailable |
| `has_parent` | Only when subsidiary inventory complete; scope `registrant_disclosed` | present / empty / unavailable |
| `subject_features` | FY + newer interim pure-SEC vectors (same as-of rules as ticket 10) | coverage on FY / interim |
| `adv` | **Always `not_applicable`** on pure issuer bundles (ticket 12 for managers) | not_applicable |

## Identity

Every payload includes:

- `bundle_subject_cik`, `bundle_kind: issuer`
- `decision_contract_version`
- `decision_watermark_identity` (business_date, gold_run_id, graph_generation_id)
- `agent_grade` from ticket 09 fail-closed evaluation

## Code

| Layer | Location |
| --- | --- |
| Pure semantics | `edgar_warehouse/serving/subject_bundle_read.py` |
| Feature as-of helpers | `edgar_warehouse/serving/subject_feature_screen.py` |
| Watermark gate | `edgar_warehouse/serving/decision_contract.py` |
| SQL sketch | `infra/snowflake/sql/decision_contract/02_subject_bundle_read_issuer.sql` |

## Usage

```python
from edgar_warehouse.serving.subject_bundle_read import build_issuer_subject_bundle

bundle = build_issuer_subject_bundle(
    subject_cik=320193,
    watermark_components={...},
    graph_insider_edges=[...],
    gold_ownership_rows=[...],
    employment_edges=[...],
    executive_pay_rows=[...],
    holders_of_subject=[...],
    subject_as_manager_portfolio=[...],
    holdings_period={"latest_complete_holdings_period": "2024-03-31", "lag_days": 45},
    auditor_edges=[...],
    parent_edges=[...],
    parent_inventory_complete=True,
    period_rows=[...],
)
if not bundle["agent_grade"]:
    # abstain
    ...
```

## Related

- Ticket 09 — Decision Watermark  
- Ticket 10 — Subject Feature Screen  
- Ticket 12 — Manager bundle ADV sections  
- Ticket 13 — SiS Agent View / Explore  
