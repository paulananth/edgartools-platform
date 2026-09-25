"""Real PG16: native evidence authenticates bounded consumption before writes."""

import hashlib
import io
import json
from uuid import uuid4

import pytest
from sqlalchemy import text

from edgar_warehouse.mdm.clean.bookkeeping import RunCoordinator
from edgar_warehouse.mdm.clean.cli import execute_manifest
from edgar_warehouse.mdm.clean.gleif_source import (
    VERSION,
    dataset_contract,
    inspect_archive,
    record_evidence,
    release_sequence,
)
from edgar_warehouse.mdm.clean.source_publications import HASHES, PublicationVerifier
from edgar_warehouse.mdm.clean.store import Conflict, Store, canonical, register_dataset
from tests.integration import test_clean_mdm_postgres as core
from tests.integration import test_clean_source_publications as sources
from tests.mdm.test_clean_gleif_source import archive_bytes, metadata

postgres = core.postgres
database = core.database
command_databases = core.command_databases
acquisition_login = sources.acquisition_login
source_db = sources.source_db
APPLE = "HWUPKR0MPOU8FGXBT394"


def native_fixture(
    database,
    source_db,
    root,
    *,
    level1=None,
    bind=False,
    publication="2026-09-11T16:00:00Z",
    previous=None,
    additional_level1=None,
    policy=None,
    company_leis=None,
):
    capture = sources.Capture(source_db, root)
    codes = {
        m: f"gleif.{m}.v1" for m in ("level1", "relationships", "reporting_exceptions")
    }
    lei = level1["LEI"]["$"] if level1 else APPLE
    aggregate = {
        **dataset_contract("level1"),
        "family": "fixture",
        "native_contract": {
            "version": VERSION,
            "record_sources": codes,
            "company_leis": company_leis or [lei],
        },
        "publication_contract": {
            "version": 1,
            "format": "clean-mdm-publication-v1",
            "continuity": "sequence-predecessor-sha256-v1",
            "publication_family": "golden_copy",
            "required_members": list(codes),
            "replacement_scope": "native-test",
            "revision_versions": {
                "contract_version": VERSION,
                "parser_version": VERSION,
                "schema_version": "1",
                "configuration_version": VERSION,
            },
        },
    }
    with database.admin.begin() as conn:
        register_dataset(conn, "gleif.publication.v1", database.registry, aggregate)
        for member, code in codes.items():
            register_dataset(
                conn,
                code,
                database.registry,
                {
                    **dataset_contract(member, level1_source=codes["level1"]),
                    "family": "fixture",
                },
            )
    manifest = {
        "version": 1,
        "source_family": "fixture",
        "publication_family": "golden_copy",
        "publication": publication,
        "publication_time": publication,
        "sequence": release_sequence(publication),
        "mode": "delta" if previous else "full",
        "coverage": "PARTIAL" if previous else "COMPLETE",
        "replacement_scope": "native-test",
        "predecessor": {
            "sequence": previous["sequence"],
            "manifest_sha256": previous["manifest_sha256"],
        }
        if previous
        else None,
        "members": [],
    }
    rows = {
        "level1": [
            {
                "LEI": {"$": APPLE},
                "Entity": {
                    "EntityCategory": {"$": "GENERAL"},
                    "LegalJurisdiction": {"$": "US-CA"},
                },
                "Registration": {"LastUpdateDate": {"$": "2026-09-10T00:00:00Z"}},
            }
        ],
        "relationships": [],
        "reporting_exceptions": [],
    }
    if level1:
        rows["level1"] = [level1]
    rows["level1"].extend(additional_level1 or [])
    wrappers = {
        "level1": ("records", "LEI_3.1"),
        "relationships": ("relations", "RR_2.1"),
        "reporting_exceptions": ("exceptions", "REPEX_2.1"),
    }
    for member, (wrapper, cdf) in wrappers.items():
        raw = archive_bytes(canonical({wrapper: rows[member]}).encode())
        meta = metadata(
            len(rows[member]),
            cdf_version=cdf,
            content_date=publication,
            file_content="GLEIF_DELTA_PUBLISHED"
            if previous
            else "GLEIF_FULL_PUBLISHED",
            delta_start=previous["publication_time"] if previous else None,
        )
        report = inspect_archive(
            io.BytesIO(raw),
            member=member,
            metadata=meta,
            expected_sha256=hashlib.sha256(raw).hexdigest(),
        )
        revision = capture.add(
            f"native/{member}",
            raw,
            manifest=manifest,
            versions=aggregate["publication_contract"]["revision_versions"],
            canonical_source_hash=report["canonical_source_hash"],
            domain_content_hash=report["domain_content_hash"],
        )
        manifest["members"].append(
            {
                "member": member,
                "logical_source_key": f"native/{member}",
                "bytes": len(raw),
                "native": meta,
                **{k: getattr(revision, k) for k in HASHES},
            }
        )
    revision = capture.add(
        "native/manifest",
        canonical(manifest).encode(),
        manifest=manifest,
        versions=aggregate["publication_contract"]["revision_versions"],
    )
    run = {
        "contract_version": 2,
        "policy_digest": policy or database.policy,
        "as_of": "2026-09-20T00:00:00Z",
        "native_source": {
            "source_code": "gleif.publication.v1",
            "publications": [str(revision.revision_id)],
            "target_sequence": manifest["sequence"],
        },
        "batches": [
            {
                "batch_id": f"native-{member}",
                "stage": "mastering",
                "consumer": "company",
                "expected_checkpoint": i,
                "checkpoint": i + 1,
                "native_input": {
                    "publication": manifest["publication"],
                    "member": member,
                    "offset": 0,
                    "count": len(rows[member]),
                },
            }
            for i, member in enumerate(codes)
        ],
    }
    path = root / "input.json"
    if bind:
        _, assertion = record_evidence(
            rows["level1"][0],
            member="level1",
            contract=dataset_contract("level1"),
            source_code=codes["level1"],
            eligible_leis={lei},
            ordinal=0,
            publication={
                "publication_key": manifest["publication"],
                "revision": manifest["sequence"],
                "artifact_sha256": manifest["members"][0]["raw_evidence_hash"],
                "member": "level1",
            },
        )
        entity, binding = core.identity_and_binding(assertion)
        run["batches"][0].update(identities=[entity], decisions=[binding])
    path.write_text(json.dumps(run))
    return capture, path


