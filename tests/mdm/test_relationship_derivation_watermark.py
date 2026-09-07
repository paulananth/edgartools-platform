"""Tests for the mdm-relationship-incremental-filters Ticket 04 watermark
mechanism: MDMPipeline.derive_relationships()'s per-type checkpoint that
scopes each ``_derive_*`` method's source read to rows new since its last
successful derivation.

Uses a real DuckDB-backed SilverDatabase (not a hand-rolled stub) for the
same reason test_pipeline_relationships.py's own
test_thirteenf_manager_resolves_name_against_real_silver_schema does: a
stub that encodes the expected SQL shape can silently drift from the real
schema/semantics in lockstep with a bug in the code under test. That risk
is especially real here since the watermark clauses compare against a real
column type (accession_number TEXT vs. ingested_at TIMESTAMPTZ) a
substring-matching stub has no way to model.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from edgar_warehouse.mdm.database import (
    Base,
    MdmAdviser,
    MdmCompany,
    MdmEntity,
    MdmFund,
    MdmPerson,
    MdmRelationshipDerivationCheckpoint,
    MdmSecurity,
)
from edgar_warehouse.mdm.pipeline import MDMPipeline
from edgar_warehouse.silver_store import SilverDatabase

from tests.mdm.test_pipeline_relationships import _add_entity, _seed_registry


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sess = Session(engine)
    _seed_registry(sess)
    yield sess
    sess.close()


def _checkpoint(session: Session, key: str) -> MdmRelationshipDerivationCheckpoint | None:
    # Not session.get(): its identity-map shortcut would return a
    # previously-loaded (and, across this file's multi-call tests, now
    # stale) object without re-querying. A plain select always re-reads.
    session.expire_all()
    return session.execute(
        select(MdmRelationshipDerivationCheckpoint).where(
            MdmRelationshipDerivationCheckpoint.checkpoint_key == key
        )
    ).scalar_one_or_none()


def _seed_thirteenf_holding(
    db: SilverDatabase,
    *,
    cik: int,
    accession_number: str,
    cusip: str,
    ingested_at: datetime,
    period_of_report: str = "2024-03-31",
) -> None:
    db._conn.execute(
        "INSERT OR REPLACE INTO sec_company (cik, entity_name) VALUES (?, ?)",
        [cik, f"Manager {cik}"],
    )
    db._conn.execute(
        """
        INSERT INTO sec_thirteenf_filing
            (accession_number, cik, period_of_report, filing_date, form,
             amendment_type, confidential_omission, parser_version)
        VALUES (?, ?, ?, ?, '13F-HR', NULL, FALSE, '1')
        """,
        [accession_number, cik, period_of_report, period_of_report],
    )
    db._conn.execute(
        """
        INSERT INTO sec_thirteenf_holding
            (cik, accession_number, holding_index, period_of_report, cusip,
             issuer_name, security_title, shares_held, market_value,
             security_class, put_call, discretion_type, parser_version,
             ingested_at)
        VALUES (?, ?, 1, ?, ?, 'Apple Inc', 'Common Stock', 1, 100,
                'equity', NULL, 'SOLE', '1', ?)
        """,
        [cik, accession_number, period_of_report, cusip, ingested_at],
    )


class TestInstitutionalHoldsWatermark:
    """INSTITUTIONAL_HOLDS: real ingested_at TIMESTAMPTZ watermark."""

    def test_no_checkpoint_scans_everything_and_sets_one(self, session, tmp_path):
        """Advisor's item 1: a never-checkpointed type must scan everything,
        not nothing -- and a successful run must leave a real checkpoint
        behind for the next call."""
        silver_path = tmp_path / "silver.duckdb"
        db = SilverDatabase(str(silver_path))
        t1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2024, 6, 1, tzinfo=timezone.utc)
        _seed_thirteenf_holding(db, cik=1001, accession_number="a1", cusip="037833100", ingested_at=t1)
        _seed_thirteenf_holding(db, cik=1002, accession_number="a2", cusip="594918104", ingested_at=t2)
        db.close()

        assert _checkpoint(session, "INSTITUTIONAL_HOLDS") is None

        pipeline = MDMPipeline(session=session, silver=SilverDatabase(str(silver_path)))
        summary = pipeline.derive_relationships(relationship_types=["INSTITUTIONAL_HOLDS"])
        assert summary["INSTITUTIONAL_HOLDS"]["inserted"] == 2

        checkpoint = _checkpoint(session, "INSTITUTIONAL_HOLDS")
        assert checkpoint is not None
        assert checkpoint.watermark_column == "ingested_at"
        assert datetime.fromisoformat(checkpoint.watermark_value) == t2

    def test_checkpoint_filters_out_already_seen_rows(self, session, tmp_path):
        """A second run, with a checkpoint already past the first row's
        ingested_at, must only pick up the newer row."""
        silver_path = tmp_path / "silver.duckdb"
        db = SilverDatabase(str(silver_path))
        t1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2024, 6, 1, tzinfo=timezone.utc)
        _seed_thirteenf_holding(db, cik=1001, accession_number="a1", cusip="037833100", ingested_at=t1)
        db.close()

        pipeline = MDMPipeline(session=session, silver=SilverDatabase(str(silver_path)))
        first = pipeline.derive_relationships(relationship_types=["INSTITUTIONAL_HOLDS"])
        assert first["INSTITUTIONAL_HOLDS"]["inserted"] == 1

        # A second, genuinely new holding lands after the first run's checkpoint.
        db2 = SilverDatabase(str(silver_path))
        _seed_thirteenf_holding(db2, cik=1002, accession_number="a2", cusip="594918104", ingested_at=t2)
        db2.close()

        pipeline2 = MDMPipeline(session=session, silver=SilverDatabase(str(silver_path)))
        second = pipeline2.derive_relationships(relationship_types=["INSTITUTIONAL_HOLDS"])
        assert second["INSTITUTIONAL_HOLDS"]["inserted"] == 1
        assert second["INSTITUTIONAL_HOLDS"]["existing"] == 1

        checkpoint = _checkpoint(session, "INSTITUTIONAL_HOLDS")
        assert datetime.fromisoformat(checkpoint.watermark_value) == t2

    def test_checkpoint_never_regresses_on_a_no_op_rerun(self, session, tmp_path):
        silver_path = tmp_path / "silver.duckdb"
        db = SilverDatabase(str(silver_path))
        t1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        _seed_thirteenf_holding(db, cik=1001, accession_number="a1", cusip="037833100", ingested_at=t1)
        db.close()

        pipeline = MDMPipeline(session=session, silver=SilverDatabase(str(silver_path)))
        pipeline.derive_relationships(relationship_types=["INSTITUTIONAL_HOLDS"])
        first_value = _checkpoint(session, "INSTITUTIONAL_HOLDS").watermark_value

        # Rerun with nothing new -- watermark_filter finds 0 rows, and the
        # checkpoint must not move (there is nothing to advance it to).
        pipeline2 = MDMPipeline(session=session, silver=SilverDatabase(str(silver_path)))
        summary = pipeline2.derive_relationships(relationship_types=["INSTITUTIONAL_HOLDS"])
        assert summary["INSTITUTIONAL_HOLDS"]["inserted"] == 0
        assert _checkpoint(session, "INSTITUTIONAL_HOLDS").watermark_value == first_value

    def test_reconciliation_pass_bypasses_the_watermark(self, session, tmp_path):
        """Critical fix this ticket made: the monthly full-universe backstop
        must ignore the checkpoint entirely, or it can never retry a row an
        earlier incremental run skipped for a transient reason."""
        silver_path = tmp_path / "silver.duckdb"
        db = SilverDatabase(str(silver_path))
        t1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        _seed_thirteenf_holding(db, cik=1001, accession_number="a1", cusip="037833100", ingested_at=t1)
        db.close()

        pipeline = MDMPipeline(session=session, silver=SilverDatabase(str(silver_path)))
        pipeline.derive_relationships(relationship_types=["INSTITUTIONAL_HOLDS"])
        assert _checkpoint(session, "INSTITUTIONAL_HOLDS") is not None

        # Ordinary rerun: watermark is now past t1, so the row is invisible again.
        ordinary = MDMPipeline(session=session, silver=SilverDatabase(str(silver_path)))
        ordinary_summary = ordinary.derive_relationships(relationship_types=["INSTITUTIONAL_HOLDS"])
        assert ordinary_summary["INSTITUTIONAL_HOLDS"]["inserted"] == 0

        # A reconciliation pass must still see it (existing, not inserted --
        # ensure_relationship dedupes on the same properties/validity window).
        backstop = MDMPipeline(session=session, silver=SilverDatabase(str(silver_path)))
        backstop_summary = backstop.derive_relationships(
            relationship_types=["INSTITUTIONAL_HOLDS"], reconciliation_pass=True
        )
        assert backstop_summary["INSTITUTIONAL_HOLDS"]["total"] == 1
        assert backstop_summary["INSTITUTIONAL_HOLDS"]["skipped_existing"] == 1


class TestInstitutionalHoldsDeactivation:
    """INSTITUTIONAL_HOLDS deactivation (mdm-relationship-incremental-filters
    Ticket 04, advisor item 3): a two-phase cross-period CUSIP-set diff --
    the watermark answers *which* manager changed, but the diff itself
    re-queries that manager's full latest-period holdings unwatermarked."""

    def test_security_dropped_from_next_13f_gets_closed(self, session, tmp_path):
        silver_path = tmp_path / "silver.duckdb"
        db = SilverDatabase(str(silver_path))
        t1 = datetime(2024, 4, 1, tzinfo=timezone.utc)
        _seed_thirteenf_holding(
            db, cik=2001, accession_number="q1-a", cusip="037833100",
            ingested_at=t1, period_of_report="2024-03-31",
        )
        _seed_thirteenf_holding(
            db, cik=2001, accession_number="q1-b", cusip="594918104",
            ingested_at=t1, period_of_report="2024-03-31",
        )
        db.close()

        pipeline = MDMPipeline(session=session, silver=SilverDatabase(str(silver_path)))
        first = pipeline.derive_relationships(relationship_types=["INSTITUTIONAL_HOLDS"])
        assert first["INSTITUTIONAL_HOLDS"]["inserted"] == 2

        # Q2's 13F only re-reports the first CUSIP -- the second was sold.
        db2 = SilverDatabase(str(silver_path))
        t2 = datetime(2024, 7, 1, tzinfo=timezone.utc)
        _seed_thirteenf_holding(
            db2, cik=2001, accession_number="q2-a", cusip="037833100",
            ingested_at=t2, period_of_report="2024-06-30",
        )
        db2.close()

        pipeline2 = MDMPipeline(session=session, silver=SilverDatabase(str(silver_path)))
        second = pipeline2.derive_relationships(relationship_types=["INSTITUTIONAL_HOLDS"])
        # Each quarter's 13F is its own point-in-time fact: the still-held
        # cusip's Q1 version is rolled forward (closed, cleanly, no
        # quarantine -- see _deactivate_institutional_holds_for_changed_
        # managers' own docstring for the conflict this guards against) and
        # a genuinely new Q2 version opens for it; the dropped cusip's Q1
        # version is simply closed with nothing to replace it.
        assert second["INSTITUTIONAL_HOLDS"]["inserted"] == 1

        from edgar_warehouse.mdm.database import MdmRelationshipInstance, MdmSecurity
        session.expire_all()
        rows = session.execute(select(MdmRelationshipInstance)).scalars().all()
        assert len(rows) == 3
        held_versions = [
            r for r in rows
            if session.get(MdmSecurity, r.target_entity_id).cusip == "037833100"
        ]
        dropped_versions = [
            r for r in rows
            if session.get(MdmSecurity, r.target_entity_id).cusip == "594918104"
        ]
        assert len(held_versions) == 2  # Q1 (closed) + Q2 (open)
        assert len(dropped_versions) == 1  # Q1 only, now closed
        held_open = [v for v in held_versions if v.valid_to_date is None]
        held_closed = [v for v in held_versions if v.valid_to_date is not None]
        assert len(held_open) == 1
        assert held_open[0].quarantined is False
        assert held_open[0].superseded_by_version_id is None
        assert held_closed[0].valid_to_date == date(2024, 6, 30)
        assert dropped_versions[0].valid_to_date == date(2024, 6, 30)

    def test_unchanged_manager_is_never_rechecked(self, session, tmp_path):
        """A manager with nothing new this run must be left untouched --
        re-diffing it anyway would defeat the point of watermarking."""
        silver_path = tmp_path / "silver.duckdb"
        db = SilverDatabase(str(silver_path))
        t1 = datetime(2024, 4, 1, tzinfo=timezone.utc)
        _seed_thirteenf_holding(
            db, cik=2002, accession_number="only-filing", cusip="037833100",
            ingested_at=t1, period_of_report="2024-03-31",
        )
        db.close()

        pipeline = MDMPipeline(session=session, silver=SilverDatabase(str(silver_path)))
        pipeline.derive_relationships(relationship_types=["INSTITUTIONAL_HOLDS"])

        # No new silver data at all -- a rerun must not touch anything,
        # even though this manager's only holding predates "today".
        pipeline2 = MDMPipeline(session=session, silver=SilverDatabase(str(silver_path)))
        second = pipeline2.derive_relationships(relationship_types=["INSTITUTIONAL_HOLDS"])
        assert second["INSTITUTIONAL_HOLDS"]["inserted"] == 0

        from edgar_warehouse.mdm.database import MdmRelationshipInstance
        session.expire_all()
        rows = session.execute(select(MdmRelationshipInstance)).scalars().all()
        assert len(rows) == 1
        assert rows[0].valid_to_date is None


