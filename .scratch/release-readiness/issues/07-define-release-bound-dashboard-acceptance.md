# Define Release-Bound Dashboard Acceptance

Type: prototype
Status: resolved
Blocked by: 01, 04

## Question

What concrete UAT artifact must prove every launch-critical read-only dashboard view against the same Release Candidate and release watermark, after Hosted Graph Completeness, without stale data, mutation controls, secret leakage, or unbounded output?

## Answer

**Artifact:** `docs/release-readiness/dashboard-acceptance.json` (same evidence-directory
convention as `rollback-rehearsal.json`). Schema: `release_candidate`, `release_watermark`,
`overall_status`, and a `views` map keyed `<DASHBOARD>::<view_id>`, one entry per view, each
carrying `status` (`not_checked`/`pass`/`fail`), `watermark_checked`, `operator`, `checked_at`,
and three independent boolean sub-checks — `mutation_surface_clear`, `secret_leakage_clear`,
`unbounded_output_clear` — plus `row_count_observed` and a free-text `note`.

**View inventory (exactly 25, all launch-critical):** every real view in the two, and only two,
Terraform-deployed Streamlit-in-Snowflake dashboards —
`EDGARTOOLS_DASHBOARD` (`infra/snowflake/streamlit/streamlit_app.py`: 5 Summary views, 10
Company Details views incl. the 4 Equity Research sub-tabs, 6 Pipeline views) and
`MDM_GRAPH_DASHBOARD` (`infra/snowflake/mdm_dashboard/streamlit_app.py`: Overview, MDM
Overview, Neo4j Overview, Mismatch Diagnostics). `examples/dashboard/edgar_universe_dashboard.py`
is explicitly **excluded** — confirmed it is not Terraform-deployed anywhere, so it isn't
launch-critical.

**Overall status logic** (`overall_status`, validated live in the prototype): `READY` only if
every view is `pass`, every `watermark_checked` equals the current `release_watermark`, and all
three sub-checks are explicitly `true` on every passing view. Any unchecked view, any
stale-watermark view (checked against an earlier watermark than the one currently in force —
e.g. gold refreshed again mid-review), any `fail`, or any **thin-sample pass** (a `pass` with one
of the three sub-checks left `null`/unset rather than confirmed `false`→corrected to `true`)
forces `NOT_READY`, each with its own distinguishable reason. This directly encodes the
CONTEXT.md glossary term's three "Avoid" cases (stale-watermark approval, thin-sample approval,
and — via the three explicit sub-checks — production-like UAT standing in for a real check of
mutation controls / secret leakage / unbounded output).

**Staleness is detected, not auto-cleared:** rebasing `release_watermark` (a new gold refresh
landing) does not wipe prior per-view checks — it flags every view whose `watermark_checked`
no longer matches as stale, so the artifact always shows exactly which views need a re-check
rather than silently forgetting what was already reviewed.

**Attesting role:** **Dashboard Reviewer** — the role ticket 01 (Release Evidence Manifest)
already named for exactly this purpose (alongside Candidate Builder, AWS Operator, Snowflake
Operator, MDM/Graph Operator, Release Owner). No new role introduced.

All four points (schema shape, staleness-detected-not-auto-cleared, view-inventory boundary,
attesting role) confirmed directly with the user after driving a logic prototype through the
stale-watermark and thin-sample cases by hand. Prototype captured on throwaway branch
`prototype/07-dashboard-acceptance` (commit `78013d8`), not merged to main — the validated
decision above is the durable artifact, the prototype code is a primary-source reference only.

This binds to the same Release Candidate/Release Data Watermark ticket 01 and ticket 04
established, and is consumed as stage 8 of 9 by ticket 06's Full-Chain Launch Gate
(`full-chain-launch-pass.json`), same pattern as ticket 05/26's rollback-rehearsal.json.
