"""journal.record on a real Change Journal (ticket 22): it records each file a
run processed, a retry appends nothing new, its verifier reads every event
back, and the files then count as processed under that identity only."""

import json
from uuid import uuid4

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm.clean import changed_files
from edgar_warehouse.workers import journal_record
from tests.integration.test_configured_bookkeeping_postgres import databases  # noqa: F401

FILES = [{"key": f"warehouse/bronze/a/{n}.json", "uri": f"file:///capture/{n}.json", "sha256": f"{n}" * 64}
         for n in (1, 2)]


def envelope(store, tmp_path, body):
    return {"checks": [journal_record.CHECK], "claim": {"run_id": str(uuid4())},
            "input": store.put(tmp_path.as_uri() + "/inputs", body), "output": (tmp_path / "out.json").as_uri()}


def test_the_worker_records_each_file_once_and_its_verifier_reads_them_back(databases, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr(journal_record, "_journal", lambda: databases.ledger)
    store, source = Artifacts(), f"fixture.{uuid4().hex}"
    body = changed_files.record_input(source=source, feed="documents", processing="i" * 64, files=FILES,
                                      forced=False, as_of="2026-10-13T09:00:00-04:00")
    task = envelope(store, tmp_path, body)
    first = journal_record.execute(task, store)
    assert journal_record.execute(task, store) == first  # a retry appends the same events
    assert journal_record.verify({**task, "candidate": first}, store) == ({journal_record.CHECK: True}, [])
    pairs = [(f["key"], f["sha256"]) for f in FILES]
    assert changed_files.unprocessed(databases.ledger, source, "i" * 64, pairs) == []
    assert changed_files.unprocessed(databases.ledger, source, "j" * 64, pairs) == [f["key"] for f in FILES]
    changed = [(FILES[0]["key"], "9" * 64), pairs[1]]
    assert changed_files.unprocessed(databases.ledger, source, "i" * 64, changed) == [FILES[0]["key"]]


def test_the_verifier_refuses_receipts_that_do_not_match_the_files(databases, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr(journal_record, "_journal", lambda: databases.ledger)
    store, source = Artifacts(), f"fixture.{uuid4().hex}"
    body = changed_files.record_input(source=source, feed="documents", processing="i" * 64, files=FILES,
                                      forced=False, as_of="2026-10-13T13:00:00Z")
    task = envelope(store, tmp_path, body)
    first = journal_record.execute(task, store)
    one = changed_files.record_input(source=source, feed="documents", processing="i" * 64, files=FILES[:1],
                                     forced=False, as_of="2026-10-13T13:00:00Z")
    with pytest.raises(ValueError, match="every file"):
        journal_record.verify({**envelope(store, tmp_path, one), "output": task["output"], "candidate": first}, store)


def test_a_forced_rerun_and_a_file_another_run_recorded_first_keep_the_first_record(databases, tmp_path, monkeypatch):  # noqa: F811
    # Review, 2026-10-13: a forced run over recorded files must finish, not conflict after its merge.
    monkeypatch.setattr(journal_record, "_journal", lambda: databases.ledger)
    store, source = Artifacts(), f"fixture.{uuid4().hex}"
    first = changed_files.record_input(source=source, feed="documents", processing="i" * 64, files=FILES[:1],
                                       forced=False, as_of="2026-10-13T13:00:00Z")
    earlier = envelope(store, tmp_path / "a", first)
    recorded = journal_record.execute(earlier, store)
    forced = changed_files.record_input(source=source, feed="documents", processing="i" * 64, files=FILES,
                                        forced=True, as_of="2026-10-14T13:00:00Z")
    task = envelope(store, tmp_path / "b", forced)
    result = journal_record.execute(task, store)
    assert journal_record.verify({**task, "candidate": result}, store) == ({journal_record.CHECK: True}, [])
    receipts = json.loads(store.verified(result))["receipts"]
    kept = json.loads(store.verified(recorded))["receipts"][0]
    assert receipts[0] == kept  # the first record of the file stands
    assert receipts[1]["event"]["run_id"] == task["claim"]["run_id"]  # the file not yet recorded
    assert receipts[2]["event"]["event_type"] == "files.forced" and receipts[2]["event"]["scope"]["files"] == "2"


def test_a_file_key_the_journal_cannot_hold_is_refused_before_any_work():
    with pytest.raises(ValueError, match="too long"):
        changed_files.event_key("fixture", "i" * 64, "k" * 2048, "s" * 64)
