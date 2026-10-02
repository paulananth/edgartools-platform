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
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import source_contract

from .steps import STEPS


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


class SourceEngine:
    def __init__(self, contract: Mapping):
        try:
            self._engine = source_contract.Engine(json.dumps(contract), STEPS)
        except source_contract.SourceRejected as error:
            raise _rejected(error) from None

    def read(self, data: bytes, *, lookups: Mapping[str, Iterable[str]] | None = None) -> Reading:
        """`lookups` names the sets an `in_lookup` check reads, such as an
        approved scope; each is a collection of strings, never one string."""
        sets = {}
        for name, values in (lookups or {}).items():
            if isinstance(values, str):
                raise TypeError(f"lookup {name} is one string, not a collection of them")
            sets[name] = list(values)
        try:
            result = self._engine.read(data, sets)
        except source_contract.SourceRejected as error:
            raise _rejected(error) from None
        return Reading(tables=result["tables"], deferred=result["deferred"])
