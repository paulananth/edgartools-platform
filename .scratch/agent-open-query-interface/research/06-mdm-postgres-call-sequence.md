# MDM Postgres call sequence: entry point to SQL execution

Ticket: `.scratch/agent-open-query-interface/issues/06-trace-mdm-postgres-call-sequence.md`
(no ticket file created by this research pass — see the task instructions;
listed here only as the expected numbering peer of
`.scratch/agent-open-query-interface/research/05-mdm-postgres-ddl-inventory.md`,
which this file continues).

Read live: 2026-09-19, against source in this worktree
(`claude/mongo-sparql-agent-contract`, checked out at
`/Users/aneenaananth/projects/edgartools-platform-worktrees/claude-mongo-sparql-agent-contract`).
Every claim below cites `file:line` in that checkout. This is source-code
tracing, not execution tracing — no command was actually run against Postgres
for this research beyond what `05-mdm-postgres-ddl-inventory.md` already did.

**Scope note carried over from `05`:** `edgar_warehouse/mdm/clean/` (the
actively-owned "Clean MDM" rebuild — `clean/store.py`, `clean/cli.py`, etc.)
is a **separate, parallel** write path (`mdm migrate --model clean`, `mdm
apply-decisions`) that was *not* traced here beyond noting where it forks off
the legacy path (§4). This document covers the **legacy** MDM path only
(`mdm mastering` / `mdm migrate --model legacy`, the default and the one
CLAUDE.md's "Phased Pipeline" section describes) — per the task's own
instruction not to touch `.scratch/clean-mdm/`.

## 1. Connection/session setup

**Where `MDM_DATABASE_URL` is read:** `edgar_warehouse/mdm/database.py:132`,
inside `get_engine()`:

```python
def get_engine(url: str | None = None) -> Engine:
    url = url or os.environ["MDM_DATABASE_URL"]
```
(`edgar_warehouse/mdm/database.py:131-132`)

This is the **only** place `MDM_DATABASE_URL` is read as a hard requirement
(`os.environ[...]`, not `.get(...)` — missing means `KeyError`, fail-closed).
The one exception is `edgar_warehouse/mdm_entity_backfill.py:322-324`
(`backfill-mdm-entity-ids`, the warehouse-side BackpropagateIdsToSilver
command — see §2 Stage 2), which reads it via `os.environ.get(...)` first and
raises its own `WarehouseRuntimeError` if empty, then calls `get_engine(mdm_url)`
with the value passed explicitly rather than letting `get_engine` re-read the
env var.

**It is SQLAlchemy, not raw psycopg2.** `get_engine` calls
`sqlalchemy.create_engine(url, **kwargs)` (`database.py:144`) and returns a
plain `sqlalchemy.engine.Engine`. `get_session(engine)` (`database.py:151-152`)
wraps it in a plain `sqlalchemy.orm.Session(engine)` — no session factory,
no scoped-session, no async engine.

**Engine construction details** (`database.py:110-148`):

- Pool sizing is env-tunable: `MDM_DB_POOL_SIZE` (default 40) /
  `MDM_DB_MAX_OVERFLOW` (default 20) — `database.py:127-128`. A long comment
  (`database.py:110-126`) explains these were raised from SQLAlchemy's
  QueuePool defaults (5/10) specifically because `MDMPipeline`'s resolve
  loops (`run_companies`, `run_securities`, `run_persons`) each open their own
  bounded worker-thread pool of **concurrent sessions against the same
  engine** — up to ~50 combined connections in one ECS task once `run_all()`
  launches its 5 entity-resolution steps as concurrent top-level futures.
  Verified live against a real server `max_connections` of 500.
- `pool_pre_ping=True` unconditionally (`database.py:133`).
- SQLite URLs (`sqlite://...`, test/stub backend only) skip
  `pool_size`/`max_overflow` because SQLite's pool classes don't accept them
  (`database.py:134-141`).
- Every engine gets `install_mdm_sql_logging(engine)` attached
  (`database.py:145-147`), which registers a SQLAlchemy
  `before_cursor_execute`/`after_cursor_execute` event pair
  (`edgar_warehouse/mdm/observability.py:38-58` — `install_mdm_sql_logging`)
  that emits a structured `mdm_sql_started`/`mdm_sql_completed` JSON event
  per statement (operation, parameter count, statement hash, table names,
  elapsed ms) unless `MDM_SQL_CALL_LOGGING=false`. This means **every** SQL
  statement this document traces is independently observable in the
  container's stdout/stderr JSON log stream, keyed by a per-statement
  `mdm-sql-<nanoseconds>` call id.

**Relative to CLI dispatch:** the engine/session is constructed **lazily,
per-command**, not once at process startup. `edgar_warehouse/mdm/cli.py`'s
`register_mdm_subparser` (`cli.py:25-...`) wires argparse subcommands to
handler functions; each handler imports and calls `get_engine()`/`get_session()`
itself, inside its own function body, e.g.:

```python
def _session() -> Session:
    from edgar_warehouse.mdm.database import get_engine, get_session
    return get_session(get_engine())
```
(`edgar_warehouse/mdm/cli.py:733-735`)

`_handle_run` (the `mdm mastering` handler) calls `_session()` directly
(`cli.py:982`); `_handle_migrate` calls `get_engine()` directly without a
session wrapper, since `migrate()` manages its own sessions internally
(`cli.py:1646-1653`). No connection is opened until a handler actually runs —
`edgar-warehouse mdm --help` never touches Postgres.

The FastAPI side does the same lazily-but-once-per-process pattern via a
module-level cache instead of per-call construction — see §3.

## 2. Write-side call sequence (Mastering → Reconcile)

The state machine that chains these six stages is generated by
`write_mdm_definition()` in `infra/scripts/deploy-aws-application.sh:2822-2975`
(a bash function that emits a Step Functions JSON definition via an inline
`python3` heredoc). Its own comment
(`infra/scripts/deploy-aws-application.sh:2953-2960`) names the exact chain
CLAUDE.md's "Phased Pipeline" section restates: **Mastering →
BackpropagateIdsToSilver → Infer Relationships → Publish → Publish
Relationships → Reconcile**, run as a nested `states:startExecution.sync:2`
execution any caller (`daily_incremental`, `load_history`, the seed machine)
invokes with `Input: {"run_id": <calling execution's own Execution.Name>}`.

Each state runs one ECS Fargate task whose container command is an array
built inline in that same file. The exact command strings
(`deploy-aws-application.sh:2906-2938`) are the ground truth for which CLI
subcommand each stage invokes:

| State | Command | CLI subparser → handler |
|---|---|---|
| Mastering | `mdm mastering --entity-type all [--limit N] --run-id $.run_id` | `cli.py:137` (`mastering`) → `_handle_run` (`cli.py:175`) |
| BackpropagateIdsToSilver | `backfill-mdm-entity-ids --run-id $.run_id` (**warehouse** CLI, not `mdm`) | `edgar_warehouse/cli.py:1449-1458` → `_handle_backfill_mdm_entity_ids` (`edgar_warehouse/cli.py:302-303`) |
| Infer Relationships | `mdm infer-relationships --limit N --run-id $.run_id` | `cli.py:622` (`br`, help text says "infer-relationships") → `_handle_backfill_relationships` (`cli.py:633`) |
| Publish | `mdm publish` | `cli.py:636` (`ex`) → `_handle_export` (`cli.py:650`, body at `cli.py:2500`) |
| Publish Relationships | `mdm publish-relationships --limit N` | `cli.py:239` (`sync`) → `_handle_sync_graph` (`cli.py:266`, body at `cli.py:1863`) |
| Reconcile | `mdm reconcile` | `cli.py:537` (`vg`) → `_handle_verify_graph` (`cli.py:573`, body at `cli.py:2216`) |

Two Catch clauses are load-bearing for how failures propagate, confirmed live
against a real incident cited in the script's own comment
(`deploy-aws-application.sh:2884-2889`, `2914-2922`, `2939-2945`):
BackpropagateIdsToSilver and Reconcile both `Catch: States.ALL` into a
non-fatal Pass state — a sweep failure or a reconcile failure does not fail
the outer chain. Mastering, Infer Relationships, Publish, and Publish
Relationships have no such Catch — a failure there **does** fail the whole
nested execution (subject to the shared `Retry` block,
`deploy-aws-application.sh:2865-2870`: 2 attempts, 120s initial backoff,
2.0x rate).

### 2a. Mastering: `mdm mastering` → `MDMPipeline` → resolver → ORM insert

```
_handle_run(args)                                    cli.py:972
  └─ silver = _require_silver_reader(...)             cli.py:977
  └─ run_id = bind_mdm_run_identity(...)              cli.py:981
  └─ session = _session()                              cli.py:982   # get_session(get_engine())
  └─ pipeline = MDMPipeline(session=session, silver=silver, run_id=run_id)
                                                         cli.py:984
  └─ (entity_type == "all") → _run_all_with_ordinary_lease(pipeline, session, ...)
                                                         cli.py:987
       └─ pipeline.run_all(...)                         pipeline.py:2898
            └─ launches run_companies / run_advisers / run_securities /
               run_persons / run_funds as concurrent top-level futures
               (per database.py's pool-sizing comment, database.py:110-126)
```

`run_companies` is the fullest-traced example
(`pipeline.py:784-1078`), representative of the others' shape:

```
MDMPipeline.run_companies(...)                        pipeline.py:784
  └─ resolver = CompanyResolver()                      pipeline.py:840
  └─ rows = self.silver.fetch(...)                     pipeline.py:880-943   # Snowflake EDGARTOOLS_SILVER, not Postgres
  └─ sql_engine = self.session.get_bind()               pipeline.py:965      # underlying Postgres Engine
  └─ ThreadPoolExecutor(max_workers=...)                 pipeline.py:1037
       └─ _resolve_row(row)  [worker thread, own session] pipeline.py:990
            └─ worker_session = get_session(sql_engine)  pipeline.py:991     # database.get_session — fresh Session, SAME engine/pool
            └─ resolver.resolve_one(worker_ctx, "edgar_cik", row, ...)
                                                          pipeline.py:1002    # resolvers/company.py (CompanyResolver)
                 └─ (via BaseResolver.resolve_or_create, resolvers/base.py:235)
                      └─ BaseResolver._create_entity(ctx, ...)  resolvers/base.py:95
                           └─ ctx.session.add(MdmEntity(...))   resolvers/base.py:108
                           └─ ctx.session.flush()                resolvers/base.py:109   # <-- SQL/ORM boundary: INSERT INTO mdm_entity
                      └─ BaseResolver._register_source(ctx, ...) resolvers/base.py:112
                           └─ ctx.session.merge(MdmSourceRef(...)) resolvers/base.py:129  # <-- SQL/ORM boundary: INSERT/UPDATE mdm_source_ref
                      └─ (domain fields) stage_candidate(...) → mdm_entity_attribute_stage rows
                      └─ BaseResolver._log_change(...)           resolvers/base.py:196
                           └─ ctx.session.add(MdmChangeLog(...)) resolvers/base.py:226
            └─ worker_session.commit()                          pipeline.py:1006  # <-- durable write
            └─ except Exception: worker_session.rollback(); raise
                                                                  pipeline.py:1012-1023
            └─ finally: worker_session.close()                   pipeline.py:1025
```

The domain golden-record row itself (`MdmCompany`/`MdmAdviser`/etc.) is
created/updated by `resolve_or_create`'s survivorship logic further inside
`resolvers/base.py` (not fully expanded here — the SQL/ORM boundary pattern
is identical: `ctx.session.add`/`.merge`/`.flush`, committed once per row by
the calling worker thread).

**Note on `self.silver.fetch(...)`**: Mastering's *input* is Snowflake
(`EDGARTOOLS_SILVER`, read via the injected `silver` reader —
`_require_silver_reader`, `cli.py:943`), not Postgres. Postgres is
Mastering's **output** only (the `mdm_entity`/`mdm_company`/.../`mdm_source_ref`/
`mdm_change_log` rows). This mirrors CLAUDE.md's own "MDM's own silver reader
is always Snowflake" note.

