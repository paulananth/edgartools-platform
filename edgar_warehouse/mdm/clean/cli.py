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
    from .capture_prepare import write_capture_manifest

    report = write_capture_manifest(
        source=args.source,
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
        with mdm.connect() as conn:
            report = read(conn)
    finally:
        mdm.dispose()
    print(json.dumps(report, sort_keys=True))
    return 0


def check_connectivity(args) -> int:
    return _print_mdm_report(lambda conn: {
        "sql": conn.scalar(text("SELECT 1")) == 1,
        "migrations": conn.scalar(text("SELECT count(*) FROM mdm.migration")),
    })


def counts(args) -> int:
    return _print_mdm_report(lambda conn: dict(conn.execute(text(
        "SELECT 'entity',count(*) FROM mdm.current_entity "
        "UNION ALL SELECT object_type,count(*) FROM mdm.current_record "
        "WHERE object_type<>'entity' GROUP BY object_type"
    )).all()))


def force_publish(args) -> int:
    """Force publish (ticket 22): write the current snapshot for one consumer as
    forced pages (`mdm.force_publish`, no master data changes), then the input
    manifest of a publish target with one unit a page, for `rules run`. The
    same --run-id gives the same pages, so a stopped command is run again."""
    from uuid import UUID, uuid4

    from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts

    run_id = str(UUID(args.run_id)) if args.run_id else str(uuid4())
    mdm = engine_from_env("MDM_DATABASE_URL")
    pages, after = [], {"object_type": "", "object_id": ""}
    try:
        while after is not None:
            with mdm.begin() as conn:
                page = conn.scalar(text(
                    "SELECT mdm.force_publish(:c,CAST(:r AS uuid),:p,:t,:i,:n)"),
                    {"c": args.consumer, "r": run_id, "p": len(pages) + 1, "t": after["object_type"],
                     "i": after["object_id"], "n": args.page_size})
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
