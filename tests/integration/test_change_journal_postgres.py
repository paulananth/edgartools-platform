"""Required PG16 qualification, using restricted runtime connections."""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.bookkeeping.clean.config import Blocked, canonical
from edgar_warehouse.change_journal import JournalConflict, envelope
from edgar_warehouse.change_journal.database import migrate
from tests.integration.test_configured_bookkeeping_postgres import databases


def event(**changes):
    return envelope(
        producer="fixture",
        event_key=str(uuid4()),
        run_id=str(uuid4()),
        source="unseen.provider",
        feed="new-feed",
        event_type="capture.authorized",
        occurred_at=datetime.now(UTC).isoformat(),
        evidence=[{"uri": "s3://fixture/manifest.json", "sha256": "a" * 64}],
        **changes,
    )


def test_append_duplicate_conflict_and_verified_receipt(databases):
    value = event()
    first = databases.ledger.append(value)
    assert databases.ledger.append(deepcopy(value)) == first
    assert databases.ledger.verify(first, expected=value) == first
    assert (
        first["canonical_hash"] == hashlib.sha256(canonical(value).encode()).hexdigest()
    )
    with pytest.raises(JournalConflict):
        databases.ledger.append({**value, "event_type": "capture.excluded"})
    damaged = {**first, "canonical_hash": "b" * 64}
    with pytest.raises(JournalConflict):
        databases.ledger.verify(damaged)
    with pytest.raises(JournalConflict):
        databases.ledger.verify({**first, "id": first["id"] + 1})


def test_concurrent_identical_and_conflicting_keys(databases):
    value = event()
    with ThreadPoolExecutor(max_workers=8) as pool:
        receipts = list(pool.map(lambda _: databases.ledger.append(value), range(16)))
    assert all(r == receipts[0] for r in receipts)
    key = event()

    def append(i):
        try:
            return databases.ledger.append({**key, "feed": f"feed-{i}"})
        except JournalConflict:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(append, range(8)))
    assert sum(r is not None for r in results) == 1


def test_one_table_restricted_runtime_and_append_only_even_for_owner(databases):
    with databases.ledger_admin.connect() as conn:
        assert conn.scalars(
            text("SELECT tablename FROM pg_tables WHERE schemaname='journal'")
        ).all() == ["event"]
        assert (
            conn.scalar(text("SELECT to_regclass('bookkeeping_mirror.event')")) is None
        )
        assert conn.scalar(text("SELECT to_regclass('mdm_mirror.event')")) is None
    for statement in (
        "SELECT * FROM journal.event",
        "DELETE FROM journal.event",
        "TRUNCATE journal.event",
        "SELECT journal.immutable()",
        "CREATE TABLE journal.bad(id int)",
    ):
        with pytest.raises(DBAPIError), databases.ledger.engine.begin() as conn:
            conn.execute(text(statement))
    for statement in (
        "DELETE FROM journal.event",
        "UPDATE journal.event SET source='bad'",
        "TRUNCATE journal.event",
    ):
        with pytest.raises(DBAPIError), databases.ledger_admin.begin() as conn:
            conn.execute(text(statement))


def test_bounded_inspection_scopes_and_hash_rejection(databases):
    value = event()
    databases.ledger.append(value)
    found = databases.ledger.list(
        source=value["source"], feed=value["feed"], run_id=value["run_id"], limit=1
    )
    assert len(found) == 1 and found[0]["event"] == value
    assert databases.ledger.list(run_id=str(uuid4())) == []
    for n in (0, -1, 1001, True):
        with pytest.raises(ValueError):
            databases.ledger.list(limit=n)
    with pytest.raises(DBAPIError), databases.ledger.engine.begin() as conn:
        conn.execute(
            text("SELECT journal.append(:b,:h)"), {"b": canonical(value), "h": "b" * 64}
        )


