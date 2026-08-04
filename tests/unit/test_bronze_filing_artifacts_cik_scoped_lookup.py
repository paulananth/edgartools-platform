"""Ticket 96: edgar.get_by_accession_number's whole-market quarterly-index
scan inherits httpx's bare 5s default timeout (edgartools' shared HTTP_MGR
client sets no timeout of its own), compounded by two nested 5x retry
decorators inside edgartools -- producing ~83s-per-call failures under
degraded SEC connectivity (confirmed live during ticket 42's third
artifact-fetch retry). Fix: fetch_filing_artifacts's get_filing default
switches to a CIK-scoped lookup (edgar.Company(cik).get_filings(
accession_number=...)) using the cik already resolved at the call site, no
fallback to the whole-market path on a miss, plus a 60s configure_http
floor as an independent defensive measure. See
.scratch/release-readiness/issues/96-edgartools-quarter-scan-timeout-artifact-fetch.md
"""

from __future__ import annotations

import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import edgar
import httpx

from edgar_warehouse.bronze_filing_artifacts import (
    fetch_filing_artifacts,
    get_filing_by_cik_and_accession,
)
from edgar_warehouse.infrastructure.object_storage import StorageLocation
from tests.unit.test_artifact_fetch_concurrency import (
    _ArtifactDb,
    _make_filing,
    _payload_downloader,
)


class _FakeEntityFilings:
    """Mirrors the two members get_filing_by_cik_and_accession relies on:
    edgar.entity.filings.EntityFilings.empty and .get(accession_number)."""

    def __init__(self, filing=None):
        self._filing = filing
        self.empty = filing is None

    def get(self, accession_number: str):
        return self._filing


class GetFilingByCikAndAccessionTests(unittest.TestCase):
    """Adapter correctness, in isolation from the rest of fetch_filing_artifacts."""

    def test_returns_filing_when_company_lookup_finds_it(self) -> None:
        filing_obj = _make_filing(1)
        fake_company = Mock()
        fake_company.get_filings.return_value = _FakeEntityFilings(filing_obj)

        with patch.object(edgar, "Company", return_value=fake_company) as company_ctor:
            result = get_filing_by_cik_and_accession(320193, "0000320193-24-000001")

        self.assertIs(result, filing_obj)
        company_ctor.assert_called_once_with(320193)
        fake_company.get_filings.assert_called_once_with(
            accession_number="0000320193-24-000001"
        )

    def test_returns_none_when_company_lookup_misses_no_fallback(self) -> None:
        """No fallback to the whole-market path on a miss (release-readiness
        ticket 96 decision) -- a CIK/accession mismatch is a real
        data-quality signal, not something to paper over."""
        fake_company = Mock()
        fake_company.get_filings.return_value = _FakeEntityFilings(None)

        with patch.object(edgar, "Company", return_value=fake_company):
            with patch.object(edgar, "get_by_accession_number") as whole_market:
                result = get_filing_by_cik_and_accession(320193, "0000320193-24-999999")

        self.assertIsNone(result)
        whole_market.assert_not_called()

    def test_returns_none_when_filings_result_is_none(self) -> None:
        """EntityData.get_filings can itself return None (e.g. invalid
        filing_date filter) -- must not raise on that shape."""
        fake_company = Mock()
        fake_company.get_filings.return_value = None

        with patch.object(edgar, "Company", return_value=fake_company):
            result = get_filing_by_cik_and_accession(320193, "0000320193-24-000002")

        self.assertIsNone(result)


class FetchFilingArtifactsDefaultLookupTests(unittest.TestCase):
    """fetch_filing_artifacts wiring: default behavior and the DI override contract."""

    def test_default_get_filing_uses_cik_scoped_lookup_not_whole_market(self) -> None:
        """No get_filing override -> resolves via the new CIK-scoped default
        and never touches edgar.get_by_accession_number (the whole-market
        quarterly-index scan this ticket eliminates from the default path)."""
        filing_obj = _make_filing(2)
        payloads = {f"doc{i}.htm": f"content-{i}".encode() for i in range(2)}
        fake_company = Mock()
        fake_company.get_filings.return_value = _FakeEntityFilings(filing_obj)

        with tempfile.TemporaryDirectory() as tmp:
            context = SimpleNamespace(
                bronze_root=StorageLocation(tmp), identity="tester@example.com"
            )
            db = _ArtifactDb(cik=320193)
            with patch.object(edgar, "Company", return_value=fake_company) as company_ctor:
                with patch.object(edgar, "get_by_accession_number") as whole_market:
                    result = fetch_filing_artifacts(
                        context=context,
                        db=db,
                        accession_number="0000320193-24-000003",
                        sync_run_id="run-1",
                        download_bytes=_payload_downloader(payloads),
                    )

        self.assertEqual(result["attachment_count"], 2)
        company_ctor.assert_called_once_with(320193)
        whole_market.assert_not_called()

    def test_not_found_raises_valueerror_no_fallback(self) -> None:
        fake_company = Mock()
        fake_company.get_filings.return_value = _FakeEntityFilings(None)

        with tempfile.TemporaryDirectory() as tmp:
            context = SimpleNamespace(
                bronze_root=StorageLocation(tmp), identity="tester@example.com"
            )
            db = _ArtifactDb(cik=320193)
            with patch.object(edgar, "Company", return_value=fake_company):
                with patch.object(edgar, "get_by_accession_number") as whole_market:
                    with self.assertRaises(ValueError):
                        fetch_filing_artifacts(
                            context=context,
                            db=db,
                            accession_number="0000320193-24-000004",
                            sync_run_id="run-1",
                            download_bytes=_payload_downloader({}),
                        )

        whole_market.assert_not_called()

    def test_explicit_get_filing_override_bypasses_cik_scoped_default(self) -> None:
        """Existing DI contract (used across ~30 call sites in this test
        suite) keeps working unchanged: an explicit override is used as-is
        and the new default machinery (edgar.Company) is never constructed."""
        filing_obj = _make_filing(1)
        payloads = {"doc0.htm": b"content-0"}

        with tempfile.TemporaryDirectory() as tmp:
            context = SimpleNamespace(
                bronze_root=StorageLocation(tmp), identity="tester@example.com"
            )
            db = _ArtifactDb(cik=320193)
            with patch.object(edgar, "Company") as company_ctor:
                result = fetch_filing_artifacts(
                    context=context,
                    db=db,
                    accession_number="0000320193-24-000005",
                    sync_run_id="run-1",
                    download_bytes=_payload_downloader(payloads),
                    get_filing=lambda accession: filing_obj,
                )

        self.assertEqual(result["attachment_count"], 1)
        company_ctor.assert_not_called()


class ConfigureHttpTimeoutFloorTests(unittest.TestCase):
    """bronze_filing_artifacts's module-level edgar.configure_http(timeout=60.0)
    call already executed for real when this test module was imported (it
    imports fetch_filing_artifacts above) -- assert its live, real effect on
    edgartools' shared HTTP_MGR rather than mocking the call, since the
    point of this fix is the actual timeout edgartools' HTTP client uses."""

    def test_60s_timeout_floor_is_live_on_shared_http_client(self) -> None:
        from edgar.httpclient import HTTP_MGR

        self.assertEqual(
            HTTP_MGR.httpx_params.get("timeout"),
            httpx.Timeout(60.0, connect=10.0),
        )


if __name__ == "__main__":
    unittest.main()
