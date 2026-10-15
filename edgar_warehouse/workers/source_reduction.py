"""Bounded declared reductions over fully authenticated reading streams.

State retains keys and unique members, never the complete input row history.
All streams must exhaust successfully before output is returned to the writer.
"""
from __future__ import annotations

from edgar_warehouse.control_contract import reference
from edgar_warehouse.rules.source_engine import ReductionEngine
from . import source_readings


def _sources(spec):
    """One source extract, or an ordered list of 1..8, as `combine` takes."""
    return [spec["source"]] if isinstance(spec["source"], str) else spec["source"]


def _name(value):
    return isinstance(value, str) and source_readings.NAME.fullmatch(value) is not None


def _selected_tables(spec):
    return [spec["table"]] if isinstance(spec["table"], str) else spec["table"]


def contract(body, refs):
    if (not isinstance(body, dict) or set(body) != {"execution", "reduce"}
            or body["execution"] != {"profile": "source.combine"}):
        raise ValueError("Reduction requires source.combine execution and reduce only")
    plan = body["reduce"]
    bounds = {"max_rows": 40_000_000, "max_input_bytes": 16 * 1024**3,
              "max_state_bytes": 256 * 1024**2, "max_keys": 10_000_000,
              "max_members": 10_000_000, "max_output_rows": 100_000,
              "max_output_bytes": 32 * 1024**2}
    if not isinstance(plan, dict) or set(plan) != {*bounds, "groups"}:
        raise ValueError("Reduction requires all input, state and output bounds and groups")
    for name, maximum in bounds.items():
        if type(plan[name]) is not int or not 1 <= plan[name] <= maximum:
            raise ValueError(f"Reduction {name} must be 1..{maximum}")
    groups = plan["groups"]
    for ref in refs.values():
        reference(ref)
    if (not isinstance(groups, dict) or not 1 <= len(groups) <= 32
            or not all(_name(name) for name in groups)):
        raise ValueError("Reduction requires 1..32 named groups")
    for name, spec in groups.items():
        required = {"source", "table", "keys", "mode", "count", "sample", "sample_limit"}
        if (not isinstance(spec, dict) or not required <= set(spec)
                or set(spec) - required - {"member", "last", "last_null", "exclude"}):
            raise ValueError("Reduction group has unknown or missing fields")
        tables = _selected_tables(spec)
        sources = _sources(spec)
        if (not isinstance(sources, list) or not 1 <= len(sources) <= 8
                or not all(_name(source) and source in refs for source in sources)
                or len(set(sources)) != len(sources)
                or not isinstance(tables, list) or not 1 <= len(tables) <= 8
                or not all(_name(table) for table in tables) or len(set(tables)) != len(tables)):
            raise ValueError("Reduction group selects 1..8 distinct declared sources and 1..8 distinct tables")
        keys = spec["keys"]
        if (not isinstance(keys, list) or not 1 <= len(keys) <= 8
                or not all(_name(key) for key in keys) or len(set(keys)) != len(keys)):
            raise ValueError("Reduction keys name 1..8 distinct text columns")
        if spec["mode"] not in ("count", "members"):
            raise ValueError("Reduction mode is count or members")
        if not _name(spec["count"]) or spec["count"] in keys:
            raise ValueError("Reduction count names a new output column")
        if (type(spec["sample_limit"]) is not int or not 0 <= spec["sample_limit"] <= 1000):
            raise ValueError("Reduction sample_limit must be 0..1000")
        if spec["mode"] == "count":
            if spec["sample"] is not None or spec["sample_limit"] != 0 or set(spec) != required:
                raise ValueError("Count reduction has no member, last, exclusion or sample")
        else:
            if (not _name(spec.get("member")) or not _name(spec["sample"])
                    or spec["sample"] in [*keys, spec["count"]]
                    or ("last" in spec and not _name(spec["last"]))):
                raise ValueError("Member reduction requires member and distinct sample columns")
            if "last" in spec and spec["last"] == spec["member"]:
                raise ValueError("Member and last columns must differ")
            if "last" in spec and (len(tables) != 1 or len(sources) != 1):
                raise ValueError("Last occurrence requires a single table and a single source; unions lack source order")
            if "last_null" in spec and ("last" not in spec or not isinstance(spec["last_null"], str)):
                raise ValueError("last_null requires a last column and a text replacement")
            if "exclude" in spec:
                target = spec["exclude"]
                if not _name(target) or target not in groups or target == name:
                    raise ValueError("Exclusion names another declared member group")
                other = groups[target]
                if (not isinstance(other, dict) or other.get("mode") != "members"
                        or other.get("keys") != keys or "exclude" in other):
                    raise ValueError("Exclusion requires matching keys and an unfiltered member group")
    return plan


def tables(plan, refs, artifacts):
    """Exhaust every reading, then finalize uncapped counts and capped samples.

    Rust retains bounded generic state; Python authenticates every stream.
    State byte accounting measures canonical UTF-8 payload, not heap size.
    Last is the last source occurrence for a specific key/member.
    """
    groups = plan["groups"]
    engine = ReductionEngine(plan)
    input_bytes = row_count = 0
    for source, ref in refs.items():
        selected = [(name, spec) for name, spec in groups.items() if source in _sources(spec)]
        consumed = 0
        for _, _, chunk, consumed in source_readings.iter_load(
                ref, artifacts, max_bytes=plan["max_input_bytes"] - input_bytes,
                max_rows=plan["max_rows"] - row_count, allow_lookup_receipts=True):
            if chunk["deferred"]:
                raise ValueError("Reduction requires resolved deferred records")
            row_count += sum(len(rows) for rows in chunk["tables"].values())
            if row_count > plan["max_rows"]:
                raise ValueError("Reduction exceeds aggregate input row budget")
            for name, spec in selected:
                names = _selected_tables(spec)
                if any(table not in chunk["tables"] for table in names):
                    raise ValueError("Reduction selects a missing table")
                for table in names:
                    engine.push(name, chunk["tables"][table])
        input_bytes += consumed
    # Only successful exhaustion of every supplied reading permits finalization.
    return engine.finish()