def test_native_publication_consumption_is_distinct_from_delivery_and_publication(
    database, source_db, command_databases, tmp_path
):
    capture, path = native_fixture(database, source_db, tmp_path)
    store = Store(database.application)
    coordinator = RunCoordinator(command_databases[0], store)
    verifier = PublicationVerifier(source_db, capture.reader)
    run_id = str(uuid4())
    first = execute_manifest(
        store,
        coordinator,
        path=str(path),
        run_id=run_id,
        stage="mastering",
        limit=1,
        publication_verifier=verifier,
    )
    assert first["source_delivery_verified"] is True
    assert first["source_consumption_complete"] is False
    assert first["end_to_end_complete"] is False
    with pytest.raises(Conflict, match="not fully consumed"):
        coordinator.completed_source(run_id)
    for _ in range(2):
        result = execute_manifest(
            store,
            coordinator,
            path=str(path),
            run_id=run_id,
            stage="mastering",
            limit=1,
            publication_verifier=verifier,
        )
    assert result["source_consumption_complete"] is True
    assert result["pending_publications"] > 0
    assert result["end_to_end_complete"] is False
    replay = execute_manifest(
        store,
        coordinator,
        path=str(path),
        run_id=run_id,
        stage="mastering",
        limit=1,
        publication_verifier=verifier,
    )
    assert replay["commits"] == []
    assert replay["source_consumption_complete"] is True
    assert coordinator.completed_source(run_id)["consumer"] == "company"


