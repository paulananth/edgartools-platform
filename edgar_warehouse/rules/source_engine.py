"""The configured source engine, behind Python (mastering to-do 15).

A rules-file contract says how to read one artifact: its format and container,
the document checks that fail it, its tables and columns, and the record
checks that set a record aside. The reading runs in Rust (`crates/
source-contract`); this module is the only Python that calls it, so the rules
commands, Bookkeeping and MDM never import Rust.

- `SourceEngine(contract)` refuses a contract with an unknown format,
  primitive or check, or a custom step `steps.STEPS` does not hold.
- `read` returns the tables and the records set aside (`deferred`), each with
  the reason the rules file gives and its raw record.
- A failed artifact raises `SourceRejected`, with a stable `code`.
"""

from __future__ import annotations

import json
from pathlib import Path
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import source_contract

from .steps import STEPS


def runtime_files() -> list[Path]:
    """Code and native binary a configured reader's execution digest covers."""
    from . import steps

    return [Path(__file__), Path(steps.__file__), Path(source_contract.source_contract.__file__)]


class SourceRejected(Exception):
    """The artifact, or the contract, failed. `code` is stable; `detail` is for people."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Reading:
    tables: dict[str, list[dict]]
    deferred: list[dict]


def _rejected(error: source_contract.SourceRejected) -> SourceRejected:
    return SourceRejected(*error.args)


def stream_json_array(stream, *, wrapper: str, on_record, max_bytes: int,
                      max_record: int, max_records: int, max_depth: int = 64,
                      min_integer: int = -(2**63)) -> dict:
    """Read one named object array without retaining the whole document.

    Callbacks may prepare candidates. Only a successful return proves EOF;
    callers must not publish, commit or authenticate earlier callback rows.
    Transport/authentication and publication policy stay with the caller.
    max_record caps encoded record bytes; raw reads and raw record bytes
    permit 65,536 bytes of buffering headroom, including whitespace.
    """
    if not isinstance(wrapper, str) or not wrapper or len(wrapper.encode()) > 128:
        raise SourceRejected("contract", "JSON stream wrapper is bounded nonempty text")
    bounds = {"max_bytes": max_bytes, "max_record": max_record, "max_records": max_records, "max_depth": max_depth}
    if any(type(value) is not int or not 0 <= value <= 2**63 - 1 for value in bounds.values()):
        raise SourceRejected("contract", "JSON stream bounds must be nonnegative signed integers")
    if type(min_integer) is not int or not -(2**63) <= min_integer <= 2**63 - 1:
        raise SourceRejected("contract", "JSON stream integer minimum must be a signed integer")
    try:
        records, size = source_contract.scan_json_array(stream, wrapper, on_record, min_integer=min_integer, **bounds)
    except source_contract.SourceRejected as error:
        raise _rejected(error) from None
    return {"record_count": records, "expanded_bytes": size}


class SourceEngine:
    def __init__(self, contract: Mapping):
        try:
            self._engine = source_contract.Engine(json.dumps(contract), STEPS)
        except source_contract.SourceRejected as error:
            raise _rejected(error) from None

    def read(self, data: bytes, *, lookups: Mapping[str, Iterable[str]] | None = None,
             context: Mapping[str, object] | None = None) -> Reading:
        """`lookups` names the sets an `in_lookup` check reads, such as an
        approved scope; each is a collection of strings, never one string."""
        sets = {}
        for name, values in (lookups or {}).items():
            if isinstance(values, str):
                raise TypeError(f"lookup {name} is one string, not a collection of them")
            sets[name] = list(values)
        try:
            result = self._engine.read(data, sets, json.dumps(dict(context or {}), ensure_ascii=False, separators=(",", ":"), allow_nan=False))
        except source_contract.SourceRejected as error:
            raise _rejected(error) from None
        return Reading(tables=result["tables"], deferred=result["deferred"])
