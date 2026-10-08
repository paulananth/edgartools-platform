"""Data quality, checked on each record before the merge (company mastering ticket 22).

A feed's `quality.yaml` (its Source's Rules document carries it into each
Dataset Contract as `quality`) holds fixes and checks, all data:

- a **fix** writes a corrected value in place of the original; the record
  keeps the original and names the fix (`provenance.quality.fixes`), and MDM
  matches and merges on the corrected value. A standardized address is the
  exception: it is a matching copy (`matching.<name>`), and the address MDM
  shows stays as the source wrote it;
- a **check** tests one value. When it fails, `on_fail` says what happens:
  `exception` sets the record aside with the reason `quality_<id>`: it never
  merges, it never stops the run (the contract lists the reason as
  non-blocking), and it waits as an open exception until it is fixed or
  ignored (operator, 2026-09-28: "Do not stop ... it becomes an exception
  that needs to be fixed or ignored"); `withhold` keeps the value but no
  matching rule may use it (`provenance.quality.withheld`); `flag` only
  counts it.

Fixes run first, so checks see the corrected values. The tests and fixes are a
fixed, versioned list, as matching tests are: a new one is new code.
"""

from __future__ import annotations

import functools
import hashlib
import re
import unicodedata
from collections import Counter
from typing import Any

ON_FAIL = frozenset({"exception", "withhold", "flag"})
_ID = re.compile(r"[a-z][a-z0-9_]*")


class QualityError(ValueError):
    """A quality block that cannot run: an unknown test, a bad path or argument."""


# --- where a check or fix reads -------------------------------------------------

def _get(record: dict, path: str):
    """`fields.<name>`, `fields.address.<component>` or `matching.<name>`."""
    area, _, rest = path.partition(".")
    item: Any = record.get(area)
    for part in rest.split("."):
        item = item.get(part) if isinstance(item, dict) else None
    return item


def _set(record: dict, path: str, value) -> None:
    area, _, rest = path.partition(".")
    parts = rest.split(".")
    target = record[area]
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    if value is None and len(parts) > 1:
        target.pop(parts[-1], None)  # an address component: absent
    else:
        # A top-level field set to None reads as unknown, as a blank does.
        target[parts[-1]] = value


def _path_ok(path: Any) -> bool:
    return isinstance(path, str) and re.fullmatch(
        r"(fields|matching)\.[a-z_]+(\.[a-z0-9_]+)?", path
    ) is not None


# --- checks: value -> passes? ---------------------------------------------------

def _present(value, _args) -> bool:
    return value not in (None, "", {}, [])


def _in_set(value, args) -> bool:
    return value is None or value in args["values"]


def _pattern(value, args) -> bool:
    return value is None or re.fullmatch(args["regex"], str(value)) is not None


def _lei_check_digit(value, _args) -> bool:
    from .adapters import UnsupportedRecord, _lei

    try:
        _lei(str(value or "").strip().upper())
    except UnsupportedRecord:
        return False
    return True


def _placeholder(value, args) -> bool:
    """Passes unless the value is a placeholder: "N/A", "NONE", "0000"."""
    if value is None:
        return True
    text = re.sub(r"[\W_]", "", str(value).upper())
    return not (text in args["values"] or (text and set(text) == {"0"}))


def _address_text(value) -> str:
    if isinstance(value, dict):
        value = " ".join(str(value.get(k) or "") for k in ("street", "street2"))
    return re.sub(r"\s+", " ", str(value or "").upper())


def _registered_agent(value, args) -> bool:
    """Passes unless the address is a registered agent's: "C/O", "1209 ORANGE ST"."""
    text = _address_text(value)
    return not any(marker in text for marker in args["markers"])


def _in_reference(value, args) -> bool:
    if value is None:
        return True
    return str(value).strip().upper() in _reference_keys(args["table"], args["sha256"])


@functools.lru_cache(maxsize=None)
def _reference_keys(table: str, sha256: str) -> frozenset:
    """The codes of the reference data the Mastering Policy pins under `table`
    (its published RDM version, profiling ticket 02). The check's sha256 must be
    that pin, so a new version is a new quality version, never a silent change.
    Read once per process: the pin makes the result invariant."""
    from edgar_warehouse.rules import files

    pin = files.reference_pin(table)
    if pin["sha256"] != sha256:
        raise QualityError(f"Reference table {table} differs from its pinned sha256")
    return frozenset(str(row["code"]).upper() for row in files.pinned_reference(table))


