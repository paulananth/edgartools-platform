"""Real HTTP transport checks, using bounded in-memory provider responses."""
from __future__ import annotations

import httpx
import pytest

from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.infrastructure.sec_client import download_provider_conditionally


def client_for(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))


def test_authority_checked_before_request_and_304_preserves_prior(monkeypatch):
    calls = []
    def provider(request):
        assert calls == ["authorized"]
        assert request.headers["If-None-Match"] == '"old"'
        calls.append("requested")
        return httpx.Response(304, headers={"ETag": '"old"'})
    client_for(monkeypatch, provider)
    result = download_provider_conditionally("https://fixture.invalid/data", "Test test@example.com",
        etag='"old"', before_request=lambda: calls.append("authorized"), max_bytes=10)
    assert result.not_modified and result.content == b"" and result.etag == '"old"'


def test_missing_authority_prevents_network(monkeypatch):
    calls = []
    client_for(monkeypatch, lambda request: calls.append(request))
    def refuse():
        raise ValueError("Journal acknowledgement unavailable")
    with pytest.raises(ValueError):
        download_provider_conditionally("https://fixture.invalid/data", "Test test@example.com",
            before_request=refuse, max_bytes=10)
    assert calls == []


@pytest.mark.parametrize("status,payload", [(200, b"over-size-limit"), (302, b""), (206, b"partial")])
def test_partial_redirect_and_oversize_fail_closed(monkeypatch, status, payload):
    calls = []
    def provider(request):
        calls.append(request.url)
        return httpx.Response(status, content=payload, headers={"Location": "https://other.invalid/"})
    client_for(monkeypatch, provider)
    with pytest.raises(WarehouseRuntimeError):
        download_provider_conditionally("https://fixture.invalid/data", "Test test@example.com",
            before_request=lambda: None, max_bytes=4)
    assert len(calls) == 1


@pytest.mark.parametrize("legacy_url", [None, "postgresql://legacy/legacy"])
def test_fresh_runtime_cannot_open_legacy_acquisition_or_fall_back_to_mdm(monkeypatch, legacy_url):
    from edgar_warehouse.acquisition.database import get_engine
    monkeypatch.setenv("CHANGE_JOURNAL_DATABASE_URL", "postgresql://fresh/change_journal_clean")
    monkeypatch.setenv("CHANGE_LEDGER_DATABASE_URL", "postgresql://legacy/legacy")
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://legacy/mdm")
    with pytest.raises(WarehouseRuntimeError, match="original stack"):
        get_engine(legacy_url)
