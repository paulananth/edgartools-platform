from __future__ import annotations

import io
import zipfile

import pytest

from edgar_warehouse.application.adv_firm_roster_ingest import (
    AdvFirmRosterParseResult,
    ingest_firm_roster_archive,
    parse_firm_roster_archive,
)
from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.silver_store import SilverDatabase

_HEADER = (
    '"Organization CRD#","7B","Count of Private Funds - 7B(1)",'
    '"Any Hedge Funds","Total number of Hedge funds",'
    '"Any PE Funds","Total number of PE funds",'
    '"Total Gross Assets of Private Funds","Count of Private Funds - 7B(2)"\n'
)


def _archive(files: dict[str, str]) -> bytes:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as bundle:
        for name, content in files.items():
            bundle.writestr(name, content)
    return payload.getvalue()


def _roster_row(
    crd: str = "1588",
    seven_b: str = "Y",
    count_7b1: str = "                   3",
    any_hedge: str = "Y",
    hedge_count: str = "3",
    any_pe: str = "N",
    pe_count: str = "",
    gross_assets: str = "           709,905,606.00",
    count_7b2: str = "                   0",
) -> str:
    return (
        f'{crd},"{seven_b}","{count_7b1}","{any_hedge}","{hedge_count}",'
        f'"{any_pe}","{pe_count}","{gross_assets}","{count_7b2}"\n'
    )


def test_firm_roster_archive_parses_real_column_names_and_strips_padding() -> None:
    archive = _archive({
        "IA_SEC_-_FIRM_ROSTER_FOIA_DOWNLOAD_-_34622660.CSV": _HEADER + _roster_row(),
    })

    parsed = parse_firm_roster_archive(
        archive, dataset_period="2026-07", source_sha256="abc123"
    )

    assert isinstance(parsed, AdvFirmRosterParseResult)
    row = parsed.rows[0]
    assert row.adviser_crd_number == "1588"
    assert row.private_funds_reported is True
    assert row.private_fund_count_7b1 == 3
    assert row.any_hedge_funds is True
    assert row.hedge_fund_count == 3
    assert row.any_pe_funds is False
    assert row.pe_fund_count is None
    assert row.total_gross_assets_private_funds == 709905606
    assert row.private_fund_count_7b2 == 0
    assert row.dataset_period == "2026-07"
    assert row.source_sha256 == "abc123"


def test_firm_roster_archive_reads_by_name_regardless_of_column_count_or_position() -> None:
    """The real exempt-advisers CSV (171 columns) and registered-advisers CSV
    (448 columns) share identical target column names but at different total
    counts/positions (confirmed live: 'Organization CRD#' is column 1 in both,
    but '7B' is column 336 registered vs. column 96 exempt). DictReader reads
    by name, so this must parse correctly with extra, differently-positioned
    columns surrounding the target ones -- not just a different filename.
    """
    header = (
        '"SEC Region","Organization CRD#","Firm Type","Share Location",'
        '"7B","Count of Private Funds - 7B(1)",'
        '"Any Hedge Funds","Total number of Hedge funds",'
        '"Any PE Funds","Total number of PE funds",'
        '"Total Gross Assets of Private Funds","Count of Private Funds - 7B(2)",'
        '"Some Other Exempt-Only Column"\n'
    )
    row = (
        'NE,2288,"ERA","Y",'
        '"Y","                   2","N","","Y","1",'
        '"           50,000,000.00","0","filler"\n'
    )
    archive = _archive({
        "IA_SEC_-_FIRM_ROSTER_FOIA_DOWNLOAD_-_34622659.CSV": header + row,
    })

    parsed = parse_firm_roster_archive(
        archive, dataset_period="2026-07", source_sha256="abc123"
    )

    assert len(parsed.rows) == 1
    result_row = parsed.rows[0]
    assert result_row.adviser_crd_number == "2288"
    assert result_row.private_fund_count_7b1 == 2
    assert result_row.pe_fund_count == 1


