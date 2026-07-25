"""Ticket 21: person + IS_INSIDER loader must not re-resolve companies."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from edgar_warehouse.mdm.cli import _ownership_insider_only_types
from edgar_warehouse.mdm.pipeline import MDMPipeline


def test_ownership_insider_only_types():
    assert _ownership_insider_only_types(["IS_INSIDER"]) is True
    assert _ownership_insider_only_types(["IS_INSIDER", "HOLDS"]) is True
    assert _ownership_insider_only_types(["IS_INSIDER", "EMPLOYED_BY"]) is False
    assert _ownership_insider_only_types(None) is False
    assert _ownership_insider_only_types([]) is False


def test_run_persons_scopes_sql_to_issuer_ciks():
    silver = MagicMock()
    silver.fetch.return_value = []
    session = MagicMock()
    session.scalars.return_value = []
    pipe = MDMPipeline(session=session, silver=silver)

    n = pipe.run_persons(issuer_ciks=[320193, 789019])
    assert n == 0
    sql, params = silver.fetch.call_args[0]
    assert "sec_ownership_reporting_owner" in sql
    assert "f.cik IN" in sql
    assert params == [320193, 789019]


def test_derive_is_insider_scopes_sql_to_issuer_ciks():
    silver = MagicMock()
    silver.fetch.return_value = []
    session = MagicMock()
    pipe = MDMPipeline(session=session, silver=silver)

    with patch.object(pipe, "_company_cik_set", return_value=set()):
        with patch.object(pipe, "_relationship_count", return_value=0):
            with patch("edgar_warehouse.mdm.pipeline.GraphSyncEngine") as ge:
                ge.build.return_value = MagicMock()
                summary = pipe.derive_relationships(
                    target_per_type=100,
                    relationship_types=["IS_INSIDER"],
                    issuer_ciks=[320193],
                )

    assert summary["IS_INSIDER"]["inserted"] == 0
    sql, params = silver.fetch.call_args[0]
    assert "IS_INSIDER" not in sql  # SQL is ownership query
    assert "sec_ownership_reporting_owner" in sql
    assert "f.cik IN" in sql
    assert params == [320193]