class TestHoldsWatermark:
    """HOLDS: no genuine ingested_at on either txn table -- accession_number
    watermark (Ticket 01/02's natural-ordering-key decision)."""

    @staticmethod
    def _ensure_mdm_entities(session: Session, *, owner_cik: int, issuer_cik: int) -> None:
        """HOLDS' owner (person) and issuer (company) must already resolve
        in MDM -- _person_entity_id/_security_entity_id's issuer fallback
        are lookups, not auto-create, unlike INSTITUTIONAL_HOLDS'
        _ensure_thirteenf_manager/_ensure_security_by_cusip. Idempotent
        (checks entity_type-scoped existence) so repeat calls across the
        two-seeding-pass tests below don't double-insert."""
        existing_person = session.execute(
            select(MdmPerson).where(MdmPerson.owner_cik == owner_cik)
        ).scalar_one_or_none()
        if existing_person is None:
            person_id = _add_entity(session, "person")
            session.add(MdmPerson(entity_id=person_id, owner_cik=owner_cik, canonical_name=f"Owner {owner_cik}"))
        existing_company = session.execute(
            select(MdmCompany).where(MdmCompany.cik == issuer_cik)
        ).scalar_one_or_none()
        if existing_company is None:
            company_id = _add_entity(session, "company")
            session.add(MdmCompany(entity_id=company_id, cik=issuer_cik, canonical_name=f"Issuer {issuer_cik}"))
        else:
            company_id = existing_company.entity_id
        # _security_entity_id is lookup-only for HOLDS (unlike
        # INSTITUTIONAL_HOLDS' auto-creating _ensure_security_by_cusip) --
        # matches on (canonical_title, issuer_entity_id), so the security
        # must already exist for the same title _seed_holds_row writes.
        existing_security = session.execute(
            select(MdmSecurity).where(
                MdmSecurity.canonical_title == "Common Stock",
                MdmSecurity.issuer_entity_id == company_id,
            )
        ).scalar_one_or_none()
        if existing_security is None:
            security_id = _add_entity(session, "security")
            session.add(MdmSecurity(
                entity_id=security_id, issuer_entity_id=company_id, canonical_title="Common Stock",
            ))
        session.commit()

    @staticmethod
    def _seed_holds_row(
        db: SilverDatabase,
        *,
        accession_number: str,
        owner_cik: int,
        issuer_cik: int,
        transaction_date: str = "2024-01-01",
        shares_owned_after: Optional[float] = 100,
    ) -> None:
        db._conn.execute(
            "INSERT OR REPLACE INTO sec_company (cik, entity_name) VALUES (?, ?)",
            [issuer_cik, f"Issuer {issuer_cik}"],
        )
        db._conn.execute(
            """
            INSERT INTO sec_company_filing (accession_number, cik, form, filing_date, report_date)
            VALUES (?, ?, '4', ?, ?)
            """,
            [accession_number, issuer_cik, transaction_date, transaction_date],
        )
        db._conn.execute(
            """
            INSERT INTO sec_ownership_reporting_owner
                (accession_number, owner_index, owner_cik, owner_name)
            VALUES (?, 1, ?, ?)
            """,
            [accession_number, owner_cik, f"Owner {owner_cik}"],
        )
        db._conn.execute(
            """
            INSERT INTO sec_ownership_non_derivative_txn
                (accession_number, owner_index, txn_index, security_title,
                 transaction_date, shares_owned_after, ownership_direct_indirect)
            VALUES (?, 1, 1, 'Common Stock', ?, ?, 'D')
            """,
            [accession_number, transaction_date, shares_owned_after],
        )

    def test_watermark_scopes_to_new_accessions_only(self, session, tmp_path):
        self._ensure_mdm_entities(session, owner_cik=2001, issuer_cik=3001)
        self._ensure_mdm_entities(session, owner_cik=2002, issuer_cik=3001)
        silver_path = tmp_path / "silver.duckdb"
        db = SilverDatabase(str(silver_path))
        # Fixed-width accession numbers sort correctly lexicographically --
        # this platform's established SEC-data-immutability invariant.
        self._seed_holds_row(db, accession_number="0000000001-24-000001", owner_cik=2001, issuer_cik=3001)
        db.close()

        pipeline = MDMPipeline(session=session, silver=SilverDatabase(str(silver_path)))
        first = pipeline.derive_relationships(relationship_types=["HOLDS"])
        assert first["HOLDS"]["inserted"] == 1
        checkpoint = _checkpoint(session, "HOLDS")
        assert checkpoint.watermark_column == "accession_number"
        assert checkpoint.watermark_value == "0000000001-24-000001"

        db2 = SilverDatabase(str(silver_path))
        self._seed_holds_row(db2, accession_number="0000000002-24-000001", owner_cik=2002, issuer_cik=3001)
        db2.close()

        pipeline2 = MDMPipeline(session=session, silver=SilverDatabase(str(silver_path)))
        second = pipeline2.derive_relationships(relationship_types=["HOLDS"])
        assert second["HOLDS"]["inserted"] == 1
        assert second["HOLDS"]["existing"] == 1
        assert _checkpoint(session, "HOLDS").watermark_value == "0000000002-24-000001"

    def test_bounded_target_per_type_does_not_advance_past_unprocessed_rows(self, session, tmp_path):
        """Advisor's item 2: a `target_per_type`-bounded call that only
        processes part of the newly-watermarked window must not advance the
        checkpoint past the rows it never got to."""
        self._ensure_mdm_entities(session, owner_cik=2001, issuer_cik=3001)
        self._ensure_mdm_entities(session, owner_cik=2002, issuer_cik=3001)
        silver_path = tmp_path / "silver.duckdb"
        db = SilverDatabase(str(silver_path))
        self._seed_holds_row(db, accession_number="0000000001-24-000001", owner_cik=2001, issuer_cik=3001)
        self._seed_holds_row(db, accession_number="0000000002-24-000001", owner_cik=2002, issuer_cik=3001)
        db.close()

        pipeline = MDMPipeline(session=session, silver=SilverDatabase(str(silver_path)))
        summary = pipeline.derive_relationships(
            target_per_type=1, relationship_types=["HOLDS"]
        )
        assert summary["HOLDS"]["inserted"] == 1
        # Only the first (lower-accession) row was ever iterated -- the
        # checkpoint must reflect exactly that row, not the second,
        # never-visited one.
        assert _checkpoint(session, "HOLDS").watermark_value == "0000000001-24-000001"

        # A follow-up unbounded call must still pick up the second row --
        # proving it was never silently skipped by an over-advanced watermark.
        pipeline2 = MDMPipeline(session=session, silver=SilverDatabase(str(silver_path)))
        second = pipeline2.derive_relationships(relationship_types=["HOLDS"])
        assert second["HOLDS"]["inserted"] == 1
        assert _checkpoint(session, "HOLDS").watermark_value == "0000000002-24-000001"


