"""Tests for Phase 7 Plan 05 Task 3: strict current/historical graph query
contracts (RTEMP-02) and canonical-merge-entity traversal remap (RLINE-01).

Uses the same `api_client`/`db_session` fixtures (conftest.py) and entity
factory helpers as tests/mdm/test_api.py.
"""
from __future__ import annotations

import uuid
from datetime import date

from tests.mdm.test_api import _entity, _rel_instance


def _relationship_with_dates(
    session,
    rel_type_name: str,
    src_eid: str,
    tgt_eid: str,
    *,
    valid_from_date=None,
    valid_to_date=None,
    date_provenance: str = "reported",
    is_active: bool = True,
):
    """Insert a relationship instance with explicit typed temporal fields,
    independent of the legacy effective_from/effective_to pair."""
    from sqlalchemy import select

    from edgar_warehouse.mdm.database import MdmRelationshipInstance, MdmRelationshipType

    rt = session.scalar(
        select(MdmRelationshipType).where(MdmRelationshipType.rel_type_name == rel_type_name)
    )
    row = MdmRelationshipInstance(
        rel_type_id=rt.rel_type_id,
        source_entity_id=src_eid,
        target_entity_id=tgt_eid,
        valid_from_date=valid_from_date,
        valid_to_date=valid_to_date,
        date_provenance=date_provenance,
        is_active=is_active,
    )
    session.add(row)
    session.flush()
    return row


def _merge(session, keep_eid: str, discard_eid: str, reason: str = "test merge") -> None:
    from edgar_warehouse.mdm.stewardship import merge_entities

    merge_entities(session, keep=keep_eid, discard=discard_eid, reason=reason)


class TestStrictAsOfDateBoundaries:
    """RTEMP-02: inclusive start, exclusive end -- an edge ending exactly on
    the query date is excluded, one starting exactly on that date is included."""

    def test_edge_ending_on_the_query_date_is_excluded(self, api_client, db_session):
        adv_eid = _entity(db_session, "adviser")
        fund_eid = _entity(db_session, "fund")
        db_session.flush()
        _relationship_with_dates(
            db_session, "MANAGES_FUND", adv_eid, fund_eid,
            valid_from_date=date(2020, 1, 1), valid_to_date=date(2025, 6, 1),
        )
        db_session.commit()

        r = api_client.get(
            f"/api/v1/mdm/graph/neighborhood/{adv_eid}",
            params={"as_of": "2025-06-01"},
        )
        assert r.json()["edges"] == []

    def test_edge_starting_on_the_query_date_is_included(self, api_client, db_session):
        adv_eid = _entity(db_session, "adviser")
        fund_eid = _entity(db_session, "fund")
        db_session.flush()
        _relationship_with_dates(
            db_session, "MANAGES_FUND", adv_eid, fund_eid,
            valid_from_date=date(2025, 6, 1), valid_to_date=None,
        )
        db_session.commit()

        r = api_client.get(
            f"/api/v1/mdm/graph/neighborhood/{adv_eid}",
            params={"as_of": "2025-06-01"},
        )
        assert len(r.json()["edges"]) == 1

    def test_edge_before_its_valid_from_date_is_excluded(self, api_client, db_session):
        adv_eid = _entity(db_session, "adviser")
        fund_eid = _entity(db_session, "fund")
        db_session.flush()
        _relationship_with_dates(
            db_session, "MANAGES_FUND", adv_eid, fund_eid,
            valid_from_date=date(2026, 1, 1), valid_to_date=None,
        )
        db_session.commit()

        r = api_client.get(
            f"/api/v1/mdm/graph/neighborhood/{adv_eid}",
            params={"as_of": "2025-06-01"},
        )
        assert r.json()["edges"] == []

    def test_open_ended_edge_still_valid_is_included(self, api_client, db_session):
        adv_eid = _entity(db_session, "adviser")
        fund_eid = _entity(db_session, "fund")
        db_session.flush()
        _relationship_with_dates(
            db_session, "MANAGES_FUND", adv_eid, fund_eid,
            valid_from_date=date(2020, 1, 1), valid_to_date=None,
        )
        db_session.commit()

        r = api_client.get(
            f"/api/v1/mdm/graph/neighborhood/{adv_eid}",
            params={"as_of": "2030-01-01"},
        )
        assert len(r.json()["edges"]) == 1


