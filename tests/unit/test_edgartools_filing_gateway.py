"""Ticket 06 — edgartools-only gateway for filing document capture (phase 1).

Seams under test (spec Capture / skip boundary):
- fetch_filing_artifacts network path uses edgartools get_filing only
- cache / silver skip still short-circuits before network
- strict_release evidence persist (bronze raw write) still works
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from edgar_warehouse import bronze_filing_artifacts
from edgar_warehouse.infrastructure.object_storage import StorageLocation


def _parse_debug_events(stderr_text: str) -> list[dict]:
    events = []
    for line in stderr_text.splitlines():
        line = line.strip()
        if not line:
            continue
        events.append(json.loads(line))
    return events


class _ArtifactDb:
    def __init__(self, *, filing=None, attachments=None, raw_objects=None) -> None:
        self.filing = filing or {
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
        return [
            row
            for row in self.raw_objects.values()
            if row.get("accession_number") == accession_number
            and (source_type is None or row.get("source_type") == source_type)
        ]

    def upsert_raw_object(self, row: dict) -> None:
        self.raw_objects[row["raw_object_id"]] = dict(row)

    def merge_filing_attachments(self, rows: list[dict], sync_run_id: str) -> int:
        self.merged_rows.extend(rows)
        self.attachments = list(rows)
        return len(rows)


class _FakeAttachment:
    def __init__(self, *, sequence_number, document, document_type, description, url, content):
        self.sequence_number = sequence_number
        self.document = document
        self.document_type = document_type
        self.description = description
        self.url = url
        self.content = content


class _FakeAttachments:
    def __init__(self, items, primary_documents=None):
        self._items = list(items)
        self.primary_documents = (
            list(primary_documents) if primary_documents is not None else list(items)
        )

    def __iter__(self):
        return iter(self._items)


class _FakeFiling:
    def __init__(self, attachments):
        self.attachments = attachments


class EdgartoolsFilingGatewayTests(unittest.TestCase):
    def test_known_primary_document_uses_edgartools_not_parallel_download(self) -> None:
        """Ticket 06: even when primary_document is known, cold fetch must not use
        the parallel sec_client download_bytes path — only edgartools get_filing."""
        accession = "0000320193-26-000010"
        payload = b"<ownershipDocument>gateway</ownershipDocument>"
        primary = _FakeAttachment(
            sequence_number="1",
            document="primary.xml",
            document_type="4",
            description="Primary document",
            url="https://www.sec.gov/Archives/edgar/data/320193/primary.xml",
            content=payload,
        )
        get_filing = Mock(return_value=_FakeFiling(_FakeAttachments([primary])))
        download_bytes = Mock(
            side_effect=AssertionError(
                "parallel non-edgartools download_bytes must not be used for filing documents"
            )
        )

        with tempfile.TemporaryDirectory() as tmp:
            db = _ArtifactDb(
                filing={
                    "cik": 320193,
                    "form": "4",
                    "primary_document": "xslF345X06/primary.xml",
                }
            )
            context = SimpleNamespace(
                bronze_root=StorageLocation(tmp), identity="tester@example.com"
            )
            result = bronze_filing_artifacts.fetch_filing_artifacts(
                context=context,
                db=db,
                accession_number=accession,
                sync_run_id="run-gateway",
                download_bytes=download_bytes,
                get_filing=get_filing,
                force=False,
            )

        get_filing.assert_called_once_with(accession)
        download_bytes.assert_not_called()
        self.assertEqual(result["network_fetches"], 1)
        self.assertEqual(result["attachment_count"], 1)
        self.assertEqual(len(db.merged_rows), 1)
        self.assertEqual(
            db.merged_rows[0]["raw_object_id"], hashlib.sha256(payload).hexdigest()
        )

    def test_cached_attachments_still_skip_network_entirely(self) -> None:
        accession = "0000320193-26-000011"
        raw_id = "raw-cached"
        attachments = [
            {
                "accession_number": accession,
                "document_name": "primary.xml",
                "document_type": "4",
                "document_url": "https://www.sec.gov/Archives/edgar/data/320193/primary.xml",
                "is_primary": True,
                "raw_object_id": raw_id,
            }
        ]
        raw_objects = {
            raw_id: {
                "raw_object_id": raw_id,
                "accession_number": accession,
                "source_type": "filing_document",
                "source_url": attachments[0]["document_url"],
                "storage_path": "s3://bucket/primary.xml",
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            db = _ArtifactDb(attachments=attachments, raw_objects=raw_objects)
            context = SimpleNamespace(
                bronze_root=StorageLocation(tmp), identity="tester@example.com"
            )
            result = bronze_filing_artifacts.fetch_filing_artifacts(
                context=context,
                db=db,
                accession_number=accession,
                sync_run_id="run-skip",
                download_bytes=Mock(side_effect=AssertionError("download")),
                get_filing=Mock(side_effect=AssertionError("edgartools")),
                force=False,
            )

        self.assertEqual(result["network_fetches"], 0)
        self.assertEqual(result["attachment_count"], 1)
        self.assertTrue(result["raw_writes"][0]["cached"])

    def test_strict_release_cold_fetch_still_persists_evidence_bytes(self) -> None:
        """Ticket 06 + 01: evidence persistence remains available (bronze raw write)."""
        accession = "0000320193-26-000012"
        payload = b"<ownershipDocument>evidence</ownershipDocument>"
        primary = _FakeAttachment(
            sequence_number="1",
            document="primary.xml",
            document_type="4",
            description="Primary",
            url="https://www.sec.gov/Archives/edgar/data/320193/primary.xml",
            content=payload,
        )
        get_filing = Mock(return_value=_FakeFiling(_FakeAttachments([primary])))

        with tempfile.TemporaryDirectory() as tmp:
            db = _ArtifactDb()
            context = SimpleNamespace(
                bronze_root=StorageLocation(tmp), identity="tester@example.com"
            )
            result = bronze_filing_artifacts.fetch_filing_artifacts(
                context=context,
                db=db,
                accession_number=accession,
                sync_run_id="run-strict",
                download_bytes=Mock(side_effect=AssertionError("no parallel download")),
                get_filing=get_filing,
                force=False,
            )
            raw_id = hashlib.sha256(payload).hexdigest()
            stored = db.get_raw_object(raw_id)

        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored["sha256"], raw_id)
        self.assertEqual(stored["byte_size"], len(payload))
        self.assertEqual(result["network_fetches"], 1)
        self.assertEqual(len(result["raw_writes"]), 1)
        self.assertNotIn("cached", result["raw_writes"][0])


class DebugEventLoggingTests(unittest.TestCase):
    """Regression: fetch_filing_artifacts previously only reported an
    aggregate network_fetches count, with no way to see which accession or
    document actually triggered a real SEC call vs. a cache hit. Each call
    now emits a structured debug event (matching sec_client.py's JSON-line
    shape) so real per-accession/per-document network activity is visible in
    logs, not just the pipeline-level totals."""

    def test_cold_fetch_emits_sec_call_and_artifact_call_events(self) -> None:
        accession = "0000320193-26-000020"
        payload = b"<ownershipDocument>debug</ownershipDocument>"
        primary = _FakeAttachment(
            sequence_number="1",
            document="primary.xml",
            document_type="4",
            description="Primary document",
            url="https://www.sec.gov/Archives/edgar/data/320193/primary.xml",
            content=payload,
        )
        get_filing = Mock(return_value=_FakeFiling(_FakeAttachments([primary])))

        with tempfile.TemporaryDirectory() as tmp:
            db = _ArtifactDb()
            context = SimpleNamespace(
                bronze_root=StorageLocation(tmp), identity="tester@example.com"
            )
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                bronze_filing_artifacts.fetch_filing_artifacts(
                    context=context,
                    db=db,
                    accession_number=accession,
                    sync_run_id="run-debug",
                    download_bytes=Mock(side_effect=AssertionError("no parallel download")),
                    get_filing=get_filing,
                    force=False,
                )

        events = _parse_debug_events(stderr.getvalue())
        event_names = [e["event"] for e in events]
        self.assertIn("sec_call_started", event_names)
        self.assertIn("sec_call_completed", event_names)
        self.assertIn("artifact_call_started", event_names)
        self.assertIn("artifact_call_completed", event_names)
        self.assertNotIn("accession_cache_hit", event_names)

        sec_completed = next(e for e in events if e["event"] == "sec_call_completed")
        self.assertEqual(sec_completed["accession_number"], accession)
        self.assertEqual(sec_completed["call"], "get_filing")

        artifact_completed = next(e for e in events if e["event"] == "artifact_call_completed")
        self.assertEqual(artifact_completed["accession_number"], accession)
        self.assertEqual(artifact_completed["document_name"], "primary.xml")
        self.assertEqual(artifact_completed["bytes"], len(payload))

    def test_cached_accession_emits_cache_hit_not_sec_call(self) -> None:
        accession = "0000320193-26-000021"
        raw_id = "raw-cached-debug"
        attachments = [
            {
                "accession_number": accession,
                "document_name": "primary.xml",
                "document_type": "4",
                "document_url": "https://www.sec.gov/Archives/edgar/data/320193/primary.xml",
                "is_primary": True,
                "raw_object_id": raw_id,
            }
        ]
        raw_objects = {
            raw_id: {
                "raw_object_id": raw_id,
                "accession_number": accession,
                "source_type": "filing_document",
                "source_url": attachments[0]["document_url"],
                "storage_path": "s3://bucket/primary.xml",
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            db = _ArtifactDb(attachments=attachments, raw_objects=raw_objects)
            context = SimpleNamespace(
                bronze_root=StorageLocation(tmp), identity="tester@example.com"
            )
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                bronze_filing_artifacts.fetch_filing_artifacts(
                    context=context,
                    db=db,
                    accession_number=accession,
                    sync_run_id="run-debug-skip",
                    download_bytes=Mock(side_effect=AssertionError("download")),
                    get_filing=Mock(side_effect=AssertionError("edgartools")),
                    force=False,
                )

        events = _parse_debug_events(stderr.getvalue())
        event_names = [e["event"] for e in events]
        self.assertEqual(event_names, ["accession_cache_hit"])
        self.assertEqual(events[0]["accession_number"], accession)
        self.assertEqual(events[0]["attachment_count"], 1)


if __name__ == "__main__":
    unittest.main()
