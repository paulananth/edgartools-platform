"""Tests for the mdm-ahead-of-silver map's Phase B backfill sweep
(edgar_warehouse/mdm_entity_backfill.py).

backfill_shard_mdm_entity_ids is the unit under test for most of this file:
given an open silver shard (DuckDB) with mdm_entity_id = NULL rows and an
MDM session with MdmSourceRef rows already registered (as the real
resolvers would have left them), it should backfill exactly the rows with a
matching source ref and leave everything else untouched.

run_mdm_entity_backfill_sweep's local/monolith path is covered end-to-end
by one test using a file-backed sqlite MDM_DATABASE_URL (not :memory:, so
the sweep's own internally-created engine sees the same data this test
seeded).
"""

from __future__ import annotations

import os
import uuid
from unittest.mock import patch

import duckdb
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import StorageLocation
from edgar_warehouse.mdm.database import Base, MdmEntity, MdmSourceRef
from edgar_warehouse.mdm_entity_backfill import (
    MDM_ENTITY_ID_TABLES,
    backfill_shard_mdm_entity_ids,
    run_mdm_entity_backfill_sweep,
)
from edgar_warehouse.silver_store import SilverDatabase


def _register(session: Session, *, entity_type: str, source_system: str, source_id: str) -> str:
    entity_id = str(uuid.uuid4())
    session.add(MdmEntity(entity_id=entity_id, entity_type=entity_type, resolution_method="test"))
    session.add(
        MdmSourceRef(
            entity_id=entity_id,
            source_system=source_system,
            source_id=source_id,
            source_priority=1,
        )
    )
    return entity_id


def test_backfill_populates_all_six_tables_from_matching_source_refs(tmp_path, db_session) -> None:
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        company_entity = _register(db_session, entity_type="company", source_system="edgar_cik", source_id="320193")
        person_entity = _register(
            db_session, entity_type="person", source_system="ownership_filing", source_id="0001-25-000001:1"
        )
        security_entity = _register(
            db_session, entity_type="security", source_system="ownership_filing", source_id="0001-25-000001:1:1"
        )
        deriv_security_entity = _register(
            db_session,
            entity_type="security",
            source_system="ownership_filing",
            source_id="0001-25-000002:derivative:1:1",
        )
        adviser_entity = _register(db_session, entity_type="adviser", source_system="adv_filing", source_id="0002-25-000001")
        fund_entity = _register(db_session, entity_type="fund", source_system="adv_filing", source_id="pfid-123")
        db_session.commit()

        db._conn.execute(
            "INSERT INTO sec_company (cik, entity_name) VALUES (320193, 'Apple Inc')"
        )
        db._conn.execute(
            "INSERT INTO sec_ownership_reporting_owner (accession_number, owner_index, owner_name) "
            "VALUES ('0001-25-000001', 1, 'Jane Doe')"
        )
        db._conn.execute(
            "INSERT INTO sec_ownership_non_derivative_txn (accession_number, owner_index, txn_index, security_title) "
            "VALUES ('0001-25-000001', 1, 1, 'Common Stock')"
        )
        db._conn.execute(
            "INSERT INTO sec_ownership_derivative_txn (accession_number, owner_index, txn_index, security_title) "
            "VALUES ('0001-25-000002', 1, 1, 'Option')"
        )
        db._conn.execute(
            "INSERT INTO sec_adv_filing (accession_number, cik, adviser_name) "
            "VALUES ('0002-25-000001', 999, 'Acme Advisers')"
        )
        db._conn.execute(
            "INSERT INTO sec_adv_private_fund (accession_number, fund_index, private_fund_id, fund_name) "
            "VALUES ('0002-25-000001', 1, 'pfid-123', 'Acme Fund I')"
        )

        counts = backfill_shard_mdm_entity_ids(db, db_session)

        assert counts == {
            "sec_company": 1,
            "sec_ownership_reporting_owner": 1,
            "sec_ownership_non_derivative_txn": 1,
            "sec_ownership_derivative_txn": 1,
            "sec_adv_filing": 1,
            "sec_adv_private_fund": 1,
        }

        assert db._conn.execute(
            "SELECT mdm_entity_id FROM sec_company WHERE cik = 320193"
        ).fetchone()[0] == company_entity
        assert db._conn.execute(
            "SELECT mdm_entity_id FROM sec_ownership_reporting_owner "
            "WHERE accession_number = '0001-25-000001' AND owner_index = 1"
        ).fetchone()[0] == person_entity
        assert db._conn.execute(
            "SELECT mdm_entity_id FROM sec_ownership_non_derivative_txn "
            "WHERE accession_number = '0001-25-000001' AND owner_index = 1 AND txn_index = 1"
        ).fetchone()[0] == security_entity
        assert db._conn.execute(
            "SELECT mdm_entity_id FROM sec_ownership_derivative_txn "
            "WHERE accession_number = '0001-25-000002' AND owner_index = 1 AND txn_index = 1"
        ).fetchone()[0] == deriv_security_entity
        assert db._conn.execute(
            "SELECT mdm_entity_id FROM sec_adv_filing WHERE accession_number = '0002-25-000001'"
        ).fetchone()[0] == adviser_entity
        assert db._conn.execute(
            "SELECT mdm_entity_id FROM sec_adv_private_fund "
            "WHERE accession_number = '0002-25-000001' AND fund_index = 1"
        ).fetchone()[0] == fund_entity
    finally:
        db.close()


