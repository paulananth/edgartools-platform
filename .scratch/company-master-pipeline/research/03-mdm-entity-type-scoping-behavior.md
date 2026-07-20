# Research: `mdm run --entity-type company` / `mdm sync-graph --entity-type company` scoping behavior

Ticket: `.scratch/company-master-pipeline/issues/03-mdm-entity-type-scoping-behavior.md`

All line numbers below are from the repo as of this research pass (2026-07-20).

---

## Q1. `mdm run --entity-type company`: does the CLI/pipeline skip all relationship-derivation logic, or is entity-type only a narrower filter applied elsewhere?

**Direct answer: it skips all relationship-derivation logic entirely.** `mdm run --entity-type company` calls exactly one pipeline method, `MDMPipeline.run_companies()`, which never touches relationship derivation, `GraphSyncEngine`, or any ownership/ADV table. This is a real branch difference from `--entity-type all`, not a shared code path with a downstream filter.

### Evidence

`edgar_warehouse/mdm/cli.py:629-661` (`_handle_run`) dispatches per entity type with an explicit `if` per branch, calling a different pipeline method for each:

```python
def _handle_run(args) -> int:
    from edgar_warehouse.mdm.pipeline import MDMPipeline

    required = _required_tables_for_run(args.entity_type)
    silver, rc = _require_silver_reader(required, "mdm run")
    if rc != 0:
        return rc

    session = _session()
    try:
        pipeline = MDMPipeline(session=session, silver=silver)
        if args.entity_type == "all":
            stats = pipeline.run_all(limit=args.limit)
            print(json.dumps(stats.__dict__, indent=2, sort_keys=True))
            return 0
        if args.entity_type == "company":
            n = pipeline.run_companies(limit=args.limit)
            print(f"companies: {n}")
        ...
```

Only `--entity-type all` reaches `pipeline.run_all()`. `--entity-type company` reaches `pipeline.run_companies()` and returns — no other pipeline method is called in that request.

Contrast with `run_all()` at `edgar_warehouse/mdm/pipeline.py:1024-1035`, which is the *only* code path that also derives relationships:

```python
def run_all(self, limit: Optional[int] = None) -> PipelineStats:
    stats = PipelineStats()
    stats.companies_processed = self.run_companies(limit=limit)
    stats.advisers_processed = self.run_advisers(limit=limit)
    stats.securities_processed = self.run_securities(limit=limit)
    stats.persons_processed = self.run_persons(limit=limit)
    stats.funds_processed = self.run_funds(limit=limit)
    stats.relationship_counts_by_type = self.derive_relationships(target_per_type=limit)
    ...
```

`run_companies()` itself (`edgar_warehouse/mdm/pipeline.py:156-180`) only queries `sec_company`, `sec_company_ticker`, and `sec_company_sync_state`, and calls `CompanyResolver.resolve_one` — no relationship code, no `GraphSyncEngine`:

```python
def run_companies(self, limit: Optional[int] = None) -> int:
    ctx = self._ctx()
    resolver = CompanyResolver()
    sql = "SELECT * FROM sec_company"
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = self.silver.fetch(sql)
    processed = 0
    started_at = time.monotonic()
    for row in rows:
        ticker = self._first(self.silver.fetch(
            "SELECT ticker, exchange FROM sec_company_ticker "
            "WHERE cik = ? ORDER BY source_rank NULLS LAST LIMIT 1",
            [row["cik"]],
        ))
        tracking = self._first(self.silver.fetch(
            "SELECT tracking_status FROM sec_company_sync_state WHERE cik = ?",
            [row["cik"]],
        ))
        resolver.resolve_one(ctx, "edgar_cik", row, ticker, tracking)
        processed += 1
        ...
    self.session.commit()
    return processed
```

The CLI layer also pre-flights the *silver source*, not just entity-type semantics, via a fixed allowlist keyed by entity type (`edgar_warehouse/mdm/cli.py:503-522`):

```python
_REQUIRED_TABLES_RUN: dict[str, dict[str, bool]] = {
    "company": {
        "sec_company": False,  # must exist; ticker/sync-state are optional
    },
    "adviser": {
        "sec_adv_filing": True,  # nonempty
    },
    "fund": {
        "sec_adv_private_fund": True,  # nonempty
    },
    "person": {
        "sec_company_filing": True,  # nonempty
        "sec_ownership_reporting_owner": True,  # nonempty
    },
    "security": {
        "sec_company_filing": True,  # nonempty
        "sec_ownership_non_derivative_txn": True,  # nonempty
        "sec_ownership_derivative_txn": False,  # referenced by security UNION; may be empty
    },
}
```