def test_firm_roster_archive_with_no_private_funds_reports_zero_counts() -> None:
    archive = _archive({
        "IA_SEC_-_FIRM_ROSTER_FOIA_DOWNLOAD_-_34622660.CSV": _HEADER + _roster_row(
            crd="9999", seven_b="N", count_7b1="0", any_hedge="N", hedge_count="",
            any_pe="N", pe_count="", gross_assets="", count_7b2="0",
        ),
    })

    parsed = parse_firm_roster_archive(
        archive, dataset_period="2026-07", source_sha256="abc123"
    )

    row = parsed.rows[0]
    assert row.private_funds_reported is False
    assert row.private_fund_count_7b1 == 0
    assert row.hedge_fund_count is None
    assert row.total_gross_assets_private_funds is None


def test_firm_roster_rows_sorted_by_crd_ascending() -> None:
    archive = _archive({
        "IA_SEC_-_FIRM_ROSTER_FOIA_DOWNLOAD_-_34622660.CSV": (
            _HEADER + _roster_row(crd="9999") + _roster_row(crd="100")
        ),
    })

    parsed = parse_firm_roster_archive(
        archive, dataset_period="2026-07", source_sha256="abc123"
    )

    assert [row.adviser_crd_number for row in parsed.rows] == ["100", "9999"]


def test_firm_roster_row_missing_crd_raises() -> None:
    archive = _archive({
        "IA_SEC_-_FIRM_ROSTER_FOIA_DOWNLOAD_-_34622660.CSV": _HEADER + _roster_row(crd=""),
    })

    with pytest.raises(WarehouseRuntimeError, match="Organization CRD#"):
        parse_firm_roster_archive(archive, dataset_period="2026-07", source_sha256="abc123")


def test_firm_roster_blank_required_count_raises() -> None:
    """Count of Private Funds - 7B(1)/7B(2) are documented as always
    populated, including an explicit "0" -- confirmed live. A blank value is
    a genuine anomaly and must fail closed, not silently collapse to 0 and
    risk a false negative in the downstream count-mismatch reconciliation
    this table exists to feed.
    """
    archive = _archive({
        "IA_SEC_-_FIRM_ROSTER_FOIA_DOWNLOAD_-_34622660.CSV": _HEADER + _roster_row(count_7b1=""),
    })

    with pytest.raises(WarehouseRuntimeError, match="Count of Private Funds - 7B\\(1\\)"):
        parse_firm_roster_archive(archive, dataset_period="2026-07", source_sha256="abc123")


def test_firm_roster_conflicting_duplicate_crd_raises() -> None:
    archive = _archive({
        "IA_SEC_-_FIRM_ROSTER_FOIA_DOWNLOAD_-_34622660.CSV": (
            _HEADER + _roster_row(crd="1588", count_7b1="3") + _roster_row(crd="1588", count_7b1="4")
        ),
    })

    with pytest.raises(WarehouseRuntimeError, match="conflicting duplicate Firm Roster CRD"):
        parse_firm_roster_archive(archive, dataset_period="2026-07", source_sha256="abc123")


def test_firm_roster_archive_missing_roster_rows_raises() -> None:
    archive = _archive({"unrelated_file.csv": "a,b\n1,2\n"})

    with pytest.raises(WarehouseRuntimeError, match="missing roster rows"):
        parse_firm_roster_archive(archive, dataset_period="2026-07", source_sha256="abc123")


def test_firm_roster_bad_zip_raises() -> None:
    with pytest.raises(WarehouseRuntimeError, match="invalid Firm Roster ZIP archive"):
        parse_firm_roster_archive(b"not a zip", dataset_period="2026-07", source_sha256="abc123")