### 2b. BackpropagateIdsToSilver: warehouse `backfill-mdm-entity-ids` — Postgres READ only, Snowflake write

This state's command lives in `edgar_warehouse/`, not `edgar_warehouse/mdm/`
— it's the warehouse CLI, invoked as a plain (non-`mdm`) subcommand.

```
run_mdm_entity_backfill_sweep(context, run_id)        edgar_warehouse/mdm_entity_backfill.py:303
  └─ mdm_url = os.environ.get("MDM_DATABASE_URL", "")  mdm_entity_backfill.py:322  # required, WarehouseRuntimeError if empty
  └─ engine = get_engine(mdm_url)                       mdm_entity_backfill.py:332  # edgar_warehouse.mdm.database.get_engine, explicit url
  └─ connection = connect_with_qmark_paramstyle(...)     mdm_entity_backfill.py:344  # Snowflake connector, for silver READ
  └─ with Session(engine) as session:                    mdm_entity_backfill.py:347
       └─ backfill_pending_rows(connection, session, landing_export)
                                                          mdm_entity_backfill.py:264
            └─ per table spec: _fetch_pending_rows_batches(connection, spec)
                                                          mdm_entity_backfill.py:211  # Snowflake SELECT * WHERE mdm_entity_id IS NULL
            └─ _lookup_entity_ids(session, entity_type=..., source_system=..., source_ids=[...])
                                                          mdm_entity_backfill.py:171
                 └─ session.execute(                      mdm_entity_backfill.py:188
                        select(MdmSourceRef.source_id, MdmSourceRef.entity_id)
                          .join(MdmEntity, MdmEntity.entity_id == MdmSourceRef.entity_id)
                          .where(MdmSourceRef.source_system == source_system)
                          .where(MdmSourceRef.source_id.in_(chunk))
                          .where(MdmEntity.entity_type == entity_type)
                    )                                                                  # <-- SQL/ORM boundary: SELECT against Postgres mdm_source_ref/mdm_entity
            └─ landing_export.record(spec.table, resolved_rows)  mdm_entity_backfill.py:297  # buffers full rows for Snowflake re-emission
  └─ write_landing_export(landing_export, context.silver_landing_export_root, ...)
                                                          mdm_entity_backfill.py:356  # writes back to Snowflake silver landing (Snowpipe path), NOT Postgres
```