class TestHoldsDeactivation:
    """HOLDS deactivation (mdm-relationship-incremental-filters Ticket 04,
    same-day grilling exchange): a shares_owned_after == 0 transaction
    closes the open version instead of recording a zero-value holding."""

    def test_zero_shares_closes_the_open_version_and_inserts_nothing(self, session, tmp_path):
        TestHoldsWatermark._ensure_mdm_entities(session, owner_cik=2001, issuer_cik=3001)
        silver_path = tmp_path / "silver.duckdb"
        db = SilverDatabase(str(silver_path))
        TestHoldsWatermark._seed_holds_row(
            db, accession_number="0000000001-24-000001", owner_cik=2001, issuer_cik=3001,
            transaction_date="2024-01-01", shares_owned_after=100,
        )
        db.close()
        pipeline = MDMPipeline(session=session, silver=SilverDatabase(str(silver_path)))
        opened = pipeline.derive_relationships(relationship_types=["HOLDS"])
        assert opened["HOLDS"]["inserted"] == 1

        from edgar_warehouse.mdm.database import MdmRelationshipInstance
        open_version = session.execute(
            select(MdmRelationshipInstance).where(MdmRelationshipInstance.valid_to_date.is_(None))
        ).scalar_one()
        assert open_version.valid_to_date is None

        db2 = SilverDatabase(str(silver_path))
        TestHoldsWatermark._seed_holds_row(
            db2, accession_number="0000000002-24-000001", owner_cik=2001, issuer_cik=3001,
            transaction_date="2024-06-01", shares_owned_after=0,
        )
        db2.close()
        pipeline2 = MDMPipeline(session=session, silver=SilverDatabase(str(silver_path)))
        closed = pipeline2.derive_relationships(relationship_types=["HOLDS"])
        # The disposal row must not itself become a new relationship version.
        assert closed["HOLDS"]["inserted"] == 0

        session.expire_all()
        rows = session.execute(select(MdmRelationshipInstance)).scalars().all()
        assert len(rows) == 1
        assert rows[0].valid_to_date == date(2024, 6, 1)

    def test_null_shares_owned_after_is_not_treated_as_zero(self, session, tmp_path):
        """The column is nullable (unknown share count) -- NULL must never
        be treated as a real zero and must not close anything."""
        TestHoldsWatermark._ensure_mdm_entities(session, owner_cik=2001, issuer_cik=3001)
        silver_path = tmp_path / "silver.duckdb"
        db = SilverDatabase(str(silver_path))
        TestHoldsWatermark._seed_holds_row(
            db, accession_number="0000000001-24-000001", owner_cik=2001, issuer_cik=3001,
            transaction_date="2024-01-01", shares_owned_after=100,
        )
        TestHoldsWatermark._seed_holds_row(
            db, accession_number="0000000002-24-000001", owner_cik=2001, issuer_cik=3001,
            transaction_date="2024-06-01", shares_owned_after=None,
        )
        db.close()

        pipeline = MDMPipeline(session=session, silver=SilverDatabase(str(silver_path)))
        summary = pipeline.derive_relationships(relationship_types=["HOLDS"])
        # Both rows produce real relationship versions -- the NULL-shares
        # row is ordinary data, not a disposal signal.
        assert summary["HOLDS"]["inserted"] == 2

    def test_reacquisition_after_disposal_opens_a_new_version(self, session, tmp_path):
        """A later, non-zero row for the same (person, security) pair after
        a zero-shares close must open a fresh version, not be silently
        swallowed by the closed one."""
        TestHoldsWatermark._ensure_mdm_entities(session, owner_cik=2001, issuer_cik=3001)
        silver_path = tmp_path / "silver.duckdb"
        db = SilverDatabase(str(silver_path))
        TestHoldsWatermark._seed_holds_row(
            db, accession_number="0000000001-24-000001", owner_cik=2001, issuer_cik=3001,
            transaction_date="2024-01-01", shares_owned_after=100,
        )
        TestHoldsWatermark._seed_holds_row(
            db, accession_number="0000000002-24-000001", owner_cik=2001, issuer_cik=3001,
            transaction_date="2024-06-01", shares_owned_after=0,
        )
        TestHoldsWatermark._seed_holds_row(
            db, accession_number="0000000003-24-000001", owner_cik=2001, issuer_cik=3001,
            transaction_date="2024-09-01", shares_owned_after=50,
        )
        db.close()

        pipeline = MDMPipeline(session=session, silver=SilverDatabase(str(silver_path)))
        summary = pipeline.derive_relationships(relationship_types=["HOLDS"])
        # Row 1 opens a version (insert), row 2 closes it (no insert), row 3
        # opens a genuinely new version (insert) -- exactly two inserts,
        # and critically, row 3 must NOT be quarantined as a false conflict
        # against the now-closed row 1 version.
        assert summary["HOLDS"]["inserted"] == 2

        from edgar_warehouse.mdm.database import MdmRelationshipInstance
        rows = session.execute(select(MdmRelationshipInstance)).scalars().all()
        assert len(rows) == 2
        closed = [r for r in rows if r.valid_to_date is not None]
        open_versions = [r for r in rows if r.valid_to_date is None]
        assert len(closed) == 1
        assert len(open_versions) == 1
        assert closed[0].valid_to_date == date(2024, 6, 1)
        assert open_versions[0].valid_from_date == date(2024, 9, 1)
        assert open_versions[0].quarantined is False
        assert open_versions[0].superseded_by_version_id is None


