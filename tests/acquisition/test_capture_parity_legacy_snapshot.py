"""run_dual_path_filing_artifact_parity's legacy snapshot after Ticket 06d.

sec_raw_object is landing-only (silver-merge-engine-migration Ticket 06d), so
the legacy snapshot cannot `SELECT * FROM sec_raw_object` on a local store:
it reads the raw objects the legacy capture just recorded through the
run's own lookup (attachments, then raw object by id). The live SEC dual-path
test (tests/application/test_dual_path_capture_parity.py) is skipped in CI, so
this covers the snapshot without SEC or Postgres.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import patch

from sqlalchemy import create_engine

from edgar_warehouse.acquisition.capture_parity import (
    APPLE_CIK,
    CaptureArtifact,
    run_dual_path_filing_artifact_parity,
)
from edgar_warehouse.acquisition.models import AcquisitionBase
from edgar_warehouse.silver_landing_store import SilverLandingStore

ACCESSION = "0000320193-26-000001"


class _Bookkeeping:
    def get_daily_index_filings(self, business_date: str) -> list[dict]:
        return [
            {
                "accession_number": ACCESSION,
                "cik": APPLE_CIK,
                "form": "4",
                "filing_date": date(2026, 8, 24),
            }
        ]


def _legacy_fetch(*, db, accession_number, sync_run_id, **_kwargs):
    """Records what fetch_filing_artifacts records for one captured document."""
    db.upsert_raw_object(
        {
            "raw_object_id": "sha-legacy",
            "source_type": "filing_document",
            "cik": APPLE_CIK,
            "accession_number": accession_number,
            "form": "4",
            "source_url": f"https://www.sec.gov/Archives/{accession_number}.txt",
            "storage_path": f"s3://bronze/{accession_number}.txt",
            "sha256": "sha-legacy",
            "fetched_at": datetime(2026, 8, 24, tzinfo=UTC),
            "http_status": 200,
        }
    )
    db.merge_filing_attachments(
        [
            {
                "accession_number": accession_number,
                "document_name": "primary.xml",
                "document_type": "4",
                "document_url": f"https://www.sec.gov/Archives/{accession_number}/primary.xml",
                "is_primary": True,
                "raw_object_id": "sha-legacy",
            }
        ],
        sync_run_id,
    )
    return {"network_fetches": 1}


def test_legacy_snapshot_reads_raw_objects_this_run_recorded(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'mdm.db'}")
    AcquisitionBase.metadata.create_all(engine)
    db = SilverLandingStore()
    try:
        with (
            patch("edgar_warehouse.bronze_filing_artifacts.fetch_filing_artifacts", side_effect=_legacy_fetch),
            patch(
                "edgar_warehouse.application.workflows.drive_filing_discovery."
                "run_filing_artifact_gated_capture_for_business_date"
            ),
            patch("edgar_warehouse.acquisition.database.get_engine", return_value=engine),
        ):
            result = run_dual_path_filing_artifact_parity(
                context=object(),
                db=db,
                bookkeeping=_Bookkeeping(),
                business_date="2026-08-24",
                sync_run_id="parity-run",
                cik_list=(APPLE_CIK,),
            )
    finally:
        db.close()

    assert result.legacy.artifacts == (
        CaptureArtifact(
            cik=APPLE_CIK,
            logical_source_key=f"{APPLE_CIK}/{ACCESSION}/full-submission-text",
            verified_evidence_reference="sha-legacy",
            decision_id=None,
        ),
    )
