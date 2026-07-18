# Streamlit Agent View vs Explore (ticket 13)

Human Audit View dual mode on Streamlit-in-Snowflake (ADR 0001).

## Modes

| Mode | Behavior |
| --- | --- |
| **Agent View** (default) | Decision Contract objects only; free gold joins blocked |
| **Explore** | Broader gold/SOURCE queries allowed; **always labeled** not agent contract / not Trading Decision input |

Mode is sticky for the Streamlit session (`edgartools_dashboard_mode`). The same
CIK can be inspected in both modes for audit comparison.

## Code

| Layer | Location |
| --- | --- |
| Pure gating (unit-tested) | `edgar_warehouse/serving/dashboard_modes.py` |
| SiS UI | `infra/snowflake/streamlit/streamlit_app.py` (mirrors allowlist for deploy) |

## Related

- Tickets 10–12 — contract objects Agent View projects  
