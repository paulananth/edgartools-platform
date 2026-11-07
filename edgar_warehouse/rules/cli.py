"""Single Rules lifecycle and submission entry point for configured pipelines."""
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


def _approve_rule(args):
    """One merge rule, switched on in the files on the operator's words. It
    only edits `merge/policy.yaml`: the merge version that carries it is a
    separate save, test run and approval (the Approve steps, skills/data-onboarding/APPROVE.md)."""
    from datetime import datetime, timezone

    if args.merge != "platform" or args.version or args.evidence or args.overrule:
        print("--rule switches one rule of the platform merge rules on: use --merge platform, without "
              "--version, --evidence or --overrule (a rule short of its bar is not overruled here)", file=sys.stderr)
        return 2
    at = args.at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        if args.proof:  # an identifier matching rule, on its Proving Run report
            entry = files.approve_identifier_rule(args.rule, proof=Path(args.proof), reason=args.reason or "",
                                                  by=args.by, words=args.words, at=at,
                                                  root=files.writable(args.root))
        else:
            entry = files.approve_rule(args.rule, by=args.by, words=args.words, at=at,
                                       root=files.writable(args.root))
    except ValueError as error:  # the refusal and its reason, not a traceback
        print(f"Not approved: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"switched_on": entry["rule_id"], "rule_version": entry["rule_version"],
                      "approved_by": args.by, "approved_at": at, "file": str(Path(args.root) / "merge" / "policy.yaml")},
                     indent=2, sort_keys=True))
    return 0


def _test(args):
    """A test run of one of a source's targets on local stores (ticket 14)."""
    from .proving import TestRunError, run
    from edgar_warehouse.mdm.target_manifest import run_arguments

    try:
        facts, run_files = run_arguments(args.fact, args.file)
        result = run(source=args.source, capture=args.capture, documents=args.documents, capture_run=args.capture_run,
                     as_of=args.as_of, stores=args.stores, out=args.out, minutes=args.minutes,
                     target=args.target, version=args.version, facts=facts, run_files=run_files)
    except (TestRunError, ValueError) as error:
        print(f"Test run stopped: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"report": str(args.out), "passed": result["passed"], "recorded": result.get("recorded"),
                      "second_pass_changed_nothing": result["second_pass_changed_nothing"]}, indent=2))
    return 0 if result["passed"] else 1


