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


def test_fund_bulk_resolution_survives_adviser_resolving_after_the_fund(db_session) -> None:
    """A fund's adviser can become resolvable only after the fund itself was
    first inserted (its ADV filing simply arrives/resolves later). The next
    `mdm run` re-processes the exact same source row: the fund's own
    identity-derived entity_id is unchanged, but its dedup lookup key
    (adviser_entity_id, name) flips from (None, name) to (<real id>, name)
    now that the adviser resolves. Before the fix this re-attempted an
    INSERT under the same primary key and crashed with
    sqlalchemy.exc.IntegrityError (duplicate key on mdm_entity_pkey) --
    reproduced live in prod 2026-08-09 via `mdm run --entity-type all
    --limit 5`. The fund lookup must recognize its own entity_id first,
    regardless of what the adviser-dedup key currently resolves to.
    """
    fund_row = {
        "accession_number": "adv-fund-race",
        "fund_index": 0,
        "private_fund_id": None,
        "adviser_crd_number": "99999",
        "fund_name": "Race Condition Fund",
        "fund_type": "hedge",
        "jurisdiction": "DE",
        "aum_amount": 5_000_000,
        "effective_date": date(2026, 6, 30),
    }

    class _RaceFundSilver:
        def fetch(self, sql: str, params=None) -> list[dict]:
            if "FROM sec_adv_private_fund" in sql:
                return [dict(fund_row)]
            raise AssertionError(f"unexpected silver query: {sql}")

    class _NoAdviserSilver:
        def fetch(self, sql: str, params=None) -> list[dict]:
            if "FROM sec_adv_filing" in sql:
                return []
            if "FROM sec_adv_office" in sql:
                return []
            raise AssertionError(f"unexpected silver query: {sql}")

    fund_pipeline = MDMPipeline(session=db_session, silver=_RaceFundSilver())
    fund_pipeline.engine._source_priority[("fund", "adv_filing")] = 30

    # First run: the fund's adviser (crd 99999) is not resolvable yet, so
    # the fund is inserted with adviser_entity_id=None.
    assert fund_pipeline.run_funds() == 1
    fund = db_session.scalar(select(MdmFund))
    assert fund is not None
    assert fund.adviser_entity_id is None
    stored_entity_id = fund.entity_id

    # The adviser now resolves (e.g. its own ADV filing loaded on a later run).
    adviser_pipeline = MDMPipeline(session=db_session, silver=_AdviserSilver(0))
    adviser_pipeline.silver.rows = [{
        "accession_number": "adv-00099",
        "cik": 1_099_099,
        "form": "ADV",
        "adviser_name": "Adviser 99999",
        "sec_file_number": "801-99999",
        "crd_number": "99999",
        "effective_date": date(2026, 6, 30),
        "filing_status": "registered",
    }]
    adviser_pipeline.engine._source_priority[("adviser", "adv_filing")] = 30
    assert adviser_pipeline.run_advisers() == 1

    # Re-processing the exact same fund source row must not crash, and must
    # update the existing fund's adviser link rather than duplicate-inserting.
    assert fund_pipeline.run_funds() == 1
    assert db_session.scalar(select(func.count()).select_from(MdmFund)) == 1
    fund = db_session.scalar(select(MdmFund))
    assert fund.entity_id == stored_entity_id
    assert fund.adviser_entity_id is not None


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