CHECKS = {
    "present@1": (_present, set()),
    "in_set@1": (_in_set, {"values"}),
    "pattern@1": (_pattern, {"regex"}),
    "lei_check_digit@1": (_lei_check_digit, set()),
    "placeholder@1": (_placeholder, {"values"}),
    "registered_agent_address@1": (_registered_agent, {"markers"}),
    "in_reference@1": (_in_reference, {"table", "sha256"}),
}


# --- fixes: record -> the paths they changed ------------------------------------

_US_STATE_TAG = re.compile(r"\s*/([A-Z]{2})/?\s*$")


def _blank_values(record, args) -> list[str]:
    """An invalid code becomes empty: SEC's "DC" as a state of incorporation."""
    path = args["field"]
    if _get(record, path) in args["values"]:
        _set(record, path, None)
        return [path]
    return []


def _name_state_marker(record, args) -> list[str]:
    """SEC's state tag ("APPLIED MATERIALS INC /DE") fills an empty state of
    incorporation. Only a US state code counts; "/ADR/" and "/NEW/" do not."""
    from .names import edgar_jurisdiction

    target = args["target"]
    if _get(record, target) not in (None, ""):
        return []
    found = _US_STATE_TAG.search(str(_get(record, args["name"]) or "").upper())
    place = edgar_jurisdiction(found.group(1)) if found else None
    if not place or not place.startswith("US-"):
        return []
    _set(record, target, found.group(1))
    return [target]


# A secondary unit ("SUITE 100", "FL 5", "# 12") says where inside a building,
# not which building: the matching copy leaves it out.
_UNIT = re.compile(
    r"(?:^|\s)(?:(?:(?:STE|FL|UNIT|RM|APT)\b|#)\s*[A-Z0-9-]+|\d+(?:ST|ND|RD|TH)\s+FL)\b"
)

_WORDS = {
    "STREET": "ST", "AVENUE": "AVE", "ROAD": "RD", "DRIVE": "DR", "BOULEVARD": "BLVD",
    "LANE": "LN", "PLACE": "PL", "COURT": "CT", "PARKWAY": "PKWY", "HIGHWAY": "HWY",
    "SUITE": "STE", "FLOOR": "FL", "ROOM": "RM", "NORTH": "N", "SOUTH": "S", "EAST": "E",
    "WEST": "W",
}


def _standard_line(text: str) -> str:
    # Accents folded, not dropped: "BERANOVÝCH" is "BERANOVYCH". Letters of
    # any script stay: a Greek street is not a placeholder.
    plain = "".join(
        c for c in unicodedata.normalize("NFKD", text.upper()) if not unicodedata.combining(c)
    )
    words = re.sub(r"[^\w#/& -]+|_", " ", plain).split()
    line = " ".join(_WORDS.get(w, w) for w in words)
    return " ".join(_UNIT.sub(" ", line).split())


def _standardize_address(record, args) -> list[str]:
    """A matching copy of an address: upper case, street words as USPS
    Publication 28 abbreviates them, the suite or floor left out, and a US
    ZIP+4 cut to five digits.

    It goes to `matching.<into>`, never over the address MDM shows: a
    standardized address is a key to compare, not a better value to display.
    The copy is always written, so a matching rule reads one place; it is
    reported as a fix, with the source's address as the original, only when
    it differs from that address other than in case.
    """
    address = _get(record, args["field"])
    if not isinstance(address, dict):
        return []
    fixed = dict(address)
    for part in ("street", "street2", "city"):
        if isinstance(fixed.get(part), str):
            lines = (_standard_line(line) for line in fixed[part].split("\n"))
            fixed[part] = "\n".join(line for line in lines if line) or None
            if fixed[part] is None:
                del fixed[part]
    postcode = fixed.get("postcode")
    if isinstance(postcode, str) and re.fullmatch(r"\d{5}-?\d{4}", postcode.strip()):
        fixed["postcode"] = postcode.strip()[:5]
    _set(record, args["into"], fixed)
    upper = {k: v.upper() if isinstance(v, str) else v for k, v in address.items()}
    return [args["into"]] if fixed != upper else []


# The args that name a path, which `check_quality` checks.
_PATH_ARGS = ("field", "target", "into", "name")

# fix: (function, required args, the arg naming the value it corrects, kept
# on the record as the original).
FIXES = {
    "blank_values@1": (_blank_values, {"field", "values"}, "field"),
    "name_state_marker@1": (_name_state_marker, {"name", "target"}, "target"),
    "standardize_address@1": (_standardize_address, {"field", "into"}, "field"),
}