def _approvals(args):
    """The approvals kept in git (ticket 193): `check` names the documents with no approval at their digest,
    `write` lists every document at its digest in the operator's words."""
    from . import approvals

    root = Path(args.root)
    try:
        if args.action == "check":
            absent = approvals.missing(root)
            print(json.dumps({"missing": [{"kind": k, "name": n, "digest": d} for k, n, d in absent]}, indent=2))
            return 1 if absent else 0
        entries = approvals.write(root, by=args.by, words=args.words, finalized=args.finalized, at=args.at)
    except (ValueError, OSError) as error:
        print(f"Approvals stopped: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"approvals": len(entries), "file": str(root / approvals.FILE)}, indent=2))
    return 0


def _handle(args):
    from .db import Rules, get_engine, migrate
    if args.rules_command == "approve" and args.rule:
        return _approve_rule(args)
    if args.rules_command in ("init", "migrate"):
        owner = get_engine(os.environ["RULES_MIGRATION_DATABASE_URL"])
        try:
            result = migrate(owner, agent_role=args.agent_role, approver_role=args.approver_role, database_name=args.database_name)
        finally:
            owner.dispose()
    else:
        rules_engine = get_engine()
        rules = Rules(rules_engine)
        try:
            if args.rules_command in ("load", "unload"):
                method = rules.from_files if args.rules_command == "load" else rules.to_files
                root = Path(args.root) if args.rules_command == "load" else files.writable(args.root)
                result = method(root, args.version)
                print(json.dumps(result, default=str, indent=2, sort_keys=True))
                return 0
            if args.rules_command == "pending":
                print(json.dumps(rules.pending(), default=str, indent=2, sort_keys=True))
                return 0
            name = args.source or args.pipeline or args.merge
            kind = "source" if args.source else "pipeline" if args.pipeline else "merge"
            operation = args.rules_command
            if operation == "save":
                path = Path(args.file)
                result = rules.save(kind, name, args.version, files.LAYOUT[kind][0](path))
            elif operation == "status":
                result = rules.history(kind, name)
            elif operation == "export":
                rules.to_file(kind, name, args.version, Path(args.output))
                result = {"path": args.output, "digest": rules.version(kind, name, args.version)["digest"]}
            elif operation == "approve":
                from edgar_warehouse.bookkeeping.clean.config import Blocked

                if not args.version or not (args.evidence or args.finalized):
                    raise Blocked("Approval names the version and the evidence hash `rules pending` showed, "
                                  "or --finalized with the merge that made the rules final")
                row = rules.approve(kind, name, args.version, evidence=args.evidence, by=args.by,
                                    words=args.words, overrule=args.overrule, finalized=args.finalized)
                result = {key: row[key] for key in ("kind", "name", "version", "status", "approved_by", "approved_at",
                                                    "approved_words", "approval_overrule", "approval_evidence")}
            elif operation == "record-proof":
                from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
                from edgar_warehouse.bookkeeping.clean.config import Blocked

                proof = Artifacts().json({"uri": args.proof_uri, "sha256": args.proof_sha256})
                if proof.get("digest") != rules.version(kind, name, args.version)["digest"]:
                    raise Blocked("Proof names a different Rules digest")
                rules.prove(kind, name, args.version, proof)
                result = {"proven": name, "version": args.version, "proof": args.proof_uri}
            elif operation == "activate":
                mdm_owner = get_engine(os.environ["RULES_MDM_ACTIVATION_DATABASE_URL"]) if os.environ.get("RULES_MDM_ACTIVATION_DATABASE_URL") else None
                try:
                    rules.activate(kind, name, args.version, mdm_engine=mdm_owner)
                finally:
                    if mdm_owner is not None:
                        mdm_owner.dispose()
                result = {"active": name, "version": args.version}
            else:
                # Submit only. Workers in their own processes do the work
                # (`python -m edgar_warehouse.workers`); Bookkeeping runs no
                # worker code (mastering to-do 20a).
                from edgar_warehouse.bookkeeping.clean.cli import configured_bookkeeping
                from edgar_warehouse.bookkeeping.clean.config import Blocked

                book = configured_bookkeeping()
                try:
                    if args.resume_run_id:
                        existing = book.status(args.resume_run_id, limit=1)["run"]["submission"]
                        if ((existing["kind"], existing["name"], existing["target"]) != (kind, name, args.target)
                                or args.feed is not None and args.feed != existing["scope"].get("feed")):
                            raise Blocked("Resume selection differs from the original run")
                        if args.input_manifest or args.input_sha256:
                            raise Blocked("Resume uses its frozen input reference; do not supply new inputs")
                        result = book.resume(args.resume_run_id)
                    else:
                        if not args.input_manifest or not args.input_sha256:
                            raise Blocked("Submission requires an exact input manifest URI and hash")
                        ref = rules.resolve(kind, name, root=os.environ["BOOKKEEPING_MANIFEST_ROOT"], artifacts=book.artifacts)
                        run_id = book.start(rules_ref=ref, inputs_ref={"uri": args.input_manifest, "sha256": args.input_sha256},
                                            target=args.target, scope={"kind": kind, "name": name, "target": args.target,
                                                                     **({"source": name} if kind == "source" else {}),
                                                                     **({"feed": args.feed} if args.feed else {})})
                        print(f"Bookkeeping run: {run_id}", file=sys.stderr, flush=True)
                        result = book.status(run_id)
                finally:
                    book.close()
        finally:
            rules_engine.dispose()
    print(json.dumps(result, default=str, indent=2, sort_keys=True))
    return 3 if isinstance(result, dict) and result.get("run", {}).get("state") in ("waiting", "blocked") else 0


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
    """Each rules file checked as `rules save` would, offline, so an agent that
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


def _catalog_cause(error, catalog) -> str:
    """Summarize API failures without returning response bodies or endpoint data."""
    if not isinstance(error, catalog.CatalogError):
        return type(error).__name__
    message = str(error)
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
            f"{counts['pipelines']} pipelines, "
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

    quality_summary = None
    try:
        if getattr(args, "bookkeeping_run", None):
            quality_summary = _bookkeeping_quality(args.bookkeeping_run)
            if quality_summary.get("status") == "unknown":
                report = {"ok": False, "status": "pending", "failed_stage": "quality_evidence",
                          "plan": {"status": "ready", "counts": counts},
                          "publish": {"status": "not_run"}, "readback": {"status": "not_run"},
                          "quality": quality_summary,
                          "cause": "Bookkeeping quality evidence is unknown or incomplete",
                          "next_action": "Finish or reconcile the Bookkeeping run, then retry publication."}
                if not quality_summary.get("run_complete"):
                    report["summary"] = (f"PENDING: Bookkeeping run {args.bookkeeping_run} is not complete; "
                                         f"{quality_summary['units_verified']}/{quality_summary['units_expected']} "
                                         f"units verified and {quality_summary['units_unknown']} unknown. "
                                         "Complete run verification before publishing.")
                else:
                    report["summary"] = (f"PENDING: Bookkeeping run {args.bookkeeping_run} has "
                                         f"{quality_summary['units_unknown']} unknown unit(s); "
                                         "complete verification before publishing.")
                return _catalog_output(report)
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
                               "scope": ["database service", "databases", "schemas", "tables", "pipelines",
                                         "table lineage"]},
                  "next_action": None if result["ok"] else
                      "Review readback differences, then rerun `rules catalog publish` and `check`."}
        report["summary"] = (f"CONFIRMED: readback from {endpoint} matches its checked scope; "
                             f"{_catalog_counts_text(counts)}; "
                             f"{result.get('quality_results_confirmed', 0)} per-load quality result(s) confirmed." if result["ok"] else
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
                           "scope": ["database service", "databases", "schemas", "tables", "pipelines",
                                     "table lineage"]},
              "next_action": None if verified["ok"] else
                  "Review readback differences, then rerun `rules catalog publish` and `check`."}
    if verified["ok"]:
        report["summary"] = (f"CONFIRMED: publish and checked readback scope matched at {endpoint}; "
                             f"{_catalog_counts_text(counts)}. Removed {_catalog_removed_text(sent['removed'])}; "
                             f"{verified.get('quality_results_confirmed', 0)} per-load quality result(s) confirmed; "
                             "created/updated counts unavailable.")
    else:
        report["failed_stage"] = "readback"
        report["summary"] = (f"PARTIAL: publish reached {endpoint}, but readback found "
                             f"{len(verified['differences'])} difference(s). Removed "
                             f"{_catalog_removed_text(sent['removed'])}; review and reconcile.")
    return _catalog_output(report)


def register(subparsers):
    parser = subparsers.add_parser("rules", help="Versioned Rules files, approvals and configured run submission")
    commands = parser.add_subparsers(dest="rules_command", required=True)
    from .sequence import register as register_sequence
    register_sequence(commands)
    # init and migrate both create or upgrade the Rules Database schema:
    # "migrate" means a schema upgrade in every store (platform validation,
    # operator 2026-09-30).
    for name, help_text in (("init", "Create the Rules Database schema (first time; rerunning changes nothing)"),
                            ("migrate", "Upgrade the Rules Database schema after a new migration file lands")):
        schema = commands.add_parser(name, help=help_text)
        schema.add_argument("--agent-role", default="rules_agent")
        schema.add_argument("--approver-role", default="rules_approver")
        schema.add_argument("--database-name", default="rules", help="The configured isolated Rules database")
        schema.set_defaults(handler=_handle)
    load = commands.add_parser("load", help="Save every rules file under --root as a version in the Rules Database")
    unload = commands.add_parser("unload", help="Write the Rules Database's versions back to files under --root")
    for command in (load, unload):
        command.add_argument("--root", required=True)
        command.add_argument("--version", required=True)
        command.set_defaults(handler=_handle)
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
    catalog.add_argument("action", choices=("plan", "publish", "check"),
                         help="plan: preview; publish: reconcile OpenMetadata; check: read back metadata and lineage")
    catalog.add_argument("--root", default=str(files.ROOT))
    catalog.add_argument("--results", type=Path,
                         help="publish, check: legacy silver quality results JSON file")
    catalog.add_argument("--bookkeeping-run",
                         help="publish, check: use this completed run's verified per-unit quality receipts")
    catalog.add_argument("--draft-terms", action="store_true",
                         help="publish: set every glossary term to Draft (a steward approves it); "
                              "by default the server's own status is left alone")
    catalog.set_defaults(handler=_catalog)
    test = commands.add_parser(
        "test", help="A source version's test run on local stores, from a capture already made (two passes)")
    test.add_argument("--source", required=True, help="The source's folder name under rules/sources")
    test.add_argument("--capture", required=True, type=Path, help="The capture folder (its receipts.jsonl and bronze/)")
    test.add_argument("--documents", required=True, type=Path, help="A JSON list of the captured documents' keys")
    test.add_argument("--capture-run", required=True, help="The capture's run id")
    test.add_argument("--as-of", required=True, help="The publication's as-of time (ISO 8601)")
    test.add_argument("--stores", required=True, type=Path,
                      help="The local stores' folder, holding worker.env, verifier.env and governance.env")
    test.add_argument("--out", required=True, type=Path, help="Where the counts-only report is written")
    test.add_argument("--minutes", type=float, default=60, help="Stop a pass that runs longer")
    test.add_argument("--target", default="mastering", help="The source's Bookkeeping target (default mastering)")
    test.add_argument("--fact", action="append", help="A run fact the target declares: name=value (repeat)")
    test.add_argument("--file", action="append", help="A run file the target declares: name=path (repeat)")
    test.add_argument("--version", help="Record the run as this saved version's test run, in the Rules Database "
                      "RULES_DATABASE_URL names (the version must be the rules on disk)")
    test.set_defaults(handler=_test)
    check = commands.add_parser("check", help="Check each rules file as `rules save` would, offline: "
                                "it loads, its targets and acquisition hold, the merge rules pass")
    check.add_argument("--source", action="append", help="Only this source (repeatable); default every file")
    check.add_argument("--root", default=str(files.ROOT))
    check.set_defaults(handler=_check)
    approvals = commands.add_parser("approvals", help="The operator's approvals kept in git beside the rules: "
                                    "check which documents lack one, or write them in the operator's words")
    approvals.add_argument("action", choices=["check", "write"])
    approvals.add_argument("--root", default=str(files.ROOT))
    approvals.add_argument("--by", help="write: who approved")
    approvals.add_argument("--words", help="write: their exact words")
    approvals.add_argument("--finalized", help="write: the merge on main that made the rules final")
    approvals.add_argument("--at", help="write: when they said it (YYYY-MM-DD)")
    approvals.set_defaults(handler=lambda args: (_approvals(args) if args.action == "check" or all(
        (args.by, args.words, args.finalized, args.at)) else
        (print("write needs --by, --words, --finalized and --at", file=sys.stderr) or 2)))
    pending = commands.add_parser("pending", help="Versions with a test run and no approval yet: evidence and changes")
    pending.set_defaults(handler=_handle)
    for operation in ("save", "status", "export", "record-proof", "approve", "activate", "run"):
        command = commands.add_parser(operation)
        _selection(command)
        if operation == "approve":
            command.add_argument("--version", help="The version `rules pending` showed (not with --rule)")
        elif operation not in ("status", "run"):
            command.add_argument("--version", required=True)
        if operation == "save":
            command.add_argument("file", help="The document's main file: <source>/source.yaml, "
                                 "<pipeline>/pipeline.yaml or merge/policy.yaml; the files beside it come too")
        elif operation == "export":
            command.add_argument("--output", required=True,
                                 help="The main file to write, as for save; the files beside it are written too")
        elif operation == "approve":
            command.add_argument("--by", required=True, help="Who approved: the operator's or steward's name")
            command.add_argument("--words", required=True, help="Their exact words of approval")
            command.add_argument("--overrule", help="Their reason, when approving a failing test run")
            command.add_argument("--evidence", help="The evidence_hash `rules pending` showed for it")
            command.add_argument("--finalized", help="The merge on main that made these rules final: approves "
                                 "them with no test run (the operator's words are the approval)")
            command.add_argument("--rule", help="Switch one merge rule on, in the files, on its proof")
            command.add_argument("--root", default=str(files.ROOT), help="The rules folder (--rule only)")
            command.add_argument("--proof", help="An identifier matching rule's Proving Run report (--rule only)")
            command.add_argument("--reason", help="With --proof: one line of what the Proving Run showed")
            command.add_argument("--at", help="When the operator gave their words, UTC (YYYY-MM-DDTHH:MM:SSZ); "
                                              "default now (--rule only)")
        elif operation == "record-proof":
            command.add_argument("--proof-uri", required=True)
            command.add_argument("--proof-sha256", required=True)
        elif operation == "run":
            command.add_argument("--target", required=True)
            command.add_argument("--feed", help="Exact acquisition feed identity")
            command.add_argument("--input-manifest")
            command.add_argument("--input-sha256")
            command.add_argument("--resume-run-id")
            command.add_argument("--limit", type=int, default=100)
        command.set_defaults(handler=_handle)
