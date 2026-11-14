"""The rules commands: check the files, register them in MDM, submit a run."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from . import files


def _selection(parser):
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--source")
    choice.add_argument("--pipeline")
    choice.add_argument("--merge")


def _handle(args):
    from . import frozen
    from .db import Rules, get_engine, migrate

    if args.rules_command in ("init", "migrate"):
        owner = get_engine(os.environ["RULES_MIGRATION_DATABASE_URL"])
        try:
            result = migrate(owner, agent_role=args.agent_role)
        finally:
            owner.dispose()
    elif args.rules_command == "entity-types":
        result = [{"source": name, "dataset_code": code, "origin": found["origin"],
                   "entity_types": ",".join(found["types"]), "rule_id": found.get("rule_id")}
                  for kind, name, path in files.documents() if kind == "source"
                  for code, found in sorted(files.entity_types(files.load_source(path)).items())]
    elif args.rules_command == "register":
        # The store owner's connection: the runtime login cannot add to MDM's registry.
        owner = get_engine(os.environ["MDM_REGISTRATION_DATABASE_URL"])
        try:
            with owner.begin() as conn:
                result = frozen.register(conn, args.source or None, Path(args.root))
        finally:
            owner.dispose()
    else:
        name = args.source or args.pipeline or args.merge
        kind = "source" if args.source else "pipeline" if args.pipeline else "merge"
        rules_engine = get_engine()
        try:
            if args.rules_command == "status":
                result = Rules(rules_engine).history(kind, name)
            else:
                result = _run(args, kind, name, Rules(rules_engine))
        finally:
            rules_engine.dispose()
    print(json.dumps(result, default=str, indent=2, sort_keys=True))
    return 3 if isinstance(result, dict) and result.get("run", {}).get("state") in ("waiting", "blocked") else 0


def _run(args, kind: str, name: str, rules) -> dict:
    """Submit only: freeze the rules files, record their digest and start the run. Workers in their own
    processes do the work (`python -m edgar_warehouse.workers`); Bookkeeping runs no worker code."""
    from edgar_warehouse.bookkeeping.clean.cli import configured_bookkeeping
    from edgar_warehouse.bookkeeping.clean.config import Blocked

    from . import frozen

    book = configured_bookkeeping()
    try:
        if args.resume_run_id:
            existing = book.status(args.resume_run_id, limit=1)["run"]["submission"]
            if ((existing["kind"], existing["name"], existing["target"]) != (kind, name, args.target)
                    or args.feed is not None and args.feed != existing["scope"].get("feed")):
                raise Blocked("Resume selection differs from the original run")
            if args.input_manifest or args.input_sha256:
                raise Blocked("Resume uses its frozen input reference; do not supply new inputs")
            return book.resume(args.resume_run_id)
        if not args.input_manifest or not args.input_sha256:
            raise Blocked("Submission requires an exact input manifest URI and hash")
        export = frozen.export(kind, name, Path(args.root))
        rules.record(export)
        ref = book.artifacts.put(os.environ["BOOKKEEPING_MANIFEST_ROOT"], export)
        from edgar_warehouse.rules.local import staged_inputs

        # A target marked `local` has its source read and combine steps run here first.
        inputs = staged_inputs(book.artifacts, export["body"], args.target,
                               {"uri": args.input_manifest, "sha256": args.input_sha256})
        run_id = book.start(rules_ref=ref, inputs_ref=inputs,
                            target=args.target, scope={"kind": kind, "name": name, "target": args.target,
                                                     **({"source": name} if kind == "source" else {}),
                                                     **({"feed": args.feed} if args.feed else {})})
        print(f"Bookkeeping run: {run_id}", file=sys.stderr, flush=True)
        return book.status(run_id)
    finally:
        book.close()


def _mapdoc(args):
    """The Mapping Documents, from the rules files alone (no database). Plain
    text, not JSON: stewards read it, and `diff` goes into a pull request."""
    from . import mapdoc

    found = mapdoc.documents(Path(args.root))
    if args.only:
        found = {path: item for path, item in found.items() if item[0] == args.only}
        if not found:
            print(f"No source, kind, pipeline or relationships named {args.only} has a Mapping Document", file=sys.stderr)
            return 2
    if args.action == "write":
        try:
            files.writable(args.root)
        except ValueError as error:
            print(error, file=sys.stderr)
            return 2
        for path, (_, sheets, sources) in found.items():
            mapdoc.write(path, sheets, sources)
            print(path)
        return 0
    changed = {path: mapdoc.differences(path, sheets) for path, (_, sheets, _) in found.items()}
    for path, lines in changed.items():
        for line in lines:
            print(f"{path}: {line}")
    # `diff` reports what a steward changed; `check` fails on it (CI).
    return 1 if args.action == "check" and any(changed.values()) else 0


def _check(args):
    """Each rules file checked as a run checks it, offline, so an agent that
    edited one as text never writes Python to see whether it still holds."""
    results = files.check(args.source or None, Path(args.root))
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0 if all(value == "ok" for value in results.values()) else 1


def _results(args) -> dict:
    from edgar_warehouse.silver_writer import results

    path = getattr(args, "results", None)
    run_id = getattr(args, "bookkeeping_run", None)
    if path and run_id:
        raise ValueError("Use either --results or --bookkeeping-run, not both")
    if run_id:
        from edgar_warehouse.bookkeeping.clean.quality import catalog_results
        return catalog_results(_bookkeeping_quality(run_id))
    return results.load(path) if path else {}


def _bookkeeping_quality(run_id: str) -> dict:
    from edgar_warehouse.bookkeeping.clean.cli import configured_bookkeeping
    from edgar_warehouse.bookkeeping.clean.quality import aggregate

    bookkeeping = configured_bookkeeping()
    try:
        return aggregate(bookkeeping, run_id)
    finally:
        bookkeeping.close()


def _bookkeeping_status(run_id: str) -> dict:
    """Read bounded Bookkeeping execution evidence without exposing its errors."""
    from edgar_warehouse.bookkeeping.clean.cli import configured_bookkeeping

    bookkeeping = configured_bookkeeping()
    try:
        return bookkeeping.status(run_id, limit=1000)
    finally:
        bookkeeping.close()


def _catalog_run_status(args, plan: dict, counts: dict, catalog) -> int:
    if getattr(args, "results", None) is not None or getattr(args, "draft_terms", False):
        report = {"ok": False, "status": "failed", "failed_stage": "configuration",
                  "plan": {"status": "ready", "counts": counts},
                  "publish": {"status": "not_run"}, "readback": {"status": "not_run"},
                  "cause": "Pipeline status does not accept quality result or draft-term options",
                  "next_action": "Run status with only --bookkeeping-run and --root."}
        report["summary"] = "FAILED: Pipeline status accepts only a Bookkeeping run and Rules root."
        return _catalog_output(report, failure_code=2)
    run_id = getattr(args, "bookkeeping_run", None)
    if not run_id:
        report = {"ok": False, "status": "failed", "failed_stage": "configuration",
                  "plan": {"status": "ready", "counts": counts},
                  "publish": {"status": "not_run"}, "readback": {"status": "not_run"},
                  "cause": "A Bookkeeping run is required",
                  "next_action": "Supply --bookkeeping-run with the target run UUID."}
        report["summary"] = "FAILED: Pipeline status requires `--bookkeeping-run`."
        return _catalog_output(report, failure_code=2)
    try:
        snapshot = _bookkeeping_status(run_id)
        update = catalog.pipeline_status_from_bookkeeping(plan, Path(args.root), snapshot)
    except (catalog.CatalogError, ValueError, KeyError, OSError) as error:
        report = {"ok": False, "status": "failed", "failed_stage": "bookkeeping",
                  "plan": {"status": "ready", "counts": counts},
                  "publish": {"status": "not_run"}, "readback": {"status": "not_run"},
                  "cause": ("Bookkeeping run has no unique planned target Pipeline"
                            if isinstance(error, catalog.CatalogError) else
                            "Bookkeeping run status is unavailable"),
                  "next_action": "Check the Bookkeeping run and its configured source/target, then retry."}
        report["summary"] = "FAILED: Bookkeeping run status could not be mapped to a target Pipeline."
        return _catalog_output(report)
    except Exception as error:
        from sqlalchemy.exc import SQLAlchemyError
        from edgar_warehouse.bookkeeping.clean.config import Blocked
        if not isinstance(error, (SQLAlchemyError, Blocked)):
            raise
        report = {"ok": False, "status": "failed", "failed_stage": "bookkeeping",
                  "plan": {"status": "ready", "counts": counts},
                  "publish": {"status": "not_run"}, "readback": {"status": "not_run"},
                  "cause": "Bookkeeping could not provide verified run status",
                  "next_action": "Check Bookkeeping database access and the run's retained status."}
        report["summary"] = "FAILED: Bookkeeping run status is unavailable."
        return _catalog_output(report)

    url, token = os.environ.get("OPENMETADATA_URL"), os.environ.get("OPENMETADATA_TOKEN")
    endpoint = catalog.endpoint_identity(url)
    if not url or not token:
        report = {"ok": False, "status": "failed", "failed_stage": "configuration",
                  "endpoint": endpoint, "plan": {"status": "ready", "counts": counts},
                  "publish": {"status": "not_run"}, "readback": {"status": "not_run"},
                  "cause": "OpenMetadata endpoint or bot token is not configured",
                  "next_action": "Set OPENMETADATA_URL and OPENMETADATA_TOKEN, then rerun status."}
        report["summary"] = (f"FAILED: Pipeline status configuration for {endpoint or 'OpenMetadata'}; "
                             "set OPENMETADATA_URL and OPENMETADATA_TOKEN.")
        return _catalog_output(report, failure_code=2)
    completed_writes = 0
    write_attempts = 0
    try:
        api_call = catalog.connect(url, token)

        def call(method, path, body=None, params=None):
            nonlocal completed_writes, write_attempts
            is_write = method in ("POST", "PUT", "PATCH", "DELETE")
            if is_write:
                write_attempts += 1
            answer = api_call(method, path, body, params)
            if is_write:
                completed_writes += 1
            return answer

        catalog.publish_pipeline_status(plan, call, update)
    except catalog.CatalogError as error:
        cause = _catalog_cause(error, catalog)
        missing_pipeline = "target Pipeline is not published" in str(error)
        rejected = re.search(r"HTTP 4\d\d\b", cause) is not None
        status = "failed" if missing_pipeline or rejected or write_attempts == 0 else "partial"
        report = {"ok": False, "status": status,
                  "failed_stage": "precondition" if missing_pipeline else "publish",
                  "endpoint": endpoint, "plan": {"status": "ready", "counts": counts},
                  "publish": {"status": "rejected" if rejected else
                              "partial" if write_attempts else "not_run",
                              "completed_write_requests": completed_writes},
                  "readback": {"status": "failed" if "readback" in str(error) else "not_run"},
                  "cause": cause,
                  "next_action": ("Run `rules catalog publish` to create or migrate the target Pipeline, then retry."
                                  if missing_pipeline else
                                  "Check the OpenMetadata token and Pipeline status permission, then retry."
                                  if rejected else
                                  "Run the read-only catalog check before retrying status publication.")}
        report["summary"] = f"{status.upper()}: Pipeline status was not confirmed at {endpoint}: {cause}."
        return _catalog_output(report)

    status = update["status"]
    failed_tasks = sum(task["executionStatus"] == "Failed" for task in status.get("taskStatus") or [])
    report = {"ok": True, "status": "confirmed", "endpoint": endpoint,
              "plan": {"status": "ready", "counts": counts},
              "pipeline_status": {"execution_status": status["executionStatus"],
                                  "failed_tasks": failed_tasks},
              "publish": {"status": "sent", "completed_write_requests": 1},
              "readback": {"status": "matched"},
              "next_action": None}
    report["summary"] = (f"CONFIRMED: target Pipeline status read back from {endpoint} as "
                         f"{status['executionStatus']}; {failed_tasks} failed task(s) recorded.")
    return _catalog_output(report)


def _catalog_cause(error, catalog) -> str:
    """Summarize API failures without returning response bodies or endpoint data."""
    if not isinstance(error, catalog.CatalogError):
        return type(error).__name__
    message = str(error)
    if "Bookkeeping target Pipeline is not published" in message:
        return "The target Pipeline is not published yet"
    if "Bookkeeping Pipeline status readback did not match" in message:
        return "OpenMetadata Pipeline status readback did not match"
    if "quality result readback mismatch after send" in message:
        return "OpenMetadata quality result readback mismatch after send"
    if "quality result readback mismatch" in message:
        return "OpenMetadata quality result readback mismatch after bounded correction"
    status = re.search(r"\bHTTP (\d{3})\b", message)
    if status:
        return f"OpenMetadata returned HTTP {status.group(1)}"
    if "did not answer" in message:
        return "OpenMetadata endpoint did not answer"
    if "invalid JSON" in message:
        return "OpenMetadata returned an invalid response"
    if "named" in message or "identity" in message:
        return "OpenMetadata returned an unexpected object identity"
    return "OpenMetadata request failed"


def _catalog_counts_text(counts: dict) -> str:
    lineage = counts["lineage"]
    return (f"{counts['domains']} domains, {counts['glossaries']} glossaries, "
            f"{counts['glossary_terms']} terms, {counts['assets']} assets, "
            f"{counts['quality_definitions']} quality definitions, {counts['quality_cases']} quality cases, "
            f"{counts['products']} products, "
            f"{counts['pipelines']} pipelines in {counts['pipeline_services']} PipelineServices, "
            f"{sum(lineage.values())} lineage edges")


def _catalog_removed_text(removed: dict) -> str:
    counts = [f"{count} {kind}" for kind, count in sorted(removed.items()) if count]
    total = sum(removed.values())
    return f"{total} owned objects" + (f" ({', '.join(counts)})" if counts else "")


def _catalog_output(report: dict, *, failure_code: int = 1) -> int:
    print(report["summary"], file=sys.stderr)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else failure_code


def _catalog(args):
    """Plan, reconcile and read back the catalog with stage-specific outcomes."""
    from . import catalog

    try:
        plan = catalog.plan(Path(args.root))
    except (catalog.CatalogError, ValueError) as error:
        cause = _catalog_cause(error, catalog)
        report = {"ok": False, "status": "failed", "failed_stage": "plan", "cause": cause,
                  "next_action": "Correct the Rules configuration and rerun `rules catalog plan`.",
                  "summary": f"FAILED: catalog plan: {cause}. Correct the Rules configuration and retry."}
        return _catalog_output(report)

    counts = catalog.plan_counts(plan)
    if args.action == "plan":
        print(f"PENDING: catalog plan only; {_catalog_counts_text(counts)}. Nothing was sent.", file=sys.stderr)
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0

    if args.action == "status":
        return _catalog_run_status(args, plan, counts, catalog)

    quality_summary = None
    try:
        if getattr(args, "bookkeeping_run", None):
            quality_summary = _bookkeeping_quality(args.bookkeeping_run)
            from edgar_warehouse.bookkeeping.clean.quality import catalog_results
            results = catalog_results(quality_summary)
        else:
            results = _results(args)
    except (ValueError, KeyError, OSError) as error:
        report = {"ok": False, "status": "failed", "failed_stage": "quality_evidence",
                  "plan": {"status": "ready", "counts": counts},
                  "publish": {"status": "not_run"}, "readback": {"status": "not_run"},
                  "cause": "Bookkeeping quality evidence is incomplete or invalid",
                  "next_action": "Complete and verify the Bookkeeping run, then retry with --bookkeeping-run."}
        report["summary"] = (f"FAILED: quality evidence unavailable ({type(error).__name__}); "
                             "complete and verify the Bookkeeping run.")
        return _catalog_output(report)
    except Exception as error:
        from sqlalchemy.exc import SQLAlchemyError
        if not isinstance(error, SQLAlchemyError):
            raise
        report = {"ok": False, "status": "failed", "failed_stage": "quality_evidence",
                  "plan": {"status": "ready", "counts": counts},
                  "publish": {"status": "not_run"}, "readback": {"status": "not_run"},
                  "cause": "Bookkeeping could not be read",
                  "next_action": "Check BOOKKEEPING_DATABASE_URL access, then retry with --bookkeeping-run."}
        report["summary"] = "FAILED: cannot read Bookkeeping quality evidence. Check Bookkeeping access and retry."
        return _catalog_output(report)

    if quality_summary and quality_summary.get("status") == "unknown" and not results:
        report = {"ok": False, "status": "pending", "failed_stage": "quality_evidence",
                  "plan": {"status": "ready", "counts": counts},
                  "publish": {"status": "not_run"}, "readback": {"status": "not_run"},
                  "quality": quality_summary,
                  "cause": "No verified per-check counts are available for this incomplete run",
                  "next_action": "Complete or reconcile work and retry; no zero-count result was fabricated."}
        report["summary"] = (f"PENDING: Bookkeeping run {quality_summary.get('run_id')} is incomplete/unknown; "
                              "there are no verified check counts to publish. No zero-count result was fabricated.")
        return _catalog_output(report)

    url, token = os.environ.get("OPENMETADATA_URL"), os.environ.get("OPENMETADATA_TOKEN")
    endpoint = catalog.endpoint_identity(url)
    if not url or not token:
        report = {"ok": False, "status": "failed", "failed_stage": "configuration",
                  "endpoint": endpoint, "plan": {"status": "ready", "counts": counts},
                  "publish": {"status": "not_run"}, "readback": {"status": "not_run"},
                  "cause": "OpenMetadata endpoint or bot token is not configured",
                  "next_action": "Set OPENMETADATA_URL and OPENMETADATA_TOKEN, then rerun the command."}
        report["summary"] = (f"FAILED: catalog configuration for {endpoint or 'OpenMetadata'}; "
                             "set OPENMETADATA_URL and OPENMETADATA_TOKEN, then retry.")
        return _catalog_output(report, failure_code=2)

    try:
        api_call = catalog.connect(url, token)
    except (catalog.CatalogError, ValueError) as error:
        cause = _catalog_cause(error, catalog)
        report = {"ok": False, "status": "failed", "failed_stage": "connect", "endpoint": endpoint,
                  "plan": {"status": "ready", "counts": counts}, "publish": {"status": "not_run"},
                  "readback": {"status": "not_run"}, "cause": cause,
                  "next_action": "Check the OpenMetadata endpoint and bot token, then retry."}
        report["summary"] = f"FAILED: cannot connect to {endpoint}: {cause}. Check endpoint and token."
        return _catalog_output(report)

    completed_writes = 0

    def call(method, path, body=None, params=None):
        nonlocal completed_writes
        answer = api_call(method, path, body, params)
        if method in ("POST", "PUT", "PATCH", "DELETE"):
            completed_writes += 1
        return answer

    if args.action == "check":
        try:
            result = catalog.verify(plan, call, results=results)
        except catalog.CatalogError as error:
            cause = _catalog_cause(error, catalog)
            report = {"ok": False, "status": "partial", "failed_stage": "readback", "endpoint": endpoint,
                      "plan": {"status": "ready", "counts": counts}, "publish": {"status": "not_run"},
                      "readback": {"status": "failed", "ok": False}, "cause": cause,
                      "next_action": "Restore API access and rerun the read-only `rules catalog check`."}
            report["summary"] = f"PARTIAL: readback from {endpoint} failed: {cause}. Retry the read-only check."
            return _catalog_output(report)
        report = {"ok": result["ok"], "status": "confirmed" if result["ok"] else "partial",
                  "endpoint": endpoint, "plan": {"status": "ready", "counts": counts},
                  **({"quality": quality_summary} if quality_summary else {}),
                  "publish": {"status": "not_run"},
                  "readback": {"status": "matched" if result["ok"] else "drift",
                               **result,
                               "scope": ["database service", "databases", "schemas", "tables",
                                         "per-source PipelineServices", "Pipelines and tasks",
                                         "table-to-table lineage", "pipeline-to-table lineage"]},
                  "next_action": None if result["ok"] else
                      "Review readback differences, then rerun `rules catalog publish` and `check`."}
        quality_label = ("quality evidence is incomplete/unknown; verified counts only" if quality_summary and
                         quality_summary.get("status") == "unknown" else None)
        report["summary"] = (f"CONFIRMED: readback from {endpoint} matches its checked scope; "
                             f"{_catalog_counts_text(counts)}; "
                             f"{result.get('quality_results_confirmed', 0)} per-load quality result(s) confirmed"
                             f"{'; ' + quality_label if quality_label else ''}." if result["ok"] else
                             f"PARTIAL: readback from {endpoint} found {len(result['differences'])} difference(s). "
                             "Review the differences and reconcile the catalog.")
        return _catalog_output(report)

    try:
        sent = catalog.publish(plan, call, draft_terms=args.draft_terms, results=results)
    except catalog.CatalogError as error:
        cause = _catalog_cause(error, catalog)
        rejected = re.search(r"HTTP 4\d\d\b", cause) is not None and completed_writes == 0
        quality_readback_failed = "quality result readback mismatch" in cause
        status = "failed" if rejected else "partial"
        failed_stage = "readback" if quality_readback_failed else "publish"
        report = {"ok": False, "status": status, "failed_stage": failed_stage, "endpoint": endpoint,
                  "plan": {"status": "ready", "counts": counts},
                  "publish": {"status": "failed" if rejected else "partial", "completed_write_requests": completed_writes,
                              "created": None, "updated": None,
                              "created_updated_counts": "unavailable", "removed": None,
                              "removed_counts_status": "unavailable"},
                  "readback": {"status": "failed" if quality_readback_failed else "not_run",
                               **({"ok": False} if quality_readback_failed else {})}, "cause": cause,
                  "next_action": ("Inspect the exact quality-result timestamp with the read-only `rules catalog check`; "
                                  "do not resend until the held result is understood."
                                  if quality_readback_failed else
                                  "Correct the rejected request or bot permissions, then retry publication."
                                  if rejected else
                                  "Run the read-only `rules catalog check` before retrying publication.")}
        report["summary"] = (f"PARTIAL: quality result readback from {endpoint} did not confirm the one permitted "
                              f"correction: {cause}. Inspect with read-only check before retrying."
                              if quality_readback_failed else
                              f"FAILED: publish to {endpoint} was rejected: {cause}. Correct the request and retry."
                              if rejected else
                              f"PARTIAL: publish to {endpoint} stopped after {completed_writes} confirmed write "
                              f"request(s): {cause}. Check readback before retrying.")
        return _catalog_output(report)

    try:
        verified = catalog.verify(plan, call, results=results)
    except catalog.CatalogError as error:
        cause = _catalog_cause(error, catalog)
        report = {"ok": False, "status": "partial", "failed_stage": "readback", "endpoint": endpoint,
                  "plan": {"status": "ready", "counts": counts},
                  "publish": {"status": "sent", "completed_write_requests": completed_writes,
                              "created": None, "updated": None,
                              "created_updated_counts": "unavailable", "removed": sent["removed"],
                              "removed_counts_status": "available",
                              "response": sent},
                  "readback": {"status": "failed", "ok": False}, "cause": cause,
                  "next_action": "Restore API access and rerun the read-only `rules catalog check`."}
        report["summary"] = f"PARTIAL: publish reached {endpoint}, but readback failed: {cause}. Retry check."
        return _catalog_output(report)

    report = {"ok": verified["ok"], "status": "confirmed" if verified["ok"] else "partial",
              "endpoint": endpoint, "plan": {"status": "ready", "counts": counts},
              **({"quality": quality_summary} if quality_summary else {}),
              "publish": {"status": "sent", "completed_write_requests": completed_writes,
                          "quality_results_sent": sent.get("quality_results_sent", 0),
                          "created": None, "updated": None,
                          "created_updated_counts": "unavailable", "removed": sent["removed"],
                          "removed_counts_status": "available",
                          "response": sent},
              "readback": {"status": "matched" if verified["ok"] else "drift",
                           **verified,
                           "scope": ["database service", "databases", "schemas", "tables",
                                     "per-source PipelineServices", "Pipelines and tasks",
                                     "table-to-table lineage", "pipeline-to-table lineage"]},
              "next_action": None if verified["ok"] else
                  "Review readback differences, then rerun `rules catalog publish` and `check`."}
    if verified["ok"]:
        report["summary"] = (f"CONFIRMED: publish and checked readback scope matched at {endpoint}; "
                             f"{_catalog_counts_text(counts)}. Removed {_catalog_removed_text(sent['removed'])}; "
                             f"{verified.get('quality_results_confirmed', 0)} per-load quality result(s) confirmed; "
                             f"{'quality evidence is incomplete/unknown with verified counts only; ' if quality_summary and quality_summary.get('status') == 'unknown' else ''}"
                             "created/updated counts unavailable.")
    else:
        report["failed_stage"] = "readback"
        report["summary"] = (f"PARTIAL: publish reached {endpoint}, but readback found "
                             f"{len(verified['differences'])} difference(s). Removed "
                             f"{_catalog_removed_text(sent['removed'])}; review and reconcile.")
    return _catalog_output(report)


def register(subparsers):
    parser = subparsers.add_parser("rules", help="The rules files: check them, register them in MDM, submit a run")
    commands = parser.add_subparsers(dest="rules_command", required=True)
    from .sequence import register as register_sequence
    register_sequence(commands)
    # init and migrate both create the Rules Database's table: "migrate" means a schema upgrade in every store.
    for name, help_text in (("init", "Create the Rules Database's table (first time; rerunning changes nothing)"),
                            ("migrate", "Upgrade the Rules Database's table after a schema change")):
        schema = commands.add_parser(name, help=help_text)
        schema.add_argument("--agent-role", default="rules_agent")
        schema.set_defaults(handler=_handle)
    registering = commands.add_parser("register", help="Register the merge rules and the sources' Dataset Contracts "
                                      "in MDM from the files (rerunning changes nothing)")
    registering.add_argument("--source", action="append", help="Only this source (repeatable); default every source")
    registering.add_argument("--root", default=str(files.ROOT))
    registering.set_defaults(handler=_handle)
    mapping = commands.add_parser(
        "mapdoc", help="The Mapping Documents (spreadsheets) generated from the rules files")
    mapping.add_argument("action", choices=("write", "diff", "check"),
                         help="write: regenerate, keeping Notes; diff: what a workbook changed; "
                              "check: fail when any workbook differs from its rules")
    mapping.add_argument("--only", help="One source, kind, standalone pipeline or relationships")
    mapping.add_argument("--root", default=str(files.ROOT))
    mapping.set_defaults(handler=_mapdoc)
    catalog = commands.add_parser(
        "catalog", help="The Data Catalog (OpenMetadata), published one way from the rules files")
    catalog.add_argument("action", choices=("plan", "publish", "check", "status"),
                         help="plan: preview; publish: reconcile; check: read back; status: publish a Bookkeeping run status")
    catalog.add_argument("--root", default=str(files.ROOT))
    catalog.add_argument("--results", type=Path,
                         help="publish, check: silver quality results JSON file of a direct silver run")
    catalog.add_argument("--bookkeeping-run",
                         help="publish/check: verified quality receipts; status: update the target Pipeline from this run")
    catalog.add_argument("--draft-terms", action="store_true",
                         help="publish: set every glossary term to Draft (a steward approves it); "
                              "by default the server's own status is left alone")
    catalog.set_defaults(handler=_catalog)
    check = commands.add_parser("check", help="Check each rules file, offline: it loads, its targets and "
                                "acquisition hold, the merge rules pass. A run makes the same check")
    check.add_argument("--source", action="append", help="Only this source (repeatable); default every file")
    check.add_argument("--root", default=str(files.ROOT))
    check.set_defaults(handler=_check)
    entity_types = commands.add_parser("entity-types", help="Where each source's records get their entity type")
    entity_types.set_defaults(handler=_handle)
    for operation in ("status", "run"):
        command = commands.add_parser(operation)
        _selection(command)
        if operation == "run":
            command.add_argument("--target", required=True)
            command.add_argument("--root", default=str(files.ROOT), help="The rules folder the run freezes")
            command.add_argument("--feed", help="Exact acquisition feed identity")
            command.add_argument("--input-manifest")
            command.add_argument("--input-sha256")
            command.add_argument("--resume-run-id")
            command.add_argument("--limit", type=int, default=100)
        command.set_defaults(handler=_handle)
