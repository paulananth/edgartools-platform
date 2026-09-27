"""Validate and freeze approved Rules exports and source-owned input worklists.

There is intentionally no Rules store here. A submission resolver supplies an
approved export; execution only reads its frozen content-addressed references.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from string import Formatter
from typing import Callable


class Blocked(ValueError):
    """Execution cannot safely reconstruct or verify its frozen scope."""


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def reference(value: dict) -> dict:
    if (not isinstance(value, dict) or set(value) != {"uri", "sha256"}
            or not isinstance(value["uri"], str) or not value["uri"]
            or not isinstance(value["sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"])):
        raise Blocked("A reference requires an exact URI and lowercase SHA-256")
    return value


@dataclass(frozen=True)
class Capability:
    version: str
    execute: Callable
    reconcile: Callable
    verify: Callable


class Registry:
    """Functions selected by capability name, never by source name.

    Reconciliation and verification are mandatory: an executor's success or
    exit code alone cannot become verified completion evidence.
    """
    def __init__(self):
        self.operations: dict[str, Capability] = {}
        self.checks: dict[str, Callable] = {}

    def operation(self, name: str, capability: Capability):
        if name in self.operations or not capability.version:
            raise ValueError("Duplicate or unversioned capability")
        self.operations[name] = capability

    def check(self, name: str, function: Callable):
        if name in self.checks:
            raise ValueError("Duplicate check")
        self.checks[name] = function


def _integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise Blocked(f"{name} must be an integer in [{low}, {high}]")
    return value


def validate(document: dict, target: str, registry: Registry) -> dict:
    """Strict versioned contract; reject unknown keys rather than guessing."""
    try:
        body = document["bookkeeping"]
        if set(body) != {"version", "targets"} or type(body["version"]) is not int or body["version"] != 1:
            raise Blocked("Unsupported bookkeeping configuration")
        selected = body["targets"][target]
        if set(selected) - {"steps", "lease_seconds", "heartbeat_seconds", "retry", "allow_zero_work", "checks"}:
            raise Blocked("Unknown target option")
        if type(selected.get("allow_zero_work", False)) is not bool:
            raise Blocked("allow_zero_work must be boolean")
        duration = _integer(selected.get("lease_seconds", 120), 2, 86400, "lease_seconds")
        heartbeat = _integer(selected.get("heartbeat_seconds", 30), 1, duration - 1, "heartbeat_seconds")
        retry = selected.get("retry", {})
        if set(retry) - {"attempts", "base_ms", "cap_ms"}:
            raise Blocked("Unknown retry option")
        attempts = _integer(retry.get("attempts", 5), 1, 100, "retry.attempts")
        base = _integer(retry.get("base_ms", 100), 1, 60000, "retry.base_ms")
        cap = _integer(retry.get("cap_ms", 5000), base, 60000, "retry.cap_ms")
        steps = selected["steps"]
        if not isinstance(steps, list) or not steps:
            raise Blocked("A target requires steps")
        seen = set()
        for step in steps:
            if set(step) != {"name", "operation", "requires", "key", "leases", "checks"}:
                raise Blocked("A step requires name, operation, requires, key, leases and checks")
            name = step["name"]
            if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]*", name) or name in seen:
                raise Blocked("Step names must be unique identifiers")
            if step["operation"] not in registry.operations:
                raise Blocked(f"Unsupported operation: {step['operation']}")
            if (not isinstance(step["requires"], list) or len(set(step["requires"])) != len(step["requires"])
                    or not set(step["requires"]) <= seen):
                raise Blocked("Prerequisites must name preceding steps")
            for key in ("key",):
                if not isinstance(step[key], str) or not step[key]:
                    raise Blocked("A step requires a work-unit key")
            if not isinstance(step["leases"], list) or not step["leases"]:
                raise Blocked("A step must declare its conflicting resources")
            for pattern in [step["key"], *step["leases"]]:
                if not isinstance(pattern, str) or not pattern:
                    raise Blocked("Lease/key patterns must be nonempty text")
                for _, field, spec, conversion in Formatter().parse(pattern):
                    if field is not None and (not re.fullmatch(r"[a-z][a-z0-9_]*", field) or spec or conversion):
                        raise Blocked("Templates support simple identifier fields only")
            if not isinstance(step["checks"], list) or len(set(step["checks"])) != len(step["checks"]):
                raise Blocked("Step checks must be a list of distinct capability names")
            for check in step["checks"]:
                if check not in registry.checks:
                    raise Blocked(f"Unsupported check: {check}")
            if not step["checks"]:
                raise Blocked("Every step requires a check")
            seen.add(name)
        checks = selected.get("checks", [])
        if (not isinstance(checks, list) or not checks or len(set(checks)) != len(checks)
                or any(c not in registry.checks for c in checks)):
            raise Blocked("A target requires supported final checks")
        return {**selected, "lease_seconds": duration, "heartbeat_seconds": heartbeat,
                "retry": {"attempts": attempts, "base_ms": base, "cap_ms": cap}}
    except Blocked:
        raise
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise Blocked("Malformed bookkeeping configuration") from exc


def worklist(manifest: dict, config: dict) -> list[dict]:
    """Freeze stage scope; version 1 retains its original worklist digest.

    Version 2 lists units separately for every configured step. An input may
    name a preceding prerequisite's unit; only its verified output can be
    resolved at execution time. No paths or work are discovered on resume.
    """
    if not isinstance(manifest, dict) or type(manifest.get("version")) is not int:
        raise Blocked("Unsupported input manifest")
    if manifest["version"] == 1 and set(manifest) == {"version", "units"}:
        stages = {step["name"]: manifest["units"] for step in config["steps"]}
    elif manifest["version"] == 2 and set(manifest) == {"version", "steps"}:
        stages = manifest["steps"]
        if not isinstance(stages, dict) or set(stages) != {s["name"] for s in config["steps"]}:
            raise Blocked("Manifest must declare exactly the configured steps")
    else:
        raise Blocked("Unsupported input manifest")
    if any(not isinstance(units, list) for units in stages.values()):
        raise Blocked("Each stage worklist must be a list")
    if any(not units for units in stages.values()) and not config.get("allow_zero_work", False):
        raise Blocked("Zero work is not permitted")
    items = []
    identities = set()
    for step in config["steps"]:
        for ordinal, unit in enumerate(stages[step["name"]]):
            if not isinstance(unit, dict) or set(unit) != {"keys", "input", "output", "cursor"}:
                raise Blocked("Units contain keys, input/output references and an opaque cursor only")
            source = unit["input"]
            if manifest["version"] == 2 and isinstance(source, dict) and set(source) == {"from"}:
                dependency = source["from"]
                if (not isinstance(dependency, dict) or set(dependency) != {"step", "key"}
                        or not isinstance(dependency["step"], str) or not isinstance(dependency["key"], str)
                        or dependency["step"] not in step["requires"]
                        or (dependency["step"], dependency["key"]) not in identities):
                    raise Blocked("Input must name an existing unit in a preceding prerequisite")
            else:
                reference(source)
            # Output URI names intent; verified content hash is supplied by the
            # durable destination receipt, not guessed during submission.
            if not isinstance(unit["output"], str) or not unit["output"]:
                raise Blocked("Output reference missing")
            if not isinstance(unit["keys"], dict) or any(not isinstance(v, str) or not v for v in unit["keys"].values()):
                raise Blocked("Unit keys must be nonempty text")
            try:
                key = step["key"].format_map(unit["keys"])
                resources = sorted(set(p.format_map(unit["keys"]) for p in step["leases"]))
            except KeyError as exc:
                raise Blocked(f"Missing configured key: {exc}") from exc
            if (step["name"], key) in identities:
                raise Blocked("Duplicate work-unit identity")
            identities.add((step["name"], key))
            items.append({"step": step["name"], "key": key, "ordinal": ordinal,
                          "resources": resources, "unit": unit})
    return items