This state never writes to Postgres — it is a pure Postgres **read** (bulk
`MdmSourceRef` lookup) that resolves already-Mastered `entity_id`s and
re-emits complete rows to Snowflake so silver picks up the `mdm_entity_id`
column. Its own module docstring is explicit about this being "deliberately
read-only against MDM" (`mdm_entity_backfill.py:6`).

### 2c. Infer Relationships: `mdm infer-relationships` → `graph.py` — Postgres-only, no Snowflake

```
_handle_backfill_relationships(args)                   cli.py:2373
  └─ session = _session()                                cli.py:2379
  └─ silver, _rc = _open_snowflake_silver_reader(...)     cli.py:2389    # optional; only for Phase 1 issuer repair
  └─ (Phase 1, if silver available) pipeline.backfill_security_issuers()
                                                           cli.py:2396-2397
  └─ (Phase 2) backfill_relationship_instances(session, limit=args.limit, run_id=run_id)
                                                           cli.py:2400 → graph.py:442
       └─ registry = GraphRegistry.load(session)           graph.py:457       # SELECT mdm_entity_type_definition, mdm_relationship_type
       └─ existing = {... for r in session.scalars(select(MdmRelationshipInstance))}
                                                           graph.py:463       # SELECT mdm_relationship_instance (full scan, dedup key)
       └─ sync_engine = GraphSyncEngine.build(session, run_id=run_id)
                                                           graph.py:465
       └─ for fund in session.scalars(select(MdmFund).where(adviser_entity_id IS NOT NULL)):
                                                           graph.py:473-476
            └─ sync_engine.ensure_relationship("MANAGES_FUND", ...)  graph.py:482
                 └─ self.session.add(MdmRelationshipInstance(...))   graph.py:331   # <-- SQL/ORM boundary: INSERT
                 └─ self.session.flush()  (or deferred batch flush)  graph.py:338
       └─ for sec in session.scalars(select(MdmSecurity).where(issuer_entity_id IS NOT NULL)):
                                                           graph.py:493-496
            └─ sync_engine.ensure_relationship("ISSUED_BY", ...)     graph.py:502
       └─ session.commit()                                graph.py:512       # <-- durable write, single commit for the whole pass
```

