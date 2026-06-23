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
                force=False,
            )

        self.assertEqual(result["attachment_count"], 1)
        self.assertEqual(result["raw_writes"][0]["cached"], True)
        self.assertEqual(db.merged_rows, [])

    def test_force_filing_artifact_downloads_index_and_document(self) -> None:
        accession = "0000320193-26-000001"
        index_html = b"""
        <html><body><table>
          <tr>
            <td>1</td><td>Primary document</td><td><a href="primary.xml">primary.xml</a></td><td>4</td>
          </tr>
        </table></body></html>
        """
        document = b"<ownershipDocument />"
        downloads = Mock(side_effect=[index_html, document])
        with tempfile.TemporaryDirectory() as tmp:
            db = _ArtifactDb()
            context = SimpleNamespace(bronze_root=StorageLocation(tmp), identity="tester@example.com")

            result = bronze_filing_artifacts.fetch_filing_artifacts(
                context=context,
                db=db,
                accession_number=accession,
                sync_run_id="run-1",
                download_bytes=downloads,
                force=True,
            )

        self.assertEqual(downloads.call_count, 2)
        self.assertEqual(result["attachment_count"], 1)
        self.assertEqual(len(result["raw_writes"]), 2)
        self.assertEqual(len(db.merged_rows), 1)


if __name__ == "__main__":
    unittest.main()