@pytest.mark.parametrize(
    "damage",
    ["missing_range", "overlap", "inline", "missing_bytes", "bad_interpretation"],
)
def test_native_preflight_failure_commits_no_work(
    database, source_db, command_databases, tmp_path, damage
):
    capture, path = native_fixture(database, source_db, tmp_path)
    manifest = json.loads(path.read_text())
    if damage == "missing_range":
        manifest["batches"].pop()
    elif damage == "overlap":
        manifest["batches"].append({**manifest["batches"][0], "batch_id": "overlap"})
    elif damage == "inline":
        manifest["batches"][0]["assertions"] = []
    elif damage == "missing_bytes":
        (tmp_path / capture.saved[-2][2].bronze_artifact_reference).unlink()
    else:
        # A replacement capture under the same native publication conflicts with
        # its immutable inventory, even when the physical bytes are unchanged.
        _, args, revision = capture.saved[0]
        raw = (tmp_path / revision.bronze_artifact_reference).read_bytes()
        capture.add(
            revision.logical_source_key,
            raw,
            manifest={
                "source_family": "fixture",
                "publication": "2026-09-11T16:00:00Z",
                "coverage": "COMPLETE",
                "replacement_scope": "native-test",
            },
            versions={
                k: args[k]
                for k in (
                    "contract_version",
                    "parser_version",
                    "schema_version",
                    "configuration_version",
                )
            },
            canonical_source_hash="0" * 64,
        )
    path.write_text(json.dumps(manifest))
    store = Store(database.application)
    coordinator = RunCoordinator(command_databases[0], store)
    with pytest.raises((Conflict, FileNotFoundError)):
        execute_manifest(
            store,
            coordinator,
            path=str(path),
            run_id=str(uuid4()),
            stage="mastering",
            limit=1,
            publication_verifier=PublicationVerifier(source_db, capture.reader),
        )
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm_v2.batch")) == 0
    with command_databases[0].connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM pipeline_run")) == 0


def test_native_run_cannot_change_its_frozen_manifest(
    database, source_db, command_databases, tmp_path
):
    capture, path = native_fixture(database, source_db, tmp_path)
    store = Store(database.application)
    coordinator = RunCoordinator(command_databases[0], store)
    args = {
        "path": str(path),
        "run_id": str(uuid4()),
        "stage": "mastering",
        "limit": 1,
        "publication_verifier": PublicationVerifier(source_db, capture.reader),
    }
    execute_manifest(store, coordinator, **args)
    manifest = json.loads(path.read_text())
    manifest["as_of"] = "2026-09-21T00:00:00Z"
    path.write_text(json.dumps(manifest))
    with pytest.raises(Conflict, match="scope changed"):
        execute_manifest(store, coordinator, **args)


def test_native_commits_recover_export_ack_loss_without_false_completion(
    database, source_db, command_databases, tmp_path
):
    from edgar_warehouse.mdm.clean.publication import LocalContractSink

    capture, path = native_fixture(database, source_db, tmp_path, bind=True)
    store = Store(database.application)
    coordinator = RunCoordinator(command_databases[0], store)
    run_id = str(uuid4())
    execute_manifest(
        store,
        coordinator,
        path=str(path),
        run_id=run_id,
        stage="mastering",
        limit=3,
        publication_verifier=PublicationVerifier(source_db, capture.reader),
    )
    sink = LocalContractSink(tmp_path / "published")

    class LostAcknowledgement:
        def publish(self, *args):
            sink.publish(*args)
            raise OSError("ack lost after writing export")

        def verify(self, *args):
            return sink.verify(*args)

    with pytest.raises(OSError, match="ack lost"):
        store.deliver_one("export", "failure", LostAcknowledgement(), lease_seconds=1)
    assert coordinator.reconcile(run_id)["end_to_end_complete"] is False
    import time

    time.sleep(1.1)
    for consumer in ("export", "graph"):
        while store.deliver_one(consumer, "retry", sink):
            pass
    assert coordinator.reconcile(run_id)["end_to_end_complete"] is True