`graph.py`'s own module docstring (`graph.py:1-6`) states the split
explicitly: "Writes mdm_relationship_instance rows (the Postgres mirror)
which are then exported to Snowflake NEO4J_GRAPH_MIGRATION via
SnowflakeGraphSyncExecutor. The Neo4j bolt driver and AuraDB are no longer
used." This state (Infer Relationships) is entirely inside that first half —
it never imports `snowflake_graph.py` or touches a Snowflake connection.

### 2d. Publish: `mdm publish` → `export.py`'s `MDMExporter` — Postgres READ + Postgres write-back (`exported_at`), Snowflake write (separate connector)

```
_handle_export(args)                                    cli.py:2500
  └─ writer = _build_snowflake_writer()                   cli.py:2505 → 2525   # SnowflakeConnectorWriter.from_env(), EDGARTOOLS_GOLD domain tables
  └─ mirror_writer = _build_snowflake_mirror_writer()      cli.py:2506 → 2531   # separate SnowflakeConnectorWriter targeting schema="MDM"
  └─ exporter = MDMExporter(session=_session(), writer=writer, mirror_writer=mirror_writer)
                                                            cli.py:2507
  └─ exporter.export_all_pending(since=..., entity_type=..., batch_size=...)
                                                            cli.py:2509 → export.py:351
       └─ loop: exporter.export_pending(...)                export.py:369 → export.py:309
            └─ pending = session.scalars(select(MdmChangeLog).where(exported_at IS NULL)...)
                                                            export.py:311-318   # <-- SQL/ORM boundary: SELECT Postgres mdm_change_log
            └─ domain_rows = session.scalars(select(model).where(entity_id.in_(entity_ids)))
                                                            export.py:332-334   # <-- SELECT Postgres domain table (mdm_company, etc.)
            └─ self.writer.upsert(sf_table, payload)         export.py:336      # Snowflake MERGE, via SnowflakeConnectorWriter.upsert (export.py:224-283)
            └─ (if mirror_writer) self._export_mirror(pending) export.py:339 → export.py:375
                 └─ mirror_writer.upsert("MDM_ENTITY", ...)   export.py:391     # Snowflake MDM schema mirror
                 └─ mirror_writer.upsert("MDM_CHANGE_LOG", ...) export.py:392-394
            └─ session.execute(update(MdmChangeLog).where(change_id.in_(...)).values(exported_at=now))
                                                            export.py:343-347   # <-- SQL/ORM boundary: UPDATE Postgres mdm_change_log
            └─ session.commit()                              export.py:348
  └─ exporter.export_all_pending_relationships(...)          cli.py:2514 → export.py:437
       └─ (per batch) export_pending_relationships             export.py:396
            └─ pending = session.scalars(select(MdmRelationshipInstance).where(graph_synced_at IS NULL)...)
                                                            export.py:407-412
            └─ mirror_writer.upsert("MDM_RELATIONSHIP_INSTANCE", payload, key="instance_id")
                                                            export.py:425       # Snowflake MDM schema mirror
            └─ session.execute(update(MdmRelationshipInstance)....values(graph_synced_at=now))
                                                            export.py:429-433   # <-- SQL/ORM boundary: UPDATE Postgres mdm_relationship_instance
            └─ session.commit()                              export.py:434
  └─ exporter.export_active_relationship_endpoints(...)      cli.py:2519       # seals endpoint entities into mirror (Ticket 20)
  └─ exporter.sync_reference_tables()                        cli.py:2520       # mdm_entity_type_definition / mdm_relationship_type → Snowflake mirror
```

`SnowflakeConnectorWriter.upsert` (`export.py:224-283`) is the actual
Snowflake SQL/ORM boundary for this stage: it creates a temp table
(`cursor.execute(CREATE TEMPORARY TABLE ...)`, `export.py:269`),
`cursor.executemany(...)` (`export.py:270`) to bulk-load rows into it, then
`cursor.execute(merge_sql)` (`export.py:283`) to MERGE into the real target
table. This is `snowflake-connector-python`, a completely separate connection
object from the SQLAlchemy Postgres `session` used above — Publish is the
one stage that genuinely touches **both** databases in the same process
run, reading+writing Postgres and writing Snowflake in the same call.

### 2e. Publish Relationships: `mdm publish-relationships` → `snowflake_graph.py`'s `SnowflakeGraphSyncExecutor` — Snowflake ONLY, no Postgres import

