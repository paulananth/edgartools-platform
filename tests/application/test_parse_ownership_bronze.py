"""RED tests for parse-ownership-bronze command behavior contract.

Wave 0 — Phase 5 Plan 01. These tests encode decisions D-01 through D-10
and MUST FAIL against the current implementation.

Known current defects that cause failures:
  - D-07: _run_parse_ownership_bronze queries sec_company_filing.form_type and
    ORDER BY period_of_report.  Current silver DDL uses `form` and `report_date`.
  - D-08: Current code uses fsspec.filesystem("s3").ls(prefix) instead of
    sec_filing_attachment + sec_raw_object + read_bytes(storage_path).
  - D-09: Missing primary artifact increments error_count but reports no
    observable metric for "primary artifact not found" distinct from parse errors.
  - D-10: The current code imports and uses fsspec to list S3 prefixes — there is
    no guard preventing SEC API use; the test asserts download_sec_bytes is never
    called and no raw S3 prefix listing occurs.
"""
from __future__ import annotations

import re
import uuid
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import StorageLocation


# ---------------------------------------------------------------------------
# Minimal fake SilverDatabase
# ---------------------------------------------------------------------------

class FakeSilverDB:
    """Records calls to SQL-issuing methods so tests can assert query content."""

    def __init__(
        self,
        *,
        filings: list[dict] | None = None,
        already_parsed: list[str] | None = None,
        attachments: dict[str, list[dict]] | None = None,
        raw_objects: dict[str, dict] | None = None,
    ) -> None:
        self.filings = filings or []
        self.already_parsed_accessions = set(already_parsed or [])
        self.attachments = attachments or {}
        self.raw_objects = raw_objects or {}

        # Track every SQL string passed to fetch() so tests can assert column names
        self.fetch_calls: list[str] = []
        self.merge_ownership_reporting_owners_calls: list[tuple] = []
        self.merge_ownership_non_derivative_txns_calls: list[tuple] = []
        self.merge_ownership_derivative_txns_calls: list[tuple] = []

    def fetch(self, sql: str, params: list | None = None) -> list[dict]:
        self.fetch_calls.append(sql)
        # Returns filings if this looks like the main filing query
        if "sec_company_filing" in sql and "form" in sql.lower():
            return list(self.filings)
        # Returns already-parsed accession numbers
        if "sec_ownership_reporting_owner" in sql:
            return [{"accession_number": a} for a in self.already_parsed_accessions]
        return []

    def get_filing_attachments(self, accession_number: str) -> list[dict]:
        return list(self.attachments.get(accession_number, []))

    def get_raw_object(self, raw_object_id: str) -> dict | None:
        return self.raw_objects.get(raw_object_id)

    def merge_ownership_reporting_owners(self, rows: list[dict], sync_run_id: str) -> int:
        self.merge_ownership_reporting_owners_calls.append((rows, sync_run_id))
        return len(rows)

    def merge_ownership_non_derivative_txns(self, rows: list[dict], sync_run_id: str) -> int:
        self.merge_ownership_non_derivative_txns_calls.append((rows, sync_run_id))
        return len(rows)

    def merge_ownership_derivative_txns(self, rows: list[dict], sync_run_id: str) -> int:
        self.merge_ownership_derivative_txns_calls.append((rows, sync_run_id))
        return len(rows)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def bronze_context(tmp_path):
    """Minimal WarehouseCommandContext backed by local tmp directories."""
    return WarehouseCommandContext(
        bronze_root=StorageLocation(str(tmp_path / "bronze")),
        storage_root=StorageLocation(str(tmp_path / "silver_root")),
        silver_root=StorageLocation(str(tmp_path / "silver")),
        snowflake_export_root=None,
        environment_name="test",
        identity="test@example.com",
        runtime_mode="bronze_capture",
    )


MINIMAL_FORM4_XML = b"""<?xml version="1.0"?>
<ownershipDocument>
  <issuer><issuerCik>910001</issuerCik><issuerName>Test Co</issuerName></issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerCik>910101</rptOwnerCik><rptOwnerName>Jane Doe</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isDirector>1</isDirector></reportingOwnerRelationship>
  </reportingOwner>
</ownershipDocument>"""


# ---------------------------------------------------------------------------
# D-07: Current silver schema column names
# ---------------------------------------------------------------------------

