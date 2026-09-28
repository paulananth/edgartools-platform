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


def _handle(args):
    from sqlalchemy import create_engine, text
    from .db import Rules, get_engine, migrate
    if args.rules_command == "init":
        owner = create_engine(os.environ["RULES_MIGRATION_DATABASE_URL"])
        try:
            result = migrate(owner, agent_role=args.agent_role)
        finally:
            owner.dispose()
    else:
        rules_engine = get_engine()
        rules = Rules(rules_engine)
        try:
            if args.rules_command == "migrate":
                method = rules.from_files if args.to_db else rules.to_files
                result = method(Path(args.root), args.version)
                print(json.dumps(result, default=str, indent=2, sort_keys=True))
                return 0
            name = args.source or args.pipeline or args.merge
            kind = "source" if args.source else "pipeline" if args.pipeline else "merge"
            operation = args.rules_command
            if operation == "save":
                result = rules.save(kind, name, args.version, files.load(Path(args.file)))
            elif operation == "status":
                with rules_engine.connect() as conn:
                    result = [dict(row) for row in conn.execute(text("SELECT kind,name,version,digest,status,proved_at,approved_by,approved_at FROM rules.rule_version WHERE kind=:k AND name=:n ORDER BY created_at"), {"k": kind, "n": name}).mappings()]
            elif operation == "export":
                rules.to_file(kind, name, args.version, Path(args.output))
                result = {"path": args.output, "digest": rules.version(kind, name, args.version)["digest"]}
            elif operation == "approve":
                rules.approve(kind, name, args.version, args.digest)
                result = {"approved": args.digest}
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
                from edgar_warehouse.bookkeeping.clean.cli import configured_bookkeeping
                from edgar_warehouse.change_journal.store import ChangeJournal, get_engine as journal_engine
                from edgar_warehouse.bookkeeping.clean.runner import run
                from edgar_warehouse.bookkeeping.clean.config import Blocked

                book = configured_bookkeeping()
                ledger_engine = journal_engine()
                try:
                    if args.resume_run_id:
                        existing = book._run(args.resume_run_id)["submission"]
                        if ((existing["kind"], existing["name"], existing["target"]) != (kind, name, args.target)
                                or args.feed is not None and args.feed != existing["scope"].get("feed")):
                            raise Blocked("Resume selection differs from the original run")
                        if args.input_manifest or args.input_sha256:
                            raise Blocked("Resume uses its frozen input reference; do not supply new inputs")
                        book.resume(args.resume_run_id)
                        run_id = args.resume_run_id
                    else:
                        if not args.input_manifest or not args.input_sha256:
                            raise Blocked("Submission requires an exact input manifest URI and hash")
                        ref = rules.resolve(kind, name, root=os.environ["BOOKKEEPING_MANIFEST_ROOT"], artifacts=book.artifacts)
                        run_id = book.start(rules_ref=ref, inputs_ref={"uri": args.input_manifest, "sha256": args.input_sha256},
                                            target=args.target, scope={"kind": kind, "name": name, "source": name,
                                                                     "feed": args.feed, "target": args.target} if args.feed else
                                                                    {"kind": kind, "name": name, "target": args.target})
                    # Preserve machine-readable result stdout, and make the
                    # durable root recoverable if execution/acknowledgement fails.
                    print(f"Bookkeeping run: {run_id}", file=sys.stderr, flush=True)
                    result = run(book, run_id, ChangeJournal(ledger_engine), limit=args.limit)
                finally:
                    ledger_engine.dispose()
                    book.close()
        finally:
            rules_engine.dispose()
    print(json.dumps(result, default=str, indent=2, sort_keys=True))
    return 3 if isinstance(result, dict) and result.get("run", {}).get("state") in ("waiting", "blocked") else 0


def register(subparsers):
    parser = subparsers.add_parser("rules", help="Versioned Rules files, approvals and configured run submission")
    commands = parser.add_subparsers(dest="rules_command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--agent-role", default="rules_agent")
    init.set_defaults(handler=_handle)
    migration = commands.add_parser("migrate")
    direction = migration.add_mutually_exclusive_group(required=True)
    direction.add_argument("--to-db", action="store_true")
    direction.add_argument("--to-files", action="store_true")
    migration.add_argument("--root", required=True)
    migration.add_argument("--version", required=True)
    migration.set_defaults(handler=_handle)
    for operation in ("save", "status", "export", "record-proof", "approve", "activate", "run"):
        command = commands.add_parser(operation)
        _selection(command)
        if operation not in ("status", "run"):
            command.add_argument("--version", required=True)
        if operation == "save":
            command.add_argument("file")
        elif operation == "export":
            command.add_argument("--output", required=True)
        elif operation == "approve":
            command.add_argument("--digest", required=True)
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