```
_handle_sync_graph(args)                                cli.py:1863
  └─ SnowflakeGraphSyncExecutor.from_env()                  cli.py:1870 → snowflake_graph.py:233
  └─ .sync(config)                                          cli.py:1870 → snowflake_graph.py:237
       └─ cursor = self.connection.cursor()                  snowflake_graph.py:262   # snowflake-connector-python cursor
       └─ cursor.execute(...)                                 snowflake_graph.py:301   # generates/runs MERGE-style SQL reading the
                                                                                          # Snowflake MDM schema mirror (written by
                                                                                          # export.py's mirror_writer in the Publish
                                                                                          # state) and writing NEO4J_GRAPH_MIGRATION
                                                                                          # node/edge tables
```

`snowflake_graph.py` imports only `edgar_warehouse.mdm.export.SnowflakeConnectionSettings`
(`snowflake_graph.py:10`) — no `edgar_warehouse.mdm.database`, no
`sqlalchemy.orm.Session`, confirmed by grepping the file (no `psycopg`,
no SQLAlchemy `Session` import anywhere in `snowflake_graph.py`). **This is
the exact point in the call graph where the "two modules" split CLAUDE.md
describes actually happens**: `graph.py` (§2c) never imports
`snowflake_graph.py`, and `snowflake_graph.py` never imports `graph.py` or
`database.py`. The only thing connecting them is that Publish (§2d) reads
what Infer Relationships (§2c) wrote to Postgres and re-materializes it into
the Snowflake MDM mirror that Publish Relationships then reads from — there
is no direct Python call from the relationship-inference code into the
Snowflake-sync code; they're bridged entirely through the Publish stage's
Postgres→Snowflake copy.

### 2f. Reconcile: `mdm reconcile` → `snowflake_graph.py`'s `SnowflakeGraphVerifier` — Snowflake ONLY

```
_handle_verify_graph(args)                              cli.py:2216
  └─ settings = SnowflakeConnectionSettings.from_env()      cli.py:2229    # export.py
  └─ connection = settings.connect()                        cli.py:2230    # snowflake-connector-python connection, NOT Postgres
  └─ SnowflakeGraphVerifier(connection, default_database=...).verify(config)
                                                            cli.py:2232-2251 → snowflake_graph.py:353
       └─ cursor = self.connection.cursor()                  snowflake_graph.py:367
       └─ (parity SQL against MDM mirror + NEO4J_GRAPH_MIGRATION tables,
           plus Native App checks: compute pool, GRAPH_INFO, BFS, WCC)
  └─ (if not --skip-review-publish) _publish_graph_review(connection, settings, args, result)
                                                            cli.py:2253 → cli.py:2172
                                                                            # writes result payload into Snowflake MDM_GRAPH_REVIEW
                                                                            # schema (graph_review_publish.py) -- also Snowflake-only
```

Reconcile, like Publish Relationships, never opens a Postgres connection —
`_handle_verify_graph`'s only connection is `settings.connect()`
(Snowflake). This matches CLAUDE.md's own "reconcile is validation-only"
framing and the fact it's wired with a non-fatal `Catch` in the state
machine (§2, table note above): a Postgres outage would not even be a
possible cause of Reconcile failure, since it never touches Postgres.

### Summary: where the Postgres/Snowflake split actually falls

| Stage | Postgres | Snowflake |
|---|---|---|
| Mastering | write (entities, source refs, change log) | read (silver input only) |
| BackpropagateIdsToSilver | read only (`MdmSourceRef` lookup) | write (silver landing re-emission) |
| Infer Relationships | write (`mdm_relationship_instance`) | none |
| Publish | read + write (`mdm_change_log.exported_at`, `mdm_relationship_instance.graph_synced_at`) | write (`EDGARTOOLS_GOLD` domain tables + `MDM` schema mirror) |
| Publish Relationships | none | read (MDM mirror) + write (`NEO4J_GRAPH_MIGRATION`) |
| Reconcile | none | read (parity checks) + write (`MDM_GRAPH_REVIEW`) |

Only **Mastering** and **Infer Relationships** ever construct a
`edgar_warehouse.mdm.database.get_engine()`/SQLAlchemy `Session` against
`MDM_DATABASE_URL` for a *write*. **Publish** is the sole stage that opens
both a Postgres session and a Snowflake connector connection in the same
process. BackpropagateIdsToSilver opens a Postgres session for reads only.
Publish Relationships and Reconcile never construct a Postgres connection at
all — confirmed by absence of any `edgar_warehouse.mdm.database` or
`sqlalchemy` import in `snowflake_graph.py`.

## 3. Read-side call sequence: FastAPI routers

### 3a. App assembly and per-request session

```
edgar-warehouse mdm api                                cli.py:2446 (_handle_api)
  └─ uvicorn.run("edgar_warehouse.mdm.api.main:app", ...)   cli.py:2449
       └─ edgar_warehouse/mdm/api/main.py: app = create_app()   main.py:56
            └─ create_app()                                       main.py:26
                 └─ api.include_router(entities.router)            main.py:30
                 └─ api.include_router(companies.router)            main.py:31
                 └─ api.include_router(advisers.router)              main.py:32
                 └─ api.include_router(persons.router)                 main.py:33
                 └─ api.include_router(securities.router)               main.py:34
                 └─ api.include_router(funds.router)                     main.py:35
                 └─ api.include_router(graph.router)                      main.py:36
                 └─ api.include_router(stewardship.router)                 main.py:37
                 └─ api.include_router(rules.router)                        main.py:38
                 └─ api.include_router(export.router)                        main.py:39
```

