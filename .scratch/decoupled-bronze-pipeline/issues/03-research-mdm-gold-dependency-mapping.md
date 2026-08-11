# Map which gold tables/columns actually depend on MDM output vs. pure silver

Type: research
Status: resolved
Blocked by: (none)

## Question

**Framing correction (2026-08-11, from resolving [Decide the fate of the
dual gold path](05-decide-dual-gold-path-fate.md)):** the "gold
tables/dynamic tables" list and the "Snowflake export set" below are not
two independent things — they're the same underlying data at two layers.
Every table is computed exactly once, by `edgar_warehouse/serving/
gold_models.py`'s `iter_gold_tables()`, exported via `GOLD_EXPORT_MAP` into
the `EDGARTOOLS_SOURCE` schema, then mirrored 1:1 (mostly literal
pass-through, 3 exceptions with real SQL) by dbt into `EDGARTOOLS_GOLD`.
Don't investigate this pairing as if it might reveal a second, independent
computation — it won't. Focus purely on the MDM-dependency question below.

Today `gold-refresh` runs only after the full MDM chain (`mdm run ->
backfill-relationships -> export -> sync-graph -> verify-graph`) completes,
inside the same synchronous Step Functions execution. This map needs to
decide MDM's role in a decoupled architecture (see the grilling ticket this
research unblocks) — but that decision needs a real answer to a narrower,
purely factual question first: **which parts of gold actually need MDM's
output, and which are computable from silver alone?**

Establish, from the actual code (`edgar_warehouse/gold.py`,
`edgar_warehouse/serving/gold_models.py`, and the dbt models in
`infra/snowflake/dbt/edgartools_gold/models/gold/`):

1. For each of the gold tables/dynamic tables listed in
   `docs/data-architecture.md`'s Data Point Catalog (`company`,
   `ownership_holdings`, `ownership_activity`, `filing_detail`,
   `filing_activity`, `adviser_disclosures`, `adviser_offices`,
   `private_funds`, `ticker_reference`, plus the Snowflake export set
   `COMPANY`, `FILING_ACTIVITY`, `OWNERSHIP_ACTIVITY`,
   `OWNERSHIP_HOLDINGS`, `ADVISER_OFFICES`, `ADVISER_DISCLOSURES`,
   `PRIVATE_FUNDS`, `FILING_DETAIL`, `TICKER_REFERENCE`,
   `SEC_FINANCIAL_FACT`, `SEC_FINANCIAL_DERIVED`, `SEC_THIRTEENF_HOLDING`,
   `EARNINGS_RELEASE`, `EXECUTIVE_RECORD`, `ACCOUNTING_FLAG`) — does its
   builder query MDM tables/the MDM Snowflake mirror at all, or only silver
   (`sec_*`) tables?
2. For the tables that DO touch MDM: which specific MDM relationship types
   feed them (e.g. `IS_INSIDER`, `INSTITUTIONAL_HOLDS`, `HOLDS`,
   `COMPANY_HOLDS`, `MANAGES_FUND`) — cite the actual query/join.
3. Is there a clean split — e.g. "most gold tables are pure-silver,
   ownership/holdings-shaped tables need MDM" — or is MDM dependency
   scattered unpredictably across otherwise-unrelated tables?
4. Does the *graph* (Snowflake Neo4j Graph Analytics Native App,
   `NEO4J_GRAPH_MIGRATION` schema) have any of its own downstream
   consumers beyond the review dashboard — i.e. is graph sync itself a
   third decoupling boundary this map needs to account for, or purely an
   MDM-internal concern?

## Answer

Method: read `edgar_warehouse/serving/gold_models.py` (1435 lines) end to
end, including every `_build_*` function body and the `_gold_table_builders`
registry / `iter_gold_tables()` / `build_gold()` (`:1240-1308`); grepped the
whole file case-insensitively for `mdm` (zero hits); read all 23 dbt gold
model `.sql` files in `infra/snowflake/dbt/edgartools_gold/models/gold/`
plus `models/sources.yml`; read `edgar_warehouse/mdm/export.py` (562 lines)
in full to trace exactly which MDM writes land in which Snowflake schema;
read the relevant slices of `edgar_warehouse/mdm/database.py`,
`edgar_warehouse/mdm/resolvers/company.py`, `edgar_warehouse/mdm/pipeline.py`,
and `edgar_warehouse/mdm/cli.py` to trace where `parent_company_entity_id`
and the `HAS_PARENT_COMPANY` relationship type actually come from and which
CLI subcommand performs which write; and grepped the whole repo (excluding
`.scratch/`, dbt `target/`, and tests) for `NEO4J_GRAPH_MIGRATION`,
`MDM_GRAPH_NODES`/`MDM_GRAPH_EDGES`, and `MDM_GRAPH_REVIEW` to find every
graph-reading code path, then read each hit's surrounding context
(`edgar_warehouse/serving/dashboard_workflows.py`,
`infra/snowflake/streamlit/streamlit_app.py`,
`infra/snowflake/sql/dashboard/01_explore_reader_grants.sql`,
`infra/snowflake/sql/decision_contract/03_dashboard_contract.sql`,
`infra/snowflake/mdm_dashboard/streamlit_app.py`).

