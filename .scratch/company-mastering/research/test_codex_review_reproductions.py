"""Review evidence: passing tests confirm current defects, not acceptance."""

from uuid import uuid4

import pytest
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.mdm.clean.bookkeeping import RunCoordinator
from edgar_warehouse.mdm.clean.cli import execute_manifest
from edgar_warehouse.mdm.clean.evidence import deferred_record
from edgar_warehouse.mdm.clean.gleif_source import dataset_contract
from edgar_warehouse.mdm.clean.source_publications import PublicationVerifier
from edgar_warehouse.mdm.clean.store import Conflict, Store, register_dataset
from tests.integration import test_clean_mdm_postgres as core
from tests.integration import test_clean_native_publications as native

postgres = core.postgres
database = core.database
command_databases = core.command_databases
acquisition_login = native.acquisition_login
source_db = native.source_db


def test_partial_native_run_cannot_resume_after_mapping_registration(
    database, source_db, command_databases, tmp_path
):
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
    with pytest.raises(Conflict, match="Root run scope changed"):
        execute_manifest(store, coordinator, **args)


def test_deferred_reread_with_changed_schema_collides(database):
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