def test_real_sec_and_gleif_fields_share_company_with_retained_provenance(
    database, source_db, command_databases, tmp_path
):
    from pathlib import Path

    from edgar_warehouse.mdm.clean.adapters import normalize
    from edgar_warehouse.mdm.clean.company_source import CONTRACT, SOURCE_CODE
    from edgar_warehouse.mdm.clean.store import register_policy

    fixture = json.loads(
        (
            Path(__file__).parents[1] / "fixtures/clean_mdm/native_company_v1.json"
        ).read_text()
    )
    capture, path = native_fixture(
        database, source_db, tmp_path, level1=fixture["gleif"], bind=True
    )
    run = json.loads(path.read_text())
    entity = run["batches"][0]["identities"][0]
    with database.admin.begin() as conn:
        register_dataset(
            conn, SOURCE_CODE, database.registry, {**CONTRACT, "family": "fixture"}
        )
        policy = register_policy(
            conn,
            {
                "version": "native-provenance-test-v1",
                "automatic_rules": [],
                "required_consumers": ["export", "graph"],
                "fields": {
                    "company": {
                        "name": {
                            "sources": [SOURCE_CODE],
                            "allow_unknown_effective": True,
                        },
                        "gleif_registration_status": {"sources": ["gleif.level1.v1"]},
                        "jurisdiction": {"sources": ["gleif.level1.v1"]},
                    }
                },
            },
        )
    sec = fixture["sec"]
    adapter = {
        **{k: v for k, v in CONTRACT["adapter"].items() if k != "classification"},
        "kind": "company",
    }
    assertion = normalize(
        {
            "cik": sec["cik"],
            "entity_type": sec["sec_entity_type"],
            "entity_name": sec["sec_entity_name"],
        },
        source_code=SOURCE_CODE,
        # This test proves field provenance, not classification: the kind is
        # stated here, as SEC `operating` decides it. The classification rule
        # is proven in test_clean_four_companies.
        contract={**CONTRACT, "adapter": adapter},
        publication={
            "publication_key": "retained-sec-cohort",
            "revision": 1,
            "effective_at": None,
            "artifact_sha256": fixture["sources"]["01-company-cohort-1000.jsonl"],
            "member": "cohort",
        },
    )
    _, binding = core.identity_and_binding(assertion, entity["entity_id"])
    core.MergeStage(Store(database.application)).apply(
        batch_id="sec-retained",
        run_id=str(uuid4()),
        policy_digest=policy,
        consumer="sec-company-test",
        expected_checkpoint=0,
        checkpoint=1,
        as_of=core.AS_OF,
        assertions=[assertion],
        identities=[entity],
        decisions=[binding],
    )
    run["policy_digest"] = policy
    run["batches"][0]["identities"] = []
    path.write_text(json.dumps(run))
    store = Store(database.application)
    coordinator = RunCoordinator(command_databases[0], store)
    full_run = str(uuid4())
    result = execute_manifest(
        store,
        coordinator,
        path=str(path),
        run_id=full_run,
        stage="mastering",
        limit=3,
        publication_verifier=PublicationVerifier(source_db, capture.reader),
    )
    assert result["source_consumption_complete"] is True
    entities = core.documents(database, "entity")
    assert len(entities) == 1
    fields = entities[entity["entity_id"]]["fields"]
    assert fields["name"]["value"] == "WEYERHAEUSER CO"
    assert fields["name"]["winner"]["source_code"] == SOURCE_CODE
    assert fields["gleif_registration_status"]["value"] == "LAPSED"
    assert fields["jurisdiction"]["winner"]["source_code"] == "gleif.level1.v1"
    # A later source lifecycle correction updates its own fields. It cannot
    # delete the SEC Company or silently activate an identity merge/unlink rule.
    prior = coordinator.completed_source(full_run)["plan"]["publications"][-1][
        "evidence"
    ]
    corrected = json.loads(json.dumps(fixture["gleif"]))
    corrected["Registration"]["RegistrationStatus"]["$"] = "RETIRED"
    corrected["Registration"]["LastUpdateDate"]["$"] = "2026-09-12T16:00:00Z"
    native_fixture(
        database,
        source_db,
        tmp_path,
        level1=corrected,
        publication="2026-09-12T16:00:00Z",
        previous=prior,
    )
    delta = json.loads(path.read_text())
    delta["policy_digest"] = policy
    delta["native_source"]["previous_run_id"] = full_run
    for batch in delta["batches"]:
        batch["batch_id"] = "correction-" + batch["batch_id"]
        batch["expected_checkpoint"] += 3
        batch["checkpoint"] += 3
    path.write_text(json.dumps(delta))
    execute_manifest(
        store,
        coordinator,
        path=str(path),
        run_id=str(uuid4()),
        stage="mastering",
        limit=3,
        publication_verifier=PublicationVerifier(source_db, capture.reader),
    )
    entities = core.documents(database, "entity")
    assert set(entities) == {entity["entity_id"]}
    assert (
        entities[entity["entity_id"]]["fields"]["gleif_registration_status"]["value"]
        == "RETIRED"
    )
    assert entities[entity["entity_id"]]["fields"]["name"]["value"] == "WEYERHAEUSER CO"