### 0. Enumerating the real registry (not the ticket's ~26 estimate)

`_gold_table_builders(conn)` (`gold_models.py:1240-1280`) returns **28**
`(name, builder)` pairs, not ~26:

`dim_company`, `dim_form`, `dim_date`, `dim_filing`, `fact_filing_activity`,
`dim_party`, `dim_security`, `dim_ownership_txn_type`, `dim_geography`,
`dim_disclosure_category`, `dim_private_fund`, `fact_ownership_transaction`,
`fact_ownership_holding_snapshot`, `fact_adv_office`, `fact_adv_disclosure`,
`fact_adv_private_fund`, `sec_financial_fact`, `sec_thirteenf_holding`,
`sec_financial_derived`, `fact_earnings_release`, `fact_guidance`,
`fact_executive_record`, `fact_accounting_flag`, `sec_subsidiary_evidence`,
`sec_auditor_report_evidence`, `sec_employment_event`,
`sec_adv_firm_roster`, `sec_adv_private_fund`.

`iter_gold_tables()` (`:1283-1297`) just wraps this list, one `_timed()`
call per builder; `build_gold()` (`:1300-1308`) is `dict(iter_gold_tables(db))`
— confirming the framing correction: there is exactly one builder registry,
walked once, regardless of which of the two callers is used. Four more
builder functions exist in this module (`build_ticker_reference_table`,
`build_earnings_calendar_table_from_rows`, `build_consensus_estimates_table_from_rows`,
`build_transcript_events_table_from_rows`, `:1366-1435`) but are **not** in
`_gold_table_builders` — they take pre-fetched `rows`/`universe_rows` lists
as parameters instead of a DB connection, are called separately from
`warehouse_orchestrator.py:822-826` and the `serving_publish.py` workflow
module, and back the `ticker_reference.sql` / `earnings_calendar.sql` /
`consensus_estimates.sql` / `transcript_events.sql` dbt models (all four
confirmed pure-`edgartools_source`, no MDM, in section 2 below). Mentioned
for completeness; out of the ticket's named scope (the `_gold_table_builders`
registry), and doesn't change any count below.

### 1. Do any of the 28 Python gold builders query MDM?

**No. Zero of 28.** `grep -in "mdm" edgar_warehouse/serving/gold_models.py`
returns no output at all — not one builder function, not one comment,
references MDM in any form. Every `_build_*` function's `conn.execute(...)`
call (the `SilverDatabase`/`ShardedSilverReader` DuckDB connection passed
into `_gold_table_builders`, `gold_models.py:1295`) selects exclusively from
`sec_*` silver tables: `sec_company`, `sec_company_filing`,
`sec_company_address`, `sec_ownership_reporting_owner`,
`sec_ownership_non_derivative_txn`, `sec_ownership_derivative_txn`,
`sec_adv_filing`, `sec_adv_office`, `sec_adv_disclosure_event`,
`sec_adv_private_fund`, `sec_adv_firm_roster`, `sec_financial_fact`,
`sec_financial_derived`, `sec_thirteenf_holding`, `sec_earnings_release`,
`sec_guidance_fact`, `sec_executive_record`, `sec_accounting_flag`,
`sec_subsidiary_evidence`, `sec_auditor_report_evidence`,
`sec_employment_event` — read directly, verified against each `_build_*`
function's `FROM`/`JOIN` clauses (`gold_models.py:213-1223`). There is no
DuckDB `ATTACH` of an MDM database, no SQLAlchemy/Postgres import, and no
reference to any Snowflake MDM mirror table anywhere in this file. **The
entire Python gold layer is computable from silver alone**, with no
exception.