class TestSilverSchemaColumnNames:
    """D-07: _run_parse_ownership_bronze MUST use `form` and `report_date`.

    The current code queries `form_type` and `period_of_report` — this test
    FAILS against the current implementation.
    """

    def test_main_query_uses_form_not_form_type(self, bronze_context, tmp_path):
        """The SQL sent to sec_company_filing must reference `form`, not `form_type`."""
        from edgar_warehouse.application import warehouse_orchestrator

        db = FakeSilverDB()
        warehouse_orchestrator._run_parse_ownership_bronze(
            context=bronze_context,
            db=db,
            sync_run_id="run-test",
            metrics={},
        )

        # Find the main filing query
        filing_queries = [
            sql for sql in db.fetch_calls
            if "sec_company_filing" in sql
        ]
        assert filing_queries, "Expected at least one query against sec_company_filing"
        for sql in filing_queries:
            assert "form_type" not in sql, (
                f"Query uses stale column 'form_type'; should use 'form'.\nSQL:\n{sql}"
            )
            assert re.search(r"\bform\b", sql), (
                f"Query must select/filter on column 'form'.\nSQL:\n{sql}"
            )

    def test_main_query_orders_by_report_date_not_period_of_report(self, bronze_context, tmp_path):
        """The ORDER BY clause must use `report_date`, not `period_of_report`."""
        from edgar_warehouse.application import warehouse_orchestrator

        db = FakeSilverDB()
        warehouse_orchestrator._run_parse_ownership_bronze(
            context=bronze_context,
            db=db,
            sync_run_id="run-test",
            metrics={},
        )

        filing_queries = [
            sql for sql in db.fetch_calls
            if "sec_company_filing" in sql
        ]
        for sql in filing_queries:
            assert "period_of_report" not in sql, (
                f"Query uses stale ORDER BY column 'period_of_report'; should use 'report_date'.\nSQL:\n{sql}"
            )

    def test_query_selects_form_in_where_clause(self, bronze_context):
        """The WHERE clause must filter on `form IN (...)` not `form_type IN (...)`."""
        from edgar_warehouse.application import warehouse_orchestrator

        db = FakeSilverDB()
        warehouse_orchestrator._run_parse_ownership_bronze(
            context=bronze_context,
            db=db,
            sync_run_id="run-test",
            metrics={},
        )

        filing_queries = [
            sql for sql in db.fetch_calls
            if "sec_company_filing" in sql and ("3" in sql or "4" in sql or "5" in sql)
        ]
        assert filing_queries, "Expected a query filtering sec_company_filing by form type values"
        for sql in filing_queries:
            # Must use 'form' as the column name for form type filtering
            assert "form_type" not in sql, (
                f"WHERE clause uses stale 'form_type'; should use 'form'."
            )


# ---------------------------------------------------------------------------
# D-08: Artifact-registry based reads
# ---------------------------------------------------------------------------

