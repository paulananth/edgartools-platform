# 05 — Audit snowflake_graph.py's sync-graph/verify-graph internals for the unscoped-load shape

Type: task
Status: resolved

## Question

`edgar_warehouse/mdm/snowflake_graph.py` (`SnowflakeGraphSyncExecutor`/
`SnowflakeGraphVerifier`) implements `mdm sync-graph` (runs on `mdm_large_arn`)
and `mdm verify-graph` (runs on `mdm_small_arn`) — both are steps of
`residual_holds_graph`'s state machine (via `wire_mdm_tail`), but neither
was actually covered by Ticket 01's audit: that ticket's spec named 7
steps explicitly and `mdm sync-graph`/`mdm verify-graph` were not among
them, even though `sync-graph` genuinely runs on `mdm-large`. Found while
closing out the map — a real coverage gap against the map's own
Destination ("every `large`/`mdm-large` consumer... checked"), not
something any prior ticket ruled out deliberately.

Audit this module's Python-side row materialization for the
MANAGES_FUND-shape risk (unscoped full load of a shared table/dataset
before scoping is known) — using real evidence (reading the actual SQL
each Python function issues and what it returns), not assumptions from
the module's size (2,456 lines).

## Blocked by

None — can start immediately.

## Answer

Confirmed clean bill of health — no fix needed. This module is
architecturally different from the audited shape by design: every
operation that scales with MDM data volume pushes the actual computation
server-side into Snowflake SQL and pulls only a small, bounded summary
back into Python.

**`SnowflakeGraphVerifier`'s parity checks** (`_render_verify_node_counts`/
`_render_verify_relationship_counts`): `GROUP BY entity_type`/
`GROUP BY relationship_type` aggregate queries — result sets are bounded
by the small, fixed number of entity types (6: company/adviser/person/
security/fund/audit_firm) and relationship types (11), never by MDM's
actual row count (hundreds of thousands of entities/relationships).

**Exact-parity checks** (`_render_exact_node_parity`/
`_render_exact_relationship_parity`): use Snowflake's `HASH_AGG(...)` to
compute a single order-independent content hash server-side across
potentially hundreds of thousands of rows — Python receives exactly one
summary row per query (`CONTENT_HASH`, `ROW_COUNT`), never the underlying
rows. The heavy lifting happens entirely inside Snowflake's own engine.

**Mismatch-sample queries** (`_render_missing_nodes`/`_render_extra_nodes`/
`_render_missing_edges`/`_render_extra_edges`/`_render_missing_edge_endpoints`):
every one of these explicitly bounds its result with
`LIMIT {context["sample_limit"]}`, where `sample_limit` defaults to **20**
(`SnowflakeGraphVerificationConfig.sample_limit: int = 20`) — genuinely a
small sample of mismatches for human review, not a full dump, matching
CLAUDE.md's own "40 mismatch samples" reference for GH-251's contract
(a slightly larger but still small, deliberately bounded figure).

**Native App health/readiness checks** (`_native_rows_check`/
`_native_execute_check`/`_native_sample_node_check`, `SHOW APPLICATIONS`
etc.): system-metadata/capability probes, inherently small and unrelated
to MDM entity/relationship volume — not a scaling risk by construction.

**`SnowflakeGraphSyncExecutor`'s sync path** (`render_graph_tables`,
executed via `_execute_sql_script`): generates MERGE/INSERT SQL text
executed server-side in Snowflake — the actual row-by-row graph
materialization happens inside Snowflake's own engine, not via Python
row iteration. The only Python-side reads in this class
(`_fetch_scalar` calls for `available_node_count`/`available_edge_count`/
`node_count`/`edge_count`) return single scalar counts.

No genuine unscoped-load-shape gap found anywhere in this module. Full
repo test suite unaffected (no code changed) — this ticket is
investigation-only, a clean-bill-of-health outcome per this map's own
"a clean bill of health is a valid, useful answer" convention (established
by tickets 01-04).

This closes the map's own coverage gap and completes the Large-profile
unscoped-load audit — every `large`/`mdm-large` consumer identified in the
map's own inventory has now been checked.