### 2. dbt layer: does any model besides `company.sql` reference `mdm_export`?

**Yes — one more, `mdm_company.sql` — but it is a pure compatibility
passthrough, not a distinct consumer with its own business logic.** Grepped
`source(` across all 23 `.sql` files under
`infra/snowflake/dbt/edgartools_gold/models/gold/`:

- **`company.sql`** (`:1,11-22,39-43`) left-joins
  `{{ source("mdm_export", "MDM_COMPANY_ENTITY") }}` onto
  `{{ source("edgartools_source", "COMPANY") }}` by `cik`, adding
  `entity_id`, `display_name` (coalesced with `entity_name`),
  `tracking_status`, `parent_company_entity_id`, and a
  `has_multi_match_mdm_entity` flag.
- **`mdm_company.sql`** (`:1,14-30`) selects straight from the same
  `{{ source("mdm_export", "MDM_COMPANY_ENTITY") }}`, materialized as a view
  aliased `MDM_COMPANY`. Its own header comment states this is a
  "byte-for-byte compatibility projection" kept only so any pre-existing
  external reader of the old `EDGARTOOLS_GOLD.MDM_COMPANY` name (before
  ticket 06 of the `unified-company-dimension` map renamed the physical
  table to `MDM_COMPANY_ENTITY`) keeps working, and states explicitly: "No
  in-repo reader was found (dashboards, dbt models) as of 2026-07-29" —
  confirmed still true here: `grep -rn "ref(\"mdm_company\"" models/` finds
  zero hits, i.e. no other dbt model `ref()`s it.
- **All other 21 `.sql` models** (`accounting_flags`,
  `adv_fund_count_reconciliation`, `adviser_disclosures`,
  `adviser_offices`, `consensus_estimates`, `earnings_calendar`,
  `earnings_releases`, `edgartools_gold_status`, `executive_records`,
  `filing_activity`, `filing_detail`, `financial_derived`,
  `financial_factors`, `financial_facts`, `guidance_facts`,
  `institutional_holdings`, `ownership_activity`, `ownership_holdings`,
  `private_funds`, `ticker_reference`, `transcript_events`) reference only
  `source("edgartools_source", ...)` or, in `financial_factors.sql`'s one
  case, `ref("financial_derived")` (itself pure `edgartools_source`) — never
  `mdm_export`. Notably **`institutional_holdings.sql`** (`:11`) — the model
  whose name most suggests an `INSTITUTIONAL_HOLDS`-relationship join —
  reads only `source("edgartools_source", "SEC_THIRTEENF_HOLDING")`; the
  `INSTITUTIONAL_HOLDS` MDM relationship type never reaches gold at all (see
  §3). `executive_records.sql:61-67` has a comment *mentioning* MDM
  ("Person identity is resolved by MDM... tenure is computed by MDM's
  `_derive_employed_by`...") to explain columns it deliberately does **not**
  carry — this is documentation of an omission, not a query; the model has
  no `source("mdm_export", ...)` reference.

`sources.yml:100-113`'s `mdm_export` source block declares exactly one
table, `MDM_COMPANY_ENTITY`, with a comment stating it is "MERGEd by
`MDMExporter.export_pending()`... directly into `EDGARTOOLS_GOLD`" — i.e.
the dbt project only knows about, and only every references, this one MDM
write target.

### 3. Which MDM relationship types feed the touched tables?

**None, directly — and this is a materially important, non-obvious finding.**
`company.sql`/`mdm_company.sql` join against `MDM_COMPANY_ENTITY`, which is
MDM's **entity-resolution golden record** (`MdmCompany` SQLAlchemy model,
`edgar_warehouse/mdm/database.py:224-254`: `entity_id`, `cik`,
`canonical_name`, `tracking_status`, `parent_company_entity_id`, etc.) — not
`MdmRelationshipInstance` or any relationship-type table. Traced the actual
write path in `edgar_warehouse/mdm/export.py`:

- `MDMExporter.export_pending()`/`export_all_pending()`
  (`:292-356`) reads `db.MdmChangeLog`, looks up each changed entity's
  `MdmCompany`/`MdmAdviser`/`MdmPerson`/`MdmSecurity`/`MdmFund` row via
  `DOMAIN_TO_TABLE` (`:23-29`), and upserts via `self.writer.upsert(sf_table, ...)`
  into `EDGARTOOLS_GOLD` — this is the **only** path that ever lands
  anything gold-visible. It is purely entity-resolution output; nothing in
  this method touches `MdmRelationshipInstance`. `self.writer` is
  `SnowflakeConnectorWriter.from_env()` (`cli.py:1872-1875`,
  `_build_snowflake_writer`), whose own comment at `cli.py:1880` states its
  target is "`EDGARTOOLS_GOLD`'s golden-record target," distinct from the
  mirror writer below — confirmed, not just named-consistent. **`DOMAIN_TO_TABLE`
  writes 5 tables into `EDGARTOOLS_GOLD`** (`MDM_COMPANY_ENTITY`,
  `MDM_ADVISER`, `MDM_PERSON`, `MDM_SECURITY`, `MDM_FUND`), but
  `sources.yml`'s `mdm_export` source block only declares
  `MDM_COMPANY_ENTITY` (§2) — so **4 of the 5 MDM golden-record tables that
  land in the gold schema are read by zero dbt models today**: real,
  unconsumed data sitting in `EDGARTOOLS_GOLD`, not something this map needs
  to design a consumer for, but worth flagging as dead weight in the current
  export path.