class TestArtifactRegistryRead:
    """D-08: Must read primary XML through sec_filing_attachment + sec_raw_object + read_bytes.

    The current code uses fsspec.filesystem("s3").ls(prefix) instead.
    These tests FAIL against the current implementation because the current
    code does not call get_filing_attachments or get_raw_object.
    """

    def test_calls_get_filing_attachments(self, bronze_context):
        """For each unparsed Form 4, must call db.get_filing_attachments(accession_number)."""
        from edgar_warehouse.application import warehouse_orchestrator

        raw_id = str(uuid.uuid4())
        db = FakeSilverDB(
            filings=[
                {"accession_number": "0001234567-24-000001", "cik": 910001, "form": "4"},
            ],
            attachments={
                "0001234567-24-000001": [
                    {
                        "accession_number": "0001234567-24-000001",
                        "document_name": "primary.xml",
                        "is_primary": True,
                        "raw_object_id": raw_id,
                    }
                ]
            },
            raw_objects={raw_id: {"storage_path": "/tmp/primary.xml", "raw_object_id": raw_id}},
        )

        # Track whether get_filing_attachments was called
        original_get_filing_attachments = db.get_filing_attachments
        attachment_calls: list[str] = []

        def spy_attachments(accession_number: str) -> list[dict]:
            attachment_calls.append(accession_number)
            return original_get_filing_attachments(accession_number)

        db.get_filing_attachments = spy_attachments

        with patch.object(
            warehouse_orchestrator, "read_bytes", return_value=MINIMAL_FORM4_XML
        ):
            warehouse_orchestrator._run_parse_ownership_bronze(
                context=bronze_context,
                db=db,
                sync_run_id="run-test",
                metrics={},
            )

        assert "0001234567-24-000001" in attachment_calls, (
            "Expected get_filing_attachments to be called with the unparsed accession number"
        )

    def test_calls_get_raw_object_with_raw_object_id(self, bronze_context):
        """After finding the primary attachment, must call db.get_raw_object(raw_object_id)."""
        from edgar_warehouse.application import warehouse_orchestrator

        raw_id = str(uuid.uuid4())
        db = FakeSilverDB(
            filings=[
                {"accession_number": "0001234567-24-000002", "cik": 910001, "form": "4"},
            ],
            attachments={
                "0001234567-24-000002": [
                    {
                        "accession_number": "0001234567-24-000002",
                        "document_name": "primary.xml",
                        "is_primary": True,
                        "raw_object_id": raw_id,
                    }
                ]
            },
            raw_objects={raw_id: {"storage_path": "/tmp/primary.xml", "raw_object_id": raw_id}},
        )

        raw_object_calls: list[str] = []
        original = db.get_raw_object

        def spy_raw_object(raw_object_id: str) -> dict | None:
            raw_object_calls.append(raw_object_id)
            return original(raw_object_id)

        db.get_raw_object = spy_raw_object

        with patch.object(
            warehouse_orchestrator, "read_bytes", return_value=MINIMAL_FORM4_XML
        ):
            warehouse_orchestrator._run_parse_ownership_bronze(
                context=bronze_context,
                db=db,
                sync_run_id="run-test",
                metrics={},
            )

        assert raw_id in raw_object_calls, (
            f"Expected get_raw_object to be called with raw_object_id={raw_id!r}"
        )

    def test_calls_read_bytes_with_storage_path_from_registry(self, bronze_context):
        """Must call read_bytes(storage_path) with the path from sec_raw_object, not a constructed prefix."""
        from edgar_warehouse.application import warehouse_orchestrator

        raw_id = str(uuid.uuid4())
        storage_path = "/tmp/unique-fixture-path.xml"
        db = FakeSilverDB(
            filings=[
                {"accession_number": "0001234567-24-000003", "cik": 910001, "form": "4"},
            ],
            attachments={
                "0001234567-24-000003": [
                    {
                        "accession_number": "0001234567-24-000003",
                        "document_name": "primary.xml",
                        "is_primary": True,
                        "raw_object_id": raw_id,
                    }
                ]
            },
            raw_objects={raw_id: {"storage_path": storage_path, "raw_object_id": raw_id}},
        )

        read_bytes_calls: list[str] = []

        def spy_read_bytes(path: str) -> bytes:
            read_bytes_calls.append(path)
            return MINIMAL_FORM4_XML

        with patch.object(warehouse_orchestrator, "read_bytes", side_effect=spy_read_bytes):
            warehouse_orchestrator._run_parse_ownership_bronze(
                context=bronze_context,
                db=db,
                sync_run_id="run-test",
                metrics={},
            )

        assert read_bytes_calls, "Expected read_bytes to be called"
        assert storage_path in read_bytes_calls, (
            f"Expected read_bytes to be called with storage_path={storage_path!r} "
            f"from sec_raw_object registry. Got: {read_bytes_calls}"
        )

    def test_does_not_use_s3_prefix_listing(self, bronze_context):
        """Must not enumerate S3 prefixes via fsspec to find primary XML files.

        The current code calls fsspec.filesystem("s3").ls(prefix) — this test asserts
        that must be removed in favor of artifact-registry reads.
        """
        import fsspec
        from edgar_warehouse.application import warehouse_orchestrator

        raw_id = str(uuid.uuid4())
        db = FakeSilverDB(
            filings=[
                {"accession_number": "0001234567-24-000004", "cik": 910001, "form": "4"},
            ],
            attachments={
                "0001234567-24-000004": [
                    {
                        "is_primary": True,
                        "raw_object_id": raw_id,
                    }
                ]
            },
            raw_objects={raw_id: {"storage_path": "/tmp/form4.xml"}},
        )

        fs_calls: list[tuple] = []
        original_filesystem = fsspec.filesystem

        def spy_filesystem(protocol: str, **kwargs):
            fs_calls.append((protocol, kwargs))
            return original_filesystem(protocol, **kwargs)

        with (
            patch("fsspec.filesystem", side_effect=spy_filesystem),
            patch.object(warehouse_orchestrator, "read_bytes", return_value=MINIMAL_FORM4_XML),
        ):
            warehouse_orchestrator._run_parse_ownership_bronze(
                context=bronze_context,
                db=db,
                sync_run_id="run-test",
                metrics={},
            )

        s3_filesystem_calls = [c for c in fs_calls if c[0] == "s3"]
        assert not s3_filesystem_calls, (
            "Must not call fsspec.filesystem('s3') to list S3 prefixes; "
            "use sec_filing_attachment + sec_raw_object + read_bytes(storage_path) instead."
        )