`_required_tables_for_run("company")` (`edgar_warehouse/mdm/cli.py:534-553`) returns exactly `{"sec_company": False}` for `entity_type == "company"` — i.e. `sec_company` must *exist* (not even be nonempty), and no ownership/ADV table is checked at all. This means `mdm run --entity-type company` will run cleanly against a silver DuckDB that has never had ownership or ADV data loaded, as long as `sec_company` exists.

### Supporting context: what would happen if `derive_relationships` *were* invoked against empty ownership/ADV tables

Not reached in the company-only path, but relevant to understanding the design intent: individual `_derive_*` relationship methods are inconsistent in how they handle a missing source table.

- Some use the graceful helper `_fetch_optional_relationship_rows` (`edgar_warehouse/mdm/pipeline.py:126-147`), which catches "missing table" exceptions and emits an `mdm_relationship_skip` event with `reason: missing_source_table`, returning `[]` instead of raising. `_derive_institutional_holds` uses this for its `sec_thirteenf_holding` bounds query (`edgar_warehouse/mdm/pipeline.py:1827-1834`).
- `_derive_is_insider` (`edgar_warehouse/mdm/pipeline.py:375-450`) does **not** use that helper — it calls `self.silver.fetch(...)` directly against a query joining `sec_ownership_reporting_owner` and `sec_company_filing` (`edgar_warehouse/mdm/pipeline.py:392`), so if `sec_ownership_reporting_owner` doesn't exist, this call would propagate an exception rather than gracefully no-op.

This inconsistency is exactly why the CLI's `entity_type == "company"` branch avoiding `derive_relationships` entirely (rather than relying on a graceful no-op inside each deriver) is the safer design — it isn't relying on unverified/inconsistent no-op behavior, it skips the derivation code path altogether.

---

## Q2. `mdm sync-graph --entity-type company`: does it sync only Company nodes with zero edge attempts, or does it also run edge-sync logic?

**Direct answer: it materializes only Company nodes as requested, but the SAME script UNCONDITIONALLY also runs the edge-sync/INSERT step for every active relationship type in MDM — the `--entity-type` filter is wired only into the node query, not the edge query.** However, this is safe in the "no ownership/ADV data yet" scenario: the edge query reads from MDM's own already-migrated Snowflake tables (`MDM_RELATIONSHIP_INSTANCE`/`MDM_RELATIONSHIP_TYPE`), not from silver DuckDB directly, so with zero relationship instances in MDM it produces zero edge rows without any error — not a silent per-type no-op decision, just an empty result set from a `WHERE` filter that naturally matches nothing yet.

### Evidence

