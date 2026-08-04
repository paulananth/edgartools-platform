"""Ticket 88: a sec_raw_object DB row is not proof the S3 object it points
at still exists (confirmed live in prod: 494 of Apple's 1,044 rows pointed
at objects that were never durably present). fetch_filing_artifacts must
verify S3 presence before trusting a cache hit, on both the fast
accession-level short-circuit and the per-document loop, and self-heal by
re-fetching rather than crashing or silently returning a dangling reference.
"""

from __future__ import annotations

import tempfile
import unittest
from types import SimpleNamespace

from edgar_warehouse.bronze_filing_artifacts import fetch_filing_artifacts
from edgar_warehouse.infrastructure.object_storage import StorageLocation
from tests.unit.test_artifact_fetch_concurrency import (
    _ArtifactDb,
    _make_filing,
    _payload_downloader,
)


class VerifyS3PresenceTests(unittest.TestCase):
    def test_fast_path_cache_hit_with_object_present_still_works(self) -> None:
        """Baseline: unmodified behavior when the S3 object genuinely exists."""
        with tempfile.TemporaryDirectory() as tmp:
            context = SimpleNamespace(bronze_root=StorageLocation(tmp), identity="tester@example.com")
            db = _ArtifactDb()
            filing_obj = _make_filing(2)
            payloads = {f"doc{i}.htm": f"content-{i}".encode() for i in range(2)}

            first = fetch_filing_artifacts(
                context=context,
                db=db,
                accession_number="0000320193-24-000001",
                sync_run_id="run-1",
                download_bytes=_payload_downloader(payloads),
                get_filing=lambda accession: filing_obj,
            )
            self.assertEqual(first["network_fetches"], 3)  # get_filing + 2 documents

            second = fetch_filing_artifacts(
                context=context,
                db=db,
                accession_number="0000320193-24-000001",
                sync_run_id="run-2",
                download_bytes=_payload_downloader(payloads),
                get_filing=lambda accession: filing_obj,
            )
            self.assertEqual(second["network_fetches"], 0)
            self.assertEqual(second["attachment_count"], 2)

    def test_fast_path_dangling_reference_triggers_real_refetch(self) -> None:
        """DB rows exist but the underlying S3 object was removed out-of-band
        (ticket 88's exact live scenario) -- must not be reported as a cache
        hit, must re-fetch for real, and must land a fresh, present object."""
        with tempfile.TemporaryDirectory() as tmp:
            context = SimpleNamespace(bronze_root=StorageLocation(tmp), identity="tester@example.com")
            db = _ArtifactDb()
            filing_obj = _make_filing(2)
            payloads = {f"doc{i}.htm": f"content-{i}".encode() for i in range(2)}

            fetch_filing_artifacts(
                context=context,
                db=db,
                accession_number="0000320193-24-000002",
                sync_run_id="run-1",
                download_bytes=_payload_downloader(payloads),
                get_filing=lambda accession: filing_obj,
            )

            # Simulate the live-observed gap: DB rows survive, S3 objects don't.
            import glob
            import os

            for path in glob.glob(os.path.join(tmp, "**", "*.htm"), recursive=True):
                os.remove(path)

            second = fetch_filing_artifacts(
                context=context,
                db=db,
                accession_number="0000320193-24-000002",
                sync_run_id="run-2",
                download_bytes=_payload_downloader(payloads),
                get_filing=lambda accession: filing_obj,
            )
            self.assertEqual(
                second["network_fetches"],
                3,  # get_filing + both dangling documents re-fetched
                "dangling reference must trigger a real re-fetch, not a phantom cache hit",
            )
            self.assertEqual(second["attachment_count"], 2)
            for record in second["raw_writes"]:
                self.assertTrue(os.path.exists(record["path"]), f"{record['path']} should exist after self-heal")

    def test_per_document_loop_dangling_reference_refetches_only_that_document(self) -> None:
        """When some but not all documents are cached (missing_rows nonempty,
        so the fast path is skipped), a per-document dangling reference must
        still fall through to a real fetch for that one document."""
        with tempfile.TemporaryDirectory() as tmp:
            context = SimpleNamespace(bronze_root=StorageLocation(tmp), identity="tester@example.com")
            db = _ArtifactDb()
            filing_obj = _make_filing(3)
            payloads = {f"doc{i}.htm": f"content-{i}".encode() for i in range(3)}

            fetch_filing_artifacts(
                context=context,
                db=db,
                accession_number="0000320193-24-000003",
                sync_run_id="run-1",
                download_bytes=_payload_downloader(payloads),
                get_filing=lambda accession: filing_obj,
            )

            import glob
            import os

            # Remove only one document's object; force a re-discovery by
            # dropping its DB row's raw_object_id resolution isn't needed --
            # instead force the fast path off by adding a genuinely-new,
            # never-fetched attachment via a fresh filing_obj.
            removed = sorted(glob.glob(os.path.join(tmp, "**", "doc1.htm"), recursive=True))
            self.assertEqual(len(removed), 1)
            os.remove(removed[0])

            filing_obj_4 = _make_filing(4)
            payloads[f"doc3.htm"] = b"content-3"

            second = fetch_filing_artifacts(
                context=context,
                db=db,
                accession_number="0000320193-24-000003",
                sync_run_id="run-2",
                download_bytes=_payload_downloader(payloads),
                get_filing=lambda accession: filing_obj_4,
            )
            # doc1 (dangling) + doc3 (newly discovered) both require real fetches.
            self.assertEqual(second["network_fetches"], 1 + 2)  # get_filing + 2 document fetches
            for record in second["raw_writes"]:
                self.assertTrue(os.path.exists(record["path"]))


if __name__ == "__main__":
    unittest.main()
