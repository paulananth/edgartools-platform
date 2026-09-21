"""Person Consumer Contract ticket 19: the ownership parse path classifies
reporting owners from bronze submissions.json, never a live SEC lookup.

Two seams: _run_parse_pipeline forwards a submissions_lookup to the ownership
parser, and _bronze_submissions_lookup resolves a CIK to its newest bronze
snapshot by glob (storage reads only)."""
from __future__ import annotations

import json
import socket
from datetime import date
from unittest.mock import MagicMock

import pytest

from edgar_warehouse.application import warehouse_orchestrator as orch


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def _refuse(*_a, **_k):
        raise AssertionError("ownership parsing must make zero network requests")

    monkeypatch.setattr(socket.socket, "connect", _refuse)


def test_run_parse_pipeline_hands_the_lookup_to_the_ownership_parser(monkeypatch):
    filing = {"accession_number": "0001", "cik": 320193, "form": "4", "filing_date": date(2025, 6, 1)}
    db = MagicMock()
    db.get_filing.return_value = filing
    for name in (
        "merge_ownership_reporting_owners", "merge_ownership_non_derivative_txns",
        "merge_ownership_derivative_txns", "merge_adv_filings", "merge_adv_offices",
        "merge_adv_disclosure_events", "merge_adv_private_funds",
    ):
        getattr(db, name).return_value = 0
    monkeypatch.setattr(orch, "_read_primary_artifact_bytes", lambda db, acc: b"<ownershipDocument/>")

    seen: dict[str, object] = {}

    def fake_parser(accession_number, content, form_type, *, submissions_lookup=None):
        seen["lookup"] = submissions_lookup
        return {}

    from edgar_warehouse import parsers

    monkeypatch.setattr(parsers, "get_parser", lambda form_type: fake_parser)

    sentinel = lambda cik: None
    orch._run_parse_pipeline(
        db=db, bookkeeping=db, accession_number="0001", sync_run_id="run-1", submissions_lookup=sentinel,
    )
    assert seen["lookup"] is sentinel
    assert db.complete_parse_run.call_args.kwargs["status"] == "succeeded"


def test_bronze_submissions_lookup_reads_the_newest_snapshot_by_glob(tmp_path):
    glob = orch.default_path_resolver().submissions_main_glob(1000001)
    assert glob == "submissions/sec/cik=1000001/main/*/*/*/CIK0001000001.json"
    older = tmp_path / glob.replace("*/*/*", "2024/01/01")
    newer = tmp_path / glob.replace("*/*/*", "2025/06/01")
    for path, entity_type in ((older, "operating"), (newer, "other")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"cik": "1000001", "name": "DOE JANE", "entityType": entity_type}))

    context = MagicMock()
    context.bronze_root = orch.StorageLocation(str(tmp_path))
    lookup = orch._bronze_submissions_lookup(context)

    assert lookup(1000001)["entityType"] == "other"
    assert lookup(1000001)["entityType"] == "other"  # cached, same answer
    assert lookup(4242424) is None


def test_bronze_submissions_lookup_reads_each_hit_once_and_rechecks_misses(tmp_path, monkeypatch):
    calls: list[int] = []
    real = orch._read_bronze_by_glob_if_present

    def counting(**kwargs):
        calls.append(kwargs["cik"])
        return real(**kwargs)

    monkeypatch.setattr(orch, "_read_bronze_by_glob_if_present", counting)
    glob = orch.default_path_resolver().submissions_main_glob(1000001)
    path = tmp_path / glob.replace("*/*/*", "2025/06/01")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"cik": "1000001", "entityType": "other"}))

    context = MagicMock()
    context.bronze_root = orch.StorageLocation(str(tmp_path))
    lookup = orch._bronze_submissions_lookup(context)
    for _ in range(3):
        lookup(1000001)
        lookup(4242424)
    assert calls.count(1000001) == 1
    assert calls.count(4242424) == 3


def test_artifact_pipeline_builds_the_lookup_once_per_run():
    import inspect

    src = inspect.getsource(orch._run_configured_form_artifact_pipeline)
    loop = src.index("for accession_index, accession_number in enumerate(selected_accessions")
    assert src.count("_bronze_submissions_lookup(context)") == 1
    assert src.index("_bronze_submissions_lookup(context)") < loop


def test_accession_resync_passes_a_bronze_lookup():
    import inspect

    src = inspect.getsource(orch._run_accession_resync)
    assert "submissions_lookup=_bronze_submissions_lookup(context)" in src


def test_lookup_attaches_the_snapshot_sha256(tmp_path):
    import hashlib

    from edgar_warehouse.parsers.ownership import SNAPSHOT_SHA256_KEY

    glob = orch.default_path_resolver().submissions_main_glob(1000001)
    path = tmp_path / glob.replace("*/*/*", "2025/06/01")
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"cik": "1000001", "entityType": "other"}).encode()
    path.write_bytes(body)
    context = MagicMock()
    context.bronze_root = orch.StorageLocation(str(tmp_path))
    payload = orch._bronze_submissions_lookup(context)(1000001)
    assert payload[SNAPSHOT_SHA256_KEY] == hashlib.sha256(body).hexdigest()