`_handle_sync_graph` (`edgar_warehouse/mdm/cli.py:1182-1206`) passes `args.entity_type` straight through to `SnowflakeGraphSyncConfig.entity_types`, and passes `args.relationship_type` straight through to `relationship_types` (defaulting to `None` → empty tuple if `--relationship-type` isn't also given):

```python
def _handle_sync_graph(args) -> int:
    ...
    result = SnowflakeGraphSyncExecutor.from_env().sync(
        _snowflake_graph_sync_config(
            entity_types=args.entity_type,
            relationship_types=args.relationship_type,
            ...
        )
    )
```

`SnowflakeGraphSyncConfig.entity_types`/`relationship_types` (`edgar_warehouse/mdm/snowflake_graph.py:118-134`) are two *independent* tuples — there is no cross-derivation of "only sync edges whose endpoint entity types are in `entity_types`."

`SnowflakeGraphSyncExecutor.sync()` (`edgar_warehouse/mdm/snowflake_graph.py:228-288`) builds one context and executes one combined SQL script (`render_graph_tables(context)`) that does the node materialization AND the edge materialization in the same unconditional pass — there's no `if entity_types` branch that skips the edge block:

```python
context = _graph_context(
    ...
    entity_types=entity_types,
    relationship_types=relationship_types,
    ...
)
cursor = self.connection.cursor()
try:
    _execute_sql_script(cursor, render_graph_tables(context))
    node_count = _fetch_scalar(cursor, f"SELECT COUNT(*) FROM {_fq(context, 'MDM_GRAPH_NODES')} ...")
    edge_count = _fetch_scalar(cursor, f"SELECT COUNT(*) FROM {_fq(context, 'MDM_GRAPH_EDGES')} ...")
```

Inside the generated SQL (`edgar_warehouse/mdm/snowflake_graph.py:1147-1389`), the node query applies `entity_type_filter`:

```sql
-- line 1264
WHERE E.IS_QUARANTINED = FALSE{context["entity_type_filter"]}
```

...but the edge INSERT query applies only `relationship_type_filter`, not any entity-type-derived filter:

```sql
-- lines 1310-1378
INSERT INTO {_fq(context, "MDM_GRAPH_EDGES")}
  (...)
SELECT
  ...
FROM {_mdm_fq(context, "MDM_RELATIONSHIP_INSTANCE")} RI
JOIN {_mdm_fq(context, "MDM_RELATIONSHIP_TYPE")} RT
  ON RT.REL_TYPE_ID = RI.REL_TYPE_ID
...
WHERE RI.IS_ACTIVE = TRUE
  AND RT.IS_ACTIVE = TRUE{context["relationship_type_filter"]}
{context["relationship_per_type_limit"]}{context["relationship_limit"]};
```

`_in_filter()` (`edgar_warehouse/mdm/snowflake_graph.py:1717-`) returns `""` (no filter clause at all) when the tuple is empty:

```python
def _in_filter(column: str, values: tuple[str, ...]) -> str:
    if not values:
        return ""
```

So calling `mdm sync-graph --entity-type company` (without also passing `--relationship-type`) leaves `relationship_types = ()`, which means `relationship_type_filter == ""`, which means the edge INSERT runs unfiltered over **every** `RI.IS_ACTIVE = TRUE` row across every relationship type currently in MDM's Snowflake-side `MDM_RELATIONSHIP_INSTANCE`/`MDM_RELATIONSHIP_TYPE` tables — not scoped to Company-only edges.

**Why this is still safe for the company-only-first scenario:** `MDM_RELATIONSHIP_INSTANCE`/`MDM_RELATIONSHIP_TYPE` are MDM's own state, materialized into Snowflake — not raw ownership/ADV *silver* tables. `_handle_sync_graph` never opens a silver reader at all (no `_require_silver_reader` call anywhere in that handler, contrast with `_handle_run`/`_handle_derive_relationships`/`_handle_load_relationships` which all call it). If `derive_relationships`/`load-relationships` has never been run (the ownership/ADV-not-yet-processed scenario this ticket cares about), `MDM_RELATIONSHIP_INSTANCE` simply has zero active rows, so the edge INSERT selects and inserts zero rows — no exception, no missing-table error, no warning. `edge_count` in the result will just be `0`.

**Caveat worth flagging for the ticket's design:** this "0 edges synced" outcome is an accidental byproduct of MDM being genuinely empty of relationships at this point in the pipeline sequencing — it is not an intentional "skip edges when entity_type=company" behavior. If a *later* company-only re-sync were run after ownership/ADV relationships already exist elsewhere in MDM (e.g. a repair run), `--entity-type company` alone would NOT prevent re-syncing all existing relationship-type edges too, because the entity filter and relationship filter are orthogonal knobs. If the intended semantics are "company nodes only, no edges, ever," the caller must also pass an empty/no-op `--relationship-type` selection that resolves to zero types — but there's no such "zero relationship types" flag; omitting `--relationship-type` means "all types," and the only way to get zero recorded relationship-type edges as a *guarantee* (not an accident of current MDM state) would be to pass `--relationship-type` values that don't yet exist, which isn't a supported no-op call shape today.

---

## Q3. `CompanyResolver` (`edgar_warehouse/mdm/resolvers/company.py`): does it depend on anything beyond company master/reference data, or does it join ownership/ADV silver state?

**Direct answer: fully independent.** `CompanyResolver` only reads from company-domain silver tables (`sec_company`, `sec_company_ticker`, `sec_tracked_universe`/`sec_company_sync_state` — supplied as pre-fetched rows by `run_companies()`, not queried by the resolver itself) and MDM's own company tables (`MdmCompany`, `MdmEntity`, `MdmSourceRef`). It never queries `sec_ownership_*`, `sec_adv_*`, or `sec_thirteenf_*`.

### Evidence

Class docstring (`edgar_warehouse/mdm/resolvers/company.py:1-6`):

```python
"""CompanyResolver — resolves SEC companies to MDM entities.

Source: silver tables sec_company, sec_company_ticker, sec_tracked_universe.
Primary match: CIK exact (definitive). Fuzzy name is available but rarely
needed because SEC CIK is a stable, unique key.
"""
```

`resolve_one()` (`edgar_warehouse/mdm/resolvers/company.py:57-117`) takes `company_row`, `ticker_row`, `tracking_row` as plain dicts (already fetched by the caller, `MDMPipeline.run_companies()`, from `sec_company`/`sec_company_ticker`/`sec_company_sync_state` — see Q1 evidence). Inside `resolve_one`, the only additional lookups are:

- `_existing_candidates()` (`edgar_warehouse/mdm/resolvers/company.py:119-135`) — queries `MdmCompany` joined to `MdmEntity` by `cik`, both MDM tables.
- `_parent_company_entity_id()` (`edgar_warehouse/mdm/resolvers/company.py:176-202`) — looks up a parent CIK column *on the same `company_row`* (from `sec_company`, not a join to another silver domain) and resolves it against `MdmCompany` (again, MDM's own company table, purely within the Company entity type):

```python
@staticmethod
def _parent_company_entity_id(ctx: ResolverContext, company_row: dict) -> Optional[str]:
    if not any(key in company_row for key in _PARENT_CIK_KEYS):
        ...
        return None
    parent_cik = (
        company_row.get("parent_company_cik")
        or company_row.get("parent_cik")
        or company_row.get("ultimate_parent_cik")
    )
    ...
    return ctx.session.scalar(
        select(MdmCompany.entity_id).where(MdmCompany.cik == parent_cik_int)
    )
```

No ownership table (`sec_ownership_*`), no ADV table (`sec_adv_*`), no 13F table (`sec_thirteenf_*`) is referenced anywhere in `resolvers/company.py`. The one cross-entity dependency (`HAS_PARENT_COMPANY` resolution, still Company→Company) degrades gracefully to `None` with a one-time logged warning (`edgar_warehouse/mdm/resolvers/company.py:177-187`) rather than failing, when the parent-CIK source column isn't present on `sec_company` — consistent with the map's own noted historical gap (`TODOS.md parent_company_entity_id_always_none`, referenced in that same warning).

Conclusion: Company resolution is genuinely a closed, independent domain — it can run correctly on a silver warehouse where ownership/ADV have never been loaded at all.

---

## Q4. Is there a company-entity equivalent of the "Relationship Coverage Record" classification, or a simpler existing pass/fail signal?

**Direct answer: there is no company-entity equivalent of the Relationship Coverage Record's three-way (`populated` / `valid_zero` / `excluded`) classification, and none is needed to safely reuse `--entity-type company` — but two existing, simpler, already-independent-of-relationship-state signals cover the practical need: `mdm coverage-report` (silver-vs-MDM count/gap per domain, includes `companies`) and `mdm verify-graph`'s per-entity-type `node_parity_<entity_type>` check (MDM-vs-Snowflake-graph exact parity, includes `node_parity_company`).** Building a formal generation-scoped three-state Entity Coverage Record analogous to the Relationship Coverage Record would be new work, but is not blocking for this ticket's destination (company-only resolution ahead of ownership/ADV) since the pass/fail signals already report success/failure without any reference to relationship data.

### Evidence

`CONTEXT.md:233-235` defines the term this ticket is checking for an equivalent of:

```
**Relationship Coverage Record**:
The single fresh classification for one active relationship type in one graph generation: `populated` for nonzero eligible edges, `valid_zero` only when complete supported derivation over complete inputs proves zero, or `excluded` for a fingerprinted and approved source/capability boundary with a review trigger.
_Avoid_: Hardcoded populated type, inherited zero, undocumented exclusion, synthetic edge
```

A repo-wide grep of `CONTEXT.md`'s glossary headers for entity/coverage/company/node terms turns up no analogous "Entity Coverage Record" or per-entity-type three-state classification term — only the relationship-scoped ones (`Relationship Coverage Record`, `Approved Relationship Exclusion`, `Required Relationship Type`, `Relationship Applicability`, all at `CONTEXT.md:233-247`).

**Existing simpler signal #1 — `mdm coverage-report`:** `compute_coverage()` (`edgar_warehouse/mdm/coverage.py:14-`) returns one row per domain (including `"companies"`) comparing `silver_count` to `mdm_count`:

```python
# edgar_warehouse/mdm/coverage.py:44-54
company_silver = _silver(
    "SELECT COUNT(DISTINCT c.cik) AS n "
    "FROM sec_company c "
    "JOIN sec_company_sync_state s ON s.cik = c.cik "
    "WHERE s.tracking_status = 'active'"
)
company_mdm = _mdm_count(MdmCompany)
```

and returns `{"domain": "companies", "silver_count": ..., "mdm_count": ..., "gap": ..., "reason": "Inactive and dropped companies excluded (tracking_status != 'active')"}`. This is purely a Company-domain comparison — it never references ownership/ADV tables for the `companies` row, so it already reports Company completeness independent of relationship state.

**Existing simpler signal #2 — `mdm verify-graph` node parity, per entity type:** `_named_node_parity_checks()` (`edgar_warehouse/mdm/snowflake_graph.py:1807-1838`) emits one named check per entry in `ALLOWED_ENTITY_TYPES` (`edgar_warehouse/mdm/snowflake_graph.py:20`: `("adviser", "audit_firm", "company", "fund", "person", "security")`), each with a binary `"ok"`/`"failed"` status based on exact count parity between MDM's active company count and the Snowflake graph's company-node count:

```python
for entity_type in ALLOWED_ENTITY_TYPES:
    row = by_type.get(entity_type)
    present = row is not None
    ...
    at_parity = present and row["mdm_minus_graph"] == 0 and row["graph_minus_mdm"] == 0
    check = {
        "name": f"node_parity_{entity_type}",
        "entity_type": entity_type,
        "present": present,
        "mdm_active_count": mdm_active_count,
        "snowflake_graph_node_count": snowflake_graph_node_count,
        "status": "ok" if at_parity else "failed",
    }
```

This produces a `node_parity_company` check with no reference to any relationship type or ownership/ADV data — it is inherently a Company-only completeness signal already.

**Gap relative to the Relationship Coverage Record concept:** neither signal distinguishes "zero because genuinely nothing to resolve yet" (`valid_zero`) from "zero because of a real bug/regression" the way the three-way relationship classification does, and neither is generation-scoped (tagged to one `GENERATION_ID` the way relationship coverage is meant to be per `CONTEXT.md:276`'s "Relationship Generation Snapshot"). If this map's future work wants Company-entity resolution to go through the same generation/parity rigor Ticket 20's relationship release used, that would be new work (a "Company Coverage Record" or extending `_named_node_parity_checks` with a three-state classification) — but that is a documentation/rigor gap, not a functional blocker: today's binary checks already report Company completeness cleanly, without any dependency on ownership/ADV having run.

---

## Conclusion for Ticket 03

**`--entity-type company` is safe to use as the mechanism for company-only MDM resolution ahead of ownership/ADV, with one caveat to note in the pipeline design (not a code defect that needs fixing before use):**

1. `mdm run --entity-type company` is a clean, independent code path: it calls only `run_companies()` → `CompanyResolver`, never touches `derive_relationships()` or any `_derive_*` method, and its CLI-layer silver preflight requires only `sec_company` to exist (not even be nonempty) — no ownership/ADV table is checked or queried. Confirmed no dependency on ownership/ADV silver state anywhere in this path.
2. `CompanyResolver` itself resolves purely from company-domain silver rows plus MDM's own `MdmCompany`/`MdmEntity` tables; the one cross-entity field (`parent_company_entity_id`) is Company→Company and degrades gracefully (logged warning, not an error) when the source column is absent.
3. `mdm sync-graph --entity-type company` materializes Company nodes correctly scoped by the entity-type filter, and will not error or warn about missing ownership/ADV data, because it never reads silver at all (no `_require_silver_reader` call in `_handle_sync_graph`) — it reads MDM's already-migrated Snowflake state. In the specific "ownership/ADV not yet processed" scenario, `MDM_RELATIONSHIP_INSTANCE` is empty, so the edge-sync half of the same script inserts zero rows with no failure.

**The one thing to be precise about in the pipeline design (a documentation/usage-pattern issue, not a bug to fix in code):** `--entity-type` on `sync-graph` filters only the *node* query; the *edge* INSERT is filtered solely by `--relationship-type` (defaulting to "all types" when omitted), independent of `--entity-type`. Today, in a fresh company-only-first generation, this is harmless because there are no relationship instances yet to select. But it means "`--entity-type company` syncs zero edges" is true *only* by coincidence of current MDM state, not by a guaranteed "company implies no-edges" contract — a later company-only re-sync run against an MDM instance that already has other relationships populated would still attempt (and succeed at) syncing all of those pre-existing relationship-type edges. If the design wants an airtight "Company Identity pass never touches edges" guarantee, that would need either (a) a real code change (thread `entity_types` into the edge query's filter, or add an explicit `--no-edges` flag), or (b) a documented operational rule that this pipeline is only ever run in the "ownership/ADV genuinely hasn't produced any MDM relationships yet" window. No such flag or rule exists in the code today.

**No modification is required to unblock the Company Identity pipeline's Phase-1 use case as scoped.** If the map wants generation-scoped three-state Company completeness classification symmetric with the Relationship Coverage Record, that is new work (no code today provides it) — but the existing `mdm coverage-report` (`companies` domain, silver-vs-MDM gap) and `mdm verify-graph`'s `node_parity_company` check already give a clean, relationship-state-independent pass/fail signal sufficient to confirm "Company resolution succeeded" without inventing anything new for this ticket's decision.