def test_migration_drift_wrong_database_and_runtime_owner_rejected(databases):
    first = migrate(databases.ledger_admin, runtime_role="ledger_runtime")
    assert migrate(databases.ledger_admin, runtime_role="ledger_runtime") == first
    with pytest.raises(Blocked):
        migrate(databases.admin, runtime_role="bk_runtime")
    with pytest.raises(Blocked):
        migrate(databases.ledger.engine, runtime_role="ledger_runtime")
    with databases.ledger_admin.begin() as conn:
        saved = conn.scalar(
            text(
                "SELECT obj_description(oid,'pg_namespace') FROM pg_namespace WHERE nspname='journal'"
            )
        )
        conn.exec_driver_sql('COMMENT ON SCHEMA journal IS \'{"001_event.sql":"bad"}\'')
    try:
        with pytest.raises(Blocked):
            migrate(databases.ledger_admin, runtime_role="ledger_runtime")
    finally:
        with databases.ledger_admin.begin() as conn:
            conn.exec_driver_sql(
                "COMMENT ON SCHEMA journal IS '" + saved.replace("'", "''") + "'"
            )


def test_cli_inspection_and_receipt_verification(
    databases, tmp_path, monkeypatch, capsys
):
    from edgar_warehouse.cli import main

    monkeypatch.setenv(
        "CHANGE_JOURNAL_DATABASE_URL",
        databases.ledger.engine.url.render_as_string(hide_password=False),
    )
    value = event()
    receipt = databases.ledger.append(value)
    path = tmp_path / "receipt.json"
    path.write_text(canonical(receipt))
    assert main(["change-journal", "verify", str(path)]) == 0
    assert str(receipt["id"]) in capsys.readouterr().out
    assert (
        main(["change-journal", "events", "--run-id", value["run_id"], "--limit", "1"])
        == 0
    )
    assert value["event_key"] in capsys.readouterr().out
    assert (
        main(
            [
                "change-journal",
                "status",
                "--source",
                "unseen.provider",
                "--feed",
                "new-feed",
            ]
        )
        == 0
    )


def test_journal_cli_init_and_migrate_use_owner_and_preserve_events(databases, monkeypatch, capsys):
    from edgar_warehouse.cli import main

    with databases.ledger_admin.connect() as conn:
        before = conn.scalar(text("SELECT count(*) FROM journal.event"))
    monkeypatch.setenv(
        "CHANGE_JOURNAL_MIGRATION_DATABASE_URL",
        databases.ledger_admin.url.render_as_string(hide_password=False),
    )
    assert main(["change-journal", "init", "--runtime-role", "ledger_runtime"]) == 0
    assert "001_event.sql" in capsys.readouterr().out
    assert main(["change-journal", "migrate", "--runtime-role", "ledger_runtime"]) == 0
    assert "001_event.sql" in capsys.readouterr().out
    with databases.ledger_admin.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM journal.event")) == before


def test_no_legacy_or_mdm_connection_fallback(monkeypatch):
    from edgar_warehouse.change_journal.store import get_engine

    monkeypatch.delenv("CHANGE_JOURNAL_DATABASE_URL", raising=False)
    monkeypatch.setenv("CHANGE_LEDGER_DATABASE_URL", "postgresql://legacy/legacy")
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://legacy/mdm")
    with pytest.raises(KeyError):
        get_engine()


def test_canonical_unicode_timezone_and_direct_noncanonical_rejection(databases):
    value = event(scope={"unicode": "café 🧭", "quoted": '"line\nkey'})
    first = databases.ledger.append(value)
    with databases.ledger.engine.begin() as conn:
        conn.execute(text("SET LOCAL TIME ZONE 'America/New_York'"))
        assert (
            conn.scalar(
                text("SELECT journal.get(:p,:k)"),
                {"p": value["producer"], "k": value["event_key"]},
            )
            == first
        )
    import json

    body = json.dumps(event(), indent=2, ensure_ascii=False)
    with pytest.raises(DBAPIError), databases.ledger.engine.begin() as conn:
        conn.execute(
            text("SELECT journal.append(:b,:h)"),
            {"b": body, "h": hashlib.sha256(body.encode()).hexdigest()},
        )
    with pytest.raises(ValueError):
        event(scope=[])