# ---------------------------------------------------------------------------
# D-09: Missing primary artifact reporting
# ---------------------------------------------------------------------------

class TestMissingPrimaryArtifactReporting:
    """D-09: Missing bronze primary artifacts must be reported in metrics, not silently skipped.

    The current code increments error_count when xml_files is empty but does not
    distinguish "primary artifact registry row missing" from parse errors.
    """

    def test_missing_primary_attachment_increments_error_count(self, bronze_context):
        """When sec_filing_attachment has no primary row, error count must increase."""
        from edgar_warehouse.application import warehouse_orchestrator

        db = FakeSilverDB(
            filings=[
                {"accession_number": "0001234567-24-000010", "cik": 910001, "form": "4"},
            ],
            attachments={},  # No attachment rows registered
            raw_objects={},
        )

        metrics: dict = {}
        warehouse_orchestrator._run_parse_ownership_bronze(
            context=bronze_context,
            db=db,
            sync_run_id="run-test",
            metrics=metrics,
        )

        # Must record missing artifact as an observable metric
        assert metrics.get("errors", 0) > 0 or metrics.get("missing_artifacts", 0) > 0, (
            "Expected error or missing_artifact count when primary attachment is not registered"
        )

    def test_missing_primary_attachment_does_not_raise(self, bronze_context):
        """Command must complete without raising an exception for missing artifacts."""
        from edgar_warehouse.application import warehouse_orchestrator

        db = FakeSilverDB(
            filings=[
                {"accession_number": "0001234567-24-000011", "cik": 910001, "form": "4"},
                {"accession_number": "0001234567-24-000012", "cik": 910001, "form": "3"},
            ],
            attachments={},
            raw_objects={},
        )

        metrics: dict = {}
        # Must not raise
        warehouse_orchestrator._run_parse_ownership_bronze(
            context=bronze_context,
            db=db,
            sync_run_id="run-test",
            metrics=metrics,
        )
        # Both accessions had no artifacts: 2 errors
        total_issues = metrics.get("errors", 0) + metrics.get("missing_artifacts", 0)
        assert total_issues >= 2, (
            f"Expected ≥2 reported issues for 2 missing-artifact filings, got metrics={metrics}"
        )


# ---------------------------------------------------------------------------
# D-09/D-10: No SEC API calls
# ---------------------------------------------------------------------------

class TestNoSecApiCalls:
    """D-10: Must not call download_sec_bytes or SEC download helpers.

    The current code does not guard against SEC fetches; these tests assert that
    the repair makes it impossible.
    """

    def test_download_sec_bytes_not_called(self, bronze_context):
        """download_sec_bytes must never be invoked during parse-ownership-bronze."""
        from edgar_warehouse.application import warehouse_orchestrator

        raw_id = str(uuid.uuid4())
        db = FakeSilverDB(
            filings=[
                {"accession_number": "0001234567-24-000020", "cik": 910001, "form": "4"},
            ],
            attachments={
                "0001234567-24-000020": [
                    {"is_primary": True, "raw_object_id": raw_id}
                ]
            },
            raw_objects={raw_id: {"storage_path": "/tmp/form4.xml"}},
        )

        with (
            patch.object(
                warehouse_orchestrator, "download_sec_bytes", side_effect=AssertionError(
                    "download_sec_bytes must not be called in parse-ownership-bronze"
                )
            ),
            patch.object(warehouse_orchestrator, "read_bytes", return_value=MINIMAL_FORM4_XML),
        ):
            # If this raises AssertionError, the current code is trying to fetch from SEC
            warehouse_orchestrator._run_parse_ownership_bronze(
                context=bronze_context,
                db=db,
                sync_run_id="run-test",
                metrics={},
            )


