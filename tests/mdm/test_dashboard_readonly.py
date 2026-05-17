from __future__ import annotations

from pathlib import Path

import pytest

from edgar_warehouse.mdm.database import MdmCompany, MdmEntity


MDM_UNAVAILABLE_COPY = (
    "MDM database unavailable. Check `MDM_DATABASE_URL`, confirm the database "
    "is reachable, and restart the dashboard."
)


def _seed_company(session, cik: int = 320193, name: str = "Apple Inc.") -> None:
    entity = MdmEntity(entity_type="company", resolution_method="test", confidence=1.0)
    session.add(entity)
    session.flush()
    session.add(MdmCompany(entity_id=entity.entity_id, cik=cik, canonical_name=name))
    session.commit()


def test_check_mdm_status_returns_structured_connected_status(db_session):
    from edgar_warehouse.mdm.dashboard_readonly import (
        MdmDashboardStatus,
        check_mdm_status,
    )

    status = check_mdm_status(session=db_session)

    assert isinstance(status, MdmDashboardStatus)
    assert status.connected is True
    assert status.message == "MDM database connected."
    assert status.env_var == "MDM_DATABASE_URL"
    assert status.details["entity_types"] >= 4


def test_run_mdm_smoke_query_returns_bounded_structured_rows(db_session):
    from edgar_warehouse.mdm.dashboard_readonly import MdmSmokeResult, run_mdm_smoke_query

    _seed_company(db_session, cik=320193, name="Apple Inc.")
    _seed_company(db_session, cik=789019, name="Microsoft Corp.")

    result = run_mdm_smoke_query(session=db_session, limit=1)

    assert isinstance(result, MdmSmokeResult)
    assert result.available is True
    assert result.limit == 1
    assert len(result.rows) == 1
    assert result.rows[0]["entity_type"] == "company"
    assert result.rows[0]["cik"] == 320193
    assert result.rows[0]["canonical_name"] == "Apple Inc."


def test_helpers_never_commit(db_session, monkeypatch):
    from edgar_warehouse.mdm import dashboard_readonly

    def fail_commit():
        raise AssertionError("dashboard read-only helpers must not commit")

    monkeypatch.setattr(db_session, "commit", fail_commit)

    dashboard_readonly.check_mdm_status(session=db_session)
    dashboard_readonly.run_mdm_smoke_query(session=db_session, limit=5)


def test_missing_mdm_configuration_uses_safe_status_copy(monkeypatch):
    from edgar_warehouse.mdm.dashboard_readonly import (
        MdmDashboardStatus,
        check_mdm_status,
    )

    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)

    status = check_mdm_status()

    assert isinstance(status, MdmDashboardStatus)
    assert status.connected is False
    assert status.message == MDM_UNAVAILABLE_COPY
    assert status.env_var == "MDM_DATABASE_URL"
    assert "MDM_DATABASE_URL" in status.as_dict()["message"]


def test_failed_mdm_connection_does_not_leak_dsn_or_raw_exception(monkeypatch):
    from edgar_warehouse.mdm.dashboard_readonly import check_mdm_status

    secret_dsn = "postgresql://dashboard_user:super-secret@example.internal/mdm"

    def fail_engine():
        raise RuntimeError(f"could not connect to {secret_dsn}")

    monkeypatch.setenv("MDM_DATABASE_URL", secret_dsn)
    monkeypatch.setattr("edgar_warehouse.mdm.dashboard_readonly.get_engine", fail_engine)

    status = check_mdm_status()
    payload = status.as_dict()
    rendered = repr(payload)

    assert payload["connected"] is False
    assert payload["message"] == MDM_UNAVAILABLE_COPY
    assert "MDM_DATABASE_URL" in rendered
    assert "super-secret" not in rendered
    assert "dashboard_user" not in rendered
    assert "example.internal" not in rendered
    assert "could not connect" not in rendered


def test_run_mdm_smoke_query_returns_safe_unavailable_result(monkeypatch):
    from edgar_warehouse.mdm.dashboard_readonly import MdmSmokeResult, run_mdm_smoke_query

    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)

    result = run_mdm_smoke_query()

    assert isinstance(result, MdmSmokeResult)
    assert result.available is False
    assert result.message == MDM_UNAVAILABLE_COPY
    assert result.rows == []
    assert result.error_env_var == "MDM_DATABASE_URL"


def test_dashboard_readonly_module_avoids_mutation_surfaces():
    module_text = Path("edgar_warehouse/mdm/dashboard_readonly.py").read_text()

    blocked_tokens = [
        "MDMPipeline",
        "migrations.runtime",
        "ResolverContext",
        "CompanyResolver",
        "AdviserResolver",
        "FundResolver",
        "PersonResolver",
        "SecurityResolver",
        "stewardship",
        "GraphSyncEngine",
        "sync_pending",
        "sync_entities",
        "_handle_run",
        "_handle_migrate",
        "_handle_sync_graph",
        "_handle_derive_relationships",
        "_handle_load_relationships",
        "commit(",
        ".commit",
    ]
    for token in blocked_tokens:
        assert token not in module_text


def test_helpers_return_plain_structures_without_stdout_parsing(db_session, capsys):
    from edgar_warehouse.mdm.dashboard_readonly import (
        check_mdm_status,
        run_mdm_smoke_query,
    )

    status = check_mdm_status(session=db_session)
    smoke = run_mdm_smoke_query(session=db_session)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert isinstance(status.as_dict(), dict)
    assert isinstance(smoke.as_dict(), dict)