def test_firm_roster_requires_dataset_period_and_sha256() -> None:
    archive = _archive({
        "IA_SEC_-_FIRM_ROSTER_FOIA_DOWNLOAD_-_34622660.CSV": _HEADER + _roster_row(),
    })

    with pytest.raises(WarehouseRuntimeError, match="lineage"):
        parse_firm_roster_archive(archive, dataset_period="", source_sha256="abc123")
    with pytest.raises(WarehouseRuntimeError, match="lineage"):
        parse_firm_roster_archive(archive, dataset_period="2026-07", source_sha256="")


def test_firm_roster_amount_strips_commas_and_whitespace() -> None:
    archive = _archive({
        "IA_SEC_-_FIRM_ROSTER_FOIA_DOWNLOAD_-_34622660.CSV": _HEADER + _roster_row(
            gross_assets="  1,234,567.89  "
        ),
    })

    parsed = parse_firm_roster_archive(
        archive, dataset_period="2026-07", source_sha256="abc123"
    )

    from decimal import Decimal

    assert parsed.rows[0].total_gross_assets_private_funds == Decimal("1234567.89")


def test_ingest_firm_roster_archive_writes_real_silver_rows(tmp_path) -> None:
    archive = _archive({
        "IA_SEC_-_FIRM_ROSTER_FOIA_DOWNLOAD_-_34622660.CSV": (
            _HEADER + _roster_row(crd="1588") + _roster_row(crd="2288", seven_b="N",
                count_7b1="0", any_hedge="N", hedge_count="", any_pe="N", pe_count="",
                gross_assets="", count_7b2="0")
        ),
    })

    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        result = ingest_firm_roster_archive(
            db, archive, dataset_period="2026-07", source_sha256="abc123", sync_run_id="run-1"
        )
        assert result == {"firm_roster": 2}

        stored = db.fetch(
            "SELECT adviser_crd_number, dataset_period, private_funds_reported, "
            "private_fund_count_7b1, hedge_fund_count, total_gross_assets_private_funds "
            "FROM sec_adv_firm_roster ORDER BY adviser_crd_number"
        )
        assert [row["adviser_crd_number"] for row in stored] == ["1588", "2288"]
        first = stored[0]
        assert first["dataset_period"] == "2026-07"
        assert first["private_funds_reported"] is True
        assert first["private_fund_count_7b1"] == 3
        assert first["hedge_fund_count"] == 3
        assert first["total_gross_assets_private_funds"] == 709905606
    finally:
        db.close()


def test_ingest_firm_roster_archive_reingest_is_idempotent(tmp_path) -> None:
    archive = _archive({
        "IA_SEC_-_FIRM_ROSTER_FOIA_DOWNLOAD_-_34622660.CSV": _HEADER + _roster_row(crd="1588"),
    })

    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        first = ingest_firm_roster_archive(
            db, archive, dataset_period="2026-07", source_sha256="abc123", sync_run_id="run-1"
        )
        second = ingest_firm_roster_archive(
            db, archive, dataset_period="2026-07", source_sha256="abc123", sync_run_id="run-2"
        )
        assert first == second == {"firm_roster": 1}

        stored = db.fetch(
            "SELECT adviser_crd_number, dataset_period FROM sec_adv_firm_roster"
        )
        assert len(stored) == 1
    finally:
        db.close()


def test_ingest_firm_roster_archive_different_period_is_a_new_row(tmp_path) -> None:
    archive = _archive({
        "IA_SEC_-_FIRM_ROSTER_FOIA_DOWNLOAD_-_34622660.CSV": _HEADER + _roster_row(crd="1588"),
    })

    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        ingest_firm_roster_archive(
            db, archive, dataset_period="2026-06", source_sha256="abc123", sync_run_id="run-1"
        )
        ingest_firm_roster_archive(
            db, archive, dataset_period="2026-07", source_sha256="abc123", sync_run_id="run-2"
        )

        stored = db.fetch(
            "SELECT dataset_period FROM sec_adv_firm_roster ORDER BY dataset_period"
        )
        assert [row["dataset_period"] for row in stored] == ["2026-06", "2026-07"]
    finally:
        db.close()
