"""Direct, function-level tests for
edgar_warehouse/mdm/security_issuer_link.py.

mdm-relationship-versioning-gap Ticket 06: links CUSIP-stub securities
(13F-derived, no Form-4 anchor, no CUSIP-to-CIK crosswalk available) to
their issuer MdmCompany row via fuzzy name matching -- reusing the existing
('company', 'fuzzy_name') matcher and threshold.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from edgar_warehouse.mdm.database import (
    Base,
    MdmCompany,
    MdmEntity,
    MdmMatchThreshold,
    MdmSecurity,
)
from edgar_warehouse.mdm.match import MatchAction
from edgar_warehouse.mdm.rules import ALL, MDMRuleEngine
from edgar_warehouse.mdm.security_issuer_link import (
    backfill_missing_issuer_links,
    load_company_candidates,
    match_issuer_candidate,
    resolve_issuer_entity_id,
)


@pytest.fixture
def engine() -> MDMRuleEngine:
    return MDMRuleEngine(
        _source_priority={(ALL, "edgar_cik"): 1},
        _field_survivorship={},
        _match_thresholds={("company", "fuzzy_name"): (0.95, 0.85)},
        _normalization={"legal_suffix": {"INC": "", "LLC": "", "CORP": ""}},
    )


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sess = Session(engine)
    sess.add(MdmMatchThreshold(
        entity_type="company", match_method="fuzzy_name",
        auto_merge_min=0.95, review_min=0.85,
    ))
    sess.commit()
    yield sess
    sess.close()


def _company(session: Session, *, entity_id: str, canonical_name: str, cik: int) -> None:
    session.add(MdmEntity(entity_id=entity_id, entity_type="company", resolution_method="cik_exact"))
    session.add(MdmCompany(entity_id=entity_id, cik=cik, canonical_name=canonical_name))


def _security_stub(
    session: Session, *, entity_id: str, cusip: str, canonical_title: str,
    issuer_entity_id: str | None = None,
) -> None:
    session.add(MdmEntity(entity_id=entity_id, entity_type="security", resolution_method="cusip_stub"))
    session.add(MdmSecurity(
        entity_id=entity_id, cusip=cusip, canonical_title=canonical_title,
        issuer_entity_id=issuer_entity_id,
    ))


# --- match_issuer_candidate / resolve_issuer_entity_id (pure, no DB) --------

def test_match_issuer_candidate_auto_merge(engine: MDMRuleEngine) -> None:
    verdict = match_issuer_candidate(
        engine, "Apple Inc",
        [{"entity_id": "e1", "canonical_name": "Apple Inc."}],
    )
    assert verdict is not None
    assert verdict.action == MatchAction.AUTO_MERGE
    assert verdict.candidate_entity_id == "e1"


def test_match_issuer_candidate_no_name_returns_none(engine: MDMRuleEngine) -> None:
    assert match_issuer_candidate(engine, None, [{"entity_id": "e1", "canonical_name": "Apple Inc."}]) is None
    assert match_issuer_candidate(engine, "", [{"entity_id": "e1", "canonical_name": "Apple Inc."}]) is None


def test_match_issuer_candidate_no_candidates_returns_none(engine: MDMRuleEngine) -> None:
    assert match_issuer_candidate(engine, "Apple Inc", []) is None


def test_match_issuer_candidate_missing_threshold_degrades_gracefully() -> None:
    """A missing mdm_match_threshold row (real config gap, e.g. an unseeded
    test/dev fixture) must not crash the caller -- this linking is
    deliberately best-effort, not required for derivation to succeed."""
    bare_engine = MDMRuleEngine(
        _source_priority={}, _field_survivorship={}, _match_thresholds={}, _normalization={},
    )
    assert match_issuer_candidate(bare_engine, "Apple Inc", [{"entity_id": "e1", "canonical_name": "Apple Inc."}]) is None


def test_resolve_issuer_entity_id_auto_merge_returns_id(engine: MDMRuleEngine) -> None:
    result = resolve_issuer_entity_id(
        engine, "Apple Inc",
        [{"entity_id": "e1", "canonical_name": "Apple Inc."}],
        cusip="037833100",
    )
    assert result == "e1"


def test_resolve_issuer_entity_id_review_tier_logs_not_links(engine: MDMRuleEngine, capsys) -> None:
    # "Blackrock Advisors" vs "Blackrock Inc" -- same shape as test_match.py's
    # own review-tier fixture case, scores between review_min and auto_merge_min.
    result = resolve_issuer_entity_id(
        engine, "Blackrock Advisors",
        [{"entity_id": "e1", "canonical_name": "Blackrock Inc"}],
        cusip="09247X101",
    )
    assert result is None
    err = capsys.readouterr().err
    assert "mdm_issuer_link_candidate_below_threshold" in err
    assert "09247X101" in err


def test_resolve_issuer_entity_id_quarantine_tier_silent(engine: MDMRuleEngine, capsys) -> None:
    result = resolve_issuer_entity_id(
        engine, "Totally Unrelated Company Name",
        [{"entity_id": "e1", "canonical_name": "Apple Inc."}],
        cusip="000000000",
    )
    assert result is None
    assert capsys.readouterr().err == ""


# --- load_company_candidates (real DB) --------------------------------------

def test_load_company_candidates_returns_all_companies(session: Session) -> None:
    _company(session, entity_id=str(uuid.uuid4()), canonical_name="Apple Inc.", cik=320193)
    _company(session, entity_id=str(uuid.uuid4()), canonical_name="Microsoft Corporation", cik=789019)
    session.commit()

    candidates = load_company_candidates(session)
    assert len(candidates) == 2
    names = {c["canonical_name"] for c in candidates}
    assert names == {"Apple Inc.", "Microsoft Corporation"}


# --- backfill_missing_issuer_links (real DB, session-level) -----------------

def test_backfill_links_high_confidence_orphan(session: Session) -> None:
    apple_id = str(uuid.uuid4())
    _company(session, entity_id=apple_id, canonical_name="Apple Inc.", cik=320193)
    stub_id = str(uuid.uuid4())
    _security_stub(session, entity_id=stub_id, cusip="037833100", canonical_title="Apple Inc.")
    session.commit()

    summary = backfill_missing_issuer_links(session)
    session.commit()

    assert summary.examined == 1
    assert summary.linked == 1
    sec = session.get(MdmSecurity, stub_id)
    assert sec.issuer_entity_id == apple_id


def test_backfill_dry_run_does_not_mutate(session: Session) -> None:
    apple_id = str(uuid.uuid4())
    _company(session, entity_id=apple_id, canonical_name="Apple Inc.", cik=320193)
    stub_id = str(uuid.uuid4())
    _security_stub(session, entity_id=stub_id, cusip="037833100", canonical_title="Apple Inc.")
    session.commit()

    summary = backfill_missing_issuer_links(session, dry_run=True)

    assert summary.linked == 1
    sec = session.get(MdmSecurity, stub_id)
    assert sec.issuer_entity_id is None


def test_backfill_skips_already_linked_securities(session: Session) -> None:
    apple_id = str(uuid.uuid4())
    _company(session, entity_id=apple_id, canonical_name="Apple Inc.", cik=320193)
    stub_id = str(uuid.uuid4())
    _security_stub(
        session, entity_id=stub_id, cusip="037833100", canonical_title="Apple Inc.",
        issuer_entity_id=apple_id,
    )
    session.commit()

    summary = backfill_missing_issuer_links(session)

    assert summary.examined == 0


def test_backfill_review_tier_logs_not_links(session: Session, capsys) -> None:
    _company(session, entity_id=str(uuid.uuid4()), canonical_name="Blackrock Inc", cik=1364742)
    stub_id = str(uuid.uuid4())
    _security_stub(session, entity_id=stub_id, cusip="09247X101", canonical_title="Blackrock Advisors")
    session.commit()

    summary = backfill_missing_issuer_links(session)

    assert summary.linked == 0
    assert summary.review_logged == 1
    sec = session.get(MdmSecurity, stub_id)
    assert sec.issuer_entity_id is None
    err = capsys.readouterr().err
    assert "mdm_issuer_link_candidate_below_threshold" in err
    assert "09247X101" in err


def test_backfill_scoped_to_cusip_stub_resolution_method(session: Session) -> None:
    """A security missing an issuer link via some OTHER resolution_method
    (not cusip_stub) is out of this ticket's scope -- confirmed via the
    ticket's own live diagnostic, which scoped to cusip_stub specifically."""
    apple_id = str(uuid.uuid4())
    _company(session, entity_id=apple_id, canonical_name="Apple Inc.", cik=320193)
    other_id = str(uuid.uuid4())
    session.add(MdmEntity(entity_id=other_id, entity_type="security", resolution_method="issuer_title_dedup"))
    session.add(MdmSecurity(entity_id=other_id, cusip="037833100", canonical_title="Apple Inc."))
    session.commit()

    summary = backfill_missing_issuer_links(session)

    assert summary.examined == 0
    sec = session.get(MdmSecurity, other_id)
    assert sec.issuer_entity_id is None


def test_backfill_low_confidence_left_unlinked(session: Session) -> None:
    _company(session, entity_id=str(uuid.uuid4()), canonical_name="Apple Inc.", cik=320193)
    stub_id = str(uuid.uuid4())
    _security_stub(session, entity_id=stub_id, cusip="000000000", canonical_title="Totally Unrelated Company")
    session.commit()

    summary = backfill_missing_issuer_links(session)

    assert summary.linked == 0
    assert summary.skipped_no_match == 1
    sec = session.get(MdmSecurity, stub_id)
    assert sec.issuer_entity_id is None
