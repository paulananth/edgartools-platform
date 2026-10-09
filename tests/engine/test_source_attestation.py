"""Independent old-runtime parity and generic attestation refusal contracts."""
import copy
import hashlib
import io
import json
import struct
import zipfile

import pytest

from edgar_warehouse.mdm.clean.gleif_publication import attest_publication
from edgar_warehouse.mdm.clean.gleif_source import FORMATS
from edgar_warehouse.rules.source_engine import SourceRejected
from edgar_warehouse.workers.source_attestation import attest_zip
from tests.engine.test_gleif_reading_contracts import MEMBERS, DATE, configured, archive, records
from tests.mdm.test_clean_gleif_source import archive_bytes, metadata
from tests.support.retired_gleif_attestation import inspect_archive as historical_inspector


@pytest.mark.parametrize("member", MEMBERS)
@pytest.mark.parametrize("format_name", ["json", "xml"])
def test_all_member_reports_and_callbacks_match_historical_runtime(member, format_name):
    rules = configured(member, format_name)
    raw = archive(rules, member, format_name)
    member_name = member.replace("-", "_")
    arguments = dict(member=member_name, expected_sha256=hashlib.sha256(raw).hexdigest(),
        metadata=metadata(3, format=format_name + ".zip", cdf_version=FORMATS[member_name][0]))
    old_rows, new_rows = [], []
    expected = historical_inspector(io.BytesIO(raw), **arguments,
                                    on_record=lambda row, index: old_rows.append((row, index)))
    actual = attest_publication(io.BytesIO(raw), **arguments,
                               on_record=lambda row, index: new_rows.append((row, index)))
    assert actual == expected
    assert new_rows == old_rows == list(zip(records(member), range(3)))


def generic_contract():
    # A different envelope, table, columns and context names require no
    # provider dispatch or transformation code at the attestation boundary.
    contract = copy.deepcopy(configured("level1", "json"))
    contract["source"] = "example.observations"
    read = contract["read"]
    read["context"] = {"position": {"type": "integer"}, "total": {"type": "integer"}}
    read["tables"] = {"observations": {"each": ".", "columns": {
        "payload": {"value": {"path": "."}}, "position": {"context": {"name": "position"}}}}}
    read["stream"].update(wrapper="observations", ordinal_context="position",
                           expected_records_context="total")
    contract["attestation"] = {"table": "observations", "record_column": "payload", "ordinal_column": "position"}
    return contract


def test_generic_provider_uses_configured_names_and_preserves_contract():
    contract = generic_contract()
    before = copy.deepcopy(contract)
    rows = [{"id": "a", "unmapped": [False, None, "é"]}, {"id": "b"}]
    payload = json.dumps({"observations": rows}, ensure_ascii=False).encode()
    raw = archive_bytes(payload)
    seen = []
    report = attest_zip(io.BytesIO(raw), contract=contract, context={"total": 2},
        expected_sha256=hashlib.sha256(raw).hexdigest(), on_record=lambda row, index: seen.append((row, index)))
    assert seen == list(zip(rows, range(2)))
    assert report["expanded_bytes"] == len(payload)
    assert report["canonical_source_hash"] == hashlib.sha256(b''.join(
        json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode() + b'\n'
        for row in rows)).hexdigest()
    assert contract == before


@pytest.mark.parametrize("fault", ["hash", "count", "trailing", "truncated", "ordinal", "missing_row"])
def test_generic_attestation_refuses_deliberate_faults(fault):
    contract = generic_contract()
    payload = b'{"observations":[{"id":"one"}]}'
    count, digest = 1, None
    if fault == "trailing": payload += b' garbage'
    if fault == "truncated": payload = payload[:-1]
    if fault == "count": count = 2
    if fault == "hash": digest = "0" * 64
    if fault == "ordinal": contract["read"]["tables"]["observations"]["columns"]["position"] = {"value": {"path": "id"}}
    if fault == "missing_row": contract["read"]["tables"]["observations"]["each"] = "absent"
    raw = archive_bytes(payload)
    with pytest.raises((ValueError, SourceRejected)) as caught:
        attest_zip(io.BytesIO(raw), contract=contract, context={"total": count},
                   expected_sha256=digest or hashlib.sha256(raw).hexdigest())
    if isinstance(caught.value, SourceRejected):
        assert caught.value.code != "contract"


@pytest.mark.parametrize("failure", [ValueError("retry"), RuntimeError("retry"), KeyboardInterrupt()])
def test_generic_callback_failure_identity(failure):
    raw = archive_bytes(b'{"observations":[{}]}')
    def fail(row, index): raise failure
    with pytest.raises(type(failure)) as caught:
        attest_zip(io.BytesIO(raw), contract=generic_contract(), context={"total": 1},
                   expected_sha256=hashlib.sha256(raw).hexdigest(), on_record=fail)
    assert caught.value is failure


def test_retired_inspector_has_no_runtime_entry_point():
    from edgar_warehouse.mdm.clean import gleif_source
    assert not hasattr(gleif_source, "inspect_archive")


@pytest.mark.parametrize("fault", ["crc", "expanded_length", "second_member", "encrypted"])
def test_physical_archive_faults_cannot_return_an_attestation(fault):
    payload = b'{"observations":[{"id":1}]}'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive_file:
        archive_file.writestr("data.json", payload)
        if fault == "second_member": archive_file.writestr("extra", b"untrusted")
    raw = bytearray(buffer.getvalue())
    central = raw.index(b"PK\x01\x02")
    if fault == "crc": raw = raw.replace(payload, payload.replace(b'1', b'2'), 1)
    if fault == "expanded_length": struct.pack_into("<I", raw, central + 24, len(payload) + 1)
    if fault == "encrypted": struct.pack_into("<H", raw, central + 8, 1)
    with pytest.raises((ValueError, SourceRejected, zipfile.BadZipFile)):
        attest_zip(io.BytesIO(raw), contract=generic_contract(), context={"total": 1},
                   expected_sha256=hashlib.sha256(raw).hexdigest())
