from __future__ import annotations

from datetime import date

from sqlalchemy import event, func, select

from edgar_warehouse.mdm.database import (
    MdmAdviser,
    MdmChangeLog,
    MdmEntityAttributeStage,
    MdmFund,
)
from edgar_warehouse.mdm.pipeline import MDMPipeline


class _AdviserSilver:
    def __init__(self, row_count: int) -> None:
        self.rows = [
            {
                "accession_number": f"adv-{index:05d}",
                "cik": 1_000_000 + index,
                "form": "ADV",
                "adviser_name": f"Adviser {index}",
                "sec_file_number": f"801-{index}",
                "crd_number": str(50_000 + index),
                "effective_date": date(2026, 6, 30),
                "filing_status": "registered",
            }
            for index in range(row_count)
        ]

    def fetch(self, sql: str, params=None) -> list[dict]:
        if "FROM sec_adv_filing" in sql:
            return list(self.rows)
        if "FROM sec_adv_office" in sql:
            return []
        raise AssertionError(f"unexpected silver query: {sql}")


class _FundSilver:
    def __init__(self, row_count: int) -> None:
        self.rows = [
            {
                "accession_number": f"adv-{index:05d}",
                "fund_index": index,
                "private_fund_id": f"PF-{index:05d}",
                "adviser_crd_number": str(50_000 + index),
                "fund_name": f"Fund {index}",
                "fund_type": "hedge",
                "jurisdiction": "DE",
                "aum_amount": 1_000_000 + index,
                "effective_date": date(2026, 6, 30),
            }
            for index in range(row_count)
        ]

    def fetch(self, sql: str, params=None) -> list[dict]:
        if "FROM sec_adv_private_fund" in sql:
            return list(self.rows)
        raise AssertionError(f"unexpected silver query: {sql}")


def test_adviser_bulk_resolution_has_bounded_database_round_trips(db_session) -> None:
    """Production ADV loads must not issue resolver SQL once per source row.

    Snowflake Postgres adds network latency to every statement.  The original
    resolver needed hundreds of round trips for this 12-row fixture and did
    not reach its first 500-row production checkpoint after five minutes.
    """

    pipeline = MDMPipeline(session=db_session, silver=_AdviserSilver(12))
    pipeline.engine._source_priority[("adviser", "adv_filing")] = 30
    statement_count = 0
    stage_insert_count = 0

    def _count_statement(_conn, _cursor, statement, *_args, **_kwargs) -> None:
        nonlocal statement_count, stage_insert_count
        statement_count += 1
        if statement.startswith("INSERT INTO mdm_entity_attribute_stage"):
            stage_insert_count += 1

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", _count_statement)
    try:
        assert pipeline.run_advisers() == 12
    finally:
        event.remove(engine, "before_cursor_execute", _count_statement)

    assert statement_count <= 40, (
        "ADV adviser resolution exceeded the bulk round-trip budget: "
        f"{statement_count} SQL statements for 12 source rows"
    )
    assert stage_insert_count == 1, (
        "mixed NULL attribute rows must retain one executemany shape; "
        f"observed {stage_insert_count} stage INSERT statements"
    )


def test_adv_bulk_projection_is_latest_and_idempotent(db_session) -> None:
    silver = _AdviserSilver(1)
    old = dict(silver.rows[0])
    old["accession_number"] = "adv-old"
    old["adviser_name"] = "Old Adviser Name"
    old["effective_date"] = date(2025, 6, 30)
    silver.rows.insert(0, old)

    pipeline = MDMPipeline(session=db_session, silver=silver)
    pipeline.engine._source_priority[("adviser", "adv_filing")] = 30

    assert pipeline.run_advisers() == 1
    adviser = db_session.scalar(select(MdmAdviser))
    assert adviser is not None
    assert adviser.canonical_name == "Adviser 0"

    first_stages = db_session.scalar(
        select(func.count()).select_from(MdmEntityAttributeStage)
    )
    first_changes = db_session.scalar(select(func.count()).select_from(MdmChangeLog))
    assert pipeline.run_advisers() == 1
    assert db_session.scalar(select(func.count()).select_from(MdmAdviser)) == 1
    assert (
        db_session.scalar(select(func.count()).select_from(MdmEntityAttributeStage))
        == first_stages
    )
    assert (
        db_session.scalar(select(func.count()).select_from(MdmChangeLog))
        == first_changes
    )


def test_fund_bulk_resolution_has_bounded_database_round_trips(db_session) -> None:
    adviser_pipeline = MDMPipeline(session=db_session, silver=_AdviserSilver(12))
    adviser_pipeline.engine._source_priority[("adviser", "adv_filing")] = 30
    adviser_pipeline.run_advisers()

    pipeline = MDMPipeline(session=db_session, silver=_FundSilver(12))
    pipeline.engine._source_priority[("fund", "adv_filing")] = 30
    statement_count = 0

    def _count_statement(*_args, **_kwargs) -> None:
        nonlocal statement_count
        statement_count += 1

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", _count_statement)
    try:
        assert pipeline.run_funds() == 12
    finally:
        event.remove(engine, "before_cursor_execute", _count_statement)

    assert db_session.scalar(select(func.count()).select_from(MdmFund)) == 12
    assert statement_count <= 40, (
        "ADV fund resolution exceeded the bulk round-trip budget: "
        f"{statement_count} SQL statements for 12 source rows"
    )
