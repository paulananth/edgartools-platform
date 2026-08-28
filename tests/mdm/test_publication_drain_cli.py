"""Unit coverage for `mdm publication-drain`'s CLI handler (Ticket 36,
change-propagation map).

Exercises the handler's own wiring -- that it constructs a real
drain_publication_queue call with sync_fn/verify_fn hooked to the
SnowflakeGraphSyncExecutor/SnowflakeGraphVerifier machinery
`mdm sync-graph`/`mdm verify-graph` already use, and turns the drain
result into the right exit code -- using stubbed Snowflake classes so this
runs on plain SQLite with no Docker/live Snowflake required. The queue
mechanics themselves are covered by tests/mdm/test_graph_publication_queue.py.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from edgar_warehouse.mdm import cli as mdm_cli
from edgar_warehouse.mdm.database import Base
from edgar_warehouse.mdm.publication import request_publication


def _session_with_one_pending_request() -> Session:
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    request_publication(session)
    session.commit()
    return session


def argparse_namespace_stub(**overrides):
    class _Args:
        pass

    args = _Args()
    args.owner = None
    args.max_requests = 1
    args.lease_seconds = None
    args.skip_native_app = True
    for key, value in overrides.items():
        setattr(args, key, value)
    return args


class _FakeSyncExecutor:
    calls: list[str] = []

    @classmethod
    def from_env(cls):
        return cls()

    def sync(self, config):
        _FakeSyncExecutor.calls.append(config.generation_id)


class _FakeVerifyResult:
    def __init__(self, passed: bool) -> None:
        self.passed = passed
        self.payload = {"passed": passed}


class _FakeVerifier:
    def __init__(self, connection, default_database=None) -> None:
        pass

    def verify(self, config):
        return _FakeVerifyResult(passed=True)


class _FakeConnection:
    def close(self) -> None:
        pass


class _FakeSettings:
    database = "FAKE_DB"

    @classmethod
    def from_env(cls):
        return cls()

    def connect(self):
        return _FakeConnection()


def _patch_snowflake_layer(monkeypatch: pytest.MonkeyPatch, *, verifier_cls=_FakeVerifier) -> None:
    monkeypatch.setattr(
        "edgar_warehouse.mdm.snowflake_graph.SnowflakeGraphSyncExecutor", _FakeSyncExecutor
    )
    monkeypatch.setattr("edgar_warehouse.mdm.snowflake_graph.SnowflakeGraphVerifier", verifier_cls)
    monkeypatch.setattr("edgar_warehouse.mdm.export.SnowflakeConnectionSettings", _FakeSettings)
    _FakeSyncExecutor.calls = []


def test_successful_drain_calls_sync_and_verify_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    _patch_snowflake_layer(monkeypatch)
    session = _session_with_one_pending_request()
    monkeypatch.setattr(mdm_cli, "_session", lambda: session)

    exit_code = mdm_cli._handle_publication_drain(argparse_namespace_stub())

    assert exit_code == 0
    assert len(_FakeSyncExecutor.calls) == 1
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["drained"]) == 1
    assert payload["drained"][0]["status"] == "graph_active"


def test_a_failed_verify_exits_nonzero(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    class _FailingVerifier(_FakeVerifier):
        def verify(self, config):
            return _FakeVerifyResult(passed=False)

    _patch_snowflake_layer(monkeypatch, verifier_cls=_FailingVerifier)
    session = _session_with_one_pending_request()
    monkeypatch.setattr(mdm_cli, "_session", lambda: session)

    exit_code = mdm_cli._handle_publication_drain(argparse_namespace_stub())

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["drained"][0]["status"] == "failed"


def test_empty_queue_exits_zero_with_no_drained_entries(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    _patch_snowflake_layer(monkeypatch)
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    monkeypatch.setattr(mdm_cli, "_session", lambda: session)

    exit_code = mdm_cli._handle_publication_drain(argparse_namespace_stub())

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["drained"] == []
