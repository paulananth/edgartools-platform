"""Idempotency tests for SEC loader cache behavior."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from edgar_warehouse import bronze_filing_artifacts
from edgar_warehouse.application import warehouse_orchestrator
from edgar_warehouse.infrastructure.dataset_path_catalog import default_path_resolver
from edgar_warehouse.infrastructure.object_storage import StorageLocation


class _CheckpointDb:
    def __init__(self, bronze_path: str, sha256: str) -> None:
        self._bronze_path = bronze_path
        self._sha256 = sha256

    def get_source_checkpoint(self, source_name: str, source_key: str):
        return {
            "bronze_path": self._bronze_path,
            "last_sha256": self._sha256,
        }


class _NoCheckpointDb:
    """Simulates a fresh silver database that has never processed this CIK locally."""

    def get_source_checkpoint(self, source_name: str, source_key: str):
        return None


class _ArtifactDb:
    def __init__(self, *, attachments=None, raw_objects=None) -> None:
        self.filing = {
            "cik": 320193,
            "form": "4",
            "primary_document": "primary.xml",
        }
        self.attachments = list(attachments or [])
        self.raw_objects = dict(raw_objects or {})
        self.merged_rows = []

    def get_filing(self, accession_number: str):
        return dict(self.filing, accession_number=accession_number)

    def get_filing_attachments(self, accession_number: str):
        return [row for row in self.attachments if row["accession_number"] == accession_number]

    def get_raw_object(self, raw_object_id: str):
        return self.raw_objects.get(raw_object_id)

    def get_raw_objects_for_accession(self, accession_number: str, source_type: str | None = None):
        rows = [
            row
            for row in self.raw_objects.values()
            if row.get("accession_number") == accession_number
            and (source_type is None or row.get("source_type") == source_type)
        ]
        return rows

    def upsert_raw_object(self, row: dict) -> None:
        self.raw_objects[row["raw_object_id"]] = dict(row)

    def merge_filing_attachments(self, rows: list[dict], sync_run_id: str) -> int:
        self.merged_rows.extend(rows)
        self.attachments = list(rows)
        return len(rows)


class _FakeAttachment:
    """Minimal double for edgar.attachments.Attachment — only the fields
    _map_edgartools_attachments() reads."""

    def __init__(self, *, sequence_number, document, document_type, description, url, content):
        self.sequence_number = sequence_number
        self.document = document
        self.document_type = document_type
        self.description = description
        self.url = url
        self.content = content


class _FakeAttachments:
    """Minimal double for edgar.attachments.Attachments — iterable, plus
    primary_documents for is_primary derivation."""

    def __init__(self, items, primary_documents=None):
        self._items = list(items)
        self.primary_documents = list(primary_documents) if primary_documents is not None else list(items)

    def __iter__(self):
        return iter(self._items)


class _FakeFiling:
    """Minimal double for edgar.Filing — only the .attachments attribute is used."""

    def __init__(self, *, attachments):
        self.attachments = attachments


class LoaderIdempotencyTests(unittest.TestCase):
    def test_cached_submission_main_skips_sec_download(self) -> None:
        payload = b'{"cik": "0000320193", "filings": {"recent": {}}}'
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            bronze_path = Path(tmp) / "submissions.json"
            bronze_path.write_bytes(payload)
            context = SimpleNamespace(bronze_root=StorageLocation(tmp), identity="tester@example.com")
            db = _CheckpointDb(str(bronze_path), digest)

            with patch.object(warehouse_orchestrator, "_download_sec_bytes", side_effect=AssertionError("SEC download")):
                result = warehouse_orchestrator._capture_submissions_main(
                    context=context,
                    db=db,
                    cik=320193,
                    fetch_date=date(2026, 5, 8),
                    force=False,
                )

        self.assertTrue(result["write_record"]["cached"])
        self.assertEqual(result["write_record"]["sha256"], digest)

    def test_force_submission_main_downloads_again(self) -> None:
        payload = b'{"cik": "0000320193", "filings": {"recent": {}}}'
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            bronze_path = Path(tmp) / "submissions.json"
            bronze_path.write_bytes(payload)
            context = SimpleNamespace(bronze_root=StorageLocation(tmp), identity="tester@example.com")
            db = _CheckpointDb(str(bronze_path), digest)

            downloader = Mock(return_value=payload)
            with patch.object(warehouse_orchestrator, "_download_sec_bytes", downloader):
                result = warehouse_orchestrator._capture_submissions_main(
                    context=context,
                    db=db,
                    cik=320193,
                    fetch_date=date(2026, 5, 8),
                    force=True,
                )

        self.assertFalse(result["write_record"].get("cached", False))
        self.assertEqual(downloader.call_count, 1)

    def test_no_checkpoint_but_existing_bronze_skips_sec_download(self) -> None:
        """A fresh silver DB (no checkpoint for this CIK) must still find bronze that
        already exists in storage from another environment's run (e.g. synced via
        `aws s3 sync`), rather than re-fetching from SEC. Regression test for the bug
        where bronze_seed_silver_gold made thousands of live SEC calls despite the
        CIKs already having bronze in S3."""
        cik = 320193
        payload = b'{"cik": "0000320193", "filings": {"recent": {}}}'
        with tempfile.TemporaryDirectory() as tmp:
            bronze_root = StorageLocation(tmp)
            # Bronze was captured on a past date by a different run/environment —
            # there is no checkpoint for it in this (fresh) silver database.
            relative_path = default_path_resolver().submissions_main_path(cik, date(2026, 1, 1))
            bronze_root.write_bytes(relative_path, payload)
            context = SimpleNamespace(bronze_root=bronze_root, identity="tester@example.com")
            db = _NoCheckpointDb()

            with patch.object(warehouse_orchestrator, "_download_sec_bytes", side_effect=AssertionError("SEC download")):
                result = warehouse_orchestrator._capture_submissions_main(
                    context=context,
                    db=db,
                    cik=cik,
                    fetch_date=date(2026, 5, 8),
                    force=False,
                )

        self.assertTrue(result["write_record"]["cached"])
        self.assertEqual(result["write_record"]["sha256"], hashlib.sha256(payload).hexdigest())

    def test_no_checkpoint_and_no_existing_bronze_downloads_from_sec(self) -> None:
        """No checkpoint and no existing bronze anywhere -> must still hit SEC."""
        with tempfile.TemporaryDirectory() as tmp:
            context = SimpleNamespace(bronze_root=StorageLocation(tmp), identity="tester@example.com")
            db = _NoCheckpointDb()
            payload = b'{"cik": "0000320193", "filings": {"recent": {}}}'
            downloader = Mock(return_value=payload)

            with patch.object(warehouse_orchestrator, "_download_sec_bytes", downloader):
                result = warehouse_orchestrator._capture_submissions_main(
                    context=context,
                    db=db,
                    cik=320193,
                    fetch_date=date(2026, 5, 8),
                    force=False,
                )

        self.assertFalse(result["write_record"].get("cached", False))
        self.assertEqual(downloader.call_count, 1)

    def test_existing_filing_attachment_skips_index_and_document_downloads(self) -> None:
        accession = "0000320193-26-000001"
        raw_object_id = "raw-primary"
        attachments = [
            {
                "accession_number": accession,
                "document_name": "primary.xml",
                "document_type": "4",
                "document_url": "https://www.sec.gov/Archives/edgar/data/320193/primary.xml",
                "is_primary": True,
                "raw_object_id": raw_object_id,
            }
        ]
        raw_objects = {
            raw_object_id: {
                "raw_object_id": raw_object_id,
                "accession_number": accession,
                "source_type": "filing_document",
                "source_url": attachments[0]["document_url"],
                "storage_path": "s3://bucket/primary.xml",
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            db = _ArtifactDb(attachments=attachments, raw_objects=raw_objects)
            context = SimpleNamespace(bronze_root=StorageLocation(tmp), identity="tester@example.com")

            result = bronze_filing_artifacts.fetch_filing_artifacts(
                context=context,
                db=db,
                accession_number=accession,
                sync_run_id="run-1",
                download_bytes=Mock(side_effect=AssertionError("SEC download")),
                get_filing=Mock(side_effect=AssertionError("edgartools fetch")),
                force=False,
            )

        self.assertEqual(result["attachment_count"], 1)
        self.assertEqual(result["raw_writes"][0]["cached"], True)
        self.assertEqual(db.merged_rows, [])
        # Cache hit: no SEC request was made, so the orchestrator must not throttle.
        self.assertEqual(result["network_fetches"], 0)

    def test_force_filing_artifact_uses_edgartools_fallback_when_primary_document_unknown(self) -> None:
        """When primary_document is unknown (fast path unavailable) or force=True, the
        fallback must fetch via edgartools (injected as get_filing), not the old
        index.html-fetch-and-BeautifulSoup-parse path. Regression test for the 503 on
        www.sec.gov/.../{accession}-index.html that survived sec_client's own retries."""
        accession = "0000320193-26-000001"
        primary_attachment = _FakeAttachment(
            sequence_number="1",
            document="primary.xml",
            document_type="4",
            description="Primary document",
            url="https://www.sec.gov/Archives/edgar/data/320193/primary.xml",
            content="<ownershipDocument />",
        )
        fake_filing = _FakeFiling(attachments=_FakeAttachments([primary_attachment]))
        get_filing = Mock(return_value=fake_filing)
        downloads = Mock(side_effect=AssertionError("download_bytes should not be called — edgartools already fetched content"))

        with tempfile.TemporaryDirectory() as tmp:
            db = _ArtifactDb()
            context = SimpleNamespace(bronze_root=StorageLocation(tmp), identity="tester@example.com")

            result = bronze_filing_artifacts.fetch_filing_artifacts(
                context=context,
                db=db,
                accession_number=accession,
                sync_run_id="run-1",
                download_bytes=downloads,
                get_filing=get_filing,
                force=True,
            )

        get_filing.assert_called_once_with(accession)
        self.assertEqual(result["attachment_count"], 1)
        # A real SEC fetch occurred (edgartools get_filing) → orchestrator must throttle.
        self.assertEqual(result["network_fetches"], 1)
        # One raw_writes entry (the document) — no separate index-page artifact anymore.
        self.assertEqual(len(result["raw_writes"]), 1)
        self.assertEqual(len(db.merged_rows), 1)
        self.assertTrue(db.merged_rows[0]["is_primary"])
        self.assertEqual(db.merged_rows[0]["document_name"], "primary.xml")

    def test_edgartools_fallback_maps_non_primary_attachment_correctly(self) -> None:
        """A filing with multiple attachments must correctly identify which one is
        primary via membership in attachments.primary_documents, not just take the
        first row."""
        accession = "0000320193-26-000002"
        exhibit = _FakeAttachment(
            sequence_number="1",
            document="exhibit99.htm",
            document_type="EX-99",
            description="Exhibit",
            url="https://www.sec.gov/Archives/edgar/data/320193/exhibit99.htm",
            content="<html>exhibit</html>",
        )
        primary = _FakeAttachment(
            sequence_number="2",
            document="primary.xml",
            document_type="4",
            description="Primary document",
            url="https://www.sec.gov/Archives/edgar/data/320193/primary.xml",
            content="<ownershipDocument />",
        )
        fake_filing = _FakeFiling(attachments=_FakeAttachments([exhibit, primary], primary_documents=[primary]))
        get_filing = Mock(return_value=fake_filing)
        downloads = Mock(side_effect=AssertionError("download_bytes should not be called"))

        with tempfile.TemporaryDirectory() as tmp:
            db = _ArtifactDb()
            context = SimpleNamespace(bronze_root=StorageLocation(tmp), identity="tester@example.com")

            result = bronze_filing_artifacts.fetch_filing_artifacts(
                context=context,
                db=db,
                accession_number=accession,
                sync_run_id="run-1",
                download_bytes=downloads,
                get_filing=get_filing,
                force=True,
            )

        self.assertEqual(result["attachment_count"], 2)
        rows_by_name = {row["document_name"]: row for row in db.merged_rows}
        self.assertFalse(rows_by_name["exhibit99.htm"]["is_primary"])
        self.assertTrue(rows_by_name["primary.xml"]["is_primary"])

    def test_13f_hr_bypasses_fast_path_to_discover_information_table(self) -> None:
        """EDGE-11 5-whys (06-04): the primary_document fast path only ever registers
        the primary/cover document. For 13F-HR, the holdings live in a separate
        INFORMATION TABLE attachment that the fast path never discovers or fetches —
        `run_bootstrap_thirteenf`'s attachment lookup then always misses and every
        13F-HR filing is skipped (sec_thirteenf_holding stays empty even though the
        bronze filing record and cover-page document are present). 13F-HR/13F-HR-A
        must always take the full edgartools attachment-discovery fallback so the
        INFORMATION TABLE attachment is fetched and registered alongside the cover
        page, even when primary_document is known and force=False."""
        accession = "0001067983-26-000123"
        cover_page = _FakeAttachment(
            sequence_number="1",
            document="primary_doc.xml",
            document_type="13F-HR",
            description="",
            url="https://www.sec.gov/Archives/edgar/data/1067983/primary_doc.xml",
            content="<edgarSubmission />",
        )
        infotable = _FakeAttachment(
            sequence_number="2",
            document="53405.xml",
            document_type="INFORMATION TABLE",
            description="INFORMATION TABLE FOR FORM 13F",
            url="https://www.sec.gov/Archives/edgar/data/1067983/53405.xml",
            content="<informationTable />",
        )
        fake_filing = _FakeFiling(
            attachments=_FakeAttachments([cover_page, infotable], primary_documents=[cover_page])
        )
        get_filing = Mock(return_value=fake_filing)
        downloads = Mock(side_effect=AssertionError(
            "download_bytes should not be called — edgartools already fetched content"
        ))

        with tempfile.TemporaryDirectory() as tmp:
            db = _ArtifactDb()
            db.filing = {
                "cik": 1067983,
                "form": "13F-HR",
                "primary_document": "xslForm13F_X02/primary_doc.xml",
            }
            context = SimpleNamespace(bronze_root=StorageLocation(tmp), identity="tester@example.com")

            result = bronze_filing_artifacts.fetch_filing_artifacts(
                context=context,
                db=db,
                accession_number=accession,
                sync_run_id="run-1",
                download_bytes=downloads,
                get_filing=get_filing,
                force=False,
            )

        get_filing.assert_called_once_with(accession)
        self.assertEqual(result["attachment_count"], 2)
        rows_by_name = {row["document_name"]: row for row in db.merged_rows}
        self.assertIn("53405.xml", rows_by_name)
        self.assertEqual(rows_by_name["53405.xml"]["document_type"], "INFORMATION TABLE")
        self.assertTrue(rows_by_name["primary_doc.xml"]["is_primary"])
        self.assertFalse(rows_by_name["53405.xml"]["is_primary"])

    def test_13f_hr_amendment_also_bypasses_fast_path(self) -> None:
        """13F-HR/A must get the same treatment as 13F-HR (EDGE-11, 06-04)."""
        accession = "0001067983-26-000456"
        cover_page = _FakeAttachment(
            sequence_number="1",
            document="primary_doc.xml",
            document_type="13F-HR/A",
            description="",
            url="https://www.sec.gov/Archives/edgar/data/1067983/primary_doc.xml",
            content="<edgarSubmission />",
        )
        infotable = _FakeAttachment(
            sequence_number="2",
            document="99999.xml",
            document_type="INFORMATION TABLE",
            description="INFORMATION TABLE FOR FORM 13F",
            url="https://www.sec.gov/Archives/edgar/data/1067983/99999.xml",
            content="<informationTable />",
        )
        fake_filing = _FakeFiling(
            attachments=_FakeAttachments([cover_page, infotable], primary_documents=[cover_page])
        )
        get_filing = Mock(return_value=fake_filing)
        downloads = Mock(side_effect=AssertionError("download_bytes should not be called"))

        with tempfile.TemporaryDirectory() as tmp:
            db = _ArtifactDb()
            db.filing = {
                "cik": 1067983,
                "form": "13F-HR/A",
                "primary_document": "xslForm13F_X02/primary_doc.xml",
            }
            context = SimpleNamespace(bronze_root=StorageLocation(tmp), identity="tester@example.com")

            result = bronze_filing_artifacts.fetch_filing_artifacts(
                context=context,
                db=db,
                accession_number=accession,
                sync_run_id="run-1",
                download_bytes=downloads,
                get_filing=get_filing,
                force=False,
            )

        get_filing.assert_called_once_with(accession)
        self.assertEqual(result["attachment_count"], 2)

    def test_def14a_existing_filing_attachment_skips_index_and_document_downloads(self) -> None:
        """DEF 14A cache hit must be as network-free as every other form type
        (07-06 Task 3: idempotency is asserted at the shared service boundary
        for every filing type, not just ownership forms)."""
        accession = "0000320193-26-000777"
        raw_object_id = "raw-def14a-primary"
        attachments = [
            {
                "accession_number": accession,
                "document_name": "def14a.htm",
                "document_type": "DEF 14A",
                "document_url": "https://www.sec.gov/Archives/edgar/data/320193/def14a.htm",
                "is_primary": True,
                "raw_object_id": raw_object_id,
            }
        ]
        raw_objects = {
            raw_object_id: {
                "raw_object_id": raw_object_id,
                "accession_number": accession,
                "source_type": "filing_document",
                "source_url": attachments[0]["document_url"],
                "storage_path": "s3://bucket/def14a.htm",
                "sha256": raw_object_id,
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            db = _ArtifactDb(attachments=attachments, raw_objects=raw_objects)
            db.filing = {"cik": 320193, "form": "DEF 14A", "primary_document": "def14a.htm"}
            context = SimpleNamespace(bronze_root=StorageLocation(tmp), identity="tester@example.com")

            result = bronze_filing_artifacts.fetch_filing_artifacts(
                context=context,
                db=db,
                accession_number=accession,
                sync_run_id="run-1",
                download_bytes=Mock(side_effect=AssertionError("SEC download")),
                get_filing=Mock(side_effect=AssertionError("edgartools fetch")),
                force=False,
            )

        self.assertEqual(result["attachment_count"], 1)
        self.assertEqual(result["raw_writes"][0]["cached"], True)
        self.assertEqual(db.merged_rows, [])
        self.assertEqual(result["network_fetches"], 0)

    def test_13f_hr_cached_attachments_skip_downloads_and_report_zero_network_fetches(self) -> None:
        """13F-HR must also honor the cache-hit path once its attachments (cover
        page + INFORMATION TABLE) are already captured -- the EDGE-11 fallback
        only applies to the first, cold-start fetch."""
        accession = "0001067983-26-000999"
        cover_raw_id = "raw-13f-cover"
        infotable_raw_id = "raw-13f-infotable"
        attachments = [
            {
                "accession_number": accession,
                "document_name": "primary_doc.xml",
                "document_type": "13F-HR",
                "document_url": "https://www.sec.gov/Archives/edgar/data/1067983/primary_doc.xml",
                "is_primary": True,
                "raw_object_id": cover_raw_id,
            },
            {
                "accession_number": accession,
                "document_name": "53405.xml",
                "document_type": "INFORMATION TABLE",
                "document_url": "https://www.sec.gov/Archives/edgar/data/1067983/53405.xml",
                "is_primary": False,
                "raw_object_id": infotable_raw_id,
            },
        ]
        raw_objects = {
            cover_raw_id: {
                "raw_object_id": cover_raw_id,
                "accession_number": accession,
                "source_type": "filing_document",
                "source_url": attachments[0]["document_url"],
                "storage_path": "s3://bucket/primary_doc.xml",
                "sha256": cover_raw_id,
            },
            infotable_raw_id: {
                "raw_object_id": infotable_raw_id,
                "accession_number": accession,
                "source_type": "attachment",
                "source_url": attachments[1]["document_url"],
                "storage_path": "s3://bucket/53405.xml",
                "sha256": infotable_raw_id,
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            db = _ArtifactDb(attachments=attachments, raw_objects=raw_objects)
            db.filing = {
                "cik": 1067983,
                "form": "13F-HR",
                "primary_document": "xslForm13F_X02/primary_doc.xml",
            }
            context = SimpleNamespace(bronze_root=StorageLocation(tmp), identity="tester@example.com")

            result = bronze_filing_artifacts.fetch_filing_artifacts(
                context=context,
                db=db,
                accession_number=accession,
                sync_run_id="run-1",
                download_bytes=Mock(side_effect=AssertionError("SEC download")),
                get_filing=Mock(side_effect=AssertionError("edgartools fetch")),
                force=False,
            )

        self.assertEqual(result["attachment_count"], 2)
        self.assertEqual(db.merged_rows, [])
        self.assertEqual(result["network_fetches"], 0)

    def test_force_repair_emits_audit_record_with_prior_and_replacement_versions(self) -> None:
        """A force refetch that replaces an already-captured document must emit a
        repair audit entry: accession, prior object hash/version, replacement
        hash/version, operator context, and reason (07-06 Task 3)."""
        accession = "0000320193-26-000001"
        prior_raw_id = "raw-old-primary"
        attachments = [
            {
                "accession_number": accession,
                "document_name": "primary.xml",
                "document_type": "4",
                "document_url": "https://www.sec.gov/Archives/edgar/data/320193/primary.xml",
                "is_primary": True,
                "raw_object_id": prior_raw_id,
            }
        ]
        raw_objects = {
            prior_raw_id: {
                "raw_object_id": prior_raw_id,
                "accession_number": accession,
                "source_type": "filing_document",
                "source_url": attachments[0]["document_url"],
                "storage_path": "s3://bucket/primary-old.xml",
                "sha256": "old-sha256",
            }
        }
        new_payload = b"<ownershipDocument>replacement</ownershipDocument>"
        primary_attachment = _FakeAttachment(
            sequence_number="1",
            document="primary.xml",
            document_type="4",
            description="Primary document",
            url="https://www.sec.gov/Archives/edgar/data/320193/primary.xml",
            content=new_payload,
        )
        fake_filing = _FakeFiling(attachments=_FakeAttachments([primary_attachment]))
        get_filing = Mock(return_value=fake_filing)

        with tempfile.TemporaryDirectory() as tmp:
            db = _ArtifactDb(attachments=attachments, raw_objects=raw_objects)
            context = SimpleNamespace(bronze_root=StorageLocation(tmp), identity="tester@example.com")

            result = bronze_filing_artifacts.fetch_filing_artifacts(
                context=context,
                db=db,
                accession_number=accession,
                sync_run_id="run-1",
                download_bytes=Mock(side_effect=AssertionError("should use edgartools content")),
                get_filing=get_filing,
                force=True,
                operator="ops@example.com",
                reason="corrupted bronze object detected during audit",
            )

        get_filing.assert_called_once_with(accession)
        self.assertIn("repair_audit", result)
        self.assertEqual(len(result["repair_audit"]), 1)
        entry = result["repair_audit"][0]
        self.assertEqual(entry["accession_number"], accession)
        self.assertEqual(entry["document_name"], "primary.xml")
        self.assertEqual(entry["prior_object_hash"], "old-sha256")
        self.assertEqual(entry["prior_object_version"], "s3://bucket/primary-old.xml")
        self.assertEqual(entry["replacement_object_hash"], hashlib.sha256(new_payload).hexdigest())
        self.assertNotEqual(entry["replacement_object_hash"], entry["prior_object_hash"])
        self.assertEqual(entry["operator"], "ops@example.com")
        self.assertEqual(entry["reason"], "corrupted bronze object detected during audit")

    def test_force_without_prior_state_emits_no_repair_audit(self) -> None:
        """force=True against a genuinely first-time fetch (no prior raw object for
        this document) is not a repair -- no audit entry should be fabricated."""
        accession = "0000320193-26-000002"
        primary_attachment = _FakeAttachment(
            sequence_number="1",
            document="primary.xml",
            document_type="4",
            description="Primary document",
            url="https://www.sec.gov/Archives/edgar/data/320193/primary.xml",
            content="<ownershipDocument />",
        )
        fake_filing = _FakeFiling(attachments=_FakeAttachments([primary_attachment]))
        get_filing = Mock(return_value=fake_filing)

        with tempfile.TemporaryDirectory() as tmp:
            db = _ArtifactDb()
            context = SimpleNamespace(bronze_root=StorageLocation(tmp), identity="tester@example.com")

            result = bronze_filing_artifacts.fetch_filing_artifacts(
                context=context,
                db=db,
                accession_number=accession,
                sync_run_id="run-1",
                download_bytes=Mock(side_effect=AssertionError("should use edgartools content")),
                get_filing=get_filing,
                force=True,
            )

        self.assertNotIn("repair_audit", result)

    def test_force_repair_without_operator_or_reason_still_audits_but_leaves_them_blank(self) -> None:
        """Existing callers that don't yet pass operator/reason (07-06 Task 3
        threads them only as far as filing_artifact_service.py/
        bronze_filing_artifacts.py) still get a truthful audit record rather than
        a fabricated operator/reason."""
        accession = "0000320193-26-000003"
        prior_raw_id = "raw-old-primary-2"
        attachments = [
            {
                "accession_number": accession,
                "document_name": "primary.xml",
                "document_type": "4",
                "document_url": "https://www.sec.gov/Archives/edgar/data/320193/primary.xml",
                "is_primary": True,
                "raw_object_id": prior_raw_id,
            }
        ]
        raw_objects = {
            prior_raw_id: {
                "raw_object_id": prior_raw_id,
                "accession_number": accession,
                "source_type": "filing_document",
                "source_url": attachments[0]["document_url"],
                "storage_path": "s3://bucket/primary-old.xml",
                "sha256": "old-sha256",
            }
        }
        primary_attachment = _FakeAttachment(
            sequence_number="1",
            document="primary.xml",
            document_type="4",
            description="Primary document",
            url="https://www.sec.gov/Archives/edgar/data/320193/primary.xml",
            content=b"<ownershipDocument>x</ownershipDocument>",
        )
        fake_filing = _FakeFiling(attachments=_FakeAttachments([primary_attachment]))
        get_filing = Mock(return_value=fake_filing)

        with tempfile.TemporaryDirectory() as tmp:
            db = _ArtifactDb(attachments=attachments, raw_objects=raw_objects)
            context = SimpleNamespace(bronze_root=StorageLocation(tmp), identity="tester@example.com")

            result = bronze_filing_artifacts.fetch_filing_artifacts(
                context=context,
                db=db,
                accession_number=accession,
                sync_run_id="run-1",
                download_bytes=Mock(side_effect=AssertionError("should use edgartools content")),
                get_filing=get_filing,
                force=True,
            )

        self.assertIn("repair_audit", result)
        self.assertIsNone(result["repair_audit"][0]["operator"])
        self.assertIsNone(result["repair_audit"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