def test_row_with_no_matching_source_ref_stays_null(tmp_path, db_session) -> None:
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        db._conn.execute(
            "INSERT INTO sec_company (cik, entity_name) VALUES (999999, 'Unresolved Co')"
        )
        counts = backfill_shard_mdm_entity_ids(db, db_session)
        assert counts["sec_company"] == 0
        row = db._conn.execute(
            "SELECT mdm_entity_id FROM sec_company WHERE cik = 999999"
        ).fetchone()
        assert row[0] is None
    finally:
        db.close()


def test_already_resolved_row_is_never_reselected_or_overwritten(tmp_path, db_session) -> None:
    """A row with mdm_entity_id already set must not be touched by the
    sweep, even if a *different*, newer MdmSourceRef exists for the same
    business key (e.g. after a merge/re-resolution upstream) -- the sweep's
    job is to fill NULLs, not to reconcile already-backfilled values."""
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        stale_entity_id = "already-set-entity-id"
        db._conn.execute(
            "INSERT INTO sec_company (cik, entity_name, mdm_entity_id) VALUES (320193, 'Apple Inc', ?)",
            [stale_entity_id],
        )
        # A newer/different resolved entity for the same CIK exists in MDM --
        # the sweep must not pick it up, since the row isn't NULL.
        _register(db_session, entity_type="company", source_system="edgar_cik", source_id="320193")
        db_session.commit()

        counts = backfill_shard_mdm_entity_ids(db, db_session)
        assert counts["sec_company"] == 0
        row = db._conn.execute(
            "SELECT mdm_entity_id FROM sec_company WHERE cik = 320193"
        ).fetchone()
        assert row[0] == stale_entity_id
    finally:
        db.close()


def test_entity_type_disambiguates_shared_source_system(tmp_path, db_session) -> None:
    """person and security both register under source_system='ownership_filing'
    with overlapping-shaped source_ids -- confirm the entity_type filter
    keeps a security's source ref from backfilling a person row (or vice
    versa) even if their source_id strings happened to collide."""
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        collision_id = "0001-25-000001:1"
        security_entity = _register(
            db_session, entity_type="security", source_system="ownership_filing", source_id=collision_id
        )
        db_session.commit()

        db._conn.execute(
            "INSERT INTO sec_ownership_reporting_owner (accession_number, owner_index, owner_name) "
            "VALUES ('0001-25-000001', 1, 'Jane Doe')"
        )
        counts = backfill_shard_mdm_entity_ids(db, db_session)
        assert counts["sec_ownership_reporting_owner"] == 0
        row = db._conn.execute(
            "SELECT mdm_entity_id FROM sec_ownership_reporting_owner "
            "WHERE accession_number = '0001-25-000001' AND owner_index = 1"
        ).fetchone()
        assert row[0] is None
    finally:
        db.close()


def _local_context(tmp_path) -> WarehouseCommandContext:
    return WarehouseCommandContext(
        bronze_root=StorageLocation(str(tmp_path / "bronze")),
        storage_root=StorageLocation(str(tmp_path / "warehouse")),
        silver_root=StorageLocation(str(tmp_path / "silver")),
        snowflake_export_root=None,
        environment_name="test",
        identity="EdgarTools Platform test@example.com",
        runtime_mode="bronze_capture",
    )


