# Dashboard research workflows

The Snowflake dashboard has a sticky, explicit mode boundary:

- **Agent View** reads only the published Decision Contract registry and fails
  closed when its watermark or graph generation is unavailable/misaligned.
- **Explore** exposes Company 360, the accounting-only Fundamentals Screener,
  Insider Watch, and the ADV Adviser/Fund Explorer. Explore results are
  research surfaces and are never agent-grade answer evidence.

All four workflows use `dashboard_workflows.py`. Queries bind user values,
select named columns, use active graph-generation joins where needed, and
enforce hard server-side limits:

| Workflow | Maximum rows |
| --- | ---: |
| Company 360 surface | 250 |
| Fundamentals Screener | 200 |
| Insider Watch | 250 |
| ADV Explorer | 200 |

Missing coverage, missing values, and insufficient history remain distinct
from a measured numeric zero. SEC filing drill-through uses deterministic
EDGAR archive URLs. ADV evidence links use the official IAPD firm summary.
Exports contain only the already-bounded on-screen result.

## Release acceptance

`infra/scripts/check-dashboard-acceptance.py` inventories every launch-critical
view. `infra/scripts/check-dashboard-uat.py` separately gates the release-bound
automated smoke, browser scenarios, rollback rehearsal, and explicit operator
signoff:

```bash
uv run python infra/scripts/check-dashboard-uat.py \
  --emit-skeleton \
  --release-candidate sha-0123456789ab \
  --out dashboard-uat.json

uv run python infra/scripts/check-dashboard-uat.py --check dashboard-uat.json
```

The UAT checker is fail-closed and requires query IDs, timings, row counts,
role/app/git/watermark/generation identity, stage digest verification, six
browser states, a verified rollback, and operator signoff. Its scope statement
is immutable: dashboard acceptance does not satisfy warehouse full-chain
execution or data-integrity release gates.