def test_delta_requires_fully_consumed_predecessor_and_replays_correction(
    database, source_db, command_databases, tmp_path
):
    capture, path = native_fixture(database, source_db, tmp_path)
    full_path = tmp_path / "full.json"
    full_path.write_bytes(path.read_bytes())
    store = Store(database.application)
    coordinator = RunCoordinator(command_databases[0], store)
    verifier = PublicationVerifier(source_db, capture.reader)
    full_run = str(uuid4())
    full = json.loads(path.read_text())
    proof = verifier.verify(
        store,
        source_code="gleif.publication.v1",
        manifest_revision_id=full["native_source"]["publications"][0],
    )
    execute_manifest(
        store,
        coordinator,
        path=str(full_path),
        run_id=full_run,
        stage="mastering",
        limit=1,
        publication_verifier=verifier,
    )
    native_fixture(
        database,
        source_db,
        tmp_path,
        publication="2026-09-12T16:00:00Z",
        previous=proof.evidence,
    )
    delta = json.loads(path.read_text())
    delta["native_source"]["previous_run_id"] = full_run
    for b in delta["batches"]:
        b["batch_id"] = "delta-" + b["batch_id"]
        b["expected_checkpoint"] += 3
        b["checkpoint"] += 3
    path.write_text(json.dumps(delta))
    run_id = str(uuid4())
    with pytest.raises(Conflict, match="not fully consumed"):
        execute_manifest(
            store,
            coordinator,
            path=str(path),
            run_id=run_id,
            stage="mastering",
            limit=3,
            publication_verifier=verifier,
        )
    execute_manifest(
        store,
        coordinator,
        path=str(full_path),
        run_id=full_run,
        stage="mastering",
        limit=3,
        publication_verifier=verifier,
    )
    result = execute_manifest(
        store,
        coordinator,
        path=str(path),
        run_id=run_id,
        stage="mastering",
        limit=3,
        publication_verifier=verifier,
    )
    assert result["source_consumption_complete"] is True
    assert coordinator.completed_source(run_id)["plan"]["recovery_mode"] == "delta"
    replay = execute_manifest(
        store,
        coordinator,
        path=str(path),
        run_id=run_id,
        stage="mastering",
        limit=3,
        publication_verifier=verifier,
    )
    assert replay["commits"] == []


@pytest.mark.parametrize(
    "lei,complete", [("INR2EJN1ERAN0W5ZP974", True), ("bad-lei", False)]
)
def test_excluded_evidence_is_retained_without_blocking_but_malformed_records_block(
    database, source_db, command_databases, tmp_path, lei, complete
):
    from edgar_warehouse.mdm.clean.publication import LocalContractSink

    capture, path = native_fixture(
        database,
        source_db,
        tmp_path,
        bind=True,
        additional_level1=[
            {"LEI": {"$": lei}, "Entity": {"EntityCategory": {"$": "GENERAL"}}}
        ],
    )
    store = Store(database.application)
    coordinator = RunCoordinator(command_databases[0], store)
    run_id = str(uuid4())
    result = execute_manifest(
        store,
        coordinator,
        path=str(path),
        run_id=run_id,
        stage="mastering",
        limit=4,
        publication_verifier=PublicationVerifier(source_db, capture.reader),
    )
    assert result["source_consumption_complete"] is True
    sink = LocalContractSink(tmp_path / "published")
    for consumer in ("export", "graph"):
        while store.deliver_one(consumer, "test", sink):
            pass
    assert coordinator.reconcile(run_id)["end_to_end_complete"] is complete
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm_v2.deferred_record")) == 1
        assert (
            conn.scalar(
                text(
                    "SELECT body->'raw_record'->'LEI'->>'$' FROM mdm_v2.deferred_record"
                )
            )
            == lei
        )
