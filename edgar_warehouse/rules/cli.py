"""Single Rules lifecycle and submission entry point for configured pipelines."""
from __future__ import annotations

import json
import os
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
    at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        entry = files.approve_rule(args.rule, by=args.by, words=args.words, at=at, root=files.writable(args.root))
    except ValueError as error:  # the refusal and its reason, not a traceback
        print(f"Not approved: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"switched_on": entry["rule_id"], "rule_version": entry["rule_version"],
                      "approved_by": args.by, "approved_at": at, "file": str(Path(args.root) / "merge" / "policy.yaml")},
                     indent=2, sort_keys=True))
    return 0


def _handle(args):
    from sqlalchemy import create_engine, text
    from .db import Rules, get_engine, migrate
    if args.rules_command == "approve" and args.rule:
        return _approve_rule(args)
    if args.rules_command in ("init", "migrate"):
        owner = create_engine(os.environ["RULES_MIGRATION_DATABASE_URL"])
        try:
            result = migrate(owner, agent_role=args.agent_role)
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
                with rules_engine.connect() as conn:
                    result = [dict(row) for row in conn.execute(text("SELECT kind,name,version,digest,status,proved_at,approved_by,approved_at,approved_words,approval_overrule FROM rules.rule_version WHERE kind=:k AND name=:n ORDER BY created_at"), {"k": kind, "n": name}).mappings()]
            elif operation == "export":
                rules.to_file(kind, name, args.version, Path(args.output))
                result = {"path": args.output, "digest": rules.version(kind, name, args.version)["digest"]}
            elif operation == "approve":
                from edgar_warehouse.bookkeeping.clean.config import Blocked

                if not args.version or not args.evidence:
                    raise Blocked("Approval names the version and the evidence hash `rules pending` showed")
                row = rules.approve(kind, name, args.version, evidence=args.evidence, by=args.by,
                                    words=args.words, overrule=args.overrule)
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
                mdm_owner = create_engine(os.environ["RULES_MDM_ACTIVATION_DATABASE_URL"]) if os.environ.get("RULES_MDM_ACTIVATION_DATABASE_URL") else None
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
                                            target=args.target, scope={"kind": kind, "name": name, "source": name,
                                                                     "feed": args.feed, "target": args.target} if args.feed else
                                                                    {"kind": kind, "name": name, "target": args.target})
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
            print(f"No source or kind named {args.only} has a Mapping Document", file=sys.stderr)
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


def _catalog(args):
    """The Data Catalog, from the rules files alone: `plan` prints what would
    be published; `publish` makes the OpenMetadata catalog equal to it."""
    from . import catalog

    plan = catalog.plan(Path(args.root))
    if args.action == "plan":
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    url, token = os.environ.get("OPENMETADATA_URL"), os.environ.get("OPENMETADATA_TOKEN")
    if not url or not token:
        print("Set OPENMETADATA_URL and OPENMETADATA_TOKEN (a bot's token: Settings > Bots)", file=sys.stderr)
        return 2
    try:
        result = catalog.publish(plan, catalog.connect(url, token))
    except catalog.CatalogError as error:
        print(f"The catalog was not published: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def register(subparsers):
    parser = subparsers.add_parser("rules", help="Versioned Rules files, approvals and configured run submission")
    commands = parser.add_subparsers(dest="rules_command", required=True)
    # init and migrate both create or upgrade the Rules Database schema:
    # "migrate" means a schema upgrade in every store (platform validation,
    # operator 2026-09-30).
    for name, help_text in (("init", "Create the Rules Database schema (first time; rerunning changes nothing)"),
                            ("migrate", "Upgrade the Rules Database schema after a new migration file lands")):
        schema = commands.add_parser(name, help=help_text)
        schema.add_argument("--agent-role", default="rules_agent")
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
    mapping.add_argument("--only", help="One source (its folder name) or kind")
    mapping.add_argument("--root", default=str(files.ROOT))
    mapping.set_defaults(handler=_mapdoc)
    catalog = commands.add_parser(
        "catalog", help="The Data Catalog (OpenMetadata), published one way from the rules files")
    catalog.add_argument("action", choices=("plan", "publish"),
                         help="plan: print the catalog the rules describe; publish: make OpenMetadata equal to it")
    catalog.add_argument("--root", default=str(files.ROOT))
    catalog.set_defaults(handler=_catalog)
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
            command.add_argument("--rule", help="Switch one merge rule on, in the files, on its proof")
            command.add_argument("--root", default=str(files.ROOT), help="The rules folder (--rule only)")
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
