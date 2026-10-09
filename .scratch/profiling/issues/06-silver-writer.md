# 06 Silver writer (rules-skill ticket 05)

Type: task. Phase: B. Blocked by: 01a, Codex retirement merged (overruled by the operator, below). Map: [map](../map.md). Plan: [plan](../plan.md).

Scope: plan decision 36. Silver for the trials and the proof is a `silver` schema
in a disposable local PG16, written through one small sink interface, so a
Snowflake sink can follow as its own ticket. rules-skill ticket 05's Delta and
Lakebase outcome (and its `deltalake` extra) is superseded by that decision.
Estimate: 3–5 days (plan).

## Checklist

- [ ] ~~Wait for Codex's old-parser retirement gate before starting (operator, 2026-10-08 18:20 ET: "Wait for Codex", asked whether to start 06 ahead of it)~~ overruled by the operator, 2026-10-08 21:15 ET: "start ticket 06 now"
- [ ] Re-check 06 against Codex's final design when the retirement gate closes (plan, phase B)
- [x] GoF consult: copy the migration loop (ticket 02's verdict holds: the four loops changed only for their own roles and grants, the shared lines never); the sink interface is required by plan decision 36, kept to one small protocol 2026-10-08 21:20 ET
- [x] Spec §6 gap: a link names its master's Dataset Contract (`source_code`), so a source key resolves to one MDM id; links point to master parts only (Trial B's profiling linked to reference and transaction parts, and twice from one column); profiling's `_silver` now emits master links with empty `kind`/`source_code` for onboarding to fill; `findings.md` §6 updated; a change to the approved spec, reported to the operator 2026-10-08 21:38 ET
- [x] Store: checksummed `silver` schema migrations on PG16 (`edgar_warehouse/silver_writer/`, `001_silver.sql`), owner and restricted runtime separated, a `silver.table_spec` registry with comments on everything (PG16 test) 2026-10-08 21:38 ET
- [x] Sink interface; the PostgreSQL sink (typed columns, BIGINT integers, jsonb for nested values, every name quoted and at most 63 bytes, `COMMENT ON` from the spec; rows copied as text and cast by the database, so a wrong value refuses the delivery) (unit and PG16 tests) 2026-10-08 21:38 ET
- [x] Register a spec: create its table; the same spec again changes nothing; a changed spec for a registered table is refused (register it as a new table) (PG16 test) 2026-10-08 21:38 ET
- [x] Land rows from flat JSON Lines, CSV or Parquet: typed per column, `loaded_at` added, each link's MDM id read from MDM by (source_code, kind, record key) with merged entities followed to their canonical id; unmastered rows keep it empty and a later landing fills it; `append` refuses a changed row, `upsert` changes only changed rows, `snapshot` also removes undelivered rows and refuses an empty delivery; each reruns without change (PG16 tests) 2026-10-08 21:38 ET
- [x] `edgar-warehouse silver init|migrate|register|land|describe`; `doctor` 0 unresolved, 130 commands named 2026-10-08 21:38 ET
- [x] PG16 tests on a populated table: idempotent rerun per load mode, refused changed spec, an unmastered row, a link resolved through real MDM mastering, bad deliveries write nothing, names with `%` and `:` (16 PG16 tests on a local PostgreSQL 16.2 via pgserver, no Docker here; CI runs them in Docker; 9 unit tests) 2026-10-08 21:38 ET
- [x] Done test: profiling re-run on Trial B (Contoso V2, not SEC); all 5 silver specs register and land through the writer with no domain-specific change: currencyexchange 36,525, date 1,461, orderrows 7,794, orders 3,242, sales 7,794 rows, typed (bigint, date, double precision, text), source keys kept, each rerun 0 inserted 0 changed; MDM ids empty because no Contoso master is onboarded (resolution through mastered records is the PG16 test) (`trials/silver/land_trial_b.py`, `result.json`) 2026-10-08 21:38 ET
- [x] `silver.table_context` (ticket 05's open part): a view over the registry with the agent-context spec's fields; `edgar-warehouse context silver [<table>]` answers within 8 KB (PG16 test) 2026-10-08 21:38 ET
- [ ] ~~RDM publish writes to silver through this writer~~ deferred: `rdm publish` writes flat JSON Lines that `silver land` reads once their specs are registered; wiring publish to land would make RDM depend on the silver database. Plan row 2's "publishes to silver" done test stays met by the JSON Lines
- [x] Skill text: data-onboarding's silver target names the writer's steps and what is not built (a warehouse sink, a flat export of nested parts, a pipeline worker); data-profiling's silver line; genericity lint passes 2026-10-08 21:38 ET
- [ ] Review (Standards, Spec, GoF), PR, CI, merge on the operator's word
