# Dashboard Buildout Research

Date: 2026-07-24  
Scope: production warehouse Streamlit, MDM/Snowflake-hosted graph review,
deployment automation, read-only safety, testing, and operator acceptance.

## Executive conclusion

The repository has two useful but incomplete dashboard products:

1. `infra/snowflake/streamlit/streamlit_app.py` is the deployable
   Streamlit-in-Snowflake (SiS) warehouse app. It has Summary, Company Details,
   and Pipeline tabs; a default Agent View; an Explore mode; company lookup;
   financial factors; filing charts; and pipeline diagnostics
   ([source](../../infra/snowflake/streamlit/streamlit_app.py#L1-L20),
   [navigation](../../infra/snowflake/streamlit/streamlit_app.py#L699-L719)).
2. `examples/mdm_graph_dashboard/streamlit_app.py` is a separate, mature,
   read-only operator review UI for MDM and Snowflake-hosted Neo4j Graph
   Analytics. It has overview, MDM, graph, and mismatch pages with bounded
   filters and safe error states, but it is launched locally and requires
   `MDM_DATABASE_URL`; it is not part of the SiS deployment
   ([runbook](../../examples/mdm_graph_dashboard/README.md#L1-L74),
   [navigation](../../examples/mdm_graph_dashboard/streamlit_app.py#L687-L727)).

The next buildout should not begin with six independent dashboard pages. The
first tracer bullet must make dashboard releases secure, reproducible, and
observable. Then ship one complete Company 360 path, followed by Screener and
Insider Watch. The MDM graph review surface should remain a separate
operator-facing app, hosted only after its Postgres-dependent helper contract is
replaced by Snowflake-readable, current-generation status objects.

This was a code-and-document research pass, not a live production UAT. The
credential-free focused suite passed on 2026-07-24:

```text
56 passed in 3.03s
```

Command:

```bash
uv run pytest \
  tests/unit/test_dashboard_modes.py \
  tests/architecture/test_snowflake_streamlit_financial_factors.py \
  tests/mdm/test_dashboard_readonly.py \
  tests/mdm/test_graph_readonly.py \
  tests/architecture/test_dashboard_foundation_boundaries.py -q
```

## Product contract

The locked product direction is coherent:

- The machine-readable Agent Decision Surface is primary; Streamlit is a Human
  Audit View, not the source of truth.
- Agent View must read only Decision Contract objects. Explore can read broader
  gold/source data but must stay visibly labeled as not-for-agent.
- The v1 human views are Company 360, Fundamentals Screener, and Insider Watch.
- The dashboard is accounting-only: no market-price joins.
- Partial data must be explicit, and watermark mismatch must fail closed.

These decisions are recorded in
[`docs/product-questions-and-dashboards.md`](../product-questions-and-dashboards.md#L15-L48).
The proposed roadmap also places Company 360, Screener, and Insider Watch at P0,
with only a thin health strip before a full command center
([roadmap](../product-questions-and-dashboards.md#L348-L373)).

That means dashboard tickets should preserve two distinct contracts:

| Surface | Audience | Permitted truth source |
| --- | --- | --- |
| Agent View | analyst auditing an agent read | versioned Decision Contract only |
| Explore | human research | labeled gold/source read models |
| Graph Review | platform/compliance operator | active-generation MDM/graph status and bounded diagnostics |

## Current warehouse app

### What exists

- The app uses the active Snowpark session and three hard-coded schemas:
  `EDGARTOOLS_GOLD`, `EDGARTOOLS_SOURCE`, and `EDGARTOOLS_DECISION`
  ([source](../../infra/snowflake/streamlit/streamlit_app.py#L12-L20)).
- Mode defaults fail closed to Agent View and exposes a sticky sidebar toggle
  plus explicit banners
  ([source](../../infra/snowflake/streamlit/streamlit_app.py#L22-L92)).
- Explore mode has universe KPIs, filing volume, company lookup, metadata,
  financial factors, filing mix/timeline, and recent filings
  ([company view](../../infra/snowflake/streamlit/streamlit_app.py#L395-L524)).
- The Pipeline tab reads run-manifest/refresh status and Snowflake task, copy,
  and dynamic-table history
  ([pipeline queries](../../infra/snowflake/streamlit/streamlit_app.py#L527-L609)).
- The gold dbt project already exposes the principal data models needed for
  Company 360, Screener, and Insider Watch: company, filings, factors, earnings,
  accounting flags, executives, institutional holdings, and ownership.

### Material gaps

#### P0: Agent View is not actually contract-only

The UI says Agent View is Decision Contract only, but Company Details runs
`_lookup_companies()` and `_company_metadata()` before the Agent View branch.
Those helpers query free gold `COMPANY` and `TICKER_REFERENCE`
([control flow](../../infra/snowflake/streamlit/streamlit_app.py#L395-L445)).
The per-query allowlist is checked only in selected call sites, so the visible
mode label is stronger than the enforced boundary.

The contract logic is also duplicated: the staged SiS file mirrors
`edgar_warehouse.serving.dashboard_modes` because only the app file is staged
([source](../../infra/snowflake/streamlit/streamlit_app.py#L1-L8)). This creates
drift risk between unit-tested policy and deployed policy.

#### P0: Agent View is a partial placeholder

The app renders `SUBJECT_FEATURE_SCREEN`, then states that bundle sections still
need published SQL views
([source](../../infra/snowflake/streamlit/streamlit_app.py#L230-L262)). It does
not yet prove contract version, decision watermark, graph/gold alignment,
coverage flags, current-versus-history semantics, or the complete issuer and
manager bundle.

#### P1: Company 360 is only a partial vertical

The current page covers metadata, factors, and filings. The product contract
also calls for insiders, earnings, executive compensation, accounting flags,
institutional holders, and relationships
([design](../product-questions-and-dashboards.md#L204-L243)). Screener and
Insider Watch are not present in the SiS navigation.

#### P1: Error handling can disclose raw Snowflake exceptions

`_safe_df()` writes the exception text into the UI
([source](../../infra/snowflake/streamlit/streamlit_app.py#L107-L112)).
The graph dashboard deliberately maps connection/permission failures to fixed,
secret-safe copy; the warehouse app should use the same policy.

#### P1: Schema/environment configuration is not deployment-derived

The app hard-codes schema names. `DASHBOARD_DATABASE` affects the upload target,
but the app has no generated environment contract and no startup assertion that
the active database, Decision schema, and expected contract version match the
release.

## Current MDM and graph review app

### What exists

The local graph-review surface is substantially better isolated than the
warehouse UI:

- It explicitly prohibits sync, repair, migrate, load, and write actions.
- Refresh only clears cached read-only payloads.
- MDM is required; Snowflake graph diagnostics are optional so MDM-only review
  remains available.
- Rows are bounded to 25, 50, 100, or 250.
- It exposes entity/relationship parity, pending publication, missing/extra
  nodes and edges, missing endpoints, and Native App failures.
- Its helper and architecture tests guard against raw SQL/Cypher in the UI,
  write tokens, mutation controls, external Bolt/Aura paths, secret leakage,
  unbounded samples, and CLI subprocess parsing
  ([architecture tests](../../tests/architecture/test_dashboard_foundation_boundaries.py#L115-L216),
  [operator-state tests](../../tests/architecture/test_dashboard_foundation_boundaries.py#L335-L472)).

The current code correctly targets Snowflake-hosted graph verification, not a
direct Neo4j Bolt/Aura connection
([runbook](../../examples/mdm_graph_dashboard/README.md#L15-L25)).

### Hosting gap

The UI is under `examples/`, is launched with local `uv run ... streamlit`, and
requires the Snowflake Postgres application DSN through `MDM_DATABASE_URL`
([runbook](../../examples/mdm_graph_dashboard/README.md#L15-L53)). Its Python
helpers import the repository's SQLAlchemy MDM models and the graph verifier.
The current warehouse deploy uploads only `streamlit_app.py` and
`environment.yml`; therefore this graph app cannot be promoted by the existing
SiS path.

Do not solve this by giving a warehouse-runtime SiS app a production Postgres
DSN. Instead, publish a bounded, active-generation, read-only Snowflake review
contract containing:

- current generation and activation time;
- entity counts by type;
- relationship counts by type;
- publication backlog/freshness;
- node/edge parity by type;
- bounded mismatch samples;
- Native App acceptance check status.

The hosted graph-review app can then query that contract with the active
Snowpark session. Deep operational verification remains the CLI/Step Functions
acceptance gate; the dashboard displays evidence and does not trigger work.

The old dashboard workstream is marked released and complete
([registry](../../.planning/REGISTRY.md#L44-L56)), and its focused tests now
pass. However, its roadmap progress table still says Phase 9 is not started
while the same roadmap declares Phase 9 complete
([roadmap](../../.planning/workstreams/mdm-neo4j-dashboard/ROADMAP.md#L16-L20),
[progress](../../.planning/workstreams/mdm-neo4j-dashboard/ROADMAP.md#L71-L77)).
Those planning files are historical evidence, not current production acceptance.

## Deployment and access-control findings

### Current path

Terraform creates the dashboard schema, internal stage, and Streamlit object,
and assigns a reader warehouse
([module](../../infra/terraform/snowflake/modules/dashboard/main.tf#L1-L37)).
Snowflake access Terraform grants the reader role schema usage and Streamlit
usage
([access](../../infra/terraform/access/snowflake/modules/account_access/main.tf#L195-L213)).
`deploy-snowflake-stack.sh --upload-dashboard` invokes the upload after the
optional dbt run, and `deploy.sh` overwrites two files on the stage with `PUT`
([wrapper](../../infra/scripts/deploy-snowflake-stack.sh#L440-L455),
[upload](../../infra/snowflake/streamlit/deploy.sh#L1-L46)).

### Gaps

- Upload is mutable and in-place. There is no source digest, release identifier,
  atomic version promotion, prior-version pointer, or rollback command.
- There is no pre-upload unit/architecture gate, post-upload object inspection,
  query smoke, browser/UAT smoke, or evidence artifact.
- There is no pruning or stale-file inventory.
- Dashboard upload is opt-in, so a warehouse/dbt deployment can finish with an
  old dashboard without making that divergence visible.
- The dashboard Terraform module accepts `reader_role_name` but does not use it.
  The app owner is therefore determined by the Terraform execution role, while
  the viewer role receives only app usage. That distinction matters because
  warehouse-runtime SiS apps run with owner rights.
- Access Terraform grants the reader role gold access, but Agent View also
  requires `EDGARTOOLS_DECISION`, and Pipeline Explore reads source and
  information-schema history. Those dependencies are not modeled as an
  explicit dashboard-owner contract.
- `environment.yml` lists unpinned top-level dependencies, so a rebuild can
  change runtime behavior without a repository change.

Snowflake's official documentation confirms the relevant security and release
constraints:

- SiS apps use owner rights by default; viewers can see anything the owner role
  allows the app to display. Snowflake recommends dedicated creation/viewer
  roles ([owner-rights documentation](https://docs.snowflake.com/en/developer-guide/streamlit/object-management/owners-rights)).
- Restricted caller rights are not supported by warehouse runtimes; adopting
  them would require a container-runtime architecture decision, not a small
  hardening patch
  ([restricted caller-rights documentation](https://docs.snowflake.com/en/developer-guide/streamlit/features/restricted-callers-rights)).
- Snowflake CLI's supported deploy flow can upload a project, create/update the
  object, and prune stale staged files
  ([deployment documentation](https://docs.snowflake.com/en/developer-guide/snowflake-cli/streamlit-apps/manage-apps/deploy-app)).

The lowest-risk v1 choice is therefore a dedicated, least-privilege
dashboard-owner role plus separate viewer role, with SQL limited to explicit
read models. Container runtime should not be introduced solely for caller
rights.

## Test and acceptance assessment

### Strong existing checks

- Pure mode normalization and allowlist behavior are unit tested.
- The warehouse factors query is tested for a bound CIK parameter, but only that
  one query path
  ([test](../../tests/architecture/test_snowflake_streamlit_financial_factors.py#L157-L182)).
- Graph helpers have extensive fixture coverage for parity, failures, bounded
  diagnostics, secret-safe errors, and no writes/stdout parsing.
- Graph UI architecture tests enforce read-only boundaries and stable operator
  copy.

### Missing release checks

- No test enumerates every warehouse-app query and proves the object is allowed
  in the selected mode.
- No test catches the pre-branch free-gold lookups in Agent View.
- No contract tests cover Company 360 joins, null/partial coverage semantics,
  watermark mismatch, or deep links.
- No end-to-end test opens the staged SiS app using the production viewer role.
- No smoke proves the deployed source digest matches the intended git commit.
- No performance budget exists for ticker search, Company 360, screen filtering,
  or a bounded graph diagnostic.
- No browser/operator acceptance record exists for empty, partial, stale,
  permission-denied, and healthy states.

Dashboard acceptance must be separate from pipeline release acceptance. A green
dashboard smoke proves the read surface can render the already-accepted release;
it must not be used as evidence that the warehouse/MDM full chain or integrity
gate passed.

## Recommended tracer-bullet tickets

The following slices are intended as GitHub issues. Each is independently
demoable and leaves a production-useful increment.

### DASH-1 — Enforce the Agent View data boundary end to end

**Outcome:** every Agent View query is generated through one tested query
registry and can access only versioned Decision Contract/status objects.

**Acceptance:**

- Remove the mirrored allowlist or generate the deployed policy from the same
  source as `dashboard_modes.py`.
- Company search/identity in Agent View comes from a Decision Contract subject
  index, not free gold.
- A test records every query issued by every Agent View route and fails on any
  non-allowlisted object.
- The page displays contract version, decision watermark, coverage flags, and
  fail-closed graph/gold alignment.
- Explore remains explicitly labeled and the same CIK can be compared across
  modes.

**Depends on:** none.  
**Blocks:** DASH-3, DASH-4, DASH-5.

### DASH-2 — Make SiS deployment immutable, least-privilege, and verifiable

**Outcome:** one command promotes an identified dashboard artifact and produces
deployment evidence.

**Acceptance:**

- Define a dedicated dashboard-owner role with only required database/schema
  usage, selected read-model `SELECT`, reader-warehouse usage, and app ownership;
  keep viewer `USAGE` separate.
- Model Gold, Decision, and permitted operational status dependencies
  explicitly in access Terraform.
- Package the app as a Snowflake CLI project, prune stale files, record commit
  SHA/source digest/environment/dependency lock, and retain a rollback target.
- Run credential-free tests before upload.
- After deploy, inspect the Streamlit object and staged digest, then run bounded
  healthy/permission smoke queries as the intended owner/viewer roles.
- Write a secret-free JSON/Markdown evidence artifact and document rollback.

**Depends on:** none.  
**Blocks:** production promotion of all later dashboard slices.

### DASH-3 — Ship one complete Company 360 vertical slice

**Outcome:** ticker/name to a single audit page covering the existing P0
accounting and disclosure data.

**Acceptance:**

- Header/identity, filings, financials, insiders, earnings, executive pay,
  accounting flags, and institutional holders render from explicit read models.
- Agent View renders only bundle fields; Explore renders broader gold detail.
- Missing tables/rows and insufficient history are distinguished from zero.
- Filing/accession links and navigation state are tested.
- Query limits and a p95 target are defined and measured on production-shaped
  data.
- A thin freshness/decision-watermark strip is always visible.

**Depends on:** DASH-1.  
**Production promotion depends on:** DASH-2.

### DASH-4 — Ship the accounting-only Fundamentals Screener

**Outcome:** analysts can filter/rank tracked companies and open Company 360.

**Acceptance:**

- Screen only tracked/active subjects.
- Support bounded filters for SIC, fiscal period, revenue, CAGR, liquidity,
  leverage, cash, FCF, accruals, and available risk flags.
- Null/insufficient-history values never sort or display as zero.
- Every result records the feature as-of date and decision watermark.
- Selection deep-links to Company 360 without losing mode.
- Result count, maximum rows, export policy, and query performance are tested.

**Depends on:** DASH-1 and DASH-3.  
**Production promotion depends on:** DASH-2.

### DASH-5 — Ship Insider Watch with Company 360 drill-through

**Outcome:** analysts can review bounded cross-issuer Form 3/4/5 activity.

**Acceptance:**

- Date, issuer, owner role, form, transaction code, and minimum notional/share
  filters are bounded and parameterized.
- Buy/sell semantics and unavailable price/notional fields are explicit.
- Results include accession evidence and drill through to Company 360.
- Earnings-window comparison is included only when the join is authoritative;
  otherwise it is visibly unavailable.
- Duplicate/amended filing behavior has fixtures and acceptance cases.

**Depends on:** DASH-1 and DASH-3.  
**Production promotion depends on:** DASH-2.

### DASH-6 — Publish a Snowflake graph-review read contract

**Outcome:** the local graph dashboard's useful state is available to a hosted
read-only app without a Postgres DSN or direct Bolt connection.

**Acceptance:**

- Publish active generation, activation time, MDM entity/relationship counts,
  publication freshness, parity by type, bounded mismatch samples, and Native
  App check status to read-only Snowflake objects.
- Every object is generation-scoped; stale/mixed generations fail closed.
- Sensitive raw relationship properties and credentials are excluded.
- Counts reconcile to `mdm verify-graph` for the same generation.
- Refresh occurs in the MDM publication/verification workflow, never from the
  dashboard.

**Depends on:** trusted MDM generation activation.  
**Blocks:** DASH-7.

### DASH-7 — Deploy the separate hosted MDM/graph operator dashboard

**Outcome:** operators can open a managed read-only graph review app with no
local environment setup.

**Acceptance:**

- Preserve the existing Overview, MDM Overview, Neo4j Overview, and Mismatch
  Diagnostics information architecture.
- Query only DASH-6 Snowflake read objects through the active Snowpark session.
- Preserve bounded filters, safe fixed error copy, no mutation controls, and no
  external Neo4j credentials.
- Display generation identity and distinguish unavailable, stale, mismatch, and
  healthy states.
- Deep verification links to the runbook/CLI evidence; the UI cannot trigger
  sync, repair, migration, activation, or load.
- Deploy through DASH-2's artifact/evidence path as a distinct Streamlit object
  and viewer grant.

**Depends on:** DASH-2 and DASH-6.

### DASH-8 — Ship the Adviser & Fund Explorer

**Outcome:** analysts can search an adviser or private fund and inspect the
current ADV facts and managed-fund relationships without treating Explore data
as Agent Decision Contract evidence.

**Acceptance:**

- Provide bounded adviser/fund search by name, CRD/file number, and private-fund
  identifier.
- Show adviser identity, office and disclosure coverage, private funds, reported
  AUM where available, and active `MANAGES_FUND` relationships.
- Label the surface Explore-only until an ADV Decision Contract is explicitly
  adopted; it must not appear as Agent View evidence.
- Display filing/source dates, active graph generation, and explicit
  unavailable/partial/stale states; null AUM is never rendered as zero.
- Deep links preserve the selected adviser/fund and expose SEC filing evidence
  without adding mutation controls.
- Use bounded, parameterized read models with credential-free fixtures and a
  production-shaped query performance check.

**Depends on:** trusted ADV gold data and MDM generation activation.  
**Production promotion depends on:** DASH-2.

### DASH-9 — Add operator UAT and release acceptance gates

**Outcome:** a dashboard release has reproducible human and automated evidence,
without being confused with a data release PASS.

**Acceptance:**

- Automated smoke covers app availability, owner/viewer grants, source digest,
  a known Company 360 subject, a bounded screener, Insider Watch, freshness, and
  graph generation/parity.
- Browser UAT covers healthy, empty, partial, stale, permission-denied, and
  mismatch states with no secret leakage.
- Capture query IDs, timings, role, app version, git commit, data watermark, and
  graph generation in a secret-free artifact.
- Define rollback and verify the prior artifact can be restored.
- Explicitly state that dashboard acceptance does not replace full-chain data
  and integrity acceptance.

**Depends on:** DASH-2; expand cases as DASH-3 through DASH-8 land.

## Dependency order

```text
DASH-1 contract enforcement ──> DASH-3 Company 360 ──> DASH-4 Screener
                                      └───────────────> DASH-5 Insider Watch

DASH-2 secure deploy ─────────> production promotion of DASH-3/4/5
          └───────────────────> DASH-7 hosted graph review

trusted MDM generation ───────> DASH-6 graph read contract ──> DASH-7

trusted ADV + MDM generation ─> DASH-8 Adviser & Fund Explorer

DASH-2 ───────────────────────> DASH-9 release acceptance
                                  (extended by DASH-3/4/5/7/8)
```

## Suggested milestone cut

**Milestone A — trustworthy dashboard delivery:** DASH-1, DASH-2, and the first
healthy/denied cases in DASH-9.

**Milestone B — analyst P0:** DASH-3, DASH-4, DASH-5, plus their DASH-9 cases.

**Milestone C — hosted graph operations:** DASH-6, DASH-7, plus generation and
mismatch acceptance in DASH-9.

**Milestone D — ADV exploration:** DASH-8 plus its DASH-9 acceptance cases.

This order delivers visible product value early while keeping the dashboard a
read-only projection of accepted warehouse and graph state.
