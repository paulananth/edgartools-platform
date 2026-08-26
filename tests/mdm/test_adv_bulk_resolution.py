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


def test_fund_bulk_resolution_second_identical_run_does_not_duplicate_stage_or_change_rows(
    db_session,
) -> None:
    """Mirrors test_adv_bulk_projection_is_latest_and_idempotent for funds
    (change-propagation map, Ticket 37): resolve_funds_bulk's
    _existing_source_ids check is the fund entity type's skip-if-unchanged
    equivalent -- an accession already seen for a private_fund_id/accession
    identity must not re-append MdmEntityAttributeStage/MdmChangeLog rows on
    a restart, even though SEC accession content is immutable so there is no
    literal "changed field" to re-detect the way content-hash resolvers do.
    """
    silver = _FundSilver(3)
    pipeline = MDMPipeline(session=db_session, silver=silver)
    pipeline.engine._source_priority[("fund", "adv_filing")] = 30

    assert pipeline.run_funds() == 3
    first_funds = db_session.scalar(select(func.count()).select_from(MdmFund))
    first_stages = db_session.scalar(
        select(func.count()).select_from(MdmEntityAttributeStage)
    )
    first_changes = db_session.scalar(select(func.count()).select_from(MdmChangeLog))
    assert first_funds == 3
    assert first_stages > 0
    assert first_changes == 3

    assert pipeline.run_funds() == 3
    assert (
        db_session.scalar(select(func.count()).select_from(MdmFund)) == first_funds
    ), "second identical run must not create duplicate fund golden records"
    assert (
        db_session.scalar(select(func.count()).select_from(MdmEntityAttributeStage))
        == first_stages
    ), "second identical run over unchanged accessions must not re-stage attributes"
    assert (
        db_session.scalar(select(func.count()).select_from(MdmChangeLog))
        == first_changes
    ), "second identical run over unchanged accessions must not log new changes"


def test_adviser_bulk_resolution_a_new_accession_for_the_same_crd_still_resolves(
    db_session,
) -> None:
    """The other half of Ticket 37's requirement: an unchanged accession is
    skipped (test_adv_bulk_projection_is_latest_and_idempotent), but a
    genuinely new accession for an already-known CRD (e.g. a later ADV
    amendment) must still be staged and logged, not silently absorbed by the
    dedup check.
    """
    silver = _AdviserSilver(1)
    pipeline = MDMPipeline(session=db_session, silver=silver)
    pipeline.engine._source_priority[("adviser", "adv_filing")] = 30

    assert pipeline.run_advisers() == 1
    first_changes = db_session.scalar(select(func.count()).select_from(MdmChangeLog))
    assert first_changes == 1

    amended = dict(silver.rows[0])
    amended["accession_number"] = "adv-00000-amended"
    amended["adviser_name"] = "Adviser 0 Renamed"
    amended["effective_date"] = date(2026, 9, 30)
    silver.rows = [amended]

    assert pipeline.run_advisers() == 1
    assert (
        db_session.scalar(select(func.count()).select_from(MdmAdviser)) == 1
    ), "the amendment must update the existing adviser, not create a second one"
    assert (
        db_session.scalar(select(func.count()).select_from(MdmChangeLog))
        == first_changes + 1
    ), "a new accession must still produce a new MdmChangeLog row, not be skipped"
    adviser = db_session.scalar(select(MdmAdviser))
    assert adviser.canonical_name == "Adviser 0 Renamed"


def test_fund_bulk_resolution_dedups_by_private_fund_id_not_accession(
    db_session,
) -> None:
    """Characterizes a real, deliberately-not-fixed-here gap (change-propagation
    map, Ticket 37's Answer): unlike adviser (dedup key = accession_number,
    always), resolve_funds_bulk's _existing_source_ids check keys on
    private_fund_id when present. A later accession amending an
    already-known pfid IS recognized by the pfid-based existing_sources
    check, so it produces no new MdmSourceRef/stage/MdmChangeLog row -- even
    though the golden MdmFund record itself still refreshes (the
    unconditional setattr loop runs regardless of the dedup check).

    This silently starves MDMExporter.export_pending (keyed on
    MdmChangeLog.exported_at IS NULL) of any signal that this fund needs
    re-export after its first-ever accession -- a real freshness bug, not
    just an audit-trail gap. Deliberately not fixed in this ticket: fixing
    it means re-keying dedup to accession_number like adviser, which would
    re-stage every already-seen pfid-keyed fund once on the next run at
    production scale (fund_index has been observed past 22,000 for a single
    adviser -- see CLAUDE.md's schema-conventions note) -- an unsized
    one-time backlog cost, not a line change. See the filed follow-up ticket
    for the real fix.
    """
    silver = _FundSilver(1)
    pipeline = MDMPipeline(session=db_session, silver=silver)
    pipeline.engine._source_priority[("fund", "adv_filing")] = 30

    assert pipeline.run_funds() == 1
    first_changes = db_session.scalar(select(func.count()).select_from(MdmChangeLog))
    assert first_changes == 1

    amended = dict(silver.rows[0])
    amended["accession_number"] = "adv-00000-amended"
    amended["fund_name"] = "Fund 0 Renamed"
    amended["effective_date"] = date(2026, 9, 30)
    silver.rows = [amended]

    assert pipeline.run_funds() == 1
    assert (
        db_session.scalar(select(func.count()).select_from(MdmFund)) == 1
    ), "the amendment must update the existing fund, not create a second one"
    fund = db_session.scalar(select(MdmFund))
    assert fund.canonical_name == "Fund 0 Renamed", (
        "the golden record does refresh even though no change is logged for it"
    )
    assert (
        db_session.scalar(select(func.count()).select_from(MdmChangeLog))
        == first_changes
    ), (
        "current behavior: a new accession under an already-known pfid is "
        "NOT logged -- MDMExporter never learns this fund needs re-export"
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
