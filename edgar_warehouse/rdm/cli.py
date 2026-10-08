"""`edgar-warehouse rdm`: migrate the RDM database, import a reference table as a
draft, record the operator's approval, publish, and compare two versions.

Connections come from the environment and are never printed:
RDM_MIGRATION_DATABASE_URL (the schema owner, for init and migrate) and
RDM_DATABASE_URL (the restricted runtime login, for everything else).
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def _handle(args):
    from sqlalchemy import create_engine

    from .database import migrate
    from .store import RDM

    if args.rdm_command in {"init", "migrate"}:
        owner = create_engine(os.environ["RDM_MIGRATION_DATABASE_URL"])
        try:
            result = migrate(owner, runtime_role=args.runtime_role, existing_only=args.rdm_command == "migrate")
        finally:
            owner.dispose()
    else:
        engine = create_engine(os.environ["RDM_DATABASE_URL"])
        rdm = RDM(engine)
        try:
            if args.rdm_command == "import-reference":
                result = import_reference(rdm, args)
            elif args.rdm_command == "draft":
                result = draft_file(rdm, args.file)
            elif args.rdm_command == "list":
                result = rdm.code_sets()
            elif args.rdm_command == "describe":
                result = rdm.describe(args.code_set, args.version)
            elif args.rdm_command == "approve":
                result = rdm.approve(args.code_set, args.version, by=args.by, words=args.words)
            elif args.rdm_command == "publish":
                result = rdm.publish(args.code_set, args.version, out=args.out)
            elif args.rdm_command == "retire":
                result = rdm.retire(args.code_set, args.version)
            elif args.rdm_command == "verify":
                result = rdm.verify(args.code_set, args.version)
            else:
                result = rdm.diff(args.code_set, args.old, args.new)
        finally:
            engine.dispose()
    print(json.dumps(result, default=str, sort_keys=True, indent=2))
    return 0


DRAFT_KEYS = {"code_set", "version", "codes", "created_by", "evidence", "supersedes", "labels", "levels", "crosswalk",
              "usage", "hints"}


def draft_file(rdm, path: Path) -> dict:
    """Draft a version from one JSON or YAML file: {code_set: {code_set, name,
    definition, authority, steward}, version, created_by, evidence, supersedes,
    codes: [{code, label, definition, parent_code, valid_from, valid_to, status,
    invalid_reason}], labels: [{code, language, label, kind, source}],
    levels: [{depth, name, definition}], crosswalk: [{from_code, to_set,
    to_version, to_code, match_type, evidence}], usage: [{store, object,
    field, match, note}], hints: [{kind, text}]}. The shape an agent writes
    from profiling findings."""
    from edgar_warehouse.control_contract import Blocked
    from edgar_warehouse.rules.files import load

    try:
        body = load(Path(path)) if Path(path).suffix in {".yaml", ".yml"} else json.loads(Path(path).read_text())
    except ValueError as exc:
        raise Blocked(f"The draft file is not JSON or YAML: {exc}") from exc
    if not isinstance(body, dict) or set(body) - DRAFT_KEYS or not {"code_set", "version", "codes", "created_by"} <= set(body):
        raise Blocked(f"A draft file holds code_set, version, codes and created_by, and only {sorted(DRAFT_KEYS)}")
    version = rdm.draft(body["code_set"], body["version"], body["codes"],
                        **{k: body[k] for k in DRAFT_KEYS - {"code_set", "version", "codes"} if k in body})
    return {"code_set": version["code_set"], "version": version["version"], "status": version["status"],
            "codes": len(body["codes"])}


def import_reference(rdm, args) -> dict:
    """Draft a reference table (`rules/reference/<name>.yaml`) as a code set
    version, and each crosswalk target RDM holds as its own code set; then
    check the draft rebuilds the table exactly. Once published and pinned, the
    table's YAML is removed (`sec-place-codes`, profiling ticket 02), so the
    folder holds only tables not yet imported."""
    from edgar_warehouse.control_contract import Blocked
    from edgar_warehouse.rules import files

    from . import tables

    table = files.reference(args.name)
    for part in args.key.split(".") if args.key else ():
        table = table[part]
    crosswalks = [tables.Crosswalk.parse(c) for c in args.crosswalk]
    found = tables.draft(table, label=args.label, crosswalks=crosswalks, source=f"rules/reference/{args.name}.yaml")
    if tables.rebuild(tables.as_version(found), label=args.label, crosswalks=crosswalks) != table:
        raise Blocked(f"{args.name} does not rebuild exactly from its draft; nothing was written")
    evidence = {"from": f"rules/reference/{args.name}.yaml", "key": args.key, "codes": len(found["codes"])}
    drafted = {}
    for c in crosswalks:
        if c.to_set in found["targets"] and c.to_set not in drafted:
            target = found["targets"][c.to_set]
            rdm.draft({"code_set": c.to_set, "name": c.to_set, "definition": f"The values of {args.name}'s {c.field}"},
                      c.to_version, target, created_by=args.created_by, evidence={**evidence, "field": c.field},
                      labels=[{"code": t["code"], "label": t["label"], "kind": "preferred"} for t in target])
            drafted[c.to_set] = len(target)
    code_set = args.code_set or args.name
    usage = []
    for used in args.used_in:
        parts = used.split(":")
        if len(parts) not in (3, 4):
            raise Blocked(f"--used-in is <store>:<object>:<field>[:<match>], not {used!r}")
        usage.append({"store": parts[0], "object": parts[1], "field": parts[2], "match": (parts[3:] or ["exact"])[0]})
    hints = []
    for hint in args.hint:
        kind, _, said = hint.partition("=")
        hints.append({"kind": kind, "text": said})
    rdm.draft({"code_set": code_set, "name": args.set_name or code_set, "definition": args.definition or ""},
              args.version, found["codes"], created_by=args.created_by, evidence=evidence, labels=found["labels"],
              crosswalk=found["crosswalk"], usage=usage, hints=hints)
    if tables.rebuild(rdm.codes(code_set, args.version), label=args.label, crosswalks=crosswalks) != table:
        raise Blocked(f"The draft of {code_set} {args.version} does not rebuild {args.name}")
    return {"code_set": code_set, "version": args.version, "codes": len(found["codes"]),
            "crosswalk_rows": len(found["crosswalk"]), "also_drafted": drafted, "rebuilds_exactly": True}


def _commands(parser):
    commands = parser.add_subparsers(dest="rdm_command", required=True)
    for name in ("init", "migrate"):
        command = commands.add_parser(name)
        command.add_argument("--runtime-role", required=True)
        command.set_defaults(handler=_handle)
    listed = commands.add_parser("list", help="Every code set, its current published version and its newest version")
    listed.set_defaults(handler=_handle)
    described = commands.add_parser("describe", help="A code set for an agent: meaning, version, pin, where used, hints")
    described.add_argument("code_set")
    described.add_argument("--version", help="Default: the current published version, else the newest")
    described.set_defaults(handler=_handle)
    drafted = commands.add_parser("draft", help="Draft a version from a JSON or YAML file (what an agent writes)")
    drafted.add_argument("--file", type=Path, required=True)
    drafted.set_defaults(handler=_handle)
    imported = commands.add_parser("import-reference", help="Draft rules/reference/<name>.yaml as a code set version")
    imported.add_argument("name")
    imported.add_argument("--key", default="", help="Dotted path to the code map inside the file")
    imported.add_argument("--label", required=True, help="The field that becomes each code's label")
    imported.add_argument("--crosswalk", action="append", default=[],
                          help="<field>=<code set>@<version>:<match type>; version 'outside' for a set RDM does not hold")
    imported.add_argument("--code-set", help="The code set id (default: the file name)")
    imported.add_argument("--set-name", help="The code set's name in plain words")
    imported.add_argument("--definition", help="What the codes stand for")
    imported.add_argument("--used-in", action="append", default=[],
                          help="<store>:<object>:<field>[:<match>]: where the codes' values live (store mdm, silver, source, other)")
    imported.add_argument("--hint", action="append", default=[],
                          help="<kind>=<text>: a hint for agents (kind meaning, use_when, avoid_when, example_question)")
    imported.add_argument("--version", default="1")
    imported.add_argument("--created-by", required=True, help="The agent and skill, or the person, drafting it")
    imported.set_defaults(handler=_handle)
    approve = commands.add_parser("approve", help="Record the operator's approval of a draft in their exact words")
    approve.add_argument("code_set")
    approve.add_argument("version")
    approve.add_argument("--by", required=True)
    approve.add_argument("--words", required=True)
    approve.set_defaults(handler=_handle)
    publish = commands.add_parser("publish", help="Publish an approved version and write its files")
    publish.add_argument("code_set")
    publish.add_argument("version")
    publish.add_argument("--out", type=Path, required=True, help="Folder for the version's JSON Lines files")
    publish.set_defaults(handler=_handle)
    for name, help_text in (("retire", "Retire a published version on the operator's word (kept, never deleted)"),
                            ("verify", "Check a version's stored sha256 against its rows")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("code_set")
        command.add_argument("version")
        command.set_defaults(handler=_handle)
    diff = commands.add_parser("diff", help="Codes added, removed, relabelled and moved between two versions")
    diff.add_argument("code_set")
    diff.add_argument("old")
    diff.add_argument("new")
    diff.set_defaults(handler=_handle)
    return commands


def register(subparsers):
    parser = subparsers.add_parser("rdm", help="Reference data: code sets, versions, approval and publishing")
    return _commands(parser)
