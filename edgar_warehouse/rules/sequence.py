"""Offline source sequencing; authorization and execution stay with Rules/Bookkeeping."""
from __future__ import annotations

import json
import re
import sys
from graphlib import CycleError, TopologicalSorter
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.config import Blocked, IDENTIFIER, validate
from edgar_warehouse.workers import PROFILES

from . import files


def _names(values, label):
    if (not isinstance(values, list)
            or any(not isinstance(value, str) or not re.fullmatch(IDENTIFIER, value) for value in values)
            or len(set(values)) != len(values)):
        raise Blocked(f"{label} must be a list of distinct source names")
    return values


def _configuration(document):
    if (not isinstance(document, dict) or set(document) != {"version", "sources"}
            or type(document["version"]) is not int or document["version"] != 1
            or not isinstance(document["sources"], dict) or not document["sources"]):
        raise Blocked("Source sequence requires version 1 and a nonempty sources mapping")
    sources = document["sources"]
    _names(list(sources), "sources")
    graph = {}
    for name, entry in sources.items():
        if not isinstance(entry, dict) or set(entry) != {"target", "requires", "after"}:
            raise Blocked(f"{name}: declare target, requires and after only")
        target = entry["target"]
        if target is not None and (not isinstance(target, str) or not re.fullmatch(IDENTIFIER, target)):
            raise Blocked(f"{name}: target must name a target or be null when unconfigured")
        required = _names(entry["requires"], f"{name}.requires")
        preferred = _names(entry["after"], f"{name}.after")
        if any(other not in sources or other == name for other in [*required, *preferred]):
            raise Blocked(f"{name}: dependencies must name other declared sources")
        graph[name] = list(dict.fromkeys([*required, *preferred]))
    try:
        order = list(TopologicalSorter(graph).static_order())
    except CycleError as error:
        raise Blocked("Source sequence contains a dependency or preferred-order cycle") from error
    return sources, order


def plan(document: dict, *, root: Path, selected=(), deferred=()) -> dict:
    """Check selected sources and their required closure, without loading unrelated files."""
    sources, order = _configuration(document)
    selected = _names(list(selected), "--source")
    deferred = _names(list(deferred), "--defer")
    if any(name not in sources for name in [*selected, *deferred]):
        raise Blocked("Selection or deferral names an undeclared source")
    included = set(selected or sources)
    pending = list(included)
    while pending:
        for name in sources[pending.pop()]["requires"]:
            if name not in included:
                included.add(name)
                pending.append(name)
    if not set(deferred) <= included:
        raise Blocked("A deferral must name a source in the selected dependency closure")

    results = {}
    for name in order:
        if name not in included:
            continue
        entry = sources[name]
        reasons = []
        if name in deferred:
            status, reasons = "deferred", ["explicit_source_deferral"]
        else:
            for dependency in entry["requires"]:
                if results[dependency]["status"] != "configured":
                    reasons.append(f"required_source_unavailable:{dependency}")
            if entry["target"] is None:
                reasons.append("source_target_not_configured")
            else:
                try:
                    target = validate(files.source(name, root), entry["target"])
                    operations = {step["operation"] for step in target["steps"]}
                    if operations - PROFILES.keys():
                        reasons.append("unsupported_worker_profile")
                    if "provider.capture" in operations:
                        reasons.append("provider_acquisition_is_separate")
                except (Blocked, OSError, ValueError, TypeError, AttributeError):
                    # Report a category only: a malformed document may contain private values.
                    reasons.append("source_target_invalid_or_missing")
            status = "blocked" if reasons else "configured"
        results[name] = {"target": entry["target"], "status": status, "reasons": reasons}
    return {"version": 1, "runtime_readiness": "not_checked",
            "order": [name for name, item in results.items() if item["status"] == "configured"],
            "sources": results}


def handle(args):
    root = Path(args.root)
    try:
        document = files.load(Path(args.file) if args.file else root / "source-sequence.yaml")
    except (OSError, ValueError):
        # Loader diagnostics can echo private YAML lines and filesystem values.
        print("Source sequence refused: sequence_file_invalid_or_missing", file=sys.stderr)
        return 2
    try:
        result = plan(document, root=root, selected=args.source, deferred=args.defer)
    except Blocked as error:
        print(f"Source sequence refused: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 3 if any(item["status"] != "configured" for item in result["sources"].values()) else 0


def register(commands):
    command = commands.add_parser("sequence", help="Check source ordering and explicit deferrals offline")
    command.add_argument("action", choices=("check",))
    command.add_argument("--file", help="Sequence YAML; defaults to <root>/source-sequence.yaml")
    command.add_argument("--root", default=str(files.ROOT))
    command.add_argument("--source", action="append", default=[], help="Select a source and its required dependencies")
    command.add_argument("--defer", action="append", default=[], help="Defer a delayed source; never bypass a requirement")
    command.set_defaults(handler=handle)
