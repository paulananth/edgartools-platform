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
                      min_integer: int = -(2**63), record_encoding: str = "native") -> dict:
    """Read one named object array without retaining the whole document.

    Callbacks may prepare candidates. Only a successful return proves EOF;
    callers must not publish, commit or authenticate earlier callback rows.
    Transport/authentication and publication policy stay with the caller.
    max_record caps encoded record bytes; raw reads and raw record bytes
    permit 65,536 bytes of buffering headroom, including whitespace.
    record_encoding='python' uses compact Python JSON float spelling for
    byte limits; the default uses native JSON spelling.
    """
    arguments = _stream_arguments(wrapper, max_bytes, max_record, max_records, max_depth, min_integer, record_encoding)
    try:
        records, size = source_contract.scan_json_array(stream, wrapper, on_record, **arguments)
    except source_contract.SourceRejected as error:
        raise _rejected(error) from None
    return {"record_count": records, "expanded_bytes": size}


def _stream_arguments(wrapper, max_bytes, max_record, max_records, max_depth, min_integer, record_encoding):
    if not isinstance(wrapper, str) or not wrapper or len(wrapper.encode()) > 128:
        raise SourceRejected("contract", "JSON stream wrapper is bounded nonempty text")
    bounds = {"max_bytes": max_bytes, "max_record": max_record, "max_records": max_records, "max_depth": max_depth}
    if any(type(value) is not int or not 0 <= value <= 2**63 - 1 for value in bounds.values()):
        raise SourceRejected("contract", "JSON stream bounds must be nonnegative signed integers")
    if type(min_integer) is not int or not -(2**63) <= min_integer <= 2**63 - 1:
        raise SourceRejected("contract", "JSON stream integer minimum must be a signed integer")
    if type(record_encoding) is not str or record_encoding not in ("native", "python"):
        raise SourceRejected("contract", "JSON stream record_encoding is native or python")
    return {**bounds, "min_integer": min_integer, "record_encoding": record_encoding}


def _lookup_iterables(lookups):
    # The native ingestion checks declared raw bounds before deduplication.
    # Do not eagerly list an unbounded generator in the Python facade.
    sets = dict(lookups or {})
    for name, values in sets.items():
        if isinstance(values, str):
            raise TypeError(f"lookup {name} is one string, not a collection of them")
    return sets


class SourceEngine:
    def __init__(self, contract: Mapping):
        read = contract.get("read")
        if isinstance(read, Mapping) and "stream" in read:
            raise SourceRejected("contract", "read.stream requires the source.read worker framing boundary")
        try:
            self._engine = source_contract.Engine(json.dumps(contract), STEPS)
        except source_contract.SourceRejected as error:
            raise _rejected(error) from None

    def stream_json_array(self, stream, *, wrapper: str, on_reading, max_bytes: int,
                          max_record: int, max_records: int, max_depth: int = 64,
                          min_integer: int = -(2**63), record_encoding: str = "native",
                          context: Mapping[str, object] | None = None, ordinal_context: str | None = None,
                          lookups: Mapping[str, Iterable[str]] | None = None) -> dict:
        """Frame and project inside Rust; callbacks prepare readings until valid EOF."""
        arguments = _stream_arguments(wrapper, max_bytes, max_record, max_records, max_depth, min_integer, record_encoding)
        def receive(body, index):
            on_reading(Reading(tables=body["tables"], deferred=body["deferred"]), index)
        try:
            records, size = self._engine.scan_json_array(stream, wrapper, receive,
                context=json.dumps(dict(context or {}), ensure_ascii=False, separators=(",", ":"), allow_nan=False),
                ordinal_context=ordinal_context, lookups=_lookup_iterables(lookups), **arguments)
        except source_contract.SourceRejected as error:
            raise _rejected(error) from None
        return {"record_count": records, "expanded_bytes": size}

    def validate_context(self, context: Mapping[str, object]) -> None:
        """Check declared caller facts before a stream can yield zero records."""
        try:
            self._engine.validate_context(json.dumps(dict(context), ensure_ascii=False,
                                                     separators=(",", ":"), allow_nan=False))
        except source_contract.SourceRejected as error:
            raise _rejected(error) from None

    def stream_xml_records(self, stream, *, envelope: Mapping, header_engine: SourceEngine,
                           on_reading, max_bytes: int, max_record: int, max_records: int,
                           max_depth: int = 64, max_header: int | None = None,
                           context: Mapping[str, object] | None = None,
                           ordinal_context: str | None = None) -> dict:
        """Normalize bounded XML records and project them with configured JSON rules.

        The header has its own configured assertions and the same caller context.
        max_header bounds normalized header nodes; it defaults to max_record.
        Raw input buffering remains capped by max_record plus 65,536 bytes.
        All callbacks prepare candidates; successful return proves complete EOF.
        """
        arguments = _stream_arguments("xml", max_bytes, max_record, max_records, max_depth, -(2**63), "python")
        del arguments["min_integer"], arguments["record_encoding"]
        if max_header is not None:
            if type(max_header) is not int or not 1 <= max_header <= 2**63 - 1:
                raise SourceRejected("contract", "XML header bound must be a positive signed integer")
            arguments["max_header"] = max_header
        def receive(body, index):
            on_reading(Reading(tables=body["tables"], deferred=body["deferred"]), index)
        try:
            records, size = self._engine.scan_xml_records(stream,
                json.dumps(dict(envelope), ensure_ascii=False, separators=(",", ":")),
                header_engine._engine, receive, context=json.dumps(dict(context or {}),
                    ensure_ascii=False, separators=(",", ":"), allow_nan=False),
                ordinal_context=ordinal_context, **arguments)
        except source_contract.SourceRejected as error:
            raise _rejected(error) from None
        return {"record_count": records, "expanded_bytes": size}

    def read(self, data: bytes, *, lookups: Mapping[str, Iterable[str]] | None = None,
             context: Mapping[str, object] | None = None) -> Reading:
        """`lookups` names the sets an `in_lookup` check reads, such as an
        approved scope; each is a collection of strings, never one string."""
        sets = _lookup_iterables(lookups)
        try:
            result = self._engine.read(data, sets, json.dumps(dict(context or {}), ensure_ascii=False, separators=(",", ":"), allow_nan=False))
        except source_contract.SourceRejected as error:
            raise _rejected(error) from None
        return Reading(tables=result["tables"], deferred=result["deferred"])
