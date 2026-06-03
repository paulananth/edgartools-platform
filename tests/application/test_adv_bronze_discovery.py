from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from edgar_warehouse.application.adv_bronze_discovery import (
    AdvBronzeArtifactCandidate,
    discover_adv_bronze_artifacts,
    read_adv_bronze_artifacts,
)


class FakeAdvSilverDB:
    def __init__(
        self,
        *,
        filings: list[dict[str, Any]] | None = None,
        attachments: dict[str, list[dict[str, Any]]] | None = None,
        raw_objects: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.filings = filings or []
        self.attachments = attachments or {}
        self.raw_objects = raw_objects or {}
        self.fetch_calls: list[dict[str, Any]] = []
        self.attachment_calls: list[str] = []
        self.raw_object_calls: list[str] = []

    def fetch(self, sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
        self.fetch_calls.append({"sql": sql, "params": params})
        return list(self.filings)

    def get_filing_attachments(self, accession_number: str) -> list[dict[str, Any]]:
        self.attachment_calls.append(accession_number)
        return list(self.attachments.get(accession_number, []))

    def get_raw_object(self, raw_object_id: str) -> dict[str, Any] | None:
        self.raw_object_calls.append(raw_object_id)
        return self.raw_objects.get(raw_object_id)


@pytest.fixture()
def no_sec_fetch():
    from edgar_warehouse.application import warehouse_orchestrator

    with (
        patch.object(
            warehouse_orchestrator,
            "download_sec_bytes",
            side_effect=AssertionError("download_sec_bytes must not be called"),
        ),
        patch(
            "edgar_warehouse.infrastructure.filing_artifact_service.refresh_filing_artifacts",
            side_effect=AssertionError("refresh_filing_artifacts must not be called"),
        ),
    ):
        yield


def test_registry_discovery_uses_adv_query_and_returns_registry_candidate(no_sec_fetch):
    accession = "0001111111-24-000001"
    raw_id = "raw-adv-1"
    storage_path = "s3://edgartools-dev-bronze/warehouse/bronze/adv-primary.xml"
    db = FakeAdvSilverDB(
        filings=[{"accession_number": accession, "cik": 1234567, "form": "ADV"}],
        attachments={
            accession: [
                {"is_primary": False, "raw_object_id": "ignored"},
                {"is_primary": True, "raw_object_id": raw_id},
            ]
        },
        raw_objects={raw_id: {"storage_path": storage_path}},
    )

    result = discover_adv_bronze_artifacts(db)

    assert not result.issues
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.accession_number == accession
    assert candidate.cik == 1234567
    assert candidate.form == "ADV"
    assert candidate.storage_path == storage_path
    assert candidate.source_kind == "registry"
    assert db.attachment_calls == [accession]
    assert db.raw_object_calls == [raw_id]

    sql = db.fetch_calls[0]["sql"]
    assert "sec_company_filing" in sql
    assert "form IN" in sql
    assert "ADV" in sql
    assert "ADV/A" in sql
    assert "ADV-W/A" in sql


def test_accession_filter_and_limit_bound_registry_candidates(no_sec_fetch):
    accessions = [
        "0001111111-24-000010",
        "0001111111-24-000011",
        "0001111111-24-000012",
    ]
    attachments = {}
    raw_objects = {}
    for index, accession in enumerate(accessions):
        raw_id = f"raw-{index}"
        attachments[accession] = [{"is_primary": True, "raw_object_id": raw_id}]
        raw_objects[raw_id] = {"storage_path": f"s3://bucket/{accession}.xml"}

    db = FakeAdvSilverDB(
        filings=[
            {"accession_number": accessions[0], "cik": 1, "form": "ADV"},
            {"accession_number": accessions[1], "cik": 1, "form": "ADV/A"},
            {"accession_number": accessions[2], "cik": 1, "form": "ADV-W"},
        ],
        attachments=attachments,
        raw_objects=raw_objects,
    )

    result = discover_adv_bronze_artifacts(
        db,
        accession_list=[accessions[1], accessions[2]],
        limit=1,
    )

    assert [candidate.accession_number for candidate in result.candidates] == [accessions[1]]
    assert db.attachment_calls == [accessions[1]]
    assert result.candidates[0].source_kind == "registry"


def test_missing_registry_artifacts_return_issues_and_continue(no_sec_fetch):
    missing_primary = "0001111111-24-000020"
    missing_raw = "0001111111-24-000021"
    empty_path = "0001111111-24-000022"
    valid = "0001111111-24-000023"
    db = FakeAdvSilverDB(
        filings=[
            {"accession_number": missing_primary, "cik": 1, "form": "ADV"},
            {"accession_number": missing_raw, "cik": 1, "form": "ADV"},
            {"accession_number": empty_path, "cik": 1, "form": "ADV"},
            {"accession_number": valid, "cik": 1, "form": "ADV"},
        ],
        attachments={
            missing_raw: [{"is_primary": True, "raw_object_id": "missing-raw-id"}],
            empty_path: [{"is_primary": True, "raw_object_id": "empty-path-id"}],
            valid: [{"is_primary": True, "raw_object_id": "valid-id"}],
        },
        raw_objects={
            "empty-path-id": {"storage_path": "   "},
            "valid-id": {"storage_path": "s3://bucket/valid-adv.xml"},
        },
    )

    result = discover_adv_bronze_artifacts(db)

    assert [candidate.accession_number for candidate in result.candidates] == [valid]
    issues_by_accession = {issue.accession_number: issue.reason for issue in result.issues}
    assert issues_by_accession[missing_primary] == "missing_primary_attachment"
    assert issues_by_accession[missing_raw] == "missing_raw_object"
    assert issues_by_accession[empty_path] == "empty_storage_path"
    assert all(issue.source_kind == "registry" for issue in result.issues)


def test_explicit_artifact_fallback_accepts_adv_and_reports_non_adv(no_sec_fetch):
    db = FakeAdvSilverDB()
    result = discover_adv_bronze_artifacts(
        db,
        explicit_artifacts=[
            {
                "accession_number": "0001111111-24-000030",
                "cik": "999001",
                "form": "adv/a",
                "storage_path": "s3://bucket/explicit-adv.xml",
            },
            {
                "accession_number": "0001111111-24-000031",
                "form": "4",
                "storage_path": "s3://bucket/form4.xml",
            },
        ],
    )

    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.accession_number == "0001111111-24-000030"
    assert candidate.form == "ADV/A"
    assert candidate.cik == 999001
    assert candidate.source_kind == "explicit"
    assert result.skipped_non_adv == 1
    assert len(result.issues) == 1
    assert result.issues[0].accession_number == "0001111111-24-000031"
    assert result.issues[0].reason == "non_adv_form"
    assert result.issues[0].source_kind == "explicit"


def test_read_adv_bronze_artifacts_uses_injected_reader_and_continues_on_unreadable():
    candidates = (
        AdvBronzeArtifactCandidate(
            accession_number="0001111111-24-000040",
            cik=1,
            form="ADV",
            storage_path="s3://bucket/readable.xml",
            source_kind="registry",
        ),
        AdvBronzeArtifactCandidate(
            accession_number="0001111111-24-000041",
            cik=1,
            form="ADV",
            storage_path="s3://bucket/unreadable.xml",
            source_kind="explicit",
        ),
    )
    calls: list[str] = []

    def read_bytes_fn(storage_path: str) -> bytes:
        calls.append(storage_path)
        if storage_path.endswith("unreadable.xml"):
            raise OSError("permission denied")
        return b"<adv/>"

    result = read_adv_bronze_artifacts(candidates, read_bytes_fn=read_bytes_fn)

    assert calls == ["s3://bucket/readable.xml", "s3://bucket/unreadable.xml"]
    assert len(result.payloads) == 1
    assert result.payloads[0].candidate.accession_number == "0001111111-24-000040"
    assert result.payloads[0].payload == b"<adv/>"
    assert len(result.issues) == 1
    assert result.issues[0].reason == "unreadable_storage_path"
    assert result.issues[0].accession_number == "0001111111-24-000041"
    assert result.issues[0].storage_path == "s3://bucket/unreadable.xml"
    assert result.issues[0].source_kind == "explicit"
