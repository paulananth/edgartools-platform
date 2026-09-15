"""Tests for MDM helpers and silver-owned warehouse tracking state.

MDM remains an explicit entity-management subsystem, but warehouse pipeline
tracking_status lives in sec_company_sync_state.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from edgar_warehouse.application.errors import WarehouseRuntimeError


# ---------------------------------------------------------------------------
# _get_mdm_tracked_ciks — MDM is required, no fallback
# ---------------------------------------------------------------------------

def test_get_mdm_tracked_ciks_raises_without_url(monkeypatch):
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)
    from edgar_warehouse.application.warehouse_orchestrator import _get_mdm_tracked_ciks
    with pytest.raises(WarehouseRuntimeError, match="MDM_DATABASE_URL is required"):
        _get_mdm_tracked_ciks("active")


def test_get_mdm_tracked_ciks_raises_on_connection_failure(monkeypatch):
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://localhost/test")
    with patch("edgar_warehouse.mdm.database.get_engine", side_effect=Exception("no DB")):
        from edgar_warehouse.application.warehouse_orchestrator import _get_mdm_tracked_ciks
        with pytest.raises(Exception, match="no DB"):
            _get_mdm_tracked_ciks("active")


def test_get_mdm_tracked_ciks_returns_ciks_from_mdm(monkeypatch):
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://localhost/test")
    from edgar_warehouse.application.warehouse_orchestrator import _get_mdm_tracked_ciks

    with patch("edgar_warehouse.mdm.database.get_engine", return_value=MagicMock()):
        with patch("edgar_warehouse.mdm.universe.get_tracked_ciks", return_value=[100, 200]):
            result = _get_mdm_tracked_ciks("active")

    assert result == [100, 200]


# ---------------------------------------------------------------------------
# _resolve_target_ciks — MDM only, no DuckDB fallback
# ---------------------------------------------------------------------------

def test_resolve_target_ciks_uses_mdm(monkeypatch):
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://localhost/test")
    from edgar_warehouse.application.warehouse_orchestrator import _resolve_target_ciks

    with patch(
        "edgar_warehouse.application.warehouse_orchestrator._get_mdm_tracked_ciks",
        return_value=[100, 200],
    ):
        result = _resolve_target_ciks(
            raw_ciks=None,
            command_name="bootstrap-full",
            tracking_status_filter="active",
        )

    assert result == [100, 200]


def test_resolve_target_ciks_raises_when_mdm_empty(monkeypatch):
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://localhost/test")
    from edgar_warehouse.application.warehouse_orchestrator import _resolve_target_ciks

    with patch(
        "edgar_warehouse.application.warehouse_orchestrator._get_mdm_tracked_ciks",
        return_value=[],
    ):
        with pytest.raises(WarehouseRuntimeError, match="seeded MDM universe"):
            _resolve_target_ciks(
                raw_ciks=None,
                command_name="bootstrap-full",
                tracking_status_filter="active",
            )


def test_resolve_target_ciks_raises_without_mdm_url(monkeypatch):
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)
    from edgar_warehouse.application.warehouse_orchestrator import _resolve_target_ciks

    with pytest.raises(WarehouseRuntimeError, match="MDM_DATABASE_URL is required"):
        _resolve_target_ciks(
            raw_ciks=None,
            command_name="bootstrap-full",
            tracking_status_filter="active",
        )


def test_resolve_target_ciks_respects_raw_ciks(monkeypatch):
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://localhost/test")
    from edgar_warehouse.application.warehouse_orchestrator import _resolve_target_ciks

    with patch(
        "edgar_warehouse.application.warehouse_orchestrator._get_mdm_tracked_ciks"
    ) as mock_mdm:
        result = _resolve_target_ciks(
            raw_ciks=["12345", "67890"],
            command_name="bootstrap-full",
            tracking_status_filter="active",
        )

    mock_mdm.assert_not_called()
    assert result == [12345, 67890]


# ---------------------------------------------------------------------------
# _filter_ciks_to_universe — silver tracking state
# ---------------------------------------------------------------------------

def test_filter_ciks_to_universe_filters_by_silver_tracking_state(monkeypatch):
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)
    from edgar_warehouse.application.warehouse_orchestrator import _filter_ciks_to_universe

    bookkeeping = MagicMock()
    bookkeeping.get_tracked_ciks.return_value = [100, 200]
    result = _filter_ciks_to_universe([100, 200, 300], bookkeeping=bookkeeping)

    assert result == [100, 200]


def test_filter_ciks_to_universe_passes_through_when_silver_empty(monkeypatch):
    """Cold-start guard: if silver returns no active CIKs, pass all impacted CIKs through."""
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)
    from edgar_warehouse.application.warehouse_orchestrator import _filter_ciks_to_universe

    bookkeeping = MagicMock()
    bookkeeping.get_tracked_ciks.return_value = []
    result = _filter_ciks_to_universe([100, 200, 300], bookkeeping=bookkeeping)

    assert result == [100, 200, 300]


def test_filter_ciks_to_universe_does_not_require_mdm_url(monkeypatch):
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)
    from edgar_warehouse.application.warehouse_orchestrator import _filter_ciks_to_universe

    bookkeeping = MagicMock()
    bookkeeping.get_tracked_ciks.return_value = [100]

    assert _filter_ciks_to_universe([100, 200, 300], bookkeeping=bookkeeping) == [100]


# ---------------------------------------------------------------------------
# _sync_mdm_tracking_status — raises on failure, no silent swallow
# ---------------------------------------------------------------------------

def test_sync_mdm_tracking_status_raises_without_url(monkeypatch):
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)
    from edgar_warehouse.application.warehouse_orchestrator import _sync_mdm_tracking_status
    with pytest.raises(WarehouseRuntimeError, match="MDM_DATABASE_URL is required"):
        _sync_mdm_tracking_status(1234, "active")


def test_sync_mdm_tracking_status_calls_update_when_url_set(monkeypatch):
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://localhost/test")
    from edgar_warehouse.application.warehouse_orchestrator import _sync_mdm_tracking_status

    with patch("edgar_warehouse.mdm.database.get_engine", return_value=MagicMock()):
        with patch("edgar_warehouse.mdm.universe.update_tracking_status", return_value=True) as mock_update:
            _sync_mdm_tracking_status(1234, "active")
    mock_update.assert_called_once()
    args = mock_update.call_args[0]
    assert args[1] == 1234
    assert args[2] == "active"


def test_sync_mdm_tracking_status_raises_on_db_failure(monkeypatch):
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://localhost/test")
    from edgar_warehouse.application.warehouse_orchestrator import _sync_mdm_tracking_status

    with patch("edgar_warehouse.mdm.database.get_engine", side_effect=Exception("DB down")):
        with pytest.raises(Exception, match="DB down"):
            _sync_mdm_tracking_status(1234, "active")


# ---------------------------------------------------------------------------
# _mdm_auto_enroll — best-effort, non-fatal
# ---------------------------------------------------------------------------

def test_mdm_auto_enroll_calls_bulk_upsert(monkeypatch):
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://localhost/test")
    from edgar_warehouse.application.warehouse_orchestrator import _mdm_auto_enroll

    with patch("edgar_warehouse.mdm.database.get_engine", return_value=MagicMock()):
        with patch("edgar_warehouse.mdm.universe.bulk_upsert_universe", return_value=3) as mock_upsert:
            _mdm_auto_enroll([100, 200, 300], scope_reason="daily_index")

    mock_upsert.assert_called_once()
    rows_arg = mock_upsert.call_args[0][1]
    assert {r["cik"] for r in rows_arg} == {100, 200, 300}


def test_mdm_auto_enroll_is_noop_without_url(monkeypatch):
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)
    from edgar_warehouse.application.warehouse_orchestrator import _mdm_auto_enroll
    _mdm_auto_enroll([100, 200], scope_reason="daily_index")  # must not raise


def test_mdm_auto_enroll_does_not_raise_on_db_failure(monkeypatch):
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://localhost/test")
    from edgar_warehouse.application.warehouse_orchestrator import _mdm_auto_enroll

    with patch("edgar_warehouse.mdm.database.get_engine", side_effect=Exception("DB down")):
        _mdm_auto_enroll([100], scope_reason="daily_index")  # must not raise


# ---------------------------------------------------------------------------
# _resolve_bootstrap_target_ciks — cik_limit/cik_offset (Wave 0 stubs)
# ---------------------------------------------------------------------------

def test_resolve_bootstrap_target_ciks_applies_cik_offset_then_cik_limit(monkeypatch):
    """_resolve_bootstrap_target_ciks honors cik_limit/cik_offset when both are provided.

    Verifies that offset is applied before limit:
    input [100, 200, 300, 400, 500], offset=1, limit=2 -> [200, 300]
    """
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://localhost/test")
    from edgar_warehouse.application.warehouse_orchestrator import _resolve_bootstrap_target_ciks

    bookkeeping = MagicMock()
    bookkeeping.get_tracked_ciks.return_value = [100, 200, 300, 400, 500]
    result = _resolve_bootstrap_target_ciks(
        bookkeeping=bookkeeping,
        raw_ciks=None,
        command_name="bootstrap-full",
        tracking_status_filter="active",
        cik_limit=2,
        cik_offset=1,
    )

    assert result == [200, 300]


def test_apply_bronze_cik_limit_emits_deprecation_warning(monkeypatch):
    """WAREHOUSE_BRONZE_CIK_LIMIT env var emits DeprecationWarning when set."""
    monkeypatch.setenv("WAREHOUSE_BRONZE_CIK_LIMIT", "3")
    from edgar_warehouse.application.warehouse_orchestrator import _apply_bronze_cik_limit

    with pytest.warns(DeprecationWarning, match="WAREHOUSE_BRONZE_CIK_LIMIT"):
        result = _apply_bronze_cik_limit([100, 200, 300, 400, 500])

    assert result == [100, 200, 300]


# ---------------------------------------------------------------------------
# _is_transient_artifact_error — artifact retry classifier
# ---------------------------------------------------------------------------


def test_403_status_is_classified_transient(monkeypatch):
    """Regression (2026-07-21): Ticket 20's strict release aborted an entire
    116-batch run because a single SEC 403 (fetching a quarterly full-index
    file) was not classified transient, so the existing retry loop gave up
    immediately instead of retrying. SEC EDGAR is unauthenticated, so 403 on
    a validly-built archive URL is its rate-limit/edge signal, not a real
    permission denial -- confirmed transient by an immediate manual re-fetch
    succeeding, and confirmed NOT concurrency-driven since three sibling
    batches running at the same moment completed with zero errors."""
    from edgar_warehouse.application.warehouse_orchestrator import (
        _is_transient_artifact_error,
    )

    class _FakeResponse:
        status_code = 403

    class _FakeHTTPStatusError(Exception):
        def __init__(self):
            super().__init__("403 Forbidden")
            self.response = _FakeResponse()

    assert _is_transient_artifact_error(_FakeHTTPStatusError()) is True


def test_other_retryable_statuses_remain_classified_transient(monkeypatch):
    from edgar_warehouse.application.warehouse_orchestrator import (
        _is_transient_artifact_error,
    )

    class _FakeResponse:
        def __init__(self, status_code):
            self.status_code = status_code

    class _FakeHTTPStatusError(Exception):
        def __init__(self, status_code):
            super().__init__(f"{status_code} error")
            self.response = _FakeResponse(status_code)

    for status_code in (408, 429, 500, 502, 503, 504):
        assert _is_transient_artifact_error(_FakeHTTPStatusError(status_code)) is True


def test_404_status_is_not_classified_transient():
    """A genuinely missing resource must not be retried -- retrying a 404
    just burns three attempts on a document that will never appear."""
    from edgar_warehouse.application.warehouse_orchestrator import (
        _is_transient_artifact_error,
    )

    class _FakeResponse:
        status_code = 404

    class _FakeHTTPStatusError(Exception):
        def __init__(self):
            super().__init__("404 Not Found")
            self.response = _FakeResponse()

    assert _is_transient_artifact_error(_FakeHTTPStatusError()) is False


def test_plain_value_error_is_not_classified_transient():
    from edgar_warehouse.application.warehouse_orchestrator import (
        _is_transient_artifact_error,
    )

    assert _is_transient_artifact_error(ValueError("no attachments found")) is False


def test_connection_error_is_classified_transient():
    from edgar_warehouse.application.warehouse_orchestrator import (
        _is_transient_artifact_error,
    )

    assert _is_transient_artifact_error(ConnectionError("connection reset")) is True
    assert _is_transient_artifact_error(TimeoutError("timed out")) is True


# ---------------------------------------------------------------------------
# _reset_edgartools_filing_cache_after_transient_content_error — private
# edgartools cache eviction, hardened against a future edgartools upgrade
# renaming/removing the private edgar._filings.get_filing_by_accession symbol
# this reaches into (no public cache-clear surface exists for it today).
# ---------------------------------------------------------------------------


def test_reset_filing_cache_clears_the_real_edgartools_private_cache(monkeypatch):
    """Locks in the live behavior against the actually-installed edgartools:
    a TransientFilingContentError anywhere in the exception's __cause__/
    __context__/reason chain must bust edgar._filings.get_filing_by_accession's
    LRU cache and report True."""
    from edgar._filings import get_filing_by_accession
    from edgar_warehouse.application.warehouse_orchestrator import (
        _reset_edgartools_filing_cache_after_transient_content_error,
    )
    from edgar_warehouse.bronze_filing_artifacts import TransientFilingContentError

    calls = {"n": 0}
    real_cache_clear = get_filing_by_accession.cache_clear
    monkeypatch.setattr(
        get_filing_by_accession,
        "cache_clear",
        lambda: (calls.__setitem__("n", calls["n"] + 1), real_cache_clear())[0],
    )

    wrapped = RuntimeError("artifact fetch failed")
    wrapped.__cause__ = TransientFilingContentError("degraded to homepage fallback")

    result = _reset_edgartools_filing_cache_after_transient_content_error(wrapped)

    assert result is True
    assert calls["n"] == 1


def test_reset_filing_cache_returns_false_without_a_transient_content_error():
    from edgar_warehouse.application.warehouse_orchestrator import (
        _reset_edgartools_filing_cache_after_transient_content_error,
    )

    assert _reset_edgartools_filing_cache_after_transient_content_error(ValueError("unrelated")) is False


def test_reset_filing_cache_degrades_gracefully_if_the_private_symbol_is_renamed(monkeypatch):
    """If a future edgartools upgrade renames/removes get_filing_by_accession
    from its private _filings module, this must return False (surfaced via
    the caller's edgartools_filing_cache_reset telemetry) rather than raise
    ImportError -- this runs inside a caller's `except` block already
    handling a real transient error, so an unhandled ImportError here would
    replace that original exception and crash the whole retry loop outright."""
    import edgar._filings as edgar_filings_module

    from edgar_warehouse.application.warehouse_orchestrator import (
        _reset_edgartools_filing_cache_after_transient_content_error,
    )
    from edgar_warehouse.bronze_filing_artifacts import TransientFilingContentError

    monkeypatch.delattr(edgar_filings_module, "get_filing_by_accession", raising=True)

    wrapped = RuntimeError("artifact fetch failed")
    wrapped.__cause__ = TransientFilingContentError("degraded to homepage fallback")

    assert _reset_edgartools_filing_cache_after_transient_content_error(wrapped) is False


def test_reset_filing_cache_degrades_gracefully_if_cache_clear_is_gone(monkeypatch):
    """Same hardening as above, for the narrower case where the symbol still
    exists but no longer exposes .cache_clear() (e.g. edgartools swaps its
    cache_except_none decorator for one that doesn't preserve the attribute)."""
    import edgar._filings as edgar_filings_module

    from edgar_warehouse.application.warehouse_orchestrator import (
        _reset_edgartools_filing_cache_after_transient_content_error,
    )
    from edgar_warehouse.bronze_filing_artifacts import TransientFilingContentError

    monkeypatch.setattr(
        edgar_filings_module, "get_filing_by_accession", lambda *a, **k: None, raising=True
    )

    wrapped = RuntimeError("artifact fetch failed")
    wrapped.__cause__ = TransientFilingContentError("degraded to homepage fallback")

    assert _reset_edgartools_filing_cache_after_transient_content_error(wrapped) is False


# ---------------------------------------------------------------------------
# object_storage — staged optimistic-concurrency promotion (ARTF-02)
# ---------------------------------------------------------------------------


def test_read_object_version_reports_missing_object(tmp_path):
    from edgar_warehouse.infrastructure.object_storage import StorageLocation as SL

    storage = SL(str(tmp_path))
    version = storage.read_object_version("does/not/exist.duckdb")
    assert version.exists is False
    assert version.etag is None


def test_read_object_version_is_stable_for_unchanged_content(tmp_path):
    from edgar_warehouse.infrastructure.object_storage import StorageLocation as SL

    storage = SL(str(tmp_path))
    storage.write_bytes("silver/sec/silver.duckdb", b"same-bytes")
    first = storage.read_object_version("silver/sec/silver.duckdb")
    second = storage.read_object_version("silver/sec/silver.duckdb")
    assert first.exists is True
    assert first.etag == second.etag


def test_read_object_version_changes_when_content_changes(tmp_path):
    from edgar_warehouse.infrastructure.object_storage import StorageLocation as SL

    storage = SL(str(tmp_path))
    storage.write_bytes("silver/sec/silver.duckdb", b"version-a")
    before = storage.read_object_version("silver/sec/silver.duckdb")
    storage.write_bytes("silver/sec/silver.duckdb", b"version-b")
    after = storage.read_object_version("silver/sec/silver.duckdb")
    assert before.etag != after.etag


def test_write_staged_bytes_never_collides_with_canonical_or_itself(tmp_path):
    from edgar_warehouse.infrastructure.object_storage import StorageLocation as SL

    storage = SL(str(tmp_path))
    staged_one = storage.write_staged_bytes("silver/sec/silver.duckdb", b"payload-1")
    staged_two = storage.write_staged_bytes("silver/sec/silver.duckdb", b"payload-2")
    assert staged_one != staged_two
    assert staged_one != "silver/sec/silver.duckdb"
    assert not Path(storage.join("silver/sec/silver.duckdb")).exists()


def test_promote_staged_succeeds_when_canonical_etag_still_matches(tmp_path):
    from edgar_warehouse.infrastructure.object_storage import StorageLocation as SL

    storage = SL(str(tmp_path))
    storage.write_bytes("silver/sec/silver.duckdb", b"original")
    baseline = storage.read_object_version("silver/sec/silver.duckdb")

    staged = storage.write_staged_bytes("silver/sec/silver.duckdb", b"merged-result")
    result = storage.promote_staged(staged, "silver/sec/silver.duckdb", expected_etag=baseline.etag)

    assert Path(storage.join("silver/sec/silver.duckdb")).read_bytes() == b"merged-result"
    assert result.new_version.etag != baseline.etag


def test_promote_staged_raises_on_concurrent_canonical_change_and_preserves_staged_object(tmp_path):
    """A simulated concurrent canonical write between baseline-read and promote must abort."""
    from edgar_warehouse.infrastructure.object_storage import PromotionConflictError, StorageLocation as SL

    storage = SL(str(tmp_path))
    storage.write_bytes("silver/sec/silver.duckdb", b"original")
    baseline = storage.read_object_version("silver/sec/silver.duckdb")

    staged = storage.write_staged_bytes("silver/sec/silver.duckdb", b"merged-result")

    # Simulate a concurrent writer landing between baseline read and promotion.
    storage.write_bytes("silver/sec/silver.duckdb", b"concurrent-write")

    with pytest.raises(PromotionConflictError):
        storage.promote_staged(staged, "silver/sec/silver.duckdb", expected_etag=baseline.etag)

    # Canonical keeps the concurrent writer's content -- no last-writer-wins.
    assert Path(storage.join("silver/sec/silver.duckdb")).read_bytes() == b"concurrent-write"
    # Staged diagnostics are preserved for inspection/retry, not deleted.
    assert Path(storage.join(staged)).read_bytes() == b"merged-result"