- `MDMExporter.export_pending_relationships()`/`export_all_pending_relationships()`
  (`:379-431`) is a **separate** method that upserts `MdmRelationshipInstance`
  rows via `self.mirror_writer.upsert("MDM_RELATIONSHIP_INSTANCE", ...)` —
  but `mirror_writer` targets the **`MDM` schema mirror** (sync-graph's
  source, per the module's own docstring at `:278-285`: "keeps the
  EDGARTOOLS_\*.MDM graph-source mirror fresh... the tables sync-graph's
  `render_graph_tables()` actually reads"), **not** `EDGARTOOLS_GOLD`. No
  dbt source declares any table from this schema; no dbt model reads it.
- Confirmed both run inside the same `mdm export` CLI invocation
  (`edgar_warehouse/mdm/cli.py:1847-1861`, `_handle_export`): it calls
  `exporter.export_all_pending(...)` then
  `exporter.export_all_pending_relationships(...)` back to back — but they
  write to two different Snowflake schemas for two different downstream
  purposes (gold vs. graph mirror), confirmed distinct destinations, not
  just distinct method names for the same table.

**The one field that looks relationship-shaped —
`parent_company_entity_id` — is not sourced from a relationship join
either.** Traced `edgar_warehouse/mdm/resolvers/company.py:80-93`: it's
computed by `_parent_company_entity_id()` (`:177-193`) directly from SEC
source columns (`parent_company_cik`/`parent_cik`/`ultimate_parent_cik`) at
**entity-resolution time** (i.e. during `mdm run`, before any relationship
derivation step runs) and staged straight onto the `MdmCompany` row. The
`HAS_PARENT_COMPANY` relationship type is derived the other direction —
`edgar_warehouse/mdm/pipeline.py:1167-1183` reads *already-resolved*
`MdmCompany.parent_company_entity_id` values and creates matching
`HAS_PARENT_COMPANY` relationship-instance edges from them (`source_system="derived"`,
`:1179`) — so the relationship type is downstream of the column, not the
column's source.

**Net finding for Q3: gold's one MDM-touching table depends on MDM's
entity-resolution stage (`mdm run` + `mdm export`'s `export_pending`
golden-record write), not on any relationship type at all.**
`IS_INSIDER`, `INSTITUTIONAL_HOLDS`, `HOLDS`, `COMPANY_HOLDS`,
`MANAGES_FUND`, `EMPLOYED_BY`, `HAS_PARENT_COMPANY` — none of these
relationship types are joined into, or feed any column of, any Python gold
table or any dbt gold model. They exist only in MDM's Postgres
(`mdm_relationship_instance`) and the Snowflake `MDM`/`NEO4J_GRAPH_MIGRATION`
schema mirrors, consumed by `sync-graph`/`verify-graph` and the graph
dashboards (see §5) — never by `EDGARTOOLS_GOLD`.

**Caveat on today's pipeline wiring vs. actual minimal dependency:** the
current `load_history` Stage 2 sequence runs `mdm run -> backfill-relationships
-> export -> sync-graph -> verify-graph` in that fixed order (per CLAUDE.md's
Phased Pipeline section), so in practice `mdm export`'s golden-record write
happens *after* `backfill-relationships` today. But nothing found in
`export_pending`'s code path reads relationship data — the ordering is a
property of today's synchronous chain, not a data dependency. This is
relevant to ticket 06's decoupling question but is inference from the code
shape, not something directly proven by an isolated test run; flagged here
rather than overstated as independently verified.

### 4. Is there a clean split, or scattered dependency?

**A very clean split — cleaner than the ticket's own hypothesis ("ownership/
holdings-shaped tables need MDM") predicted, and the actual boundary is
narrower than that guess.** Counts:

- **Python gold layer: 0 of 28 tables touch MDM.** Not just ownership
  tables — `dim_party`, `fact_ownership_transaction`,
  `fact_ownership_holding_snapshot` (the ownership-shaped tables the
  ticket's own hypothesis flagged as likely candidates) are pure silver,
  confirmed in §1.
- **dbt layer: 2 of 23 models touch MDM** (`company.sql`,
  `mdm_company.sql`), and both are the *same* underlying join against the
  *same single* source table (`MDM_COMPANY_ENTITY`) — `mdm_company.sql` is a
  compatibility view with no independent consumer (§2), so there is
  effectively **one** real MDM-dependent gold surface:
  `EDGARTOOLS_GOLD.COMPANY`'s five MDM-sourced columns (`entity_id`,
  `display_name`, `tracking_status`, `parent_company_entity_id`,
  `has_multi_match_mdm_entity`) enriching an otherwise pure-silver base
  table. Confirmed the full base-row chain, not just assumed it:
  `company.sql:39`'s `source("edgartools_source", "COMPANY")` is populated
  by Snowflake native-pull from the S3 export path Python writes via
  `GOLD_EXPORT_MAP["company"] = "dim_company"`
  (`edgar_warehouse/serving/targets/snowflake.py:81`) and
  `SNOWFLAKE_EXPORT_TABLES["COMPANY"] = "company"`
  (`edgar_warehouse/infrastructure/run_manifest_builder.py:12`) — i.e. the
  Snowflake `COMPANY` table's non-MDM columns are exactly the pure-silver
  `_build_dim_company()` output (§1, `gold_models.py:213-232`), not an
  independent or partially-MDM-derived dataset.
- **Two real counts, not a manufactured third one:** 0 of 28 Python
  builders touch MDM; 2 of 23 dbt models touch MDM, collapsing to one real
  MDM-dependent gold surface (`EDGARTOOLS_GOLD.COMPANY`, since
  `mdm_company.sql`'s `MDM_COMPANY` alias has no independent consumer, §2).
  Every other table in both registries — all 28 Python-built tables and all
  21 non-`company`/`mdm_company` dbt models — is fully computable from
  silver alone. `company.sql`'s `LEFT JOIN` means the one touched table
  still exists and its non-MDM columns still populate with MDM absent —
  only the 5 MDM-sourced columns come back `NULL` (`m.*` in
  `company.sql:34-38`).
- The dependency is not scattered: it is concentrated in exactly one table,
  attaches at exactly one join key (`cik`), and draws from exactly one MDM
  writer method (`export_pending`'s entity-resolution golden record) — not
  from relationship derivation, not from graph sync, not from any other
  MDM subsystem.

### 4b. Is the "LEFT JOIN tolerates MDM being absent" claim safe, or does anything filter on the MDM columns downstream?

**Mostly safe, with one confirmed, real exception that qualifies the
verdict below.** Grepped `tracking_status`, `entity_id`, `display_name`,
`has_multi_match_mdm_entity`, and `parent_company_entity_id` across the dbt
gold models, `dashboard_workflows.py`, the decision-contract SQL, and
`streamlit_app.py`, outside `company.sql`/`mdm_company.sql` themselves:

- `display_name` (used as `c.display_name as entity_name` in
  `dashboard_workflows.py:170,249,265`) and the `entity_id` occurrences at
  `dashboard_workflows.py:295-320` (a *different* query, the adviser/fund
  screen surface, aliasing MDM adviser/fund entity IDs — not
  `COMPANY.entity_id`) are plain column reads/aliases, not filters — no risk.
- **Two real filters on `tracking_status` exist, with opposite fallback
  behavior:**
  - `dashboard_workflows.py:181`: `where coalesce(c.tracking_status, 'active') = 'active'`
    — `NULL` (MDM absent/stale) coalesces **to** `'active'`, so rows with no
    MDM match still pass. This confirms the "tolerant" framing for the
    Explore dashboard's fundamentals-screen surface.
  - `infra/snowflake/sql/decision_contract/01_subject_feature_screen.sql:21`:
    `WHERE LOWER(COALESCE(tracking_status, '')) = 'active'` — `NULL`
    coalesces **to `''`**, which does not equal `'active'`, so a company
    with no MDM match (or MDM temporarily behind gold) is **excluded** from
    the Decision Subject Universe entirely. This file's own header comment
    confirms the behavior is deliberate, not an oversight: "COMPANY is
    enriched by the MDM company export. Decision Subject Universe
    membership is therefore the explicit `tracking_status='active'` subset,
    not every warehouse company" (`:7-9`).

**Qualification this adds to the ticket-06 verdict:** "MDM as optional
enrichment" holds cleanly for `EDGARTOOLS_GOLD.COMPANY` itself and for the
main Explore dashboard's screen surface — both degrade gracefully (`NULL`
columns / default-active) if MDM lags. It does **not** hold for the
Decision Contract's `SUBJECT_FEATURE_SCREEN` / Agent View universe — that
surface has a hard, filtering dependency on MDM's `tracking_status` having
already been resolved and exported, and a decoupled design that lets gold
run meaningfully ahead of MDM would need to either accept a temporarily
smaller Decision Subject Universe (companies silently missing from Agent
View until MDM catches up) or treat this one view's freshness as its own
explicit gate, separate from gold's.

### 5. Does the graph have downstream consumers beyond the review dashboard?

**Yes — confirmed, and this changes the framing in the ticket's own
question 4/5.** Graph sync is not purely MDM-internal; it has real,
production-facing gold-adjacent consumers distinct from the operator review
dashboard. Grepped the whole repo (excluding `.scratch/`, dbt `target/`,
tests) for `NEO4J_GRAPH_MIGRATION`, `MDM_GRAPH_NODES`/`MDM_GRAPH_EDGES`, and
`MDM_GRAPH_REVIEW`:

**(a) The operator review dashboard** (as the ticket already assumed):
`infra/snowflake/mdm_dashboard/streamlit_app.py` (the deployed
Streamlit-in-Snowflake app referenced by CLAUDE.md as the "Operator
MDM/graph review dashboard") reads exclusively from the curated
`MDM_GRAPH_REVIEW` schema's parity/mismatch **views**
(`V_GRAPH_REVIEW_ACTIVE_GENERATION`, `V_GRAPH_REVIEW_ENTITY_PARITY`,
`V_GRAPH_REVIEW_RELATIONSHIP_PARITY`, `V_GRAPH_REVIEW_MISMATCH_SAMPLE`,
`V_GRAPH_REVIEW_NATIVE_APP_CHECK`, `:38,79,89,92,95,98`) — never the raw
`NEO4J_GRAPH_MIGRATION.MDM_GRAPH_NODES`/`MDM_GRAPH_EDGES` tables directly.
The ticket's own path, `examples/mdm_graph_dashboard/streamlit_app.py`, is a
**separate app**, not confirmed to read the same views — it contains no
`NEO4J_GRAPH_MIGRATION`/`MDM_GRAPH_REVIEW` string anywhere (grep came back
empty), only an "MDM database permission denied" error string, suggesting
it queries MDM's own Postgres/API directly rather than the Snowflake mirror
schema. Not investigated further since it doesn't change this section's
verdict (which rests on (b)/(c)/(d) below, all independently confirmed).

**(b) A second, genuinely distinct consumer: the main production
dashboard's "Relationships" tab.** `edgar_warehouse/serving/dashboard_workflows.py`'s
`company_query()` function has a `"relationships"` surface
(`:118-138`) whose SQL joins directly against
`NEO4J_GRAPH_MIGRATION.MDM_GRAPH_EDGES` and `NEO4J_GRAPH_MIGRATION.MDM_GRAPH_NODES`,
gated through `NEO4J_GRAPH_MIGRATION.GRAPH_ACTIVE_POINTER` (`:122-136`, the
generation-scoped active-pointer pattern from GH-251). This is called from
`infra/snowflake/streamlit/streamlit_app.py` — the primary, CLAUDE.md-documented
"Streamlit-in-Snowflake dashboard" — which imports `company_query`
(`:41-48`, `:78-85`) and wires it to a `("Relationships", "relationships")`
tab (`:463`, invoked at `:468`). This is a live, per-company drill-through
feature in the main dashboard, not a debugging tool, and it queries the raw
graph tables directly rather than through a curated review layer.

**(c) The same main dashboard's freshness strip** also reads
`NEO4J_GRAPH_MIGRATION.GRAPH_ACTIVE_POINTER` directly
(`streamlit_app.py:1045-1064`, specifically `:1053`) to surface
`graph_generation_id` alongside gold's own `updated_at`/`business_date` —
i.e. graph freshness is treated as a first-class fact the dashboard exposes
next to gold freshness, not something hidden behind MDM.

**(d) The Decision Contract (Agent View) path.**
`infra/snowflake/sql/decision_contract/03_dashboard_contract.sql` — the
schema backing `streamlit_app.py`'s `MODE_AGENT_VIEW` (`:1026-1043`) —
joins `NEO4J_GRAPH_MIGRATION.GRAPH_ACTIVE_POINTER` in
`DECISION_CONTRACT_STATUS` (`:28-48`, join at `:40-42`) and joins
`NEO4J_GRAPH_MIGRATION.MDM_GRAPH_NODES` + `GRAPH_ACTIVE_POINTER` again
further down the same file (`:80-81`, `:160`, `:193-194`) to resolve subject
identity for the fail-closed Agent-Grade evidence contract. This is a
Terraform/SQL-bootstrap-tracked, production-facing contract (GH-246,
referenced live in CLAUDE.md's dev-blockers section as already applied to
prod), not a sketch-only artifact.

**(e) Access is deliberately provisioned, not incidental.**
`infra/snowflake/sql/dashboard/01_explore_reader_grants.sql:11-17` grants
the Explore dashboard's reader role explicit `USAGE`/`SELECT` on
`NEO4J_GRAPH_MIGRATION.MDM_GRAPH_NODES`, `MDM_GRAPH_EDGES`, and
`GRAPH_ACTIVE_POINTER` — someone specifically wired dashboard-role access to
the raw graph schema, confirming (b)/(c) are intentional product surfaces,
not an accidental/leftover reference.

**Verdict for Q5: graph sync is a real, separate decoupling boundary this
map needs to design around — it is not purely MDM-internal.** It has at
least three consumers beyond the operator review dashboard: the main
dashboard's Relationships tab, the main dashboard's freshness strip, and
the Decision Contract's Agent View evidence gate. Notably, **none of these
three route through `EDGARTOOLS_GOLD`** — they all query
`NEO4J_GRAPH_MIGRATION` directly from Snowflake — so this dependency is
structurally different from §1-4's finding: it is a real downstream
consumer of graph *sync* output, but it bypasses the gold layer entirely
rather than flowing through it. A decoupled architecture that treats "gold"
and "graph sync" as the same completion signal would be over-coupling two
things gold itself doesn't need (§1-4), while a design that drops graph
sync entirely, or treats it as purely MDM-internal with no external SLA,
would break three live-code consumers.

## Verdict

1. **Zero of 28 Python gold table builders (`gold_models.py`'s
   `_gold_table_builders`/`iter_gold_tables()`) query MDM in any form** —
   confirmed by full-file grep and by reading every `_build_*` function's
   SQL. The entire Python gold layer is silver-only.
2. **Exactly 2 of 23 dbt gold models reference the `mdm_export` source**
   (`company.sql`, `mdm_company.sql`), and both are the same join against
   the same single table (`MDM_COMPANY_ENTITY`) — `mdm_company.sql` is a
   no-op compatibility alias with no independent consumer, so there is
   effectively one MDM-dependent gold surface, not two.
3. **No relationship type feeds any gold table, directly or indirectly.**
   The one MDM-touching gold table (`COMPANY`) depends on MDM's
   entity-resolution golden record (`mdm run` + `mdm export`'s
   `export_pending` write), not on `backfill-relationships`,
   `IS_INSIDER`/`INSTITUTIONAL_HOLDS`/`HOLDS`/`COMPANY_HOLDS`/`MANAGES_FUND`/
   `EMPLOYED_BY`, or even `HAS_PARENT_COMPANY` (whose source column
   predates, rather than depends on, that relationship type's derivation).
   Today's synchronous ordering (export after backfill-relationships) is a
   pipeline-sequencing artifact, not a data dependency — noted as inference
   from code shape, not independently load-tested.
4. **A very clean split, narrower than the ticket's own hypothesis: 0 of 28
   Python builders and 21 of 23 dbt models are pure silver; MDM dependency
   collapses to exactly one real gold surface (`EDGARTOOLS_GOLD.COMPANY`),
   as a `LEFT JOIN` enrichment overlay on 5 of that table's columns, keyed
   on `cik`, whose own non-MDM columns are confirmed (not assumed) to trace
   straight back to the pure-silver `dim_company` builder via
   `GOLD_EXPORT_MAP`/`SNOWFLAKE_EXPORT_TABLES`.** Not scattered across
   ownership/holdings-shaped tables as originally guessed — `dim_party`,
   `fact_ownership_transaction`, and `fact_ownership_holding_snapshot` are
   all pure silver. **One confirmed qualification, not just a schema-level
   assumption (§4b):** the enrichment degrades gracefully (NULL columns) for
   `COMPANY` itself and for the Explore dashboard's screen surface, but the
   Decision Contract's `SUBJECT_FEATURE_SCREEN`/Agent View universe
   explicitly filters on `tracking_status='active'` with no coalesce-to-active
   fallback — that one surface has a hard, non-optional dependency on MDM's
   entity-resolution + export having already run for a given company.
   Separately: MDM's export path writes 5 golden-record tables into
   `EDGARTOOLS_GOLD` (`DOMAIN_TO_TABLE`, `export.py:23-29`), but only 1
   (`MDM_COMPANY_ENTITY`) is read by any dbt model — 4 are unconsumed.
5. **Graph sync (`NEO4J_GRAPH_MIGRATION`) has real downstream consumers
   beyond the operator review dashboard** — the main production dashboard's
   Relationships tab and freshness strip, and the Decision Contract's Agent
   View evidence gate — all reading the raw graph schema directly, bypassing
   `EDGARTOOLS_GOLD` entirely. This is a genuinely separate decoupling
   surface from gold's MDM dependency (§1-4): gold barely needs MDM at all,
   but graph *sync specifically* has its own, non-MDM-internal consumers
   that a redesign cannot silently drop.

**For [Decide MDM's role in the decoupled architecture](06-decide-mdm-role-in-new-architecture.md):**
the evidence strongly supports **"MDM as a narrow, optional downstream
consumer, not a universal gate on gold"** — with one explicit carve-out for
graph sync. Specifically:

- **Gold-refresh does not need to wait on MDM at all for the entire Python
  layer (28/28 tables) and 21 of 23 dbt models**, and for the one dbt model
  that does (`company.sql`), the dependency is a `LEFT JOIN` enrichment,
  not a blocking precondition — dbt's own `LEFT JOIN` semantics tolerate
  MDM being absent or stale for `COMPANY` itself (rows simply land with
  `NULL` `entity_id`/`display_name`/`tracking_status`/
  `parent_company_entity_id`/`has_multi_match_mdm_entity`, falling back to
  `entity_name` for `display_name` via the existing `coalesce()` at
  `company.sql:35`) and for the Explore dashboard's screen surface
  (`dashboard_workflows.py:181`'s `coalesce(tracking_status, 'active')`).
  A decoupled design could plausibly run gold-refresh entirely independent
  of MDM's completion for those surfaces, and re-run/backfill just
  `COMPANY`'s MDM columns whenever MDM's entity-resolution + export catches
  up — the data model already tolerates that skew today for everything
  except one view. **Confirmed exception (§4b):** the Decision Contract's
  `SUBJECT_FEATURE_SCREEN`/Agent View universe filters on
  `tracking_status='active'` with no active-by-default fallback, so that
  one surface's *membership* (not just its enrichment columns) genuinely
  waits on MDM — a fully MDM-optional gold design would need to either
  accept a temporarily-smaller Decision Subject Universe or gate that one
  view specifically, not assume it inherits `COMPANY`'s tolerance.
- **This narrow role applies to MDM's entity-resolution/export function
  specifically** (`mdm run` + `mdm export`'s golden-record write) — this
  ticket found **no** gold dependency at all on `backfill-relationships`,
  making relationship derivation an even more clearly optional,
  fully-decoupled MDM-internal step from gold's perspective.
- **Graph sync (`sync-graph`/`verify-graph`) cannot be folded into "purely
  MDM-internal, no external SLA"** the way relationship derivation can —
  §5 found three live consumers of its output outside MDM's own boundary.
  Ticket 06 should treat graph sync as its own decoupling question (closer
  to gold's own async-consumer shape: "when does the graph's active
  generation pointer need to be fresh enough for the dashboard/Decision
  Contract to trust it") rather than assuming it inherits whatever
  completion semantics MDM's entity-resolution/relationship stages get.
