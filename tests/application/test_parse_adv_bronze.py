from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import StorageLocation


class FakeAdvParseDB:
    def __init__(
        self,
        *,
        filings: list[dict[str, Any]] | None = None,
        already_parsed: list[str] | None = None,
        attachments: dict[str, list[dict[str, Any]]] | None = None,
        raw_objects: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.filings = filings or []
        self.already_parsed = set(already_parsed or [])
        self.attachments = attachments or {}
        self.raw_objects = raw_objects or {}
        self.fetch_calls: list[str] = []
        self.attachment_calls: list[str] = []
        self.raw_object_calls: list[str] = []
        self.merge_adv_filings_calls: list[tuple[list[dict[str, Any]], str]] = []
        self.merge_adv_offices_calls: list[tuple[list[dict[str, Any]], str]] = []
        self.merge_adv_disclosure_events_calls: list[tuple[list[dict[str, Any]], str]] = []
        self.merge_adv_private_funds_calls: list[tuple[list[dict[str, Any]], str]] = []

    def fetch(self, sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
        self.fetch_calls.append(sql)
        if "sec_adv_filing" in sql:
            return [{"accession_number": accession} for accession in sorted(self.already_parsed)]
        if "sec_company_filing" in sql:
            return list(self.filings)
        return []

    def get_filing_attachments(self, accession_number: str) -> list[dict[str, Any]]:
        self.attachment_calls.append(accession_number)
        return list(self.attachments.get(accession_number, []))

    def get_raw_object(self, raw_object_id: str) -> dict[str, Any] | None:
        self.raw_object_calls.append(raw_object_id)
        return self.raw_objects.get(raw_object_id)

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


def _registry_db(accessions: list[str], *, already_parsed: list[str] | None = None) -> FakeAdvParseDB:
    attachments: dict[str, list[dict[str, Any]]] = {}
    raw_objects: dict[str, dict[str, Any]] = {}
    filings: list[dict[str, Any]] = []
    for index, accession in enumerate(accessions, start=1):
        raw_id = f"raw-{index}"
        filings.append({"accession_number": accession, "cik": 900000 + index, "form": "ADV"})
        attachments[accession] = [{"is_primary": True, "raw_object_id": raw_id}]
        raw_objects[raw_id] = {"storage_path": f"s3://bucket/{accession}.xml"}
    return FakeAdvParseDB(
        filings=filings,
        already_parsed=already_parsed,
        attachments=attachments,
        raw_objects=raw_objects,
    )


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

    assert args.limit == 2
    assert args.accession_list == ["0001111111-24-000001", "0001111111-24-000002"]
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


def test_cli_parser_rejects_malformed_artifact_value():
    from edgar_warehouse.cli import build_parser

    with pytest.raises(SystemExit):
        build_parser().parse_args(["parse-adv-bronze", "--artifact", "not-enough-fields"])


def test_registry_candidate_is_read_parsed_and_merged(bronze_context, no_sec_fetch):
    from edgar_warehouse.application import warehouse_orchestrator

    accession = "0001111111-24-000010"
    db = _registry_db([accession])
    parse_calls: list[tuple[str, str, str, int | None]] = []

    def parse_adv(accession_number: str, content: str, form: str, cik: int | None = None):
        parse_calls.append((accession_number, content, form, cik))
        return _adv_rows(accession_number)

    with (
        patch.object(warehouse_orchestrator, "read_bytes", return_value=b"<adv>payload</adv>") as read_bytes,
        patch("edgar_warehouse.parsers.adv.parse_adv", side_effect=parse_adv),
    ):
        metrics: dict[str, Any] = {}
        warehouse_orchestrator._run_parse_adv_bronze(
            context=bronze_context,
            db=db,
            sync_run_id="run-adv",
            metrics=metrics,
        )

    assert read_bytes.call_args.args == ("s3://bucket/0001111111-24-000010.xml",)
    assert parse_calls == [(accession, "<adv>payload</adv>", "ADV", 900001)]
    assert db.merge_adv_filings_calls == [(_adv_rows(accession)["sec_adv_filing"], "run-adv")]
    assert db.merge_adv_offices_calls == [(_adv_rows(accession)["sec_adv_office"], "run-adv")]
    assert db.merge_adv_disclosure_events_calls == [(_adv_rows(accession)["sec_adv_disclosure_event"], "run-adv")]
    assert db.merge_adv_private_funds_calls == [(_adv_rows(accession)["sec_adv_private_fund"], "run-adv")]
    assert metrics["parsed"] == 1
    assert metrics["rows_written"] == 4


def test_explicit_artifact_input_is_reachable_without_registry_rows(bronze_context, no_sec_fetch):
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
        metrics: dict[str, Any] = {}
        warehouse_orchestrator._run_parse_adv_bronze(
            context=bronze_context,
            db=db,
            sync_run_id="run-explicit",
            metrics=metrics,
            explicit_artifacts=[
                {
                    "accession_number": accession,
                    "form": "ADV/A",
                    "storage_path": "s3://bucket/explicit.xml",
                    "cik": 42,
                }
            ],
        )

    assert db.attachment_calls == []
    assert read_bytes.call_args.args == ("s3://bucket/explicit.xml",)
    assert parse_calls == [(accession, "explicit adv", "ADV/A", 42)]
    assert metrics["explicit_artifacts"] == 1
    assert metrics["parsed"] == 1


def test_already_parsed_accession_is_skipped_before_storage_read(bronze_context, no_sec_fetch):
    from edgar_warehouse.application import warehouse_orchestrator

    accession = "0001111111-24-000030"
    db = _registry_db([accession], already_parsed=[accession])

    with patch.object(
        warehouse_orchestrator,
        "read_bytes",
        side_effect=AssertionError("already parsed accession should not read storage"),
    ):
        metrics: dict[str, Any] = {}
        warehouse_orchestrator._run_parse_adv_bronze(
            context=bronze_context,
            db=db,
            sync_run_id="run-skip",
            metrics=metrics,
        )

    assert metrics["already_parsed"] == 1
    assert metrics["selected"] == 0
    assert metrics["skipped"] == 1
    assert metrics["parsed"] == 0
    assert db.merge_adv_filings_calls == []


def test_limit_counts_not_yet_parsed_candidates(bronze_context, no_sec_fetch):
    from edgar_warehouse.application import warehouse_orchestrator

    already = "0001111111-24-000040"
    first_new = "0001111111-24-000041"
    second_new = "0001111111-24-000042"
    db = _registry_db([already, first_new, second_new], already_parsed=[already])
    read_calls: list[str] = []

    def read_bytes(storage_path: str) -> bytes:
        read_calls.append(storage_path)
        return b"adv payload"

    with (
        patch.object(warehouse_orchestrator, "read_bytes", side_effect=read_bytes),
        patch("edgar_warehouse.parsers.adv.parse_adv", side_effect=lambda accession, *_args: _adv_rows(accession)),
    ):
        metrics: dict[str, Any] = {}
        warehouse_orchestrator._run_parse_adv_bronze(
            context=bronze_context,
            db=db,
            sync_run_id="run-limit",
            metrics=metrics,
            limit=1,
        )

    assert read_calls == [f"s3://bucket/{first_new}.xml"]
    assert metrics["skipped"] == 1
    assert metrics["selected"] == 1
    assert metrics["parsed"] == 1
    assert db.merge_adv_filings_calls[0][0][0]["accession_number"] == first_new


def test_missing_and_unreadable_artifacts_are_counted_and_do_not_abort(bronze_context, no_sec_fetch):
    from edgar_warehouse.application import warehouse_orchestrator

    missing = "0001111111-24-000050"
    unreadable = "0001111111-24-000051"
    valid = "0001111111-24-000052"
    db = FakeAdvParseDB(
        filings=[
            {"accession_number": missing, "cik": 1, "form": "ADV"},
            {"accession_number": unreadable, "cik": 2, "form": "ADV"},
            {"accession_number": valid, "cik": 3, "form": "ADV"},
        ],
        attachments={
            unreadable: [{"is_primary": True, "raw_object_id": "raw-unreadable"}],
            valid: [{"is_primary": True, "raw_object_id": "raw-valid"}],
        },
        raw_objects={
            "raw-unreadable": {"storage_path": "s3://bucket/unreadable.xml"},
            "raw-valid": {"storage_path": "s3://bucket/valid.xml"},
        },
    )

    def read_bytes(storage_path: str) -> bytes:
        if storage_path.endswith("unreadable.xml"):
            raise OSError("permission denied")
        return b"valid adv"

    with (
        patch.object(warehouse_orchestrator, "read_bytes", side_effect=read_bytes),
        patch("edgar_warehouse.parsers.adv.parse_adv", side_effect=lambda accession, *_args: _adv_rows(accession)),
    ):
        metrics: dict[str, Any] = {}
        warehouse_orchestrator._run_parse_adv_bronze(
            context=bronze_context,
            db=db,
            sync_run_id="run-missing",
            metrics=metrics,
        )

    assert metrics["missing_artifacts"] == 1
    assert metrics["unreadable_artifacts"] == 1
    assert metrics["parsed"] == 1
    assert db.merge_adv_filings_calls[0][0][0]["accession_number"] == valid


def test_parser_errors_are_counted_and_later_candidates_continue(bronze_context, no_sec_fetch):
    from edgar_warehouse.application import warehouse_orchestrator

    bad = "0001111111-24-000060"
    good = "0001111111-24-000061"
    db = _registry_db([bad, good])
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
        metrics: dict[str, Any] = {}
        warehouse_orchestrator._run_parse_adv_bronze(
            context=bronze_context,
            db=db,
            sync_run_id="run-parser-error",
            metrics=metrics,
        )

    assert metrics["errors"] == 1
    assert metrics["parsed"] == 1
    assert db.merge_adv_filings_calls == [([{"accession_number": good}], "run-parser-error")]
    assert any(event == "parse_adv_bronze_error" for event, _payload in events)
