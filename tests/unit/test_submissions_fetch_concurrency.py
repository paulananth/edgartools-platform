"""Ticket 78: ThreadPoolExecutor concurrency in the shared submissions
bronze-capture batch (implements pipeline-throughput-architecture ticket 06's
decision -- the same treatment as ticket 77, applied to
`_capture_submission_bronze_snapshots`, the function behind all 5
SEC-fetching commands' submissions capture).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pyrate_limiter import Duration, InMemoryBucket, Limiter, Rate

from edgar_warehouse.application import warehouse_orchestrator
from edgar_warehouse.infrastructure.object_storage import StorageLocation


def _flatten_chunks(chunk_iterator) -> list[dict]:
    """bronze-capture-oom Ticket 01: _capture_submission_bronze_snapshots
    now yields bounded chunks instead of returning one flat list. Every
    CIK batch in this file is far smaller than the default chunk size, so
    flattening reproduces the exact same flat list these tests already
    assert against.
    """
    snapshots: list[dict] = []
    for chunk in chunk_iterator:
        snapshots.extend(chunk)
    return snapshots


class _SubmissionsBookkeeping:
    """Records the thread every db.get_source_checkpoint call ran on, for
    the DB-access-serialization test. Checkpoints are keyed exactly as
    _read_bronze_if_cached expects: (source_name, source_key)."""

    def __init__(self, *, checkpoints: dict | None = None) -> None:
        self.checkpoints = dict(checkpoints or {})
        self.call_thread_ids: list[int] = []

    def get_source_checkpoint(self, source_name: str, source_key: str):
        self.call_thread_ids.append(threading.get_ident())
        return self.checkpoints.get((source_name, source_key))


def _main_payload(cik: int, *, pagination_files: list[str] | None = None) -> bytes:
    document = {
        "cik": f"{cik:010d}",
        "filings": {
            "recent": {},
            "files": [{"name": name} for name in (pagination_files or [])],
        },
    }
    return json.dumps(document).encode("utf-8")


def _pagination_payload(file_name: str) -> bytes:
    return json.dumps({"filings": {"files": [], "source": file_name}}).encode("utf-8")


def _downloader(payload_by_url_suffix: dict[str, bytes], *, delay: float = 0.0):
    def _download(*, url: str, identity: str) -> bytes:
        if delay:
            time.sleep(delay)
        for suffix, payload in payload_by_url_suffix.items():
            if url.endswith(suffix):
                return payload
        raise AssertionError(f"unexpected URL requested: {url}")

    return _download


class SubmissionsFetchConcurrencyTests(unittest.TestCase):
    def test_correctness_equivalence_concurrent_matches_sequential(self) -> None:
        """Test 1: N CIKs (some with pagination files) through the concurrent
        path (pool=5) must produce identical final snapshots -- same order,
        same payloads, same write records -- as the same batch forced
        sequential (pool=1)."""
        ciks = [1001, 1002, 1003, 1004, 1005, 1006]
        pagination_files = {1004: ["CIK0000001004-submissions-001.json"]}
        payloads: dict[str, bytes] = {}
        for cik in ciks:
            payloads[f"CIK{cik:010d}.json"] = _main_payload(
                cik, pagination_files=pagination_files.get(cik)
            )
        for cik, files in pagination_files.items():
            for file_name in files:
                payloads[file_name] = _pagination_payload(file_name)

        outcomes: dict[str, list[dict]] = {}
        for concurrency in ("1", "5"):
            with tempfile.TemporaryDirectory() as tmp, patch.dict(
                os.environ, {"WAREHOUSE_SUBMISSIONS_FETCH_CONCURRENCY": concurrency}
            ), patch.object(
                warehouse_orchestrator, "_download_sec_bytes", side_effect=_downloader(payloads)
            ):
                bookkeeping = _SubmissionsBookkeeping()
                context = SimpleNamespace(
                    bronze_root=StorageLocation(tmp), identity="tester@example.com"
                )
                snapshots = _flatten_chunks(
                    warehouse_orchestrator._capture_submission_bronze_snapshots(
                        context=context,
                        bookkeeping=bookkeeping,
                        ciks=ciks,
                        include_pagination=True,
                        fetch_date=date(2026, 8, 3),
                        force=False,
                    )
                )
                outcomes[concurrency] = snapshots

        sequential = outcomes["1"]
        concurrent = outcomes["5"]
        self.assertEqual([s["cik"] for s in sequential], ciks)
        self.assertEqual([s["cik"] for s in concurrent], ciks)
        self.assertEqual(
            [s["main_write_record"]["sha256"] for s in sequential],
            [s["main_write_record"]["sha256"] for s in concurrent],
        )
        self.assertEqual(
            [s["manifest_file_names"] for s in sequential],
            [s["manifest_file_names"] for s in concurrent],
        )
        self.assertEqual(
            [[p["write_record"]["sha256"] for p in s["pagination_snapshots"]] for s in sequential],
            [[p["write_record"]["sha256"] for p in s["pagination_snapshots"]] for s in concurrent],
        )
        self.assertEqual(
            sum(len(s["raw_writes"]) for s in sequential),
            sum(len(s["raw_writes"]) for s in concurrent),
        )

    def test_rate_limiter_compliance_throttles_regardless_of_pool_size(self) -> None:
        """Test 2: a real pyrate_limiter Limiter shared across worker threads
        must still throttle correctly."""
        ciks = [2001, 2002, 2003, 2004, 2005, 2006]
        rate_per_sec = 3
        bucket = InMemoryBucket([Rate(rate_per_sec, Duration.SECOND)])
        try:
            limiter = Limiter(
                bucket, max_delay=Duration.SECOND * 10, raise_when_fail=False, retry_until_max_delay=True
            )
        except TypeError:
            limiter = Limiter(bucket)

        payloads = {f"CIK{cik:010d}.json": _main_payload(cik) for cik in ciks}

        def download(url: str, identity: str) -> bytes:
            limiter.try_acquire("submissions_fetch_concurrency_test")
            for suffix, payload in payloads.items():
                if url.endswith(suffix):
                    return payload
            raise AssertionError(f"unexpected URL requested: {url}")

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"WAREHOUSE_SUBMISSIONS_FETCH_CONCURRENCY": "5"}
        ), patch.object(warehouse_orchestrator, "_download_sec_bytes", side_effect=download):
            bookkeeping = _SubmissionsBookkeeping()
            context = SimpleNamespace(
                bronze_root=StorageLocation(tmp), identity="tester@example.com"
            )
            started = time.monotonic()
            _flatten_chunks(
                warehouse_orchestrator._capture_submission_bronze_snapshots(
                    context=context,
                    bookkeeping=bookkeeping,
                    ciks=ciks,
                    include_pagination=False,
                    fetch_date=date(2026, 8, 3),
                    force=False,
                )
            )
            elapsed = time.monotonic() - started

        minimum_expected = (len(ciks) - rate_per_sec) / rate_per_sec
        self.assertGreaterEqual(elapsed, minimum_expected * 0.8)

    def test_db_access_stays_on_main_thread(self) -> None:
        """Test 3: every db.get_source_checkpoint call -- across both the
        main-fetch wave and the pagination wave -- must happen on the thread
        that called _capture_submission_bronze_snapshots, never a pool
        thread. A single SilverDatabase DuckDB connection is not safe for
        concurrent access (ticket 03's stated constraint)."""
        ciks = [3001, 3002, 3003, 3004, 3005]
        pagination_files = {
            cik: [f"CIK{cik:010d}-submissions-001.json"] for cik in ciks[:2]
        }
        payloads: dict[str, bytes] = {}
        for cik in ciks:
            payloads[f"CIK{cik:010d}.json"] = _main_payload(
                cik, pagination_files=pagination_files.get(cik)
            )
        for files in pagination_files.values():
            for file_name in files:
                payloads[file_name] = _pagination_payload(file_name)

        main_thread_id = threading.get_ident()

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"WAREHOUSE_SUBMISSIONS_FETCH_CONCURRENCY": "5"}
        ), patch.object(
            warehouse_orchestrator, "_download_sec_bytes", side_effect=_downloader(payloads, delay=0.03)
        ):
            bookkeeping = _SubmissionsBookkeeping()
            context = SimpleNamespace(
                bronze_root=StorageLocation(tmp), identity="tester@example.com"
            )
            _flatten_chunks(
                warehouse_orchestrator._capture_submission_bronze_snapshots(
                    context=context,
                    bookkeeping=bookkeeping,
                    ciks=ciks,
                    include_pagination=True,
                    fetch_date=date(2026, 8, 3),
                    force=False,
                )
            )

        self.assertTrue(bookkeeping.call_thread_ids, "expected db.get_source_checkpoint calls to have been recorded")
        self.assertTrue(
            all(thread_id == main_thread_id for thread_id in bookkeeping.call_thread_ids),
            f"db.get_source_checkpoint calls occurred off the main thread: {bookkeeping.call_thread_ids}",
        )

    def test_partial_failure_no_snapshots_returned(self) -> None:
        """Test 4: one CIK among several concurrent main-fetches fails. The
        batch must fail closed -- raise the original exception, return
        nothing -- matching today's sequential behavior where a mid-loop
        failure propagates out of _run_submissions_bronze_then_silver before
        any bronze_snapshots are used downstream."""
        ciks = [4001, 4002, 4003, 4004, 4005]
        failing_cik = 4003
        payloads = {
            f"CIK{cik:010d}.json": _main_payload(cik) for cik in ciks if cik != failing_cik
        }

        def download(url: str, identity: str) -> bytes:
            if url.endswith(f"CIK{failing_cik:010d}.json"):
                raise ConnectionError("simulated transient SEC failure")
            for suffix, payload in payloads.items():
                if url.endswith(suffix):
                    return payload
            raise AssertionError(f"unexpected URL requested: {url}")

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"WAREHOUSE_SUBMISSIONS_FETCH_CONCURRENCY": "5"}
        ), patch.object(warehouse_orchestrator, "_download_sec_bytes", side_effect=download):
            bookkeeping = _SubmissionsBookkeeping()
            context = SimpleNamespace(
                bronze_root=StorageLocation(tmp), identity="tester@example.com"
            )
            with self.assertRaises(ConnectionError):
                _flatten_chunks(
                    warehouse_orchestrator._capture_submission_bronze_snapshots(
                        context=context,
                        bookkeeping=bookkeeping,
                        ciks=ciks,
                        include_pagination=False,
                        fetch_date=date(2026, 8, 3),
                        force=False,
                    )
                )

    def test_cache_hits_skip_network_and_progress_still_fires(self) -> None:
        """A CIK whose submissions_main is already cached must not trigger a
        real fetch, and on_progress must still see it counted."""
        cik = 5001
        payload = _main_payload(cik)
        sha256 = hashlib.sha256(payload).hexdigest()

        with tempfile.TemporaryDirectory() as tmp:
            bronze_path = Path(tmp) / "submissions" / f"CIK{cik:010d}.json"
            bronze_path.parent.mkdir(parents=True, exist_ok=True)
            bronze_path.write_bytes(payload)

            bookkeeping = _SubmissionsBookkeeping(
                checkpoints={
                    ("submissions_main", f"cik:{cik}"): {
                        "bronze_path": str(bronze_path),
                        "last_sha256": sha256,
                    }
                }
            )
            context = SimpleNamespace(
                bronze_root=StorageLocation(tmp), identity="tester@example.com"
            )
            progress_calls: list[int] = []

            with patch.object(
                warehouse_orchestrator,
                "_download_sec_bytes",
                side_effect=AssertionError("cached CIK must not hit the network"),
            ):
                snapshots = _flatten_chunks(
                    warehouse_orchestrator._capture_submission_bronze_snapshots(
                        context=context,
                        bookkeeping=bookkeeping,
                        ciks=[cik],
                        include_pagination=False,
                        fetch_date=date(2026, 8, 3),
                        force=False,
                        on_progress=progress_calls.append,
                    )
                )

        self.assertEqual(snapshots[0]["main_write_record"]["sha256"], sha256)
        self.assertEqual(progress_calls, [1])

    def test_cache_hit_reads_run_concurrently(self) -> None:
        """Ticket 11 follow-up (pipeline-throughput-architecture): when every
        CIK is a cache hit -- exactly bootstrap-batch's --artifact-policy skip
        scenario -- the file reads must run through the worker pool, not
        sequentially on the main thread. Only the db.get_source_checkpoint
        lookup (asserted on the main thread by test_db_access_stays_on_main_thread)
        needs to serialize; the S3 read itself has no such constraint."""
        ciks = [6001, 6002, 6003, 6004, 6005, 6006]
        payloads: dict[int, bytes] = {cik: _main_payload(cik) for cik in ciks}
        checkpoints: dict[tuple[str, str], dict] = {}

        with tempfile.TemporaryDirectory() as tmp:
            for cik in ciks:
                bronze_path = Path(tmp) / "submissions" / f"CIK{cik:010d}.json"
                bronze_path.parent.mkdir(parents=True, exist_ok=True)
                bronze_path.write_bytes(payloads[cik])
                checkpoints[("submissions_main", f"cik:{cik}")] = {
                    "bronze_path": str(bronze_path),
                    "last_sha256": hashlib.sha256(payloads[cik]).hexdigest(),
                }

            bookkeeping = _SubmissionsBookkeeping(checkpoints=checkpoints)
            context = SimpleNamespace(
                bronze_root=StorageLocation(tmp), identity="tester@example.com"
            )

            read_delay = 0.05
            real_read_bytes = warehouse_orchestrator.read_bytes

            def _delayed_read_bytes(path: str) -> bytes:
                time.sleep(read_delay)
                return real_read_bytes(path)

            with patch.dict(
                os.environ, {"WAREHOUSE_SUBMISSIONS_FETCH_CONCURRENCY": "5"}
            ), patch.object(
                warehouse_orchestrator,
                "_download_sec_bytes",
                side_effect=AssertionError("every CIK here is a cache hit; must not hit the network"),
            ), patch.object(
                warehouse_orchestrator, "read_bytes", side_effect=_delayed_read_bytes
            ):
                started = time.monotonic()
                snapshots = _flatten_chunks(
                    warehouse_orchestrator._capture_submission_bronze_snapshots(
                        context=context,
                        bookkeeping=bookkeeping,
                        ciks=ciks,
                        include_pagination=False,
                        fetch_date=date(2026, 8, 3),
                        force=False,
                    )
                )
                elapsed = time.monotonic() - started

        # Sequential would cost len(ciks) * read_delay = 0.30s; concurrent
        # (pool=5, 6 items) costs ceil(6/5) * read_delay = 2 * 0.05 = 0.10s.
        # Assert well under the sequential floor, generous for CI jitter.
        self.assertLess(elapsed, len(ciks) * read_delay * 0.7)
        self.assertEqual(len(snapshots), len(ciks))
        for snapshot in snapshots:
            self.assertTrue(snapshot["main_write_record"]["cached"])


    def test_chunks_are_yielded_lazily_not_materialized_upfront(self) -> None:
        """bronze-capture-oom Ticket 01: proves the generator doesn't fetch a
        later chunk until an earlier one has actually been consumed by the
        caller -- the real fix for the confirmed prod OOM this ticket
        documents (every CIK's payload held in memory at once), not just a
        return-shape change from list to generator.
        """
        ciks = [7001, 7002, 7003, 7004, 7005]
        payloads = {f"CIK{cik:010d}.json": _main_payload(cik) for cik in ciks}
        fetched_ciks: list[int] = []

        def download(url: str, identity: str) -> bytes:
            for suffix, payload in payloads.items():
                if url.endswith(suffix):
                    fetched_ciks.append(int(suffix[3:13]))
                    return payload
            raise AssertionError(f"unexpected URL requested: {url}")

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"WAREHOUSE_SUBMISSION_SNAPSHOT_CHUNK_SIZE": "2"}
        ), patch.object(warehouse_orchestrator, "_download_sec_bytes", side_effect=download):
            bookkeeping = _SubmissionsBookkeeping()
            context = SimpleNamespace(
                bronze_root=StorageLocation(tmp), identity="tester@example.com"
            )

            generator = warehouse_orchestrator._capture_submission_bronze_snapshots(
                context=context,
                bookkeeping=bookkeeping,
                ciks=ciks,
                include_pagination=False,
                fetch_date=date(2026, 8, 3),
                force=False,
            )

            first_chunk = next(generator)
            self.assertEqual(sorted(fetched_ciks), [7001, 7002])
            self.assertEqual([s["cik"] for s in first_chunk], [7001, 7002])

            second_chunk = next(generator)
            self.assertEqual(sorted(fetched_ciks), [7001, 7002, 7003, 7004])
            self.assertEqual([s["cik"] for s in second_chunk], [7003, 7004])

            third_chunk = next(generator)
            self.assertEqual(sorted(fetched_ciks), [7001, 7002, 7003, 7004, 7005])
            self.assertEqual([s["cik"] for s in third_chunk], [7005])

            with self.assertRaises(StopIteration):
                next(generator)


if __name__ == "__main__":
    unittest.main()
