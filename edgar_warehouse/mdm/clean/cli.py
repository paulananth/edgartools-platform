"""MDM command handlers: preparation, queries and publication requests."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import text

from .connections import engine_from_env


def prepare_clean_company(args) -> int:
    from .company_prepare import write_company_manifest

    report = write_company_manifest(
        capture=args.capture,
        documents=args.documents,
        population=args.population,
        catalog=args.catalog,
        capture_run=args.capture_run,
        catalog_run=args.catalog_run,
        observed_at=args.observed_at,
        name_census=args.name_census,
        output=args.output,
        as_of=args.as_of,
        revision=args.revision,
        force=args.all,
    )
    print(json.dumps(report, sort_keys=True))
    return 0


def prepare_capture(args) -> int:
    from .target_manifest import run_arguments, write_manifest

    facts, run_files = run_arguments(args.fact, args.file)
    report = write_manifest(
        facts=facts,
        run_files=run_files,
        source=args.source,
        target=args.target,
        capture=args.capture,
        documents=args.documents,
        capture_run=args.capture_run,
        output=args.output,
        as_of=args.as_of,
        revision=args.revision,
        force=args.all,
    )
    print(json.dumps(report, sort_keys=True))
    return 0


def name_census(args) -> int:
    from .name_frequency import write_name_frequency

    report = write_name_frequency(
        capture=args.capture,
        population=args.population,
        gleif_reading={"uri": Path(args.gleif_reading).resolve().as_uri(), "sha256": args.gleif_reading_sha256},
        gleif_metadata=args.gleif_metadata,
        output=args.output,
        cascade=args.cascade,
        catalog=args.catalog,
    )
    print(json.dumps(report, sort_keys=True))
    return 0


def _print_mdm_report(read) -> int:
    """Run one read on the MDM database as the application role and print it."""
    mdm = engine_from_env("MDM_DATABASE_URL")
    try:
        with mdm.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
            report = read(conn)
    finally:
        mdm.dispose()
    print(json.dumps(report, sort_keys=True))
    return 0


def check_connectivity(args) -> int:
    def report(conn):
        from sqlalchemy import func, select

        adapter = _inspection_adapter(conn)
        return {
            "sql": conn.scalar(text("SELECT 1")) == 1,
            "migrations": conn.scalar(
                select(func.count()).select_from(adapter.tables["migration"])
            ),
        }

    return _print_mdm_report(report)


def _inspection_adapter(conn):
    from .record_reads import for_connection

    return for_connection(conn).adapter


def counts(args) -> int:
    def report(conn):
        result = _inspection_adapter(conn).count_types(
            ("entity", "relationship", "review"), connection=conn
        )
        return {kind: count for kind, count in result.items() if kind == "entity" or count}

    return _print_mdm_report(report)


def force_publish(args) -> int:
    """Force publish (ticket 22): write the current snapshot for one consumer as
    forced pages (no master data changes), then the input
    manifest of a publish target with one unit a page, for `rules run`. The
    same --run-id gives the same pages, so a stopped command is run again."""
    from uuid import UUID, uuid4

    from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts

    run_id = str(UUID(args.run_id)) if args.run_id else str(uuid4())
    mdm = engine_from_env("MDM_DATABASE_URL")
    pages, after = [], {"object_type": "", "object_id": ""}
    try:
        from .store import Store
        from .forced_publication import page as forced_page

        selected = Store(mdm)
        while after is not None:
            page = forced_page(selected,args.consumer,run_id,len(pages)+1,after,args.page_size)
            pages.append(page)
            after = page["next"]
    finally:
        mdm.dispose()
    store = Artifacts()
    root = Path(args.output).resolve().as_uri()
    units = [{"keys": {"batch_id": page["batch_id"], "consumer": args.consumer},
              # A page as MDM holds it; whether this call wrote it is not part of it.
              "input": store.put(f"{root}/pages", {"version": 1, "forced": True,
                                                   **{k: page[k] for k in ("batch_id", "generation", "records")}}),
              "output": f"{root}/published/{n}.json", "cursor": {}}
             for n, page in enumerate(pages, 1)]
    manifest = store.put(root, {"version": 2, "steps": {args.step: units}})
    print(json.dumps({"run_id": run_id, "consumer": args.consumer, "forced": True, "pages": len(pages),
                      "records": sum(page["records"] for page in pages), "manifest": manifest}, sort_keys=True))
    return 0


def rebuild_name_index(args) -> int:
    from .master_search import rebuild

    engine = engine_from_env("MDM_DATABASE_URL", restricted=False)
    try:
        report = rebuild(engine, limit=args.limit, page_size=args.page_size, restart=args.restart)
    finally:
        engine.dispose()
    print(json.dumps(report, sort_keys=True))
    return 0


def rebuild_detail_lookup(args) -> int:
    from .detail_lookups import rebuild

    engine = engine_from_env("MDM_DATABASE_URL", restricted=False)
    try:
        report = rebuild(engine, limit=args.limit, page_size=args.page_size, restart=args.restart)
    finally:
        engine.dispose()
    print(json.dumps(report, sort_keys=True))
    return 0
