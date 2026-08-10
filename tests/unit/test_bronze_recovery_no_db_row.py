"""Mirror of ticket 88's gap: a sec_raw_object DB row can be missing even
though its bronze S3 content is durably present -- confirmed live 2026-08-10
during task 42's full-universe backfill. A prior run can capture bronze
content for an accession and then crash (OOM) before its silver DB
bookkeeping merges back to canonical, leaving zero existing_rows on the next
retry despite the content already being captured. fetch_filing_artifacts
must recover such documents from bronze storage instead of re-fetching them
from SEC, per CLAUDE.md's "SEC data idempotency" policy.
"""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from types import SimpleNamespace

from edgar_warehouse.bronze_filing_artifacts import fetch_filing_artifacts
from edgar_warehouse.infrastructure.dataset_path_catalog import default_capture_spec_factory
from edgar_warehouse.infrastructure.object_storage import StorageLocation
from tests.unit.test_artifact_fetch_concurrency import (
    _ArtifactDb,
    _make_filing,
    _payload_downloader,
)


class BronzeRecoveryNoDbRowTests(unittest.TestCase):
    def test_bronze_present_with_no_db_row_skips_document_fetch(self) -> None:
        """The exact live scenario: bronze already has both documents, but
        the accession has zero existing_rows (fresh silver.duckdb, or a
        prior crashed run). No document-fetch call should reach SEC."""
        with tempfile.TemporaryDirectory() as tmp:
            context = SimpleNamespace(bronze_root=StorageLocation(tmp), identity="tester@example.com")
            db = _ArtifactDb()
            capture_specs = default_capture_spec_factory()
            filing_obj = _make_filing(2)
            payloads = {f"doc{i}.htm": f"content-{i}".encode() for i in range(2)}

            # Pre-populate bronze directly, bypassing the DB entirely --
            # simulates a prior run's durable S3 write that never got its
            # silver bookkeeping merged back to canonical.
            expected_paths = {}
            for i in range(2):
                spec = capture_specs.filing_document(
                    cik=320193,
                    accession_number="0000320193-24-000010",
                    document_name=f"doc{i}.htm",
                    is_primary=(i == 0),
                )
                destination = context.bronze_root.write_immutable_bytes(
                    spec.relative_path, payloads[f"doc{i}.htm"]
                )
                expected_paths[f"doc{i}.htm"] = destination

            def _must_not_fetch_documents(url: str, identity: str):
                raise AssertionError(f"bronze-recovered document must not be re-fetched: {url}")

            result = fetch_filing_artifacts(
                context=context,
                db=db,
                accession_number="0000320193-24-000010",
                sync_run_id="run-1",
                download_bytes=_must_not_fetch_documents,
                get_filing=lambda accession: filing_obj,
            )

            # Only the get_filing metadata call is a real SEC network fetch.
            self.assertEqual(result["network_fetches"], 1)
            self.assertEqual(result["bronze_recovered_count"], 2)
            self.assertEqual(result["attachment_count"], 2)

            # DB rows must now exist -- the whole point is fixing the retry,
            # not just avoiding the refetch once.
            for i in range(2):
                sha256 = hashlib.sha256(payloads[f"doc{i}.htm"]).hexdigest()
                raw_object = db.raw_objects.get(sha256)
                self.assertIsNotNone(raw_object, f"doc{i} must get a raw_object DB row")
                self.assertEqual(raw_object["storage_path"], expected_paths[f"doc{i}.htm"])
            self.assertEqual(len(db.merged_rows), 2)

    def test_bronze_recovery_disabled_under_force(self) -> None:
        """force=True is a repair intent -- it must not trust bronze content
        any more than it trusts a DB row; every document is genuinely
        re-fetched from SEC."""
        with tempfile.TemporaryDirectory() as tmp:
            context = SimpleNamespace(bronze_root=StorageLocation(tmp), identity="tester@example.com")
            db = _ArtifactDb()
            capture_specs = default_capture_spec_factory()
            filing_obj = _make_filing(1)
            payloads = {"doc0.htm": b"content-0"}

            spec = capture_specs.filing_document(
                cik=320193,
                accession_number="0000320193-24-000011",
                document_name="doc0.htm",
                is_primary=True,
            )
            context.bronze_root.write_immutable_bytes(spec.relative_path, payloads["doc0.htm"])

            result = fetch_filing_artifacts(
                context=context,
                db=db,
                accession_number="0000320193-24-000011",
                sync_run_id="run-1",
                download_bytes=_payload_downloader(payloads),
                get_filing=lambda accession: filing_obj,
                force=True,
            )
            self.assertEqual(result["network_fetches"], 2)  # get_filing + real document refetch
            self.assertEqual(result["bronze_recovered_count"], 0)

    def test_mixed_bronze_recovery_and_genuine_new_fetch(self) -> None:
        """One document already in bronze (no DB row), the other genuinely
        new -- only the new one should reach SEC."""
        with tempfile.TemporaryDirectory() as tmp:
            context = SimpleNamespace(bronze_root=StorageLocation(tmp), identity="tester@example.com")
            db = _ArtifactDb()
            capture_specs = default_capture_spec_factory()
            filing_obj = _make_filing(2)
            payloads = {f"doc{i}.htm": f"content-{i}".encode() for i in range(2)}

            # Only doc0 is pre-captured in bronze.
            spec0 = capture_specs.filing_document(
                cik=320193,
                accession_number="0000320193-24-000012",
                document_name="doc0.htm",
                is_primary=True,
            )
            context.bronze_root.write_immutable_bytes(spec0.relative_path, payloads["doc0.htm"])

            fetched_urls: list[str] = []

            def _download(url: str, identity: str) -> bytes:
                fetched_urls.append(url)
                name = url.rsplit("/", 1)[-1]
                return payloads[name]

            result = fetch_filing_artifacts(
                context=context,
                db=db,
                accession_number="0000320193-24-000012",
                sync_run_id="run-1",
                download_bytes=_download,
                get_filing=lambda accession: filing_obj,
            )

            self.assertEqual(result["bronze_recovered_count"], 1)
            self.assertEqual(result["network_fetches"], 2)  # get_filing + doc1's real fetch
            self.assertEqual(len(fetched_urls), 1)
            self.assertTrue(fetched_urls[0].endswith("doc1.htm"))
            self.assertEqual(result["attachment_count"], 2)


if __name__ == "__main__":
    unittest.main()