Every route handler declares `session: Session = Depends(get_db)`. `get_db`
(`edgar_warehouse/mdm/api/deps.py:14-22`):

```python
_engine = None

def get_db() -> Iterator[Session]:
    global _engine
    if _engine is None:
        _engine = get_engine()
    s = get_session(_engine)
    try:
        yield s
    finally:
        s.close()
```

This is a **process-lifetime singleton Engine** (constructed once, on the
first request, cached in the module-global `_engine`) with a **fresh
`Session` per request** (created and closed inside the FastAPI dependency
generator, one per HTTP request). This is the standard FastAPI
per-request-session pattern; it shares the engine's connection pool
(`MDM_DB_POOL_SIZE`/`MDM_DB_MAX_OVERFLOW`, §1) across every concurrent
request the API process serves.

### 3b. `graph.py` router — reads live from the Postgres mirror

`edgar_warehouse/mdm/api/routers/graph.py:1-4`'s own module docstring: "All
graph data is read from the PostgreSQL mirror (mdm_relationship_instance).
Graph analytics run via the Snowflake-hosted Neo4j Graph Analytics native
app." (matching CLAUDE.md's own framing verbatim).

Traced example — `GET /graph/neighborhood/{entity_id}`:

```
neighborhood(entity_id, depth, rel_types, as_of, ...)   graph.py:167
  └─ registry = _registry(session)                        graph.py:176 → graph.py:31
       └─ GraphRegistry.load(session)                       graph.py:32 → graph.py:41-66
            └─ session.scalars(select(MdmEntityTypeDefinition)...)   graph.py:43-47  # SELECT
            └─ session.scalars(select(MdmRelationshipType)...)        graph.py:52-54  # SELECT
  └─ canonical_of, discarded_by_canonical = _canonical_groups(session)
                                                            graph.py:182 → graph.py:155
       └─ _merge_lineage(session)                            graph.py:157 → graph.py:123
            └─ session.scalars(select(MdmChangeLog).where(changed_fields IS NOT NULL))
                                                            graph.py:130-132  # SELECT
  └─ (per depth level) session.scalars(select(MdmRelationshipInstance).where(...))
                                                            graph.py:211-255  # <-- SQL/ORM boundary: SELECT mdm_relationship_instance,
                                                                                # filtered on source/target_entity_id IN, quarantined,
                                                                                # is_active or as_of_date temporal bounds
  └─ (per new node) _node_for(session, registry, ep, ...)   graph.py:279 → graph.py:105
       └─ session.get(MdmEntity, canonical_entity_id)        graph.py:111       # SELECT by PK
  └─ return Neighborhood(nodes=..., edges=...)
```

No write anywhere in this router — every endpoint (`list_relationship_types`,
`get_relationship_type`, `neighborhood`, `traversal`, `shared_insiders`,
`sync_status`) issues only `session.scalar`/`session.scalars`/`session.get`
reads. `traversal` (`graph.py:299-311`) is a thin POST wrapper that just
calls the same `neighborhood()` function directly (not through HTTP) with
the request body's fields unpacked.

### 3c. `companies.py` router — read-only, joins domain to relationship tables

`GET /companies/{cik}/insiders` (`companies.py:35-67`) is representative:

```
get_insiders(cik, as_of, session)                       companies.py:35
  └─ company = _company_by_cik(session, cik)               companies.py:41 → companies.py:23
       └─ session.scalar(select(MdmCompany).where(MdmCompany.cik == cik))
                                                            companies.py:24         # SELECT
  └─ rt = session.scalar(select(MdmRelationshipType).where(rel_type_name == "IS_INSIDER"))
                                                            companies.py:42-44        # SELECT
  └─ edges = session.scalars(select(MdmRelationshipInstance).where(rel_type_id==..., target_entity_id==company.entity_id, is_active==True)[, effective_from/to bounds])
                                                            companies.py:47-60         # SELECT
  └─ persons = session.scalars(select(MdmPerson).where(entity_id.in_(person_ids)))
                                                            companies.py:64-66         # SELECT
```

Entirely read-only; all three of `get_company`/`get_insiders`/`get_advisers`/
`get_securities` follow the identical shape (one lookup, one filtered
`select`, no writes).

### 3d. `entities.py` router — read-only registry lookups, no cross-DB call

`GET /entities`/`GET /entities/{id}`/`POST /entities/resolve`
(`entities.py:24-115`) are all `session.get`/`session.scalar`/`session.scalars`
reads against `MdmEntity`/`MdmSourceRef`/domain tables — no writes, no
Snowflake connection anywhere in this file.

### 3e. `stewardship.py` and `rules.py` — the write-capable routers

Unlike the read-only routers above, `stewardship.py` (`POST
/stewardship/reviews/{id}/accept`, `/reject`, `/entities/{id}/quarantine`,
`/unquarantine`, `/entities/merge`, `PATCH /entities/{id}`) and `rules.py`
(`POST`/`PATCH`/`DELETE` on `/source-priority`, `/field-survivorship`,
`/match-thresholds`, `/normalization`) are the API's only mutating surface.
`patch_entity` (`stewardship.py:77-114`) shows the pattern directly inline:

