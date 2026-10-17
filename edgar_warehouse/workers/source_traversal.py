"""Configured traversal of an authenticated private snapshot, through valid EOF.

Callbacks prepare provisional readings. This module neither authenticates the
snapshot nor publishes rows; only a successful return supplies complete evidence.
"""
from __future__ import annotations

import copy
import fnmatch
import zipfile
from contextlib import ExitStack
from pathlib import Path

from edgar_warehouse.rules import source_engine
from . import source_readings


def runtime_files():
    return [Path(__file__), Path(source_readings.__file__), *source_engine.runtime_files()]


def _compile(contract):
    read = contract["read"]
    spec = read["stream"]
    # Ceilings a contract may declare (ticket 83): the spool is a private
    # file and the index names any number of pieces, so only one record (and
    # one piece) is bounded below the machine.
    maxima = {"max_input_bytes": 2**40, "max_bytes": 2**40,
              "max_record": 32 * 1024**2, "max_records": 10**12,
              "max_depth": 64, "partition_bytes": 8 * 1024**2,
              "partition_records": 100_000, "max_partitions": 10**7,
              "max_spool_bytes": 2**40, "max_output_rows": 10**12}
    framing = spec.get("framing", "json_array") if isinstance(spec, dict) else None
    if framing not in ("json_array", "xml_records", "delimited"):
        raise ValueError("Unknown configured stream framing")
    required = {*maxima, "container", "ordinal_context"}
    required |= {"json_array": {"wrapper", "min_integer", "record_encoding"},
                 "xml_records": {"framing", "xml", "header_read"},
                 "delimited": {"framing", "delimited"}}[framing]
    if (not isinstance(spec, dict) or not required <= set(spec)
            or set(spec) - required - {"expected_records_context", "framing", "member"} -
                ({"max_header"} if framing == "xml_records" else set())):
        raise ValueError("read.stream must declare every framing, partition and spool bound")
    member = spec.get("member")
    if "member" in spec and (spec["container"] != "zip" or not isinstance(member, str)
                             or not 1 <= len(member.encode()) <= 256 or "[" in member):
        raise ValueError("read.stream member is a ZIP member name pattern of 1 to 256 bytes (* and ?)")
    if framing == "delimited":
        delimited = spec["delimited"]
        if (not isinstance(delimited, dict) or set(delimited) != {"format", "encoding"}
                or delimited["format"] not in ("csv", "tsv")
                or delimited["encoding"] not in ("utf-8", "windows-1252")):
            raise ValueError("A delimited stream declares its format (csv or tsv) and one encoding "
                             "(utf-8 or windows-1252; choosing between two needs the whole file)")
    for key, maximum in maxima.items():
        minimum = 0 if key == "max_records" else 1
        if type(spec[key]) is not int or not minimum <= spec[key] <= maximum:
            raise ValueError(f"read.stream {key} is outside its bounded range")
    if (read.get("format") != "json" or "container" in read
            or spec["container"] not in ("none", "zip")):
        raise ValueError("read.stream requires JSON record projection and explicit framing policy")
    # `wrapper: null` reads a document that is itself the array (ticket 104).
    if framing == "json_array" and ((spec["wrapper"] is not None and (not isinstance(spec["wrapper"], str)
                                     or not spec["wrapper"] or len(spec["wrapper"].encode()) > 128))
            or type(spec["min_integer"]) is not int
            or not -(2**63) <= spec["min_integer"] <= 2**63 - 1
            or spec["record_encoding"] not in ("native", "python")):
        raise ValueError("JSON array stream requires explicit numeric and wrapper policy")
    header_engine = None
    if framing == "xml_records":
        if "max_header" in spec and (type(spec["max_header"]) is not int
                or not 1 <= spec["max_header"] <= 32 * 1024**2):
            raise ValueError("read.stream max_header is outside its bounded range")
        xml = spec.get("xml")
        fields = {"namespace", "root", "header", "container", "record", "record_wrapper"}
        if (not isinstance(xml, dict) or set(xml) != fields
                or any(not isinstance(xml[name], str) or not 1 <= len(xml[name].encode()) <= 512
                       for name in fields - {"record_wrapper"})
                or (xml["record_wrapper"] is not None and
                    (not isinstance(xml["record_wrapper"], str) or not 1 <= len(xml["record_wrapper"].encode()) <= 128))):
            raise ValueError("XML stream requires a bounded explicit envelope")
        header_read = spec.get("header_read")
        if (not isinstance(header_read, dict) or header_read.get("format") != "json"
                or "container" in header_read or "stream" in header_read
                or header_read.get("context", {}) != read.get("context", {})):
            raise ValueError("XML header uses configured JSON assertions with the same context")
        header_engine = source_engine.SourceEngine({"read": header_read})
    elif "xml" in spec or "header_read" in spec:
        raise ValueError("XML envelope/header policy requires XML framing")
    ordinal = spec["ordinal_context"]
    if ordinal is not None:
        declared = read.get("context", {}).get(ordinal) if isinstance(ordinal, str) else None
        if not isinstance(declared, dict) or declared.get("type") != "integer":
            raise ValueError("Stream ordinal_context must name a declared integer context")
    expected = spec.get("expected_records_context")
    if "expected_records_context" in spec:
        declared = read.get("context", {}).get(expected) if isinstance(expected, str) else None
        if not isinstance(declared, dict) or declared.get("type") != "integer":
            raise ValueError("Stream expected_records_context must name a declared integer context")
    limits = read.get("limits", {})
    if (type(limits.get("max_bytes")) is not int
            or not 1 <= limits["max_bytes"] <= 32 * 1024**2
            or type(limits.get("max_records")) is not int
            or not 1 <= limits["max_records"] <= 100_000):
        raise ValueError("Record projection requires bounded read.limits")
    projection = copy.deepcopy(contract)
    del projection["read"]["stream"]
    engine = source_engine.SourceEngine(projection)
    source_readings.table_names(list(read["tables"]))
    return spec, engine, header_engine


