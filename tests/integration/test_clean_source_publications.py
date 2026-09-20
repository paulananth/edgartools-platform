"""Source-only acceptance with real capture APIs, restricted roles and PG16."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.acquisition.ledger import (
    AcquisitionLedger,
    DecisionCause,
    FetchDecisionRequest,
    FetchDisposition,
    FetchWorkState,
)
from edgar_warehouse.acquisition.revisions import CompletenessType, SourceRevisionLedger
from edgar_warehouse.mdm.clean.adapters import normalize
from edgar_warehouse.mdm.clean.source_publications import (
    PublicationVerifier,
    plan_continuity,
)
from edgar_warehouse.mdm.clean.store import (
    Conflict,
    Store,
    canonical,
    digest,
    register_dataset,
)
from edgar_warehouse.mdm.migrations import runtime as migrations
from tests.integration import test_clean_mdm_postgres as clean_fixtures

database = clean_fixtures.database
postgres = clean_fixtures.postgres

FIXTURE = Path(__file__).parents[1] / "fixtures/clean_mdm/publication_v1"


@pytest.fixture(scope="module")
def acquisition_login(postgres):
    admin, _ = postgres
    with admin.begin() as conn:
        conn.execute(
            text(
                "CREATE ROLE application LOGIN PASSWORD 'test' NOSUPERUSER NOCREATEDB NOCREATEROLE"
            )
        )
    return admin


@pytest.fixture
def source_db(acquisition_login):
    admin = acquisition_login
    name = f"publication_{uuid4().hex}"
    with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
    owner = create_engine(admin.url.set(database=name))
    migrations._apply_acquisition_ledger_migration(owner)
    migrations._apply_exclusion_and_evidence_import_migration(owner)
    migrations._apply_source_fetch_validators_migration(owner)
    runtime = create_engine(admin.url.set(database=name, username="application"))
    try:
        yield runtime
    finally:
        runtime.dispose()
        owner.dispose()
        with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.exec_driver_sql(f'DROP DATABASE "{name}"')


class Capture:
    def __init__(self, engine, root):
        self.engine = engine
        self.root = root
        self.ledger = AcquisitionLedger(engine)
        self.revisions = SourceRevisionLedger(engine)
        self.decisions = {}
        self.saved = []

    def add(self, key, raw, *, manifest, capture=True, versions=None, **overrides):
        sha = hashlib.sha256(raw).hexdigest()
        file = self.root / sha
        file.write_bytes(raw)
        decision = self.ledger.create_fetch_decision(
            FetchDecisionRequest(
                candidate_id=str(uuid4()),
                source_family=manifest["source_family"],
                logical_source_key=key,
                source_url=f"https://fixture.invalid/{sha}",
                cause=DecisionCause.CAPTURED_DISCOVERY,
                cause_reference="offline-fixture-v1",
                disposition=FetchDisposition.FETCH_AUTHORIZED,
                blocker=None,
                next_action="ACQUIRE_FETCH_LEASE",
            )
        )
        if capture:
            lease = self.ledger.claim_fetch(
                decision.decision_id, worker_id="fixture", lease_seconds=60
            )
            self.ledger.finalize_fetch(
                decision.decision_id,
                worker_id="fixture",
                fencing_token=lease.fencing_token,
                final_state=FetchWorkState.CAPTURED,
                artifact_reference=sha,
            )
        args = {
            "raw_evidence_hash": sha,
            "canonical_source_hash": sha,
            "domain_content_hash": sha,
            "contract_version": "fixture-v1",
            "parser_version": "fixture-v1",
            "schema_version": "1",
            "configuration_version": "fixture-v1",
            "completeness_type": CompletenessType(manifest["coverage"]),
            "declared_replacement_scope": manifest["replacement_scope"],
            "source_native_revision": manifest["publication"],
        }
        args.update(versions or {})
        args.update(overrides)
        if capture:
            revision = self.revisions.materialize_from_capture(
                decision.decision_id, **args
            )
            self.saved.append((decision.decision_id, args, revision))
            return revision
        return decision

    def reader(self, reference):
        path = (self.root / reference).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Artifact outside fixture root")
        return path.open("rb")


@pytest.fixture
def source_fixture(database, source_db, tmp_path):
    dataset = json.loads((FIXTURE / "dataset.json").read_bytes())
    with database.admin.begin() as conn:
        register_dataset(conn, "fixture.publication", database.registry, dataset)
    return Capture(source_db, tmp_path), Store(database.application), dataset


def load_fixture(capture, *, edit=None, omit=None, reverse=False, member_edit=None):
    manifest = json.loads((FIXTURE / "manifest.json").read_bytes())
    if edit:
        edit(manifest)
    members = json.loads((FIXTURE / "manifest.json").read_bytes())["members"]
    if reverse:
        members.reverse()
    for member in members:
        if member["member"] != omit:
            capture.add(
                member["logical_source_key"],
                (FIXTURE / f"{member['member']}.jsonl").read_bytes(),
                manifest=manifest,
                **(member_edit or {}),
            )
    revision = capture.add(
        "fixture/manifest",
        (canonical(manifest) + "\n").encode()
        if edit
        else (FIXTURE / "manifest.json").read_bytes(),
        manifest=manifest,
    )
    return manifest, revision


def verify(capture, store, revision):
    return PublicationVerifier(capture.engine, capture.reader).verify(
        store,
        source_code="fixture.publication",
        manifest_revision_id=revision.revision_id,
    )


def test_source_only_repeat_reorder_and_normalized_evidence(source_fixture, database):
    capture, store, dataset = source_fixture
    manifest, revision = load_fixture(capture, reverse=True)
    first = verify(capture, store, revision)
    # Lost acknowledgement: replay the real revision API, in opposite order.
    for decision, args, saved in reversed(capture.saved):
        assert capture.revisions.materialize_from_capture(decision, **args) == saved
    second = verify(capture, store, revision)
    assert first == second
    assert first.proof_digest == second.proof_digest
    expected = json.loads((FIXTURE / "expected.json").read_bytes())
    assert first.evidence["inventory_digest"] == expected["inventory_digest"]
    assert [m["member"] for m in first.evidence["members"]] == sorted(
        dataset["publication_contract"]["required_members"]
    )
    rows = [
        json.loads(line)
        for line in (FIXTURE / "level1.jsonl").read_bytes().splitlines()
    ]

    def normalized(records):
        return sorted(
            [
                normalize(
                    row,
                    source_code="fixture.publication",
                    contract=dataset,
                    publication={
                        "publication_key": manifest["publication"],
                        "revision": 1,
                        "effective_at": "2026-09-20T00:00:00+00:00",
                        "artifact_sha256": manifest["members"][0]["raw_evidence_hash"],
                        "member": "level1",
                    },
                )
                for row in records
            ],
            key=lambda a: a["assertion_id"],
        )

    assert digest(normalized(rows)) == digest(normalized(list(reversed(rows))))
    assert normalized(rows) == expected["normalized_assertions"]
    assert digest(normalized(rows)) == expected["normalized_assertions_digest"]
    proof = plan_continuity([second, first], target_sequence=1)
    assert proof["recovery_mode"] == "full_reconciliation"
    assert not proof["consumption_complete"] and not proof["downstream_complete"]
    with database.application.connect() as conn:
        for table in (
            "identity",
            "assertion",
            "projection",
            "batch",
            "checkpoint",
            "publication",
        ):
            assert conn.scalar(text(f"SELECT count(*) FROM mdm_v2.{table}")) == 0
    with capture.engine.begin() as conn:
        conn.execute(text("SET LOCAL ROLE edgartools_acquisition_processor"))
        assert conn.scalar(text("SELECT count(*) FROM source_revision")) == 4
    with (
        pytest.raises(DBAPIError, match="permission denied"),
        capture.engine.begin() as conn,
    ):
        conn.execute(text("SET LOCAL ROLE edgartools_acquisition_processor"))
        conn.execute(text("DELETE FROM source_revision"))


@pytest.mark.parametrize(
    "defect",
    [
        "missing",
        "duplicate_member",
        "duplicate_key",
        "missing_kind",
        "raw_hash",
        "canonical_hash",
        "domain_hash",
        "bytes",
        "wrong_key",
        "extra_revision",
        "wrong_publication",
        "wrong_version",
        "corrupt_member",
        "corrupt_manifest",
    ],
)
def test_publication_fails_closed(source_fixture, defect):
    capture, store, _ = source_fixture

    def edit(manifest):
        member = manifest["members"][0]
        if defect == "duplicate_member":
            manifest["members"][1]["member"] = member["member"]
        elif defect == "duplicate_key":
            manifest["members"][1]["logical_source_key"] = member["logical_source_key"]
        elif defect == "missing_kind":
            manifest["members"].pop()
        elif defect in {"raw_hash", "canonical_hash", "domain_hash"}:
            key = {
                "raw_hash": "raw_evidence_hash",
                "canonical_hash": "canonical_source_hash",
                "domain_hash": "domain_content_hash",
            }[defect]
            member[key] = "a" * 64
        elif defect == "bytes":
            member["bytes"] += 1
        elif defect == "wrong_key":
            member["logical_source_key"] = "not-captured"

    member_edit = {}
    if defect == "wrong_publication":
        member_edit = {"source_native_revision": "different-publication"}
    if defect == "wrong_version":
        member_edit = {"versions": {"parser_version": "unapproved-v2"}}
    manifest, revision = load_fixture(
        capture,
        edit=edit,
        omit="relationships" if defect == "missing" else None,
        member_edit=member_edit,
    )
    if defect == "extra_revision":
        capture.add("fixture/level1", b"conflicting delivery", manifest=manifest)
    if defect.startswith("corrupt_"):
        sha = (
            revision.raw_evidence_hash
            if defect == "corrupt_manifest"
            else manifest["members"][0]["raw_evidence_hash"]
        )
        (capture.root / sha).write_bytes(b"corrupted after capture")
    with pytest.raises(Conflict):
        verify(capture, store, revision)


def test_delta_delivery_is_complete_but_scope_is_partial(source_fixture):
    capture, store, _ = source_fixture
    _, baseline_revision = load_fixture(capture)
    baseline = verify(capture, store, baseline_revision)

    def delta(m):
        m.update(
            publication="delta-2",
            sequence=2,
            mode="delta",
            coverage="PARTIAL",
            predecessor={
                "sequence": 1,
                "manifest_sha256": baseline.evidence["manifest_sha256"],
            },
        )

    _, revision = load_fixture(capture, edit=delta)
    verified = verify(capture, store, revision)
    assert verified.evidence["delivery_verified"]
    assert verified.evidence["coverage"] == "PARTIAL"
    assert (
        plan_continuity([verified], previous=baseline, target_sequence=2)[
            "recovery_mode"
        ]
        == "delta"
    )


def test_missing_and_uncaptured_manifest_are_not_verified(source_fixture):
    capture, store, _ = source_fixture
    verifier = PublicationVerifier(capture.engine, capture.reader)
    with pytest.raises(Conflict, match="Missing or unverified"):
        verifier.verify(
            store, source_code="fixture.publication", manifest_revision_id=str(uuid4())
        )
    manifest = json.loads((FIXTURE / "manifest.json").read_bytes())
    decision = capture.add("fixture/manifest", b"{}", manifest=manifest, capture=False)
    from edgar_warehouse.acquisition.revisions import RevisionNotEligible

    with pytest.raises(RevisionNotEligible):
        capture.revisions.materialize_from_capture(
            decision.decision_id,
            raw_evidence_hash="a" * 64,
            canonical_source_hash="a" * 64,
            domain_content_hash="a" * 64,
            contract_version="fixture-v1",
            parser_version="fixture-v1",
            schema_version="1",
            configuration_version="fixture-v1",
        )


def test_verification_does_not_depend_on_success_of_mdm_transaction(
    source_fixture, database
):
    capture, store, _ = source_fixture
    _, revision = load_fixture(capture)
    verified = verify(capture, store, revision)
    proof = plan_continuity([verified], target_sequence=1)
    req = clean_fixtures.request(
        database,
        source_family="fixture",
        publication_family="golden_copy",
        committed_publication=verified.evidence["publication"],
        continuity_proof=proof,
    )
    with (
        pytest.raises(RuntimeError, match="crash"),
        database.application.begin() as conn,
    ):
        store.commit(conn, req, str(uuid4()))
        raise RuntimeError("crash before master commit")
    with database.application.connect() as conn:
        for table in ("batch", "checkpoint", "identity", "publication"):
            assert conn.scalar(text(f"SELECT count(*) FROM mdm_v2.{table}")) == 0
    assert verify(capture, store, revision) == verified
    run_id = str(uuid4())
    with database.application.begin() as conn:
        store.commit(conn, req, run_id)
    with database.application.connect() as conn:
        checkpoints = (
            conn.execute(
                text(
                    "SELECT source_family,publication_family,continuity_proof FROM mdm_v2.checkpoint"
                )
            )
            .mappings()
            .all()
        )
        assert len(checkpoints) == 1
        assert checkpoints[0]["publication_family"] == "golden_copy"
        assert checkpoints[0]["continuity_proof"] == proof
        assert conn.scalar(text("SELECT count(*) FROM mdm_v2.identity")) == 0
    assert store.run_status(run_id)["pending"] == 2
    assert not store.run_status(run_id)["publication_complete"]


@pytest.mark.parametrize(
    "raw",
    [
        b'{"version":1,"version":1}',
        b'{"version":1,"unknown":NaN}',
        b"[]",
        b'{"version":true}',
    ],
)
def test_ambiguous_or_nonfinite_manifest_fails_closed(source_fixture, raw):
    capture, store, _ = source_fixture
    manifest = json.loads((FIXTURE / "manifest.json").read_bytes())
    revision = capture.add("fixture/manifest", raw, manifest=manifest)
    with pytest.raises(Conflict):
        verify(capture, store, revision)


def test_artifact_bounds_and_missing_bytes(source_fixture, monkeypatch):
    capture, store, _ = source_fixture
    _, revision = load_fixture(capture)
    from edgar_warehouse.mdm.clean import source_publications

    with monkeypatch.context() as patch:
        patch.setattr(source_publications, "MEMBER_LIMIT", 1)
        with pytest.raises(Conflict, match="verification bound"):
            verify(capture, store, revision)

    # Simulate an unavailable stage/archive reader without deleting evidence.
    def unavailable(_):
        raise FileNotFoundError("artifact unavailable")

    with pytest.raises(FileNotFoundError):
        PublicationVerifier(capture.engine, unavailable).verify(
            store,
            source_code="fixture.publication",
            manifest_revision_id=revision.revision_id,
        )


def test_unverified_revision_row_cannot_substitute_for_capture(source_fixture):
    capture, store, _ = source_fixture
    manifest = json.loads((FIXTURE / "manifest.json").read_bytes())
    raw = (FIXTURE / "manifest.json").read_bytes()
    decision = capture.add("fixture/manifest", raw, manifest=manifest, capture=False)
    sha = hashlib.sha256(raw).hexdigest()
    # Deliberately bypass the Python materializer as its restricted SQL role:
    # the verifier must require the immutable CAPTURED transition as well.
    with capture.engine.begin() as conn:
        conn.execute(text("SET LOCAL ROLE edgartools_acquisition_processor"))
        revision_id = conn.scalar(
            text("""INSERT INTO source_revision (
            decision_id, source_family, logical_source_key, observation_position,
            source_native_revision, raw_evidence_hash, canonical_source_hash,
            domain_content_hash, contract_version, parser_version, schema_version,
            configuration_version, completeness_type, declared_replacement_scope,
            bronze_artifact_reference, content_impact)
            SELECT decision_id,source_family,logical_source_key,observation_position,
            :publication,:sha,:sha,:sha,'fixture-v1','fixture-v1','1','fixture-v1',
            'COMPLETE',:scope,:sha,'CHANGED' FROM source_fetch_decision WHERE decision_id=:id
            RETURNING revision_id"""),
            {
                "publication": manifest["publication"],
                "sha": sha,
                "scope": manifest["replacement_scope"],
                "id": decision.decision_id,
            },
        )
    with pytest.raises(Conflict, match="unverified"):
        PublicationVerifier(capture.engine, capture.reader).verify(
            store,
            source_code="fixture.publication",
            manifest_revision_id=str(revision_id),
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"sequence": True},
        {"sequence": -1},
        {"mode": "full", "coverage": "PARTIAL"},
        {"mode": "delta", "coverage": "PARTIAL", "predecessor": None},
        {
            "mode": "delta",
            "coverage": "PARTIAL",
            "predecessor": {"sequence": 1, "manifest_sha256": "a" * 64},
        },
        {"replacement_scope": "unapproved-scope"},
        {"publication_family": "opencorporates"},
    ],
)
def test_source_metadata_is_validated_from_captured_bytes(source_fixture, changes):
    capture, store, _ = source_fixture
    _, revision = load_fixture(capture, edit=lambda m: m.update(changes))
    with pytest.raises(Conflict):
        verify(capture, store, revision)