class TestUnknownDateProvenance:
    """RTEMP-02: unknown-date edges are excluded by default and only surfaced
    (labeled uncertain) when explicitly requested."""

    def test_unknown_provenance_edge_excluded_by_default(self, api_client, db_session):
        adv_eid = _entity(db_session, "adviser")
        fund_eid = _entity(db_session, "fund")
        db_session.flush()
        _relationship_with_dates(
            db_session, "MANAGES_FUND", adv_eid, fund_eid,
            valid_from_date=None, valid_to_date=None, date_provenance="unknown",
        )
        db_session.commit()

        r = api_client.get(
            f"/api/v1/mdm/graph/neighborhood/{adv_eid}",
            params={"as_of": "2025-06-01"},
        )
        assert r.json()["edges"] == []

    def test_unknown_provenance_edge_included_and_labeled_when_requested(self, api_client, db_session):
        adv_eid = _entity(db_session, "adviser")
        fund_eid = _entity(db_session, "fund")
        db_session.flush()
        _relationship_with_dates(
            db_session, "MANAGES_FUND", adv_eid, fund_eid,
            valid_from_date=None, valid_to_date=None, date_provenance="unknown",
        )
        db_session.commit()

        r = api_client.get(
            f"/api/v1/mdm/graph/neighborhood/{adv_eid}",
            params={"as_of": "2025-06-01", "include_unknown_dates": True},
        )
        edges = r.json()["edges"]
        assert len(edges) == 1
        assert edges[0]["date_uncertain"] is True
        assert edges[0]["date_provenance"] == "unknown"

    def test_reported_edge_not_labeled_uncertain(self, api_client, db_session):
        adv_eid = _entity(db_session, "adviser")
        fund_eid = _entity(db_session, "fund")
        db_session.flush()
        _relationship_with_dates(
            db_session, "MANAGES_FUND", adv_eid, fund_eid,
            valid_from_date=date(2020, 1, 1), valid_to_date=None, date_provenance="reported",
        )
        db_session.commit()

        r = api_client.get(
            f"/api/v1/mdm/graph/neighborhood/{adv_eid}",
            params={"as_of": "2025-06-01"},
        )
        edges = r.json()["edges"]
        assert len(edges) == 1
        assert edges[0]["date_uncertain"] is False

    def test_current_by_default_no_as_of_returns_all_active_regardless_of_provenance(
        self, api_client, db_session
    ):
        adv_eid = _entity(db_session, "adviser")
        fund_eid = _entity(db_session, "fund")
        db_session.flush()
        _relationship_with_dates(
            db_session, "MANAGES_FUND", adv_eid, fund_eid,
            valid_from_date=None, valid_to_date=None, date_provenance="unknown",
        )
        db_session.commit()

        r = api_client.get(f"/api/v1/mdm/graph/neighborhood/{adv_eid}")
        assert len(r.json()["edges"]) == 1


class TestHistoricalSupersededVersions:
    """RTEMP-02 / phase success criteria: strict as_of_date traversal must
    see whichever version was actually valid at that date, including a
    since-superseded (is_active=False) one -- not just whatever is active
    today. The no-as_of "current" default is unaffected."""

    def test_as_of_in_the_past_finds_the_superseded_version(self, api_client, db_session):
        adv_eid = _entity(db_session, "adviser")
        fund_eid = _entity(db_session, "fund")
        db_session.flush()
        _relationship_with_dates(
            db_session, "MANAGES_FUND", adv_eid, fund_eid,
            valid_from_date=date(2020, 1, 1), valid_to_date=date(2023, 1, 1),
            is_active=False,
        )
        _relationship_with_dates(
            db_session, "MANAGES_FUND", adv_eid, fund_eid,
            valid_from_date=date(2023, 1, 1), valid_to_date=None,
            is_active=True,
        )
        db_session.commit()

        r = api_client.get(
            f"/api/v1/mdm/graph/neighborhood/{adv_eid}",
            params={"as_of": "2021-06-01"},
        )
        edges = r.json()["edges"]
        assert len(edges) == 1
        assert edges[0]["valid_from_date"] == "2020-01-01"

    def test_as_of_now_finds_the_current_version(self, api_client, db_session):
        adv_eid = _entity(db_session, "adviser")
        fund_eid = _entity(db_session, "fund")
        db_session.flush()
        _relationship_with_dates(
            db_session, "MANAGES_FUND", adv_eid, fund_eid,
            valid_from_date=date(2020, 1, 1), valid_to_date=date(2023, 1, 1),
            is_active=False,
        )
        _relationship_with_dates(
            db_session, "MANAGES_FUND", adv_eid, fund_eid,
            valid_from_date=date(2023, 1, 1), valid_to_date=None,
            is_active=True,
        )
        db_session.commit()

        r = api_client.get(
            f"/api/v1/mdm/graph/neighborhood/{adv_eid}",
            params={"as_of": "2025-01-01"},
        )
        edges = r.json()["edges"]
        assert len(edges) == 1
        assert edges[0]["valid_from_date"] == "2023-01-01"

    def test_current_by_default_ignores_superseded_versions(self, api_client, db_session):
        """No as_of at all: only the currently-active version, matching the
        pre-existing "live now" contract -- the superseded row must not leak
        into a plain (non-historical) neighborhood query."""
        adv_eid = _entity(db_session, "adviser")
        fund_eid = _entity(db_session, "fund")
        db_session.flush()
        _relationship_with_dates(
            db_session, "MANAGES_FUND", adv_eid, fund_eid,
            valid_from_date=date(2020, 1, 1), valid_to_date=date(2023, 1, 1),
            is_active=False,
        )
        _relationship_with_dates(
            db_session, "MANAGES_FUND", adv_eid, fund_eid,
            valid_from_date=date(2023, 1, 1), valid_to_date=None,
            is_active=True,
        )
        db_session.commit()

        r = api_client.get(f"/api/v1/mdm/graph/neighborhood/{adv_eid}")
        edges = r.json()["edges"]
        assert len(edges) == 1
        assert edges[0]["valid_from_date"] == "2023-01-01"