# ---------------------------------------------------------------------------
# Skip already-parsed accessions (D-01, D-02)
# ---------------------------------------------------------------------------

class TestSkipAlreadyParsed:
    """D-01/D-02: Accessions present in sec_ownership_reporting_owner must be skipped."""

    def test_already_parsed_accession_is_skipped(self, bronze_context):
        """If sec_ownership_reporting_owner already has rows for an accession, skip it."""
        from edgar_warehouse.application import warehouse_orchestrator

        accession = "0001234567-24-000030"
        db = FakeSilverDB(
            filings=[
                {"accession_number": accession, "cik": 910001, "form": "4"},
            ],
            already_parsed=[accession],
        )

        metrics: dict = {}
        warehouse_orchestrator._run_parse_ownership_bronze(
            context=bronze_context,
            db=db,
            sync_run_id="run-test",
            metrics=metrics,
        )

        assert metrics.get("skipped", 0) >= 1, (
            f"Expected skipped≥1 for already-parsed accession; got metrics={metrics}"
        )
        # Must not attempt to read artifact
        assert not db.merge_ownership_reporting_owners_calls, (
            "Must not merge ownership rows for already-parsed accessions"
        )

    def test_skip_check_queries_sec_ownership_reporting_owner(self, bronze_context):
        """The skip-check must query sec_ownership_reporting_owner for known accessions."""
        from edgar_warehouse.application import warehouse_orchestrator

        db = FakeSilverDB()
        warehouse_orchestrator._run_parse_ownership_bronze(
            context=bronze_context,
            db=db,
            sync_run_id="run-test",
            metrics={},
        )

        skip_queries = [
            sql for sql in db.fetch_calls
            if "sec_ownership_reporting_owner" in sql
        ]
        assert skip_queries, (
            "Expected a query against sec_ownership_reporting_owner to build the already-parsed set"
        )


# ---------------------------------------------------------------------------
# Parser output merged into all three silver tables (D-01, D-02)
# ---------------------------------------------------------------------------

class TestParserOutputMerged:
    """D-01/D-02: Parsed ownership rows must be merged into all three silver tables."""

    def test_all_three_silver_tables_receive_merge_calls(self, bronze_context):
        """When parser produces rows, all three merge methods must be called."""
        from edgar_warehouse.application import warehouse_orchestrator

        raw_id = str(uuid.uuid4())
        accession = "0001234567-24-000040"
        db = FakeSilverDB(
            filings=[{"accession_number": accession, "cik": 910001, "form": "4"}],
            attachments={
                accession: [{"is_primary": True, "raw_object_id": raw_id}]
            },
            raw_objects={raw_id: {"storage_path": "/tmp/form4.xml"}},
        )

        fake_parsed = {
            "sec_ownership_reporting_owner": [
                {"accession_number": accession, "owner_index": 0, "owner_name": "Jane Doe"}
            ],
            "sec_ownership_non_derivative_txn": [
                {
                    "accession_number": accession,
                    "owner_index": 0,
                    "txn_index": 0,
                    "security_title": "Common Stock",
                }
            ],
            "sec_ownership_derivative_txn": [],
        }

        with (
            patch.object(warehouse_orchestrator, "read_bytes", return_value=MINIMAL_FORM4_XML),
            patch(
                "edgar_warehouse.parsers.ownership.parse_ownership",
                return_value=fake_parsed,
            ) as mock_parse,
        ):
            warehouse_orchestrator._run_parse_ownership_bronze(
                context=bronze_context,
                db=db,
                sync_run_id="run-test",
                metrics={},
            )

        assert mock_parse.called, "parse_ownership must be called"
        assert db.merge_ownership_reporting_owners_calls, (
            "Expected merge_ownership_reporting_owners to be called"
        )
        assert db.merge_ownership_non_derivative_txns_calls, (
            "Expected merge_ownership_non_derivative_txns to be called"
        )
        assert db.merge_ownership_derivative_txns_calls, (
            "Expected merge_ownership_derivative_txns to be called (even for empty list)"
        )
