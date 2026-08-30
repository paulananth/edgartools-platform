"""End-to-end fetch-firm-roster command dispatch, network boundary mocked."""

from __future__ import annotations

import hashlib
import json

import pytest

from edgar_warehouse.application import warehouse_orchestrator
from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import StorageLocation
from edgar_warehouse.silver_store import SilverDatabase
from tests.support.bookkeeping_fixtures import bookkeeping_fixture

_REGISTERED_HREF = (
    "/files/investment/data/other/information-about-registered-investment-"
    "advisers-exempt-reporting-advisers/ia07012026.zip"
)
_EXEMPT_HREF = (
    "/files/investment/data/other/information-about-registered-investment-"
    "advisers-exempt-reporting-advisers/ia07012026-exempt.zip"
)
_LISTING_HTML = f"""
<ul>
<li><a href="{_EXEMPT_HREF}">Exempt Investment Advisers, July 2026</a></li>
<li><a href="{_REGISTERED_HREF}">Registered Investment Advisers, July 2026</a></li>
<li><a href="/files/investment/data/other/information-about-registered-investment-advisers-exempt-reporting-advisers/ia060126_0.zip">Registered Investment Advisers, June 2026</a></li>
</ul>
"""


def _context(tmp_path) -> WarehouseCommandContext:
    return WarehouseCommandContext(
        bronze_root=StorageLocation(str(tmp_path / "bronze")),
        storage_root=StorageLocation(str(tmp_path / "warehouse")),
        silver_root=StorageLocation(str(tmp_path / "silver")),
        snowflake_export_root=None,
        environment_name="test",
        identity="EdgarTools Platform test@example.com",
        runtime_mode="bronze_capture",
    )


def _db_path(context: WarehouseCommandContext) -> str:
    return context.silver_root.join("silver", "sec", "silver.duckdb")


def test_fetch_firm_roster_fetches_latest_period_and_writes_manifest(tmp_path, monkeypatch) -> None:
    context = _context(tmp_path)

    responses = {
        "https://www.sec.gov/data-research/sec-markets-data/"
        "information-about-registered-investment-advisers-exempt-reporting-advisers": (
            _LISTING_HTML.encode("utf-8")
        ),
        f"https://www.sec.gov{_REGISTERED_HREF}": b"registered-zip-bytes",
        f"https://www.sec.gov{_EXEMPT_HREF}": b"exempt-zip-bytes",
    }

    def _fake_download(url: str, identity: str) -> bytes:
        assert identity == context.identity
        return responses[url]

    monkeypatch.setattr(
        "edgar_warehouse.infrastructure.sec_client.download_sec_bytes", _fake_download
    )
    monkeypatch.setattr(
        warehouse_orchestrator, "_bookkeeping_store", lambda: bookkeeping_fixture()
    )

    result = warehouse_orchestrator._execute_warehouse(
        context=context,
        command_name="fetch-firm-roster",
        arguments={"run_id": "test-run-1"},
    )

    assert result["status"] == "ok"
    manifest = json.loads(
        (tmp_path / "bronze" / "runs" / "fetch-firm-roster" / "test-run-1" / "source_manifest.json").read_text()
    )
    assert len(manifest["sources"]) == 2
    assert {source["dataset_period"] for source in manifest["sources"]} == {"2026-07"}
    assert {source["sha256"] for source in manifest["sources"]} == {
        hashlib.sha256(b"registered-zip-bytes").hexdigest(),
        hashlib.sha256(b"exempt-zip-bytes").hexdigest(),
    }
    staged_registered = (
        tmp_path / "bronze" / "runs" / "fetch-firm-roster" / "test-run-1" / "ia07012026.zip"
    )
    staged_exempt = (
        tmp_path / "bronze" / "runs" / "fetch-firm-roster" / "test-run-1" / "ia07012026-exempt.zip"
    )
    assert staged_registered.read_bytes() == b"registered-zip-bytes"
    assert staged_exempt.read_bytes() == b"exempt-zip-bytes"


def test_fetch_firm_roster_is_a_no_op_when_latest_period_already_ingested(tmp_path, monkeypatch) -> None:
    context = _context(tmp_path)
    db = SilverDatabase(_db_path(context))
    try:
        db.merge_adv_firm_roster([{
            "adviser_crd_number": "1588",
            "dataset_period": "2026-07",
            "private_funds_reported": True,
            "private_fund_count_7b1": 3,
            "any_hedge_funds": True,
            "hedge_fund_count": 3,
            "any_pe_funds": False,
            "pe_fund_count": None,
            "total_gross_assets_private_funds": 709905606,
            "private_fund_count_7b2": 0,
            "source_sha256": "abc123",
            "parser_version": "firm_roster_v1",
        }], "seed-run")
    finally:
        db.close()

    def _fail_if_archive_downloaded(url: str, identity: str) -> bytes:
        if url.endswith(".zip"):
            raise AssertionError(f"unexpected archive download: {url}")
        return _LISTING_HTML.encode("utf-8")

    monkeypatch.setattr(
        "edgar_warehouse.infrastructure.sec_client.download_sec_bytes",
        _fail_if_archive_downloaded,
    )
    monkeypatch.setattr(
        warehouse_orchestrator, "_bookkeeping_store", lambda: bookkeeping_fixture()
    )

    result = warehouse_orchestrator._execute_warehouse(
        context=context,
        command_name="fetch-firm-roster",
        arguments={"run_id": "test-run-2"},
    )

    assert result["status"] == "ok"
    manifest = json.loads(
        (tmp_path / "bronze" / "runs" / "fetch-firm-roster" / "test-run-2" / "source_manifest.json").read_text()
    )
    assert manifest == {"sources": []}


def test_fetch_firm_roster_force_without_dataset_period_rejected(tmp_path, monkeypatch) -> None:
    context = _context(tmp_path)

    monkeypatch.setattr(
        "edgar_warehouse.infrastructure.sec_client.download_sec_bytes",
        lambda url, identity: (_ for _ in ()).throw(AssertionError("no network call expected")),
    )
    monkeypatch.setattr(
        warehouse_orchestrator, "_bookkeeping_store", lambda: bookkeeping_fixture()
    )

    with pytest.raises(WarehouseRuntimeError, match="--force requires --dataset-period"):
        warehouse_orchestrator._execute_warehouse(
            context=context,
            command_name="fetch-firm-roster",
            arguments={"run_id": "test-run-3", "force": True},
        )