class TestEmployedByDualCheckpoint:
    """EMPLOYED_BY's two independent source tables need two independent
    checkpoints -- one shared watermark value can't represent both."""

    def test_exec_and_event_checkpoints_advance_independently(self, session, tmp_path):
        company_id = _add_entity(session, "company")
        session.add(MdmCompany(entity_id=company_id, cik=4001, canonical_name="Employer Co"))
        session.commit()

        silver_path = tmp_path / "silver.duckdb"
        db = SilverDatabase(str(silver_path))
        db._conn.execute(
            "INSERT OR REPLACE INTO sec_company (cik, entity_name) VALUES (?, ?)",
            [4001, "Employer Co"],
        )
        db._conn.execute(
            """
            INSERT INTO sec_executive_record
                (cik, accession_number, fiscal_year, exec_name, exec_role, ingested_at)
            VALUES (4001, 'proxy-1', 2024, 'Jane Doe', 'CEO', ?)
            """,
            [datetime(2024, 1, 1, tzinfo=timezone.utc)],
        )
        db.close()

        pipeline = MDMPipeline(session=session, silver=SilverDatabase(str(silver_path)))
        summary = pipeline.derive_relationships(relationship_types=["EMPLOYED_BY"])
        assert summary["EMPLOYED_BY"]["inserted"] == 1

        exec_checkpoint = _checkpoint(session, "EMPLOYED_BY:exec")
        event_checkpoint = _checkpoint(session, "EMPLOYED_BY:event")
        assert exec_checkpoint is not None
        assert exec_checkpoint.rel_type_name == "EMPLOYED_BY"
        # No sec_employment_event rows were ever seeded -- its own
        # checkpoint must stay unset (nothing to advance to), independent of
        # the exec checkpoint that did advance.
        assert event_checkpoint is None


