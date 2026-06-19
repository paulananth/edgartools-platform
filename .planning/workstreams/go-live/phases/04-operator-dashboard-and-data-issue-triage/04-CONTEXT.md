# Phase 4: Operator Dashboard And Data Issue Triage - Context

**Gathered:** 2026-06-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Operators can use the dashboard and runbook as the first inspection path for
launch data issues (Requirements: DASH-01, DASH-02, DASH-03).

Phase 4 explicitly scopes source-code and runbook edits for three deliverables:

1. **README rewrite** (`examples/mdm_graph_dashboard/README.md`) — remove
   `NEO4J_*` external graph setup instructions and replace with
   Snowflake-hosted graph setup. This is the upstream closeout work from
   `neo4j-snowflake` Phase 4 Plan 03 (`04-03-PLAN.md`), executed inside
   Phase 4 go-live on the `workspace/go-live` branch.

2. **Data issue triage guide** (`runbook/data-issue-triage.md`) — a new
   operator-facing document covering all 8 DASH-02 layers (ingestion,
   bronze/silver, MDM, hosted graph, dbt/gold, Native App, dashboard,
   permissions) with symptom descriptions, diagnostic CLI commands, owner,
   and escalation path.

3. **Dashboard UAT** — operator runs the dashboard locally with dev
   credentials (MDM_DATABASE_URL from dev Secrets Manager + dev Snowflake
   connection), inspects the four views, and records text pass/fail notes in
   the existing `evidence/dashboard-security.md` Phase 1 template (5 UAT
   rows). Documented as "dev precedent only — prod proof required separately."

The dashboard remains an inspection surface; CLI verification (`edgar-warehouse
mdm verify-graph`, dbt test, Step Functions) remains the acceptance gate.

</domain>

<decisions>
## Implementation Decisions

### NEO4J_* Cleanup Ownership (DASH-03)

- **D-01:** Phase 4 **executes the `04-03-PLAN.md` scope** (from the
  `neo4j-snowflake` workstream) as go-live Phase 4 work. This is the
  explicit "source-code or runbook edits" exception to go-live workstream
  isolation. The `neo4j-snowflake` workstream is not touched; all commits
  land on `workspace/go-live`.
- **D-02:** All Phase 4 commits — including the README rewrite and arch test
  updates — land on `workspace/go-live`. The neo4j-snowflake workstream branch
  is not modified.
- **D-03:** `uv run pytest tests/architecture/test_dashboard_foundation_boundaries.py -q`
  is the automated gate after the README rewrite. Tests must pass before the
  README plan is considered complete.
- **D-04:** The README rewrite is a **standalone Wave 1 plan** (`04-01`).
  Dashboard UAT and triage guide plans are Wave 2 (can run after 04-01
  completes).

### Data Issue Triage Guide (DASH-02)

- **D-05:** Create a **new** `runbook/data-issue-triage.md` in
  `.planning/workstreams/go-live/phases/04-operator-dashboard-and-data-issue-triage/runbook/`.
  Same pattern as Phase 3's `runbook/mdm-secrets.md`. This is a Phase 4
  planning artifact (not a permanent repo doc).
- **D-06:** Each layer entry includes **diagnostic CLI commands** (1-2 per
  layer) so an operator can follow the guide start-to-finish without looking
  up other docs. Commands must be non-destructive, read-only checks.
- **D-07:** Covers **all 8 layers** from DASH-02: ingestion, bronze/silver,
  MDM, hosted graph, dbt/gold, Native App, dashboard, and permissions. No
  layer omitted. Launch-critical layers (MDM, hosted graph, dbt/gold, Native
  App) get priority treatment; ingestion/permissions/dashboard-layer entries
  are still required but may be briefer.

### Dashboard UAT (DASH-01, DASH-03)

