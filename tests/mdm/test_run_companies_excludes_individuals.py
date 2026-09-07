"""mdm-company-person-contamination ticket 01: run_companies() must not
resolve an individual Form 3/4/5/144 reporting owner as an mdm_company
entity. Live evidence (2026-09-07): sec_company -- the table run_companies()
reads unfiltered -- contains every CIK the pipeline has ever discovered,
including individual reporting owners (SEC assigns them their own CIK the
same way it does a real registrant), because Form 4s list both the
issuer's and the individual's own CIK. A CIK whose entire
sec_company_filing history is confined to beneficial-ownership/insider
forms (3/4/5/144, SC 13D/13G + amendments, DFAN14A) never files as a real
operating registrant -- validated live against known real examples this
session (companies always have a non-ownership form; confirmed
individuals never do).

Uses a real SilverDatabase-backed DuckDB file (not the substring-matched
StubSilver used elsewhere in this test package) deliberately: StubSilver's
fetch() ignores the SQL string's WHERE clause entirely, so it cannot
distinguish a filtered query from an unfiltered one -- a StubSilver-based
test would pass whether or not this fix existed.
"""
from __future__ import annotations

import os
import tempfile

from sqlalchemy import select

from edgar_warehouse.mdm.database import MdmCompany
from edgar_warehouse.mdm.pipeline import MDMPipeline
from edgar_warehouse.silver_store import SilverDatabase

from tests.mdm.test_run_companies_concurrency import _seeded_sqlite_session, _StubBookkeeping


def _silver_with_company_and_individual(tmp_path) -> SilverDatabase:
    """One real company (has a 10-K) and one individual reporting owner
    (only ever filed Form 4), both present in sec_company the same way
    live discovery would put them there."""
    silver_path = os.path.join(tmp_path, "silver.duckdb")
    db = SilverDatabase(silver_path)
    db._conn.execute(
        "INSERT INTO sec_company (cik, entity_name) VALUES (?, ?), (?, ?)",
        [910001, "Issuer Corp", 910101, "Doe Jane"],
    )
    # DuckDB's sec_company_filing has accession_number as its sole PK (never
    # widened to (accession_number, cik) the way Snowflake's post-Ticket-16
    # table is) -- each row here needs its own distinct accession_number.
    db._conn.execute(
        "INSERT INTO sec_company_filing (accession_number, cik, form, filing_date, report_date) "
        "VALUES (?, ?, ?, ?, ?), (?, ?, ?, ?, ?), (?, ?, ?, ?, ?)",
        [
            "0001234567-24-000001", 910001, "4", "2024-01-15", "2024-01-14",
            "0001234567-24-000002", 910001, "10-K", "2024-03-01", "2023-12-31",
            "0001234567-24-000003", 910101, "4", "2024-01-16", "2024-01-14",
        ],
    )
    db.close()
    return SilverDatabase(silver_path)


class TestRunCompaniesExcludesIndividualReportingOwners:
    def test_unbounded_full_universe_call_excludes_the_individual(self, tmp_path) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        silver = _silver_with_company_and_individual(str(tmp_path))
        pipeline = MDMPipeline(session=session, silver=silver)

        processed = pipeline.run_companies(bookkeeping=_StubBookkeeping())

        assert processed == 1
        resolved_ciks = {
            row.cik for row in session.execute(select(MdmCompany)).scalars().all()
        }
        assert resolved_ciks == {910001}

    def test_bounded_limit_call_excludes_the_individual(self, tmp_path) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        silver = _silver_with_company_and_individual(str(tmp_path))
        pipeline = MDMPipeline(session=session, silver=silver)

        processed = pipeline.run_companies(limit=10, bookkeeping=_StubBookkeeping())

        assert processed == 1
        resolved_ciks = {
            row.cik for row in session.execute(select(MdmCompany)).scalars().all()
        }
        assert resolved_ciks == {910001}

    def test_cik_scoped_call_excludes_the_individual_even_if_explicitly_requested(
        self, tmp_path
    ) -> None:
        """A caller passing an individual's CIK by mistake (issuer_ciks is
        meant to carry real issuer CIKs, e.g. Ticket 21's missing-issuer-
        shell path) must not get a bogus company entity for it."""
        session = _seeded_sqlite_session(static_pool=True)
        silver = _silver_with_company_and_individual(str(tmp_path))
        pipeline = MDMPipeline(session=session, silver=silver)

        processed = pipeline.run_companies(
            issuer_ciks=[910001, 910101], bookkeeping=_StubBookkeeping()
        )

        assert processed == 1
        resolved_ciks = {
            row.cik for row in session.execute(select(MdmCompany)).scalars().all()
        }
        assert resolved_ciks == {910001}

    def test_resumable_full_universe_call_excludes_the_individual(
        self, tmp_path, monkeypatch
    ) -> None:
        """The resume path's own frozen-snapshot query is a separate SQL
        construction site from the plain unbounded query above -- must
        exclude the individual too, not just on a first pass but from the
        snapshot itself (mirrors /gof-refactor-reviewer's finding: this
        method has 5 separate sec_company reads, and the resume path is
        the one this test package's existing coverage didn't reach)."""
        monkeypatch.setenv("WAREHOUSE_BRONZE_ROOT", str(tmp_path / "bronze"))
        session = _seeded_sqlite_session(static_pool=True)
        silver = _silver_with_company_and_individual(str(tmp_path))
        pipeline = MDMPipeline(session=session, silver=silver)

        processed = pipeline.run_companies(run_id="resume-test-run", bookkeeping=_StubBookkeeping())

        assert processed == 1
        resolved_ciks = {
            row.cik for row in session.execute(select(MdmCompany)).scalars().all()
        }
        assert resolved_ciks == {910001}

    def test_cik_with_no_filing_history_is_not_excluded(self, tmp_path) -> None:
        """Absence of sec_company_filing rows isn't evidence of being an
        individual -- a CIK never seen in that table (e.g. a company whose
        artifact fetch hasn't run yet) must still resolve normally."""
        silver_path = os.path.join(str(tmp_path), "silver.duckdb")
        db = SilverDatabase(silver_path)
        db._conn.execute(
            "INSERT INTO sec_company (cik, entity_name) VALUES (?, ?)",
            [920001, "No Filing History Yet Inc"],
        )
        db.close()
        session = _seeded_sqlite_session(static_pool=True)
        pipeline = MDMPipeline(session=session, silver=SilverDatabase(silver_path))

        processed = pipeline.run_companies(bookkeeping=_StubBookkeeping())

        assert processed == 1
        resolved_ciks = {
            row.cik for row in session.execute(select(MdmCompany)).scalars().all()
        }
        assert resolved_ciks == {920001}