class TestManagesFundWatermark:
    """MANAGES_FUND: CRD-range batched (mdm-oom-manages-fund fix), same
    accession_number watermark shape as HOLDS -- exercised against a real
    SilverDatabase rather than StubSilver specifically because StubSilver's
    substring-matching fetch() never filters by the SQL text's WHERE
    clause (only its own hardcoded MIN/MAX/BETWEEN/IN cases), so it cannot
    tell a watermark-filtered query from an unfiltered one -- only a real
    backend can prove the second run actually reads less."""

    def test_watermark_scopes_to_new_accessions_only(self, session, tmp_path):
        adviser_id = _add_entity(session, "adviser")
        session.add(MdmAdviser(
            entity_id=adviser_id, cik=5001, crd_number="555001", canonical_name="Adviser 555001",
        ))
        fund_id = _add_entity(session, "fund")
        session.add(MdmFund(
            entity_id=fund_id, adviser_entity_id=adviser_id, private_fund_id="fund-1",
            canonical_name="Fund One",
        ))
        session.commit()

        silver_path = tmp_path / "silver.duckdb"
        db = SilverDatabase(str(silver_path))
        db._conn.execute(
            """
            INSERT INTO sec_adv_filing
                (accession_number, crd_number, effective_date, filing_action)
            VALUES ('iapd-adv:100', '555001', '2024-01-01', 'annual_amendment')
            """
        )
        db._conn.execute(
            """
            INSERT INTO sec_adv_private_fund
                (accession_number, fund_index, filing_id, adviser_crd_number, private_fund_id,
                 schedule_section, reporting_role, effective_date, filing_action)
            VALUES ('iapd-adv:100', 1, '100', '555001', 'fund-1', '7B1',
                    'detailed_reporter', '2024-01-01', 'annual_amendment')
            """
        )
        db.close()

        pipeline = MDMPipeline(session=session, silver=SilverDatabase(str(silver_path)))
        first = pipeline.derive_relationships(relationship_types=["MANAGES_FUND"])
        assert first["MANAGES_FUND"]["inserted"] == 1
        checkpoint = _checkpoint(session, "MANAGES_FUND")
        assert checkpoint is not None
        assert checkpoint.watermark_column == "accession_number"
        assert checkpoint.watermark_value == "iapd-adv:100"

        # Rerun with nothing new: the watermark-filtered filing_rows/
        # source_rows fetch returns nothing for this CRD, so the
        # deactivation diff never touches it and the existing relationship
        # is left alone (not spuriously closed).
        pipeline2 = MDMPipeline(session=session, silver=SilverDatabase(str(silver_path)))
        second = pipeline2.derive_relationships(relationship_types=["MANAGES_FUND"])
        assert second["MANAGES_FUND"]["inserted"] == 0
        assert second["MANAGES_FUND"]["existing"] == 1
        assert _checkpoint(session, "MANAGES_FUND").watermark_value == "iapd-adv:100"