```python
setattr(row, payload.field, payload.value)
session.add(db.MdmChangeLog(...))
session.commit()
```
(`stewardship.py:104-113`)

The other four stewardship mutations (`accept_review`, `reject_review`,
`quarantine`, `merge_entities`) delegate to `edgar_warehouse/mdm/stewardship.py`
module-level functions (`sw.accept_review`, etc., imported at
`api/routers/stewardship.py:10`), each of which calls `session.commit()`
itself (`stewardship.py:82`, `93`, `109`, `126`, `148` — the module, not the
router). `rules.py`'s five mutation endpoints all follow the identical
`session.add(row); session.commit()` (or bare `session.commit()` for a
`PATCH`/`DELETE` that only mutated attributes already tracked by the
session) shape at `rules.py:58-59`, `72`, `109-110`, `123`, `154-155`, `168`,
`201-202`, `215`, `225`.

## 4. Migrations: `mdm migrate`

```
_handle_migrate(args)                                   cli.py:1645
  └─ (args.model == "legacy", the default)
  └─ from edgar_warehouse.mdm.migrations.runtime import migrate
                                                            cli.py:1647
  └─ migrate(get_engine(), seed=args.seed)                 cli.py:1653 → migrations/runtime.py:375
       └─ dialect = engine.dialect.name                     migrations/runtime.py:377
       └─ (postgresql branch) sequential SQL-file application:
            _apply_sql_file(engine, "001_initial_schema.sql")      migrations/runtime.py:383
            _apply_sql_file(engine, "003_tracking_status_index.sql") migrations/runtime.py:384
            _apply_sql_file(engine, "004_company_ticker_parent.sql")  migrations/runtime.py:385
            (Python-seed entity types before 005, since 005's INSERTs FK to them)
                                                                       migrations/runtime.py:387-390
            _apply_sql_file(engine, "005_fundamentals_relationships.sql")  migrations/runtime.py:391
            ... through "022_relationship_derivation_checkpoint_cursor.sql" migrations/runtime.py:392-408
            _apply_acquisition_ledger_migration(engine)      migrations/runtime.py:399  # 013, owner-role-gated (see below)
            _apply_source_registry_migration(engine)         migrations/runtime.py:400  # 014, owner-role-gated
            _apply_source_evidence_conflict_migration(engine) migrations/runtime.py:401 # 015, owner-role-gated
            _apply_exclusion_and_evidence_import_migration(engine) migrations/runtime.py:403 # 017, owner-role-gated
            _apply_source_fetch_validators_migration(engine) migrations/runtime.py:404  # 018, owner-role-gated
       └─ (if seed) with Session(engine) as session: seed_defaults(session); session.commit()
                                                            migrations/runtime.py:410-413
```

**The actual applier** is `_apply_sql_file` (`migrations/runtime.py:670-673`):

```python
def _apply_sql_file(engine: Engine, filename: str) -> None:
    with engine.begin() as conn:
        for statement in _sql_file_statements(filename):
            conn.execute(text(statement))
```

Each migration file is read from disk (`Path(__file__).with_name(filename)`,
`migrations/runtime.py:679`), split into individual statements by a
hand-written SQL splitter (`_split_sql`, `migrations/runtime.py:692-741` —
handles single-quoted strings, `--` line comments, and `$$...$$`
dollar-quoted PL/pgSQL blocks so semicolons inside a function body don't
split it), and each statement is run via plain `conn.execute(text(statement))`
inside one `engine.begin()` transaction per file (auto-commit on successful
exit of the `with` block, rollback on exception — this is SQLAlchemy Core's
`Engine.begin()` context manager, not the ORM `Session`).

