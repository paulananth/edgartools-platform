"""parse-adv-bronze parses operator-staged ADV XML named by --artifact.

silver-merge-engine-migration Ticket 07 deleted the command's two local reads
(registry discovery over sec_company_filing, and the already_parsed gate over
sec_adv_filing): the local store is never hydrated, so both were always empty.
The FakeAdvParseDB below fails any read to prove none is left.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import StorageLocation


class FakeAdvParseDB:
    def __init__(self) -> None:
        self.merge_adv_filings_calls: list[tuple[list[dict[str, Any]], str]] = []
        self.merge_adv_offices_calls: list[tuple[list[dict[str, Any]], str]] = []
        self.merge_adv_disclosure_events_calls: list[tuple[list[dict[str, Any]], str]] = []
        self.merge_adv_private_funds_calls: list[tuple[list[dict[str, Any]], str]] = []

    def fetch(self, sql: str, params: Any = None) -> list[dict[str, Any]]:
        raise AssertionError(f"parse-adv-bronze must not read the local store: {sql}")

    def get_filing_attachments(self, accession_number: str) -> list[dict[str, Any]]:
        raise AssertionError("parse-adv-bronze must not read the local store")

    def get_raw_object(self, raw_object_id: str) -> dict[str, Any] | None:
        raise AssertionError("parse-adv-bronze must not read the local store")

    def merge_adv_filings(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        self.merge_adv_filings_calls.append((rows, sync_run_id))
        return len(rows)

    def merge_adv_offices(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        self.merge_adv_offices_calls.append((rows, sync_run_id))
        return len(rows)

    def merge_adv_disclosure_events(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        self.merge_adv_disclosure_events_calls.append((rows, sync_run_id))
        return len(rows)

    def merge_adv_private_funds(self, rows: list[dict[str, Any]], sync_run_id: str) -> int:
        self.merge_adv_private_funds_calls.append((rows, sync_run_id))
        return len(rows)


@pytest.fixture()
def bronze_context(tmp_path):
    return WarehouseCommandContext(
        bronze_root=StorageLocation(str(tmp_path / "bronze")),
        storage_root=StorageLocation(str(tmp_path / "warehouse")),
        silver_root=StorageLocation(str(tmp_path / "silver")),
        snowflake_export_root=None,
        environment_name="test",
        identity="test@example.com",
        runtime_mode="bronze_capture",
    )


@pytest.fixture()
def no_sec_fetch():
    from edgar_warehouse.application import warehouse_orchestrator

    with (
        patch.object(
            warehouse_orchestrator,
            "_download_sec_bytes",
            side_effect=AssertionError("download_sec_bytes must not be called"),
        ),
        patch(
            "edgar_warehouse.infrastructure.filing_artifact_service.refresh_filing_artifacts",
            side_effect=AssertionError("refresh_filing_artifacts must not be called"),
        ),
    ):
        yield


def _adv_rows(accession: str) -> dict[str, list[dict[str, Any]]]:
    return {
        "sec_adv_filing": [{"accession_number": accession, "adviser_name": "Adviser"}],
        "sec_adv_office": [{"accession_number": accession, "office_index": 1}],
        "sec_adv_disclosure_event": [{"accession_number": accession, "event_index": 1}],
        "sec_adv_private_fund": [{"accession_number": accession, "fund_index": 1}],
    }


def _artifact(accession: str, path: str, *, form: str = "ADV", cik: int | None = None) -> dict[str, Any]:
    artifact: dict[str, Any] = {"accession_number": accession, "form": form, "storage_path": path}
    if cik is not None:
        artifact["cik"] = cik
    return artifact


def _run(
    bronze_context, db, sync_run_id: str, artifacts: list[dict[str, Any]], **kwargs: Any
) -> dict[str, Any]:
    from edgar_warehouse.application import warehouse_orchestrator

    metrics: dict[str, Any] = {}
    warehouse_orchestrator._run_parse_adv_bronze(
        context=bronze_context,
        db=db,
        sync_run_id=sync_run_id,
        metrics=metrics,
        explicit_artifacts=artifacts,
        **kwargs,
    )
    return metrics


def test_cli_parser_accepts_limit_accession_list_and_repeated_artifacts():
    from edgar_warehouse.cli import build_parser

    args = build_parser().parse_args(
        [
            "parse-adv-bronze",
            "--limit",
            "2",
            "--accession-list",
            "0001111111-24-000001,0001111111-24-000002",
            "--artifact",
            "0001111111-24-000001,ADV,s3://bucket/a.xml,123",
            "--artifact",
            "0001111111-24-000002,ADV/A,s3://bucket/b.xml",
        ]
    )

    assert args.artifacts == [
        {
            "accession_number": "0001111111-24-000001",
            "form": "ADV",
            "storage_path": "s3://bucket/a.xml",
            "cik": 123,
        },
        {
            "accession_number": "0001111111-24-000002",
            "form": "ADV/A",
            "storage_path": "s3://bucket/b.xml",
        },
    ]
    assert args.limit == 2
    assert args.accession_list == ["0001111111-24-000001", "0001111111-24-000002"]


def test_accession_list_and_limit_bound_named_artifacts(bronze_context, no_sec_fetch):
    from edgar_warehouse.application import warehouse_orchestrator

    first, second, third = "0001111111-24-000070", "0001111111-24-000071", "0001111111-24-000072"
    read_calls: list[str] = []

    def read_bytes(storage_path: str) -> bytes:
        read_calls.append(storage_path)
        return b"adv payload"

    with (
        patch.object(warehouse_orchestrator, "read_bytes", side_effect=read_bytes),
        patch("edgar_warehouse.parsers.adv.parse_adv", side_effect=lambda acc, *_args: _adv_rows(acc)),
    ):
        metrics = _run(
            bronze_context,
            FakeAdvParseDB(),
            "run-bounded",
            [
                _artifact(first, "s3://bucket/first.xml"),
                _artifact(second, "s3://bucket/second.xml"),
                _artifact(third, "s3://bucket/third.xml"),
            ],
            accession_list=[second, third],
            limit=1,
        )

    assert read_calls == ["s3://bucket/second.xml"]
    assert metrics["discovered"] == 2
    assert metrics["selected"] == 1
    assert metrics["parsed"] == 1


def test_cli_parser_requires_an_artifact():
    from edgar_warehouse.cli import build_parser

    with pytest.raises(SystemExit):
        build_parser().parse_args(["parse-adv-bronze"])


def test_cli_parser_rejects_malformed_artifact_value():
    from edgar_warehouse.cli import build_parser

    with pytest.raises(SystemExit):
        build_parser().parse_args(["parse-adv-bronze", "--artifact", "not-enough-fields"])


def test_explicit_artifact_is_read_parsed_and_merged_without_local_reads(bronze_context, no_sec_fetch):
    from edgar_warehouse.application import warehouse_orchestrator

    accession = "0001111111-24-000020"
    db = FakeAdvParseDB()
    parse_calls: list[tuple[str, str, str, int | None]] = []

    def parse_adv(accession_number: str, content: str, form: str, cik: int | None = None):
        parse_calls.append((accession_number, content, form, cik))
        return _adv_rows(accession_number)

    with (
        patch.object(warehouse_orchestrator, "read_bytes", return_value=b"explicit adv") as read_bytes,
        patch("edgar_warehouse.parsers.adv.parse_adv", side_effect=parse_adv),
    ):
        metrics = _run(
            bronze_context,
            db,
            "run-explicit",
            [_artifact(accession, "s3://bucket/explicit.xml", form="ADV/A", cik=42)],
        )

    assert read_bytes.call_args.args == ("s3://bucket/explicit.xml",)
    assert parse_calls == [(accession, "explicit adv", "ADV/A", 42)]
    rows = _adv_rows(accession)
    assert db.merge_adv_filings_calls == [(rows["sec_adv_filing"], "run-explicit")]
    assert db.merge_adv_offices_calls == [(rows["sec_adv_office"], "run-explicit")]
    assert db.merge_adv_disclosure_events_calls == [(rows["sec_adv_disclosure_event"], "run-explicit")]
    assert db.merge_adv_private_funds_calls == [(rows["sec_adv_private_fund"], "run-explicit")]
    assert metrics["explicit_artifacts"] == 1
    assert metrics["parsed"] == 1
    assert metrics["rows_written"] == 4


def test_invalid_and_unreadable_artifacts_are_counted_and_do_not_abort(bronze_context, no_sec_fetch):
    from edgar_warehouse.application import warehouse_orchestrator

    db = FakeAdvParseDB()

    def read_bytes(storage_path: str) -> bytes:
        if storage_path.endswith("unreadable.xml"):
            raise OSError("permission denied")
        return b"valid adv"

    with (
        patch.object(warehouse_orchestrator, "read_bytes", side_effect=read_bytes),
        patch("edgar_warehouse.parsers.adv.parse_adv", side_effect=lambda acc, *_args: _adv_rows(acc)),
    ):
        metrics = _run(
            bronze_context,
            db,
            "run-missing",
            [
                _artifact("0001111111-24-000050", "s3://bucket/form4.xml", form="4"),
                _artifact("0001111111-24-000051", "s3://bucket/unreadable.xml"),
                _artifact("0001111111-24-000052", "s3://bucket/valid.xml"),
            ],
        )

    assert metrics["missing_artifacts"] == 1
    assert metrics["unreadable_artifacts"] == 1
    assert metrics["parsed"] == 1
    assert db.merge_adv_filings_calls[0][0][0]["accession_number"] == "0001111111-24-000052"


def test_parser_errors_are_counted_and_later_artifacts_continue(bronze_context, no_sec_fetch):
    from edgar_warehouse.application import warehouse_orchestrator

    bad = "0001111111-24-000060"
    good = "0001111111-24-000061"
    db = FakeAdvParseDB()
    events: list[tuple[str, dict[str, Any]]] = []

    def parse_adv(accession_number: str, *_args: Any) -> dict[str, list[dict[str, Any]]]:
        if accession_number == bad:
            raise ValueError("bad adv payload")
        return {"sec_adv_filing": [{"accession_number": accession_number}]}

    with (
        patch.object(warehouse_orchestrator, "read_bytes", return_value=b"adv payload"),
        patch.object(
            warehouse_orchestrator,
            "_emit_pipeline_event",
            side_effect=lambda event, **payload: events.append((event, payload)),
        ),
        patch("edgar_warehouse.parsers.adv.parse_adv", side_effect=parse_adv),
    ):
        metrics = _run(
            bronze_context,
            db,
            "run-parser-error",
            [_artifact(bad, "s3://bucket/bad.xml"), _artifact(good, "s3://bucket/good.xml")],
        )

    assert metrics["errors"] == 1
    assert metrics["parsed"] == 1
    assert db.merge_adv_filings_calls == [([{"accession_number": good}], "run-parser-error")]
    assert any(event == "parse_adv_bronze_error" for event, _payload in events)
