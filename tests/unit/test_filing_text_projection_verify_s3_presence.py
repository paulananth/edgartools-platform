"""Ticket 88: extract_text_for_accession must not trust a raw_object DB row
whose S3 object is absent -- it should self-heal by re-fetching (reusing
fetch_filing_artifacts's own now-S3-verified logic) rather than crash with
an opaque s3fs/fsspec error, which is what happened live in prod.
"""

from __future__ import annotations

import tempfile
import unittest
from types import SimpleNamespace

from edgar_warehouse.filing_text_projection import extract_text_for_accession
from edgar_warehouse.infrastructure.object_storage import StorageLocation
from tests.unit.test_artifact_fetch_concurrency import (
    _ArtifactDb,
    _make_filing,
    _payload_downloader,
)


class _TextDb(_ArtifactDb):
    def __init__(self, *, cik: int = 320193) -> None:
        super().__init__(cik=cik)
        self.text_rows: list[dict] = []

    def upsert_filing_text(self, row: dict) -> None:
        self._record()
        self.text_rows.append(row)


class ExtractTextS3PresenceTests(unittest.TestCase):
    def test_missing_primary_object_self_heals_via_refetch(self) -> None:
        with tempfile.TemporaryDirectory() as bronze_tmp, tempfile.TemporaryDirectory() as storage_tmp:
            context = SimpleNamespace(
                bronze_root=StorageLocation(bronze_tmp),
                storage_root=StorageLocation(storage_tmp),
                identity="tester@example.com",
            )
            db = _TextDb()
            filing_obj = _make_filing(1)
            payloads = {"doc0.htm": b"<html><body>Real filing content</body></html>"}

            # Patch the module-level import target used by extract_text_for_accession's
            # deferred import for refresh_filing_artifacts's get_filing/download_bytes.
            import edgar_warehouse.infrastructure.filing_artifact_service as fas

            def fake_refresh(*, context, db, accession_number, sync_run_id, force):
                from edgar_warehouse.bronze_filing_artifacts import fetch_filing_artifacts

                return fetch_filing_artifacts(
                    context=context,
                    db=db,
                    accession_number=accession_number,
                    sync_run_id=sync_run_id,
                    download_bytes=_payload_downloader(payloads),
                    get_filing=lambda accession: filing_obj,
                    force=force,
                )

            original = fas.refresh_filing_artifacts
            fas.refresh_filing_artifacts = fake_refresh
            try:
                # No prior attachment/raw_object rows at all (db.attachments empty) --
                # simulates a dangling/never-hydrated reference case as well as the
                # genuinely-missing-row case.
                row = extract_text_for_accession(
                    context=context,
                    db=db,
                    accession_number="0000320193-24-000004",
                    sync_run_id="run-1",
                )
            finally:
                fas.refresh_filing_artifacts = original

            self.assertIn("Real filing content", open(row["text_storage_path"]).read())
            self.assertEqual(len(db.text_rows), 1)

    def test_dangling_reference_self_heals_not_crashes(self) -> None:
        """The exact live scenario: a raw_object row exists, but its S3 key
        was removed out-of-band. Must self-heal, not raise/crash."""
        with tempfile.TemporaryDirectory() as bronze_tmp, tempfile.TemporaryDirectory() as storage_tmp:
            context = SimpleNamespace(
                bronze_root=StorageLocation(bronze_tmp),
                storage_root=StorageLocation(storage_tmp),
                identity="tester@example.com",
            )
            db = _TextDb()
            filing_obj = _make_filing(1)
            payloads = {"doc0.htm": b"<html><body>Fresh content after repair</body></html>"}

            from edgar_warehouse.bronze_filing_artifacts import fetch_filing_artifacts

            fetch_filing_artifacts(
                context=context,
                db=db,
                accession_number="0000320193-24-000005",
                sync_run_id="run-0",
                download_bytes=_payload_downloader(payloads),
                get_filing=lambda accession: filing_obj,
            )

            import glob
            import os

            for path in glob.glob(os.path.join(bronze_tmp, "**", "*.htm"), recursive=True):
                os.remove(path)

            import edgar_warehouse.infrastructure.filing_artifact_service as fas

            def fake_refresh(*, context, db, accession_number, sync_run_id, force):
                return fetch_filing_artifacts(
                    context=context,
                    db=db,
                    accession_number=accession_number,
                    sync_run_id=sync_run_id,
                    download_bytes=_payload_downloader(payloads),
                    get_filing=lambda accession: filing_obj,
                    force=force,
                )

            original = fas.refresh_filing_artifacts
            fas.refresh_filing_artifacts = fake_refresh
            try:
                row = extract_text_for_accession(
                    context=context,
                    db=db,
                    accession_number="0000320193-24-000005",
                    sync_run_id="run-1",
                )
            finally:
                fas.refresh_filing_artifacts = original

            self.assertIn("Fresh content after repair", open(row["text_storage_path"]).read())


if __name__ == "__main__":
    unittest.main()