**Five migrations (013-015, 017-018) are self-managing and privilege-gated**
rather than unconditionally applied — `_apply_acquisition_ledger_migration`
(`migrations/runtime.py:417-450`) is the representative shape: it checks
`to_regclass(...)` to see if already installed; if installed, it checks
`pg_has_role(current_user, '<owner_role>', 'MEMBER')` and, if the connecting
role (typically the ordinary `application` DSN) lacks that membership, logs
a structured `mdm_migration_privileged_rerun_skipped` event
(`_log_privileged_rerun_skipped`, `migrations/runtime.py:18-44`) and returns
`False` — a **silent no-op**, by design, because these DDL statements need
`CREATEROLE`/schema-owner privileges the runtime `application` role
deliberately never holds. A first install runs `SET LOCAL ROLE
edgartools_acquisition_owner` (or the migration's specific owner role) inside
the same transaction as the role-provisioning statement
(`migrations/runtime.py:446-449`) so the remaining DDL executes as that
owner. This is exactly the mechanism CLAUDE.md's own comment in this file
references ("MDM Postgres migration-011 schema drift" incident,
`migrations/runtime.py:26-30`) — a rerun by the wrong role can silently
report "success" while touching nothing, which is why the event is now
logged explicitly.

**"Clean MDM" fork**: `_handle_migrate` branches to a completely different
function, `edgar_warehouse.mdm.clean.store.migrate_clean`, when
`--model clean` is passed (`cli.py:1649-1651`). Not traced further here per
the task's read-only/hands-off instruction for `.scratch/clean-mdm/` and its
associated source — flagged only so a future reader knows the branch point
exists and where it is (`cli.py:1649-1651`).

**Row-count / connectivity check commands** (`mdm counts`, `mdm
check-connectivity`) are thin wrappers around `migrations/runtime.py`'s own
`count_tables(engine)` (`migrations/runtime.py:646-656`, one `SELECT
COUNT(*) FROM <table>` per table in the hardcoded `MDM_TABLES` list,
`migrations/runtime.py:46-66`) and `check_connectivity(engine)`
(`migrations/runtime.py:634-643`, `SELECT 1` plus a
`sqlalchemy.inspect(engine).get_table_names()` diff against the same list).

**CLAUDE.md's own operational note** ("`mdm migrate` does not run
automatically on deploy") is corroborated structurally here: nothing in
`cli.py`, `database.py`, or `migrations/runtime.py` invokes `migrate()` as a
side effect of any other command — every other handler that needs the schema
already present simply queries/writes against it and fails with a normal
SQLAlchemy error (missing table/column) if migrations were never run.

## 5. Session/transaction discipline

CLAUDE.md's hard-won-rules claim — "SQLAlchemy's `Session` never
auto-commits, and a logged 'succeeded' is not evidence of a durable write" —
holds up against every write path traced above. Every mutating code path
this research found ends in an **explicit** `session.commit()`:

| Call site | Commit location |
|---|---|
| Mastering, per-row worker session | `pipeline.py:1006` (`worker_session.commit()`) |
| Mastering, `run_persons`'s own outer session | `pipeline.py:1502` (`self.session.commit()`) |
| Infer Relationships (`backfill_relationship_instances`) | `graph.py:512` |
| Publish (`export_pending`) | `export.py:348` |
| Publish (`export_pending_relationships`) | `export.py:434` |
| API `PATCH /stewardship/entities/{id}` | `stewardship.py:113` (router file) |
| API stewardship mutations (`accept_review`/`reject_review`/`quarantine`/`unquarantine`/`merge_entities`) | `edgar_warehouse/mdm/stewardship.py:82,93,109,126,148` (module, not router) |
| API `rules.py` mutations (5 endpoints) | `rules.py:59,72,110,123,155,168,202,215,225` |
| Migrations (`seed_defaults`) | `migrations/runtime.py:412-413` |

**No implicit/autocommit path was found.** `get_engine()` does not pass
`isolation_level="AUTOCOMMIT"` or any autocommit kwarg (`database.py:131-148`);
`Session(engine)` (`get_session`, `database.py:151-152`) is a plain
SQLAlchemy 2.x `Session`, which defaults to `autocommit=False`-equivalent
behavior (begin-on-first-use, commit only on explicit `.commit()`).

**Where this is actually exercised (and where it bit the team once)**: the
per-row worker-thread pattern in `pipeline.py`'s `_resolve_row` closures
(`run_companies`: `pipeline.py:990-1025`; the same shape repeats in
`run_advisers`, `run_securities`, `run_persons`, `run_relationships`) commits
**once per resolved row**, on its own private `worker_session` — not once
per batch and not on the pipeline's own `self.session`. The `except
Exception: worker_session.rollback(); raise` block
(`pipeline.py:1012-1023`) carries an explicit incident citation in its own
comment: a failed `flush()` leaves a Session unusable
(`PendingRollbackError` on every subsequent query) until rolled back, and an
earlier version of this code lacked the rollback — "which is how one
CheckViolation turned into ~5 hours of cascading failures in
daily-incremental-ticket17-verify-1789514832 (2026-09-16)." This is
independent, primary-source confirmation (found directly in the code
comment, not inferred) of exactly the failure mode CLAUDE.md's rule is
warning about, and shows the fix (explicit `rollback()` before `finally:
close()`) actually landed in the code.

**Batch/outer-loop commits vs. per-row commits**: not every write path
commits per row. `backfill_relationship_instances` (§2c) and
`export_pending`/`export_pending_relationships` (§2d) each do their whole
bounded batch (up to `limit`/`batch_size` rows) inside a single Session with
one `commit()` at the end of the function — a mid-batch exception there
would roll back the *entire* batch's inserts/updates (no partial commit),
unlike Mastering's per-row-commit shape where a single row's failure only
loses that one row's work. Neither pattern is universal across this
codebase; the choice tracks whether the caller wants row-level idempotent
retry (Mastering, via concurrent independent workers) or batch-level
atomicity (relationship backfill, export).

**Rollback outside the worker-thread pattern**: `graph.py`'s
`GraphSyncEngine.ensure_relationship` does not itself catch exceptions or
roll back — a failure partway through `backfill_relationship_instances`'s
loop (§2c) propagates up through `_handle_backfill_relationships` uncaught;
the `session.close()` in that handler's `finally` block
(`cli.py:2379-2403`, via the same session lifecycle every non-worker-thread
handler uses) closes the session without an explicit rollback, but
SQLAlchemy's own `Session.close()` implicitly rolls back any
not-yet-committed transaction — no separate explicit `.rollback()` call was
needed or written there, since (unlike the per-row worker pattern) there is
no code between the exception and the session teardown that would try to
reuse the now-broken session for another query.