- **D-08:** UAT runs with **dev credentials**: `MDM_DATABASE_URL` loaded
  from dev AWS Secrets Manager (same as Phase 3 re-verification), dev
  Snowflake connection (`DBT_SNOWFLAKE_*` / `SNOWFLAKE_CONNECTION`). Not
  blocked by prod secret population.
- **D-09:** UAT evidence is annotated "dev precedent only — prod proof
  required separately," matching the Phase 1 launch gate matrix pattern for
  dev-only runs.
- **D-10:** Phase 4 **fills the existing 5 UAT rows** in
  `evidence/dashboard-security.md` (from Phase 1 template): MDM overview,
  Hosted graph overview, Mismatch diagnostics, Manual refresh, Bounded
  samples. No new evidence file created.
- **D-11:** UAT is **live**: operator runs
  `uv run --extra dashboard --extra mdm-runtime streamlit run examples/mdm_graph_dashboard/streamlit_app.py`
  locally, inspects each view, and records text pass/fail notes. Screenshots
  are optional if secret-safe; text notes are sufficient.

### Secret Safety (DASH-03 + go-live security rules)

- **D-12:** No secrets, DSNs, passwords, tokens, raw connector exceptions,
  stack traces, or unbounded exports in any evidence or planning file.
- **D-13:** `MDM_DATABASE_URL` is loaded into environment only (never printed
  or pasted). Same convention as Phase 3 Task 3.
- **D-14:** The triage guide's diagnostic commands are read-only checks only.
  No `put-secret-value`, `get-secret-value --query SecretString`, or mutation
  commands appear in the guide.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 4 requirements and goal
- `.planning/workstreams/go-live/ROADMAP.md` — Phase 4 goal, requirements
  (DASH-01, DASH-02, DASH-03), and success criteria (1-5).
- `.planning/workstreams/go-live/REQUIREMENTS.md` — full DASH-01/02/03
  definitions and traceability table.

### Launch gate matrix and evidence targets (Phase 1)
- `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md`
  — rows 26-27 (Dashboard UAT BLOCKED, NEO4J_* cleanup BLOCKED) and rows
  90-100 ("Likely Layer And Remediation" triage table Phase 4 extends).
- `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/dashboard-security.md`
  — UAT evidence target for Phase 4 (5 pending rows to fill per D-10).

### Upstream closeout plan (what Phase 4 executes in Wave 1)
- `.planning/workstreams/neo4j-snowflake/phases/04-dashboard-hosted-graph-migration/04-03-PLAN.md`
  — the upstream plan Phase 4 executes. Contains task list, acceptance
  criteria, and arch test commands for README rewrite and verification
  checklist. MUST read before writing `04-01-PLAN.md`.

### Dashboard source files under test
- `examples/mdm_graph_dashboard/streamlit_app.py` — the dashboard (727
  lines). Sections: Overview, MDM Overview, "Neo4j Overview" (routes
  Snowflake-hosted graph), Mismatch Diagnostics. Read-only. Route label
  "Neo4j Overview" is preserved per 04-03-PLAN.md D-03.
- `examples/mdm_graph_dashboard/README.md` — rewrite target for Wave 1
  (replace NEO4J_* with Snowflake-hosted graph setup instructions).
- `edgar_warehouse/mdm/dashboard_readonly.py` — MDM read-only helper (734
  lines). Called by streamlit_app.py for MDM metrics.

### Architecture tests gate
- `tests/architecture/test_dashboard_foundation_boundaries.py` — automated
  gate after README rewrite (D-03). Must pass before Wave 1 plan closes.

### Phase 3 pattern to mirror
- `.planning/workstreams/go-live/phases/03-mdm-hosted-graph-e2e-acceptance/03-CONTEXT.md`
  — dev-precedent pattern, evidence annotation conventions, and runbook
  format (D-05, D-09 mirror D-07/D-08 from Phase 3).
- `.planning/workstreams/go-live/phases/03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md`
  — Phase 3 runbook format for the triage guide to follow.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `examples/mdm_graph_dashboard/streamlit_app.py` — all four dashboard sections
  already implemented and tested. Phase 4 does NOT modify this file; it only
  rewrites `README.md`.
