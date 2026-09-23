"""Defects Codex found reviewing PR #695, kept as the record of their repair.

Codex wrote these asserting the errors that occurred then, so that a passing
test meant a confirmed defect. Each is now stated as the behaviour that must
hold, except where the operator accepted the limit rather than repairing it,
which is said so explicitly.

Review: `.scratch/handover/2026-09-23-codex-company-mastering-review.md`.
"""

from uuid import uuid4

import pytest
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.mdm.clean.bookkeeping import RunCoordinator
from edgar_warehouse.mdm.clean.cli import execute_manifest
from edgar_warehouse.mdm.clean.evidence import deferred_record
from edgar_warehouse.mdm.clean.gleif_source import dataset_contract
from edgar_warehouse.mdm.clean.source_publications import PublicationVerifier
from edgar_warehouse.mdm.clean.store import Store, register_dataset
from tests.integration import test_clean_mdm_postgres as core
from tests.integration import test_clean_native_publications as native

postgres = core.postgres
database = core.database
command_databases = core.command_databases
acquisition_login = native.acquisition_login
source_db = native.source_db


def test_a_partial_native_run_resumes_after_a_mapping_is_registered(
    database, source_db, command_databases, tmp_path
):
    """A run resumes under the readings it started with.

    Reading the newest mapping on every invocation put its digest into the
    reconstructed run scope, so registering a corrected mapping mid-run made
    the run unresumable with "Root run scope changed". The run now pins its
    readings and resolves those.
    """
    capture, path = native.native_fixture(database, source_db, tmp_path)
    store = Store(database.application)
    coordinator = RunCoordinator(command_databases[0], store)
    args = {
        "path": str(path),
        "run_id": str(uuid4()),
        "stage": "mastering",
        "limit": 1,
        "publication_verifier": PublicationVerifier(source_db, capture.reader),
    }
    first = execute_manifest(store, coordinator, **args)
    assert not first["source_consumption_complete"]
    # Every source the run reads is pinned, each at the reading it started on.
    pinned = coordinator.pinned_readings(args["run_id"])
    assert pinned["gleif.level1.v1"] == 1
    assert set(pinned.values()) == {1}
    with database.admin.begin() as conn:
        register_dataset(
            conn,
            "gleif.level1.v1",
            database.registry,
            {
                **dataset_contract("level1"),
                "family": "fixture",
                "semantics": "snapshot",
            },
        )
    resumed = execute_manifest(store, coordinator, **args)
    assert resumed["observed_batches"] >= first["observed_batches"]
    # The run still reads what it began with, not the mapping registered since.
    assert coordinator.pinned_readings(args["run_id"]) == pinned


def test_a_deferred_reread_that_changes_its_body_still_collides(database):
    """An accepted limit, not a defect awaiting repair.

    Migration 032 lets a deferred record's schema match any registered
    reading, which fixed the disagreement between an assertion and a deferred
    record from one read. It does not give a deferred record a reading of its
    own: its natural key is (source_code, publication_key, record_locator),
    which a re-read reuses, so a record that defers *differently* under a
    corrected mapping still fails its batch.

    Repairing it needs a mapping-qualified deferred identity and a widened
    uniqueness rule in migration 027. The operator accepted the limit on
    2026-09-23 rather than pay for that now. A re-read that defers identically
    is unaffected and is covered in the main integration suite.
    """
    args = {
        "source_code": "fixture.primary",
        "publication_key": "p1",
        "record_locator": "line:9",
        "reason": "invalid_field_shape",
        "raw_record": {"key": "same"},
        "provenance": {"adapter_version": "v1"},
    }
    core.apply(database, 1, deferred=[deferred_record(schema_version="1", **args)])
    core.register_reading(
        database, "fixture.primary", core.contract_body(schema_version="2")
    )
    with pytest.raises(DBAPIError, match="Deferred source publication collision"):
        core.apply(database, 2, deferred=[deferred_record(schema_version="2", **args)])