class TestCanonicalMergeRemap:
    """RLINE-01: traversal converges onto the canonical (kept) entity even
    though mdm_relationship_instance still stores the discarded raw id, and
    the response still surfaces the original identity/merge lineage."""

    def test_merged_entity_multi_hop_path_remains_connected(self, api_client, db_session):
        # subsidiary -[HAS_PARENT_COMPANY]-> company_old, then company_old is merged into company_new.
        subsidiary_eid = _entity(db_session, "company")
        company_old_eid = _entity(db_session, "company")
        company_new_eid = _entity(db_session, "company")
        db_session.flush()
        _rel_instance(db_session, "HAS_PARENT_COMPANY", subsidiary_eid, company_old_eid)
        db_session.commit()

        _merge(db_session, keep_eid=company_new_eid, discard_eid=company_old_eid)
        db_session.commit()

        # Querying the NEW (kept) entity's neighborhood must still find the
        # edge, even though it's stored under the OLD (discarded) entity_id.
        r = api_client.get(f"/api/v1/mdm/graph/neighborhood/{company_new_eid}")
        body = r.json()
        assert len(body["edges"]) == 1
        edge = body["edges"][0]
        assert edge["target_entity_id"] == company_new_eid
        assert edge["target_entity_id_original"] == company_old_eid

        node_ids = {n["entity_id"] for n in body["nodes"]}
        assert company_new_eid in node_ids
        assert company_old_eid not in node_ids  # canonical, not raw, node identity

        new_node = next(n for n in body["nodes"] if n["entity_id"] == company_new_eid)
        assert company_old_eid in new_node["merged_from"]

    def test_querying_by_the_discarded_id_still_resolves_through_canonical(self, api_client, db_session):
        subsidiary_eid = _entity(db_session, "company")
        company_old_eid = _entity(db_session, "company")
        company_new_eid = _entity(db_session, "company")
        db_session.flush()
        _rel_instance(db_session, "HAS_PARENT_COMPANY", subsidiary_eid, company_old_eid)
        db_session.commit()
        _merge(db_session, keep_eid=company_new_eid, discard_eid=company_old_eid)
        db_session.commit()

        r = api_client.get(f"/api/v1/mdm/graph/neighborhood/{company_old_eid}")
        body = r.json()
        assert len(body["edges"]) == 1
        assert body["edges"][0]["target_entity_id"] == company_new_eid

    def test_unmerged_node_has_empty_merged_from(self, api_client, db_session):
        adv_eid = _entity(db_session, "adviser")
        fund_eid = _entity(db_session, "fund")
        db_session.flush()
        _rel_instance(db_session, "MANAGES_FUND", adv_eid, fund_eid)
        db_session.commit()

        r = api_client.get(f"/api/v1/mdm/graph/neighborhood/{adv_eid}")
        body = r.json()
        adv_node = next(n for n in body["nodes"] if n["entity_id"] == adv_eid)
        assert adv_node["merged_from"] == []
