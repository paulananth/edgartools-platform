# Select the rendered dashboard UI test seam

Type: research (AFK)
Status: resolved
Assignee: Codex
Blocks: 04-implement-dashboard-subject-resolver-and-ui-contract-tests

## Question

Which test seam can deterministically drive the rendered Streamlit tab inputs
and assert tab-specific output states, while keeping SQL contract tests and
release-readiness acceptance separate?

## Answer

Use Streamlit `AppTest` as the primary deterministic rendered-UI test seam.
The project locks Streamlit 1.56.0 in `uv.lock`; AppTest imports successfully
with `uv run --extra dashboard`. It drives the real widget tree, reruns, and
session state while a fake `snowflake.snowpark.context.get_active_session`
returns deterministic DataFrames.

Keep the existing fake-Streamlit tests as companion coverage. They preserve
query binding, Agent View allowlists, flat-file imports in Streamlit-in-Snowflake,
and secret-safe error-copy guarantees, but their no-op widgets do not prove
rendered interaction.

Do not use Playwright or another browser harness for deterministic preflight:
none is configured, and a live Snowflake-hosted Streamlit run would require
authenticated Snowsight access. It may be added only as an explicitly-authorized
live acceptance layer.

### Test fixture boundary

Inject a fake Snowpark session before `AppTest.from_file(...).run()`. Route
each normalized SQL fingerprint and bound parameter tuple to small static
DataFrames. The canonical subject fixture maps `AAPL` to `APPLE INC.` / CIK
320193 and supplies one row for each positive tab route; an empty DataFrame or
raised safe exception drives `no_coverage` and `unavailable` cases.

### Required matrix

| Tab | Rendered interaction assertions |
| --- | --- |
| Summary | Agent contract banner/status and Explore summary fixture output |
| Company 360 | `AAPL` resolves to CIK 320193; Agent View exposes only contract output; Explore exposes populated and unavailable surfaces |
| Fundamentals | Agent View explains Explore-only boundary; Explore shows results and resolved-subject `no_coverage` |
| Insider Watch | Agent View explains Explore-only boundary; Explore shows transaction results and issuer drill-through |
| ADV | Adviser/fund search shows results and deterministic `no_match` |
| Pipeline | Agent View explains boundary; Explore shows bounded operational result and unavailable state |

The AppTest suite runs with `uv run --extra dashboard python -m pytest <ui-test-path> -q`.
It is appended to the dashboard deploy script's credential-free preflight, not
to `dashboard-acceptance.json` or a pipeline test.