def test_legacy_root_rejected_without_mutating_its_control_or_delivery(
    databases, tmp_path
):
    from edgar_warehouse.bookkeeping.clean.config import digest
    from tests.integration.test_configured_bookkeeping_postgres import submit

    book, rid, _, _ = submit(databases, tmp_path, count=1)
    root, configuration, _, items = book._frozen(rid)
    legacy = {k: v for k, v in root["submission"].items() if k != "journal"}
    old_run = str(uuid4())
    with databases.runtime.begin() as conn:
        conn.execute(
            text(
                "SELECT bookkeeping.start_run(CAST(:r AS uuid),CAST(:s AS jsonb),:h,CAST(:w AS jsonb))"
            ),
            {
                "r": old_run,
                "s": canonical(legacy),
                "h": digest(legacy),
                "w": canonical(items),
            },
        )
    before = book.status(old_run)
    with pytest.raises(Blocked):
        book.resume(old_run)
    with pytest.raises(Blocked):
        book.deliver(databases.ledger, old_run)
    assert book.status(old_run) == before


def test_cli_delivery_recovery_reports_pending_without_executing_work(
    databases, tmp_path, monkeypatch, capsys
):
    from edgar_warehouse.cli import main
    from tests.integration.test_configured_bookkeeping_postgres import complete, submit

    book, rid, _, _ = submit(databases, tmp_path, count=1)
    complete(book, rid)
    monkeypatch.setenv(
        "BOOKKEEPING_CLEAN_DATABASE_URL",
        databases.runtime.url.render_as_string(hide_password=False),
    )
    monkeypatch.setenv(
        "CHANGE_JOURNAL_DATABASE_URL",
        databases.ledger.engine.url.render_as_string(hide_password=False),
    )
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)
    original = databases.ledger.append

    def unavailable(*args, **kwargs):
        raise ConnectionError("offline")

    monkeypatch.setattr(
        "edgar_warehouse.change_journal.store.ChangeJournal.append", unavailable
    )
    assert main(["change-journal", "recover", "bookkeeping", rid, "--limit", "1"]) == 3
    assert book.status(rid)["pending_deliveries"] == 1
    monkeypatch.setattr(
        "edgar_warehouse.change_journal.store.ChangeJournal.append",
        lambda self, value: original(value),
    )
    assert main(["change-journal", "recover", "bookkeeping", rid, "--limit", "1"]) == 0
    assert book.status(rid)["pending_deliveries"] == 0
    assert book.status(rid)["counts"] == {"verified": 1}
    capsys.readouterr()


def test_bookkeeping_producer_timezone_retains_identical_retry_receipt(
    databases, tmp_path
):
    from sqlalchemy import create_engine
    from edgar_warehouse.bookkeeping.clean.capabilities import standard_registry
    from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
    from tests.integration.test_configured_bookkeeping_postgres import complete, submit

    timezone_engine = create_engine(
        databases.runtime.url, connect_args={"options": "-c timezone=America/New_York"}
    )
    try:
        book = Bookkeeping(timezone_engine, standard_registry())
        book, rid, _, _ = submit(databases, tmp_path, count=1, book=book)
        complete(book, rid)
        assert book.deliver(databases.ledger, rid) == 1
        with timezone_engine.connect() as conn:
            event = (
                conn.execute(
                    text(
                        "SELECT * FROM bookkeeping.journal_outbox WHERE run_id=CAST(:r AS uuid)"
                    ),
                    {"r": rid},
                )
                .mappings()
                .one()
            )
        receipt = databases.ledger.get("bookkeeping", str(event["event_id"]))
        assert receipt["event"]["occurred_at"].endswith("+00:00")
        other_timezone = Bookkeeping(databases.runtime, standard_registry())
        with databases.runtime.connect() as conn:
            same = (
                conn.execute(
                    text(
                        "SELECT * FROM bookkeeping.journal_outbox WHERE run_id=CAST(:r AS uuid)"
                    ),
                    {"r": rid},
                )
                .mappings()
                .one()
            )
        assert databases.ledger.append(other_timezone.journal_event(same)) == receipt
    finally:
        timezone_engine.dispose()
