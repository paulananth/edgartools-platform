from __future__ import annotations

from edgar_warehouse.acquisition.database import get_engine


def test_change_ledger_url_is_preferred_over_mdm(monkeypatch) -> None:
    monkeypatch.setenv("CHANGE_LEDGER_DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://postgres:test@127.0.0.1:5432/mdm")
    engine = get_engine()
    assert engine.url.get_backend_name() == "sqlite"


def test_change_ledger_falls_back_to_mdm_url(monkeypatch) -> None:
    monkeypatch.delenv("CHANGE_LEDGER_DATABASE_URL", raising=False)
    monkeypatch.setenv("MDM_DATABASE_URL", "sqlite:///:memory:")
    engine = get_engine()
    assert engine.url.get_backend_name() == "sqlite"