def test_sweep_local_monolith_path_end_to_end(tmp_path) -> None:
    mdm_db_path = tmp_path / "mdm.sqlite"
    engine = create_engine(f"sqlite:///{mdm_db_path}")
    Base.metadata.create_all(engine)
    with Session(engine) as seed_session:
        company_entity = _register(seed_session, entity_type="company", source_system="edgar_cik", source_id="320193")
        seed_session.commit()
    engine.dispose()

    silver_root = StorageLocation(str(tmp_path / "silver"))
    silver_path = silver_root.join("silver", "sec", "silver.duckdb")
    os.makedirs(os.path.dirname(silver_path), exist_ok=True)
    db = SilverDatabase(silver_path)
    db._conn.execute("INSERT INTO sec_company (cik, entity_name) VALUES (320193, 'Apple Inc')")
    db.close()

    context = _local_context(tmp_path)
    with patch.dict(os.environ, {"MDM_DATABASE_URL": f"sqlite:///{mdm_db_path}"}):
        result = run_mdm_entity_backfill_sweep(context, "test-run")

    assert result["totals"]["sec_company"] == 1

    verify_db = duckdb.connect(silver_path)
    try:
        row = verify_db.execute(
            "SELECT mdm_entity_id FROM sec_company WHERE cik = 320193"
        ).fetchone()
    finally:
        verify_db.close()
    assert row[0] == company_entity


def test_sweep_shard_path_publishes_changed_shards_and_survives_one_conflict(tmp_path) -> None:
    """Remote/sharded path: two shards, one gets a real update and publishes,
    one hits PromotionConflictError on publish -- the sweep must record the
    conflict, skip publishing that shard, and still complete (not abort)."""
    from unittest.mock import MagicMock, patch

    from edgar_warehouse.infrastructure.object_storage import PromotionConflictError

    mdm_db_path = tmp_path / "mdm.sqlite"
    engine = create_engine(f"sqlite:///{mdm_db_path}")
    Base.metadata.create_all(engine)
    with Session(engine) as seed_session:
        entity_0 = _register(seed_session, entity_type="company", source_system="edgar_cik", source_id="1")
        entity_1 = _register(seed_session, entity_type="company", source_system="edgar_cik", source_id="2")
        seed_session.commit()
    engine.dispose()

    shard_0_path = str(tmp_path / "shard-0.duckdb")
    shard_1_path = str(tmp_path / "shard-1.duckdb")
    db0 = SilverDatabase(shard_0_path)
    db0._conn.execute("INSERT INTO sec_company (cik, entity_name) VALUES (1, 'Co One')")
    db0.close()
    db1 = SilverDatabase(shard_1_path)
    db1._conn.execute("INSERT INTO sec_company (cik, entity_name) VALUES (2, 'Co Two')")
    db1.close()

    context = MagicMock()
    context.storage_root.is_remote = True

    def fake_publish(ctx, shard_index):
        if shard_index == 1:
            raise PromotionConflictError(
                expected_etag="etag-old",
                actual_etag="etag-new",
                staged_relative_path="silver/sec/shards/staging/shard-1.duckdb",
                canonical_relative_path="silver/sec/shards/shard-1.duckdb",
            )
        return {"layer": "silver_shard", "shard_index": shard_index}

    with patch.dict(os.environ, {"MDM_DATABASE_URL": f"sqlite:///{mdm_db_path}"}), \
         patch(
             "edgar_warehouse.application.warehouse_orchestrator._read_shard_manifest",
             return_value={"shard_count": 2},
         ), \
         patch(
             "edgar_warehouse.application.warehouse_orchestrator._hydrate_all_shards",
             return_value=[shard_0_path, shard_1_path],
         ), \
         patch(
             "edgar_warehouse.application.warehouse_orchestrator._publish_shard_if_remote",
             side_effect=fake_publish,
         ):
        result = run_mdm_entity_backfill_sweep(context, "test-run")

    assert result["totals"]["sec_company"] == 2
    assert result["conflicts"] == [1]
    shard_results = {s["shard_index"]: s for s in result["shards"]}
    assert shard_results[0]["published"] is True
    assert shard_results[1]["published"] is False

    verify0 = duckdb.connect(shard_0_path)
    try:
        row0 = verify0.execute("SELECT mdm_entity_id FROM sec_company WHERE cik = 1").fetchone()
    finally:
        verify0.close()
    assert row0[0] == entity_0

    # Shard 1's local UPDATE still happened even though publish was skipped
    # -- the next sweep will re-hydrate remote (unchanged) and redo it.
    verify1 = duckdb.connect(shard_1_path)
    try:
        row1 = verify1.execute("SELECT mdm_entity_id FROM sec_company WHERE cik = 2").fetchone()
    finally:
        verify1.close()
    assert row1[0] == entity_1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
