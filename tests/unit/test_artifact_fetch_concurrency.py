"""Ticket 77: ThreadPoolExecutor concurrency in fetch_filing_artifacts's
per-document loop (implements pipeline-throughput-architecture ticket 03's
decision, scoped to the artifact-fetch loop only).

Real-data-backed per this workstream's established discipline: no mocked
rate limiter -- test 2 exercises the actual pyrate_limiter Limiter class.
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pyrate_limiter import Duration, InMemoryBucket, Limiter, Rate

from edgar_warehouse import bronze_filing_artifacts
from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.application.warehouse_orchestrator import (
    _is_immutable_object_conflict,
    _is_transient_artifact_error,
)
from edgar_warehouse.infrastructure.dataset_path_catalog import default_capture_spec_factory
from edgar_warehouse.infrastructure.object_storage import StorageLocation


class _FakeAttachment:
    def __init__(self, *, sequence_number, document, document_type, description, url):
        self.sequence_number = sequence_number
        self.document = document
        self.document_type = document_type
        self.description = description
        self.url = url


class _FakeAttachments:
    def __init__(self, items, primary_documents=None):
        self._items = list(items)
        self.primary_documents = (
            list(primary_documents) if primary_documents is not None else list(items)
        )

    def __iter__(self):
        return iter(self._items)


class _FakeFiling:
    def __init__(self, *, attachments):
        self.attachments = attachments


class _ArtifactDb:
    """Fresh-accession double that also records the thread every db.* call
    ran on, for the DB-write-serialization test."""

    def __init__(self, *, cik: int = 320193, form: str = "10-K") -> None:
        self.filing = {"cik": cik, "form": form, "primary_document": "primary.htm"}
        self.attachments: list[dict] = []
        self.raw_objects: dict[str, dict] = {}
        self.merged_rows: list[dict] = []
        self.call_thread_ids: list[int] = []

    def _record(self) -> None:
        self.call_thread_ids.append(threading.get_ident())

    def get_filing(self, accession_number: str):
        self._record()
        return dict(self.filing, accession_number=accession_number)

    def get_filing_attachments(self, accession_number: str):
        self._record()
        return [row for row in self.attachments if row["accession_number"] == accession_number]

    def get_raw_object(self, raw_object_id: str):
        self._record()
        return self.raw_objects.get(raw_object_id)

    def upsert_raw_object(self, row: dict) -> None:
        self._record()
        self.raw_objects[row["raw_object_id"]] = dict(row)

    def merge_filing_attachments(self, rows: list[dict], sync_run_id: str) -> int:
        self._record()
        self.merged_rows.extend(rows)
        self.attachments = list(rows)
        return len(rows)


def _make_filing(n: int, *, host: str = "320193") -> _FakeFiling:
    attachments = [
        _FakeAttachment(
            sequence_number=str(i + 1),
            document=f"doc{i}.htm",
            document_type="10-K" if i == 0 else "EX-99",
            description=f"document {i}",
            url=f"https://www.sec.gov/Archives/edgar/data/{host}/doc{i}.htm",
        )
        for i in range(n)
    ]
    return _FakeFiling(attachments=_FakeAttachments(attachments, primary_documents=[attachments[0]]))


def _payload_downloader(payloads: dict[str, bytes], *, delay: float = 0.0):
    def _download(url: str, identity: str) -> bytes:
        if delay:
            time.sleep(delay)
        name = url.rsplit("/", 1)[-1]
        return payloads[name]

    return _download


class ArtifactFetchConcurrencyTests(unittest.TestCase):
    def test_correctness_equivalence_concurrent_matches_sequential(self) -> None:
        """Test 1: N fake documents through the concurrent path (pool=5) must
        produce identical final state -- same merge order, same raw_writes,
        same counts -- as the same run forced sequential (pool=1)."""
        accession = "0000320193-26-000001"
        n = 6
        payloads = {f"doc{i}.htm": f"content-{i}".encode() for i in range(n)}

        outcomes: dict[str, tuple[dict, _ArtifactDb]] = {}
        for concurrency in ("1", "5"):
            with tempfile.TemporaryDirectory() as tmp, patch.dict(
                os.environ, {"WAREHOUSE_ARTIFACT_FETCH_CONCURRENCY": concurrency}
            ):
                db = _ArtifactDb()
                context = SimpleNamespace(
                    bronze_root=StorageLocation(tmp), identity="tester@example.com"
                )
                result = bronze_filing_artifacts.fetch_filing_artifacts(
                    context=context,
                    db=db,
                    accession_number=accession,
                    sync_run_id="run-1",
                    download_bytes=_payload_downloader(payloads),
                    get_filing=lambda acc: _make_filing(n),
                    force=False,
                )
                outcomes[concurrency] = (result, db)

        sequential_result, sequential_db = outcomes["1"]
        concurrent_result, concurrent_db = outcomes["5"]

        self.assertEqual(sequential_result["attachment_count"], n)
        self.assertEqual(concurrent_result["attachment_count"], n)
        self.assertEqual(sequential_result["network_fetches"], concurrent_result["network_fetches"])
        self.assertEqual(
            [(row["document_name"], row["is_primary"]) for row in sequential_db.merged_rows],
            [(row["document_name"], row["is_primary"]) for row in concurrent_db.merged_rows],
        )
        self.assertEqual(
            [row["raw_object_id"] for row in sequential_result["raw_writes"]],
            [row["raw_object_id"] for row in concurrent_result["raw_writes"]],
        )
        self.assertEqual(
            {row["document_name"]: row["raw_object_id"] for row in sequential_db.merged_rows},
            {row["document_name"]: row["raw_object_id"] for row in concurrent_db.merged_rows},
        )

    def test_rate_limiter_compliance_throttles_regardless_of_pool_size(self) -> None:
        """Test 2: a real pyrate_limiter Limiter shared across worker threads
        must still throttle correctly -- confirms the internal RLock actually
        serializes acquisition instead of pool concurrency defeating it."""
        accession = "0000320193-26-000002"
        n = 6
        rate_per_sec = 3
        bucket = InMemoryBucket([Rate(rate_per_sec, Duration.SECOND)])
        try:
            limiter = Limiter(
                bucket, max_delay=Duration.SECOND * 10, raise_when_fail=False, retry_until_max_delay=True
            )
        except TypeError:
            limiter = Limiter(bucket)
        payloads = {f"doc{i}.htm": f"content-{i}".encode() for i in range(n)}

        def download(url: str, identity: str) -> bytes:
            limiter.try_acquire("artifact_fetch_concurrency_test")
            name = url.rsplit("/", 1)[-1]
            return payloads[name]

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"WAREHOUSE_ARTIFACT_FETCH_CONCURRENCY": "5"}
        ):
            db = _ArtifactDb()
            context = SimpleNamespace(
                bronze_root=StorageLocation(tmp), identity="tester@example.com"
            )
            started = time.monotonic()
            bronze_filing_artifacts.fetch_filing_artifacts(
                context=context,
                db=db,
                accession_number=accession,
                sync_run_id="run-1",
                download_bytes=download,
                get_filing=lambda acc: _make_filing(n),
                force=False,
            )
            elapsed = time.monotonic() - started

        # n requests against a rate_per_sec/sec bucket must take at least
        # roughly (n - rate_per_sec) / rate_per_sec seconds of throttling once
        # the bucket's initial capacity is spent -- true regardless of pool
        # size (5 workers here) only if the limiter is genuinely thread-safe.
        minimum_expected = (n - rate_per_sec) / rate_per_sec
        self.assertGreaterEqual(elapsed, minimum_expected * 0.8)

    def test_db_writes_stay_serialized_on_main_thread(self) -> None:
        """Test 3: every db.* call -- including the per-document
        upsert_raw_object calls driven by worker results -- must happen on
        the thread that called fetch_filing_artifacts, never a pool thread.
        A single SilverDatabase DuckDB connection is not safe for concurrent
        access (ticket 03's stated constraint)."""
        accession = "0000320193-26-000005"
        n = 5
        payloads = {f"doc{i}.htm": f"content-{i}".encode() for i in range(n)}
        main_thread_id = threading.get_ident()

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"WAREHOUSE_ARTIFACT_FETCH_CONCURRENCY": "5"}
        ):
            db = _ArtifactDb()
            context = SimpleNamespace(
                bronze_root=StorageLocation(tmp), identity="tester@example.com"
            )
            bronze_filing_artifacts.fetch_filing_artifacts(
                context=context,
                db=db,
                accession_number=accession,
                sync_run_id="run-1",
                # Small delay forces genuine worker overlap instead of one
                # thread finishing before the next is even scheduled.
                download_bytes=_payload_downloader(payloads, delay=0.03),
                get_filing=lambda acc: _make_filing(n),
                force=False,
            )

        self.assertTrue(db.call_thread_ids, "expected db.* calls to have been recorded")
        self.assertTrue(
            all(thread_id == main_thread_id for thread_id in db.call_thread_ids),
            f"db.* calls occurred off the main thread: {db.call_thread_ids}",
        )

    def test_partial_failure_immutable_conflict_no_partial_merge(self) -> None:
        """Test 4: one document among several concurrent fetches hits a real
        immutable-content conflict (ticket 74's exact failure mode: a stale
        object already exists at the same key with different bytes). The
        resulting exception must classify identically to today's sequential
        behavior, and sec_filing_attachment must never see a partial merge.

        force=True (an operator repair run): the bronze-recovery path
        (fetch_filing_artifacts's no-DB-row fast path added for the
        crash-retry case) is deliberately gated on `not force`, so this run
        goes through the real fetch+write path for every document, exactly
        as it always has -- forcing the genuine write_immutable_bytes
        conflict this test exists to exercise, not a mocked stand-in.
        """
        accession = "0000320193-26-000006"
        n = 5
        cik = 320193
        failing_document = "doc2.htm"
        payloads = {f"doc{i}.htm": f"content-{i}".encode() for i in range(n)}

        with tempfile.TemporaryDirectory() as tmp:
            storage = StorageLocation(tmp)
            specs = default_capture_spec_factory()
            conflicting_spec = specs.filing_document(
                cik=cik,
                accession_number=accession,
                document_name=failing_document,
                is_primary=False,
            )
            # Pre-seed a conflicting object at the exact immutable key this
            # fetch would write to, so write_immutable_bytes raises the real
            # production error instead of a mocked stand-in.
            storage.write_bytes(conflicting_spec.relative_path, b"stale pre-existing content")

            db = _ArtifactDb(cik=cik, form="10-K")
            context = SimpleNamespace(bronze_root=storage, identity="tester@example.com")

            with patch.dict(os.environ, {"WAREHOUSE_ARTIFACT_FETCH_CONCURRENCY": "5"}):
                with self.assertRaises(WarehouseRuntimeError) as ctx:
                    bronze_filing_artifacts.fetch_filing_artifacts(
                        context=context,
                        db=db,
                        accession_number=accession,
                        sync_run_id="run-1",
                        download_bytes=_payload_downloader(payloads),
                        get_filing=lambda acc: _make_filing(n),
                        force=True,
                    )

        self.assertIn("already exists with different content", str(ctx.exception))
        self.assertTrue(_is_immutable_object_conflict(ctx.exception))
        self.assertFalse(_is_transient_artifact_error(ctx.exception))
        # Fail-closed: no partial merge into sec_filing_attachment, matching
        # the sequential loop's invariant exactly.
        self.assertEqual(db.merged_rows, [])

    def test_stale_object_with_no_db_row_is_bronze_recovered_not_flagged(self) -> None:
        """Companion to the force=True test above: under the ordinary
        force=False path, content already sitting at a document's canonical
        bronze key with no DB row is now trusted and recovered rather than
        re-fetched -- a deliberate behavior change (bronze-recovery ticket,
        2026-08-10). In real production this is safe because
        write_immutable_bytes is the only writer to a canonical bronze key
        and enforces content-identity atomically at write time, so "content
        exists at this key" already implies "this is the one accepted
        payload for it" -- the only way this test's synthetic
        `storage.write_bytes` bypass could happen for real is out-of-band
        drift (ticket 87/93), which is already tolerated elsewhere in this
        pipeline (isolated per-document, not fatal). The tradeoff: this path
        no longer re-detects that drift itself -- it now surfaces via the
        `artifact_bronze_recovered` event instead of a raised conflict."""
        accession = "0000320193-26-000006"
        n = 5
        cik = 320193
        recovered_document = "doc2.htm"
        payloads = {f"doc{i}.htm": f"content-{i}".encode() for i in range(n)}

        with tempfile.TemporaryDirectory() as tmp:
            storage = StorageLocation(tmp)
            specs = default_capture_spec_factory()
            existing_spec = specs.filing_document(
                cik=cik, accession_number=accession, document_name=recovered_document, is_primary=False,
            )
            existing_bytes = b"already-captured-content"
            storage.write_bytes(existing_spec.relative_path, existing_bytes)

            db = _ArtifactDb(cik=cik, form="10-K")
            context = SimpleNamespace(bronze_root=storage, identity="tester@example.com")
            fetched_documents: list[str] = []

            def _download(url: str, identity: str) -> bytes:
                name = url.rsplit("/", 1)[-1]
                fetched_documents.append(name)
                return payloads[name]

            result = bronze_filing_artifacts.fetch_filing_artifacts(
                context=context,
                db=db,
                accession_number=accession,
                sync_run_id="run-1",
                download_bytes=_download,
                get_filing=lambda acc: _make_filing(n),
                force=False,
            )

        self.assertNotIn(recovered_document, fetched_documents)
        self.assertEqual(result["bronze_recovered_count"], 1)
        self.assertEqual(result["attachment_count"], n)
        self.assertEqual(len(db.merged_rows), n)

    def test_worker_pool_bounded_by_pending_document_count(self) -> None:
        """A single-document accession (the common case -- most ownership
        Form 4s) must not spin up an idle 5-worker pool; the pool size is
        min(pending, configured concurrency)."""
        accession = "0000320193-26-000007"
        payloads = {"doc0.htm": b"solo-content"}

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"WAREHOUSE_ARTIFACT_FETCH_CONCURRENCY": "5"}
        ):
            db = _ArtifactDb()
            context = SimpleNamespace(
                bronze_root=StorageLocation(tmp), identity="tester@example.com"
            )
            result = bronze_filing_artifacts.fetch_filing_artifacts(
                context=context,
                db=db,
                accession_number=accession,
                sync_run_id="run-1",
                download_bytes=_payload_downloader(payloads),
                get_filing=lambda acc: _make_filing(1),
                force=False,
            )

        self.assertEqual(result["attachment_count"], 1)
        self.assertEqual(len(db.merged_rows), 1)


if __name__ == "__main__":
    unittest.main()