# --- the block ------------------------------------------------------------------

def check_quality(block: Any) -> None:
    """Refuse a quality block that could not run exactly as written."""
    if not isinstance(block, dict) or set(block) - {"version", "fixes", "checks"}:
        raise QualityError("A quality block holds version, fixes and checks only")
    if not isinstance(block.get("version"), str) or not block["version"]:
        raise QualityError("A quality block names its version")
    seen: set[str] = set()
    for kind, table, name_key in (("fixes", FIXES, "fix"), ("checks", CHECKS, "test")):
        for item in block.get(kind) or []:
            if not isinstance(item, dict) or not _ID.fullmatch(str(item.get("id", ""))):
                raise QualityError(f"Each of {kind} has an id of lower-case words")
            if item["id"] in seen:
                raise QualityError(f"Quality id {item['id']} is used twice")
            seen.add(item["id"])
            name = item.get(name_key)
            if name not in table:
                raise QualityError(f"Quality {item['id']} names an unknown {name_key}: {name}")
            required = table[name][1]
            args = item.get("args") or {}
            if not isinstance(args, dict) or not required <= set(args):
                raise QualityError(f"Quality {item['id']} needs args {sorted(required)}")
            paths = [v for k, v in args.items() if k in _PATH_ARGS]
            if kind == "checks":
                if item.get("on_fail") not in ON_FAIL:
                    raise QualityError(f"Check {item['id']} says exception, withhold or flag")
                paths.append(item.get("value"))
            if not all(_path_ok(p) for p in paths):
                raise QualityError(f"Quality {item['id']} reads fields.<name> or matching.<name>")


def apply(block: dict, fields: dict, matching: dict | None) -> dict:
    """Run one record's fixes, then its checks. Returns `provenance.quality`.

    Raises `UnsupportedRecord("quality_<id>")` for a failed `exception` check.
    """
    from .adapters import UnsupportedRecord

    record = {"fields": fields, "matching": matching if matching is not None else {}}
    result: dict = {"version": block["version"]}
    for item in block.get("fixes") or []:
        args = item.get("args") or {}
        fix, _, corrects = FIXES[item["fix"]]
        original = _copy(_get(record, args[corrects]))
        for path in fix(record, args):
            result.setdefault("fixes", {})[item["id"]] = {"path": path, "original": original}
    for item in block.get("checks") or []:
        if CHECKS[item["test"]][0](_get(record, item["value"]), item.get("args") or {}):
            continue
        if item["on_fail"] == "exception":
            raise UnsupportedRecord(f"quality_{item['id']}", {"quality": {"check": item["id"], "version": block["version"]}})
        key = "withheld" if item["on_fail"] == "withhold" else "flags"
        entry = item["value"] if key == "withheld" else item["id"]
        if entry not in result.setdefault(key, []):
            result[key].append(entry)
    return result


def _copy(value):
    return dict(value) if isinstance(value, dict) else value


def withheld(record: dict, path: str) -> bool:
    """Whether a matching rule may not use `path` on this stored record: the
    path is withheld, lies inside a withheld value, or holds one (a whole
    address whose street is a placeholder)."""
    quality = (record.get("provenance") or {}).get("quality") or {}
    return any(
        path == w or path.startswith(w + ".") or w.startswith(path + ".")
        for w in quality.get("withheld") or []
    )


def counts(assertions: list[dict], deferred: list[dict]) -> dict:
    """What one batch's quality did, per fix and check: the run reports it."""
    tally: Counter = Counter()
    for a in assertions:
        quality = (a.get("provenance") or {}).get("quality") or {}
        for fix in quality.get("fixes") or {}:
            tally[f"fixed:{fix}"] += 1
        for path in quality.get("withheld") or []:
            tally[f"withheld:{path}"] += 1
        for flag in quality.get("flags") or []:
            tally[f"flagged:{flag}"] += 1
    for d in deferred:
        if str(d.get("reason", "")).startswith("quality_"):
            tally[f"exception:{d['reason'].removeprefix('quality_')}"] += 1
    return dict(sorted(tally.items()))


def exception_reasons(block: dict) -> set[str]:
    """The reasons this block's `exception` checks set records aside with:
    each must be non-blocking in its Dataset Contract."""
    return {f"quality_{c['id']}" for c in block.get("checks") or [] if c.get("on_fail") == "exception"}