- `edgar_warehouse/mdm/dashboard_readonly.py` — read-only MDM helper.
  `get_mdm_dashboard_metrics().as_dict()` already supplies the MDM overview
  data. No changes needed.
- `tests/architecture/test_dashboard_foundation_boundaries.py` — architecture
  guardrails. Phase 4 Wave 1 updates these tests to enforce the post-rewrite
  README contract (no NEO4J_*, Bolt, Aura, `check-connectivity --neo4j`).

### Established Patterns
- **Evidence template pattern** (from Phase 1/2/3): live command output goes
  into Phase 1 evidence files (`evidence/*.md`); Phase 4 fills existing rows
  rather than creating new evidence files (D-10).
- **Dev-precedent annotation** (from Phase 2 and 3): dev UAT runs are
  documented as "dev precedent only — prod proof required separately" —
  Phase 4 UAT follows this same annotation (D-09).
- **Runbook pattern** (from Phase 3): `runbook/<topic>.md` in the phase
  directory. Phase 4's triage guide follows this format (D-05).
- **Secret-safe loading** (from Phase 3 Task 3): `MDM_DATABASE_URL` loaded
  via `aws secretsmanager get-secret-value ... --output text` into env var;
  never printed. Same convention for Phase 4 UAT (D-13).

### Integration Points
- `examples/mdm_graph_dashboard/README.md` — primary file modified in Wave 1.
- `evidence/dashboard-security.md` — primary evidence target in Wave 2 UAT.
- `01-LAUNCH-GATE-MATRIX.md` rows 26-27 — updated with evidence links after
  UAT and README rewrite complete (same pattern as Phase 3 updating rows 22-25).

</code_context>

<specifics>
## Specific Ideas

- The `04-03-PLAN.md` uses these exact acceptance criteria for the README
  rewrite (downstream agents MUST follow them):
  - README tells operators how to launch the dashboard locally with `uv`.
  - README points to `edgar-warehouse mdm verify-graph`,
    `infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql`, and the AWS
    hosted graph E2E command as documentation text only.
  - README states the dashboard has no destructive or write controls.
  - README contains no active external `NEO4J_*`, Bolt, Aura, or read-only
    `MATCH` setup path.
  - Route label "Neo4j Overview" is preserved (per D-03 of 04-03-PLAN.md
    must_haves) while page copy names Snowflake-hosted Neo4j Graph Analytics.
- The triage guide (D-05) should cross-reference the launch gate matrix's
  existing "Likely Layer And Remediation" table (rows 90-100) rather than
  duplicating it — it extends, not replaces.
- Dashboard UAT launch command (D-11):
  `uv run --extra dashboard --extra mdm-runtime streamlit run examples/mdm_graph_dashboard/streamlit_app.py`
- The dashboard section name "Neo4j Overview" is intentionally preserved —
  do not rename it. The section now shows Snowflake-hosted graph data (per
  Plan 04-02 migration already complete).

</specifics>

<deferred>
## Deferred Ideas

- Prod Snowflake dashboard UAT — blocked by prod MDM secrets not yet
  populated. Deferred to Phase 5 go/no-go packet or post-launch follow-up.
- Managed dashboard deployment (Snowflake-in-Streamlit) — explicitly out of
  scope per REQUIREMENTS.md "Out of Scope" and "Future Requirements" list.
- Historical trend views (data quality, graph parity) — future requirement
  post go-live.
- Removal of external Neo4j runtime remnants (neo4j docker, Aura references
  outside the dashboard) — formal deprecation tracked in REQUIREMENTS.md
  "Future Requirements"; not Phase 4 scope.

None — no todos matched Phase 4 scope in cross_reference_todos check.

</deferred>

---

*Phase: 4-operator-dashboard-and-data-issue-triage*
*Context gathered: 2026-06-16*