class Traversal:
    """Compile once, then traverse snapshots under one explicit archive policy.

    ``configured`` permits the contract's member selection; ``whole`` requires
    a single-member ZIP for full-source attestation. Native engines stay private.
    """

    def __init__(self, contract, *, archive_policy):
        if archive_policy not in ("configured", "whole"):
            raise ValueError("Traversal archive policy is configured or whole")
        contract = copy.deepcopy(contract)
        self._spec, self._engine, self._header_engine = _compile(contract)
        self._archive_policy = archive_policy
        self._lookups = contract["read"].get("lookup_sets") or {}

    @property
    def spec(self):
        """A private copy of the bounds callers use for staging and hashing."""
        return copy.deepcopy(self._spec)

    def validate_context(self, context) -> int | None:
        """Preflight before opening source bytes; scan also validates its input."""
        spec = self._spec
        ordinal = spec["ordinal_context"]
        expected_name = spec.get("expected_records_context")
        expected_count = context.get(expected_name) if expected_name is not None else None
        if self._archive_policy == "whole":
            if (spec["container"] != "zip" or expected_name is None
                    or type(expected_count) is not int or not 0 <= expected_count <= spec["max_records"]):
                raise ValueError("Attestation requires a ZIP and bounded pinned record count")
            if ordinal is None or ordinal in context:
                raise ValueError("Attestation generates the configured ordinal context")
        else:
            if spec.get("framing") == "xml_records" and self._lookups:
                raise ValueError("Indexed stream lookup receipts currently require JSON or delimited framing")
            if ordinal is not None and ordinal in context:
                raise ValueError("Stream ordinal context is generated, never supplied by a caller")
        self._engine.validate_context({**context, **({ordinal: 1} if ordinal is not None else {})})
        if self._archive_policy == "configured" and expected_name is not None and (
                type(expected_count) is not int or not 0 <= expected_count <= spec["max_records"]):
            raise ValueError("Stream expected record count is outside its declared bound")
        return expected_count

    def scan(self, snapshot, *, context, on_reading, lookups=None):
        """Traverse to valid EOF and return record/expanded-byte accounting.

        The caller retains snapshot authentication and callback side effects.
        A callback prefix never proves successful completion of this input.
        """
        expected_count = self.validate_context(context)
        spec = self._spec
        whole = self._archive_policy == "whole"
        if whole and spec.get("framing", "json_array") not in ("json_array", "xml_records"):
            raise ValueError("Attestation supports JSON or XML framing only")
        with ExitStack() as stack:
            stream = snapshot
            member_size = None
            if spec["container"] == "zip":
                archive = stack.enter_context(zipfile.ZipFile(snapshot))
                members = archive.infolist()
                if not whole and "member" in spec:
                    members = [m for m in members if fnmatch.fnmatchcase(m.filename, spec["member"])]
                if len(members) != 1 or members[0].is_dir() or members[0].flag_bits & 1:
                    raise ValueError("Source requires one unencrypted ZIP member" if whole else
                        "Stream ZIP requires exactly one unencrypted file"
                        + (" matching its member pattern" if "member" in spec else ""))
                if members[0].file_size > spec["max_bytes"]:
                    raise ValueError("Expanded source size exceeds bound" if whole else
                                     "Stream ZIP member exceeds expanded byte bound")
                member_size = members[0].file_size
                stream = stack.enter_context(archive.open(members[0]))
            arguments = {key: spec[key] for key in ("max_bytes", "max_record")}
            arguments.update(max_records=expected_count if whole else spec["max_records"],
                             context=context, ordinal_context=spec["ordinal_context"], on_reading=on_reading)
            if spec.get("framing") == "delimited":
                scan = self._engine.stream_delimited(stream, format=spec["delimited"]["format"],
                    encoding=spec["delimited"]["encoding"], lookups=lookups, **arguments)
            elif self._header_engine is None:
                scan = self._engine.stream_json_array(stream, wrapper=spec["wrapper"],
                    lookups=lookups, **arguments, **{key: spec[key] for key in
                        ("max_depth", "min_integer", "record_encoding")})
            else:
                scan = self._engine.stream_xml_records(stream, envelope=spec["xml"],
                    header_engine=self._header_engine, max_header=spec.get("max_header"),
                    max_depth=spec["max_depth"], **arguments)
            if expected_count is not None and scan["record_count"] != expected_count:
                raise ValueError("Source record count or expanded length mismatch" if whole else
                                 "Stream record count differs from pinned context")
            if member_size is not None and scan["expanded_bytes"] != member_size:
                raise ValueError("Source record count or expanded length mismatch" if whole else
                                 "Stream ZIP expanded length differs from declared member size")
        return scan
