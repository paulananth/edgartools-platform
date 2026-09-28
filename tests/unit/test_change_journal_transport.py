"""Real HTTP transport checks, using bounded in-memory provider responses."""

from __future__ import annotations

import httpx
import pytest

from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.infrastructure.sec_client import download_provider_conditionally


@pytest.mark.parametrize(
    "url",
    [
        "https://fixture.invalid/feed/../outside",
        "https://fixture.invalid/feed/%2e%2e/outside",
        "https://fixture.invalid/feed/%252e%252e/outside",
        "https://fixture.invalid/feed/%2e%2e%2foutside",
        "https://fixture.invalid/feed/%5coutside",
        "https://fixture.invalid/feed/one\n",
        "https://fixture.invalid:bad/feed/one",
    ],
)
def test_approved_coverage_rejects_provider_path_normalization(url):
    from edgar_warehouse.change_journal.capture import _approved_url

    assert not _approved_url(url, ["https://fixture.invalid/feed/"])


def test_approved_coverage_accepts_normal_member_path():
    from edgar_warehouse.change_journal.capture import _approved_url

    assert _approved_url(
        "https://fixture.invalid/feed/release-1.xml.zip",
        ["https://fixture.invalid/feed/"],
    )


def client_for(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )


def test_authority_checked_before_request_and_304_preserves_prior(monkeypatch):
    calls = []

    def provider(request):
        assert calls == ["authorized"]
        assert request.headers["If-None-Match"] == '"old"'
        calls.append("requested")
        return httpx.Response(304, headers={"ETag": '"old"'})

    client_for(monkeypatch, provider)
    result = download_provider_conditionally(
        "https://fixture.invalid/data",
        "Test test@example.com",
        etag='"old"',
        before_request=lambda: calls.append("authorized"),
        max_bytes=10,
    )
    assert result.not_modified and result.content == b"" and result.etag == '"old"'


def test_missing_authority_prevents_network(monkeypatch):
    calls = []
    client_for(monkeypatch, lambda request: calls.append(request))

    def refuse():
        raise ValueError("Journal acknowledgement unavailable")

    with pytest.raises(ValueError):
        download_provider_conditionally(
            "https://fixture.invalid/data",
            "Test test@example.com",
            before_request=refuse,
            max_bytes=10,
        )
    assert calls == []


@pytest.mark.parametrize(
    "status,payload", [(200, b"over-size-limit"), (302, b""), (206, b"partial")]
)
def test_partial_redirect_and_oversize_fail_closed(monkeypatch, status, payload):
    calls = []

    def provider(request):
        calls.append(request.url)
        return httpx.Response(
            status, content=payload, headers={"Location": "https://other.invalid/"}
        )

    client_for(monkeypatch, provider)
    with pytest.raises(WarehouseRuntimeError):
        download_provider_conditionally(
            "https://fixture.invalid/data",
            "Test test@example.com",
            before_request=lambda: None,
            max_bytes=4,
        )
    assert len(calls) == 1


@pytest.mark.parametrize("legacy_url", [None, "postgresql://legacy/legacy"])
def test_fresh_runtime_cannot_open_legacy_acquisition_or_fall_back_to_mdm(
    monkeypatch, legacy_url
):
    from edgar_warehouse.acquisition.database import get_engine

    monkeypatch.setenv(
        "CHANGE_JOURNAL_DATABASE_URL", "postgresql://fresh/change_journal_clean"
    )
    monkeypatch.setenv("CHANGE_LEDGER_DATABASE_URL", "postgresql://legacy/legacy")
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://legacy/mdm")
    with pytest.raises(RuntimeError, match="retired"):
        get_engine(legacy_url)


def test_retired_control_connections_refuse_explicit_urls_without_fresh_env(monkeypatch):
    from edgar_warehouse.acquisition.database import get_engine as acquisition_engine
    from edgar_warehouse.bookkeeping.database import get_engine as bookkeeping_engine

    monkeypatch.delenv("CHANGE_JOURNAL_DATABASE_URL", raising=False)
    for factory in (acquisition_engine, bookkeeping_engine):
        with pytest.raises(RuntimeError, match="retired"):
            factory("sqlite:///:memory:")


def test_runnable_cli_does_not_expose_retired_commands():
    from edgar_warehouse.cli import _runtime_parser

    parser = _runtime_parser()
    with pytest.raises(SystemExit) as error:
        parser.parse_args(["capture-filing-artifact"])
    assert error.value.code == 2
    with pytest.raises(SystemExit) as error:
        parser.parse_args(["mdm", "mastering"])
    assert error.value.code == 2


def test_fresh_runtime_refuses_legacy_cli_before_dispatch(monkeypatch):
    from edgar_warehouse.cli import main

    monkeypatch.setenv(
        "CHANGE_JOURNAL_DATABASE_URL", "postgresql://fresh/change_journal_clean"
    )
    calls = []
    monkeypatch.setattr(
        "edgar_warehouse.cli.run_command", lambda *args: calls.append(args)
    )
    with pytest.raises(SystemExit) as error:
        main(["seed-universe", "--limit", "1"])
    assert error.value.code == 2 and calls == []


def test_fresh_runtime_refuses_ungated_sec_fetch_before_transport(monkeypatch):
    from edgar_warehouse.infrastructure.sec_client import download_sec_bytes

    monkeypatch.setenv(
        "CHANGE_JOURNAL_DATABASE_URL", "postgresql://fresh/change_journal_clean"
    )
    calls = []
    client_for(monkeypatch, lambda request: calls.append(request))
    with pytest.raises(WarehouseRuntimeError, match="Bookkeeping authority"):
        download_sec_bytes(
            "https://data.sec.gov/submissions/CIK0000320193.json",
            "Test test@example.com",
        )
    assert calls == []
