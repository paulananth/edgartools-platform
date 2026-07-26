# 04 — SiS nav integration

Type: grilling  
Status: resolved  
Blocked by: 01  

## Question

New Streamlit app vs extend `infra/snowflake/streamlit/streamlit_app.py`? How should nav items be named?

## Answer

**Extend the existing SiS app** (same deploy/stage path, mode chrome, gold helpers).

Proposed nav:

```text
Summary | Company | Earnings | Catalysts | Ideas | Pipeline
```

| Nav label | Maps to |
|-----------|---------|
| Summary | Existing summary / health strip |
| Company | Research Workspace (ERD-3) — evolved Company Details |
| Earnings | ERD-1 |
| Catalysts | ERD-2 |
| Ideas | ERD-4 (screener + Explore recipes) |
| Pipeline | Existing ops (Explore-gated as today) |

**Rejected:** separate `examples/er_dashboard` as production host (prototype-only OK for spikes).  
**Note:** multipage module split is an implementation detail; staging must keep mode allowlist consistent with `dashboard_modes.py`.
