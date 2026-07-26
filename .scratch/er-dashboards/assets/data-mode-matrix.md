# Data × mode matrix for ER dashboards

**Default fail-closed:** unknown object → Agent View blocked.  
**Explore:** all gold/SOURCE + ERDP Explore products allowed; always bannered.

| Object / capability | Agent View | Explore | Used by |
|---------------------|:----------:|:-------:|---------|
| `SUBJECT_FEATURE_SCREEN` | ✓ | ✓ | ERD-4 pure-SEC |
| `SUBJECT_BUNDLE_READ*` | ✓ | ✓ | ERD-3 relationships, audit strip |
| `DECISION_WATERMARK` / contract status | ✓ | ✓ | All chrome |
| `EDGARTOOLS_GOLD_STATUS` | ✓ (lag only) | ✓ | Freshness strip |
| `COMPANY` / `TICKER_REFERENCE` | ✗ | ✓ | All identity |
| `FILING_ACTIVITY` / `FILING_DETAIL` | ✗ | ✓ | ERD-2, ERD-3 |
| `FINANCIAL_DERIVED` / `FINANCIAL_FACTS` / `FINANCIAL_FACTORS` | ✗* | ✓ | ERD-1,3,4 |
| `EARNINGS_RELEASES` | ✗ | ✓ | ERD-1, ERD-3 |
| `EARNINGS_CALENDAR` (ERDP-03) | ✗ | ✓ | ERD-1, ERD-2 |
| `OWNERSHIP_*` / `INSTITUTIONAL_HOLDINGS` | ✗** | ✓ | ERD-2,3,4 |
| `ACCOUNTING_FLAGS` / `EXECUTIVE_RECORDS` | ✗ | ✓ | ERD-3 |
| ERDP-07 PriceProvider / EOD join | ✗ | ✓ | ERD-1,3,4 |
| Future `CONSENSUS_ESTIMATES` | ✗ | ✓ | ERD-1 |
| Future `GUIDANCE_FACTS` | ✗ | ✓ | ERD-1 |
| Future `TRANSCRIPT_EVENTS` | ✗ | ✓ | ERD-1 |
| yfinance network calls | ✗ | ✓ (cached) | ERDP-07 |

\* Agent View may surface **contracted** feature vectors via Feature Screen / Bundle only — not free multi-year gold history tables.  
\** Bundle sections may expose holder/auditor slices under contract; free tape queries stay Explore.

## Label requirements (Explore market / Street)

Every widget that renders non-SEC Explore products must show:

```text
source_system=<yahoo|finnhub|firm_manual|…> · grade=explore · not agent Decision Contract
```

## Implementation hook

```python
# Pseudo — extend existing helpers
if mode == MODE_AGENT_VIEW and not _is_object_allowed(mode, object_name):
    st.info("Switch to Explore for this ER research panel.")
    return
```

Do **not** add ERDP tables to `AGENT_VIEW_ALLOWED_OBJECTS` without a new ADR.
