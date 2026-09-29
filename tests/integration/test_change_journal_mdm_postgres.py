"""Fresh Rules registration and MDM journal publication without legacy tables."""

from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from edgar_warehouse.bookkeeping.clean.capabilities import standard_registry
from edgar_warehouse.bookkeeping.clean.config import canonical, digest
from edgar_warehouse.bookkeeping.clean.destinations import migrate_guard
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
from edgar_warehouse.bookkeeping.clean.mdm_capabilities import register_mdm
from edgar_warehouse.bookkeeping.clean.runner import run
from edgar_warehouse.change_journal.publication import JournalPublisher
from edgar_warehouse.mdm.clean.adapters import normalize
from edgar_warehouse.mdm.clean.store import Conflict, migrate, register_policy
from tests.integration.test_change_journal_acquisition_postgres import definition
from tests.integration.test_clean_mdm_postgres import AS_OF, identity_and_binding
from tests.integration.test_configured_bookkeeping_postgres import databases


def test_fresh_rules_registration_ingest_and_lost_journal_ack(databases, tmp_path):
    dbname = "change_journal_validation_mdm_" + uuid4().hex[:12]
    with databases.destination_admin.connect().execution_options(
        isolation_level="AUTOCOMMIT"
    ) as conn:
        conn.exec_driver_sql(f"CREATE DATABASE {dbname}")
    owner = create_engine(databases.destination_admin.url.set(database=dbname))
    runtime = create_engine(
        databases.mdm.url.set(database=dbname),
        connect_args={"options": "-c timezone=America/New_York"},
    )
    try:
        migrate(owner, application_role="clean_application")
        migrate_guard(owner, runtime_role="clean_application")
        code = "fresh.company.v1"
        contract = {
            "provider": "Fixture",
            "family": "fixture",
            "schema_version": "1",
            "record_key": "key",
            "publication_key": "release",
            "effective_time": "unknown",
            "semantics": "patch",
            "adapter": {
                "version": "fresh-1",
                "kind": "company",
                "record_key": ["key"],
                "retain_deferred": True,
                "fields": {"name": "name"},
            },
        }
        with owner.begin() as conn:
            policy = register_policy(
                conn,
                {
                    "version": 1,
                    "required_consumers": ["journal"],
                    "automatic_rules": [],
                    "fields": {
                        "company": {
                            "name": {"sources": [code], "allow_unknown_effective": True}
                        }
                    },
                },
            )
        registry = standard_registry()
        publisher = None
        register_mdm(registry, runtime, publisher_factory=lambda _: publisher)
        book = Bookkeeping(databases.runtime, registry)
        name = "fresh-" + uuid4().hex
        feed = definition()
        feed["datasets"] = [code]
        body = {
            "source": name,
            "mdm": {code: {"contract": contract}},
            "acquisition": {"version": 1, "feeds": {"company": feed}},
            "bookkeeping": {
                "version": 1,
                "targets": {
                    "mdm": {
                        "steps": [
                            {
                                "name": "merge",
                                "operation": "mdm.ingest",
                                "requires": [],
                                "key": "{batch_id}",
                                "leases": ["mdm:consumer:{consumer}"],
                                "checks": ["input.hash", "output.receipt"],
                            },
                            {
                                "name": "publish",
                                "operation": "mdm.publish",
                                "requires": ["merge"],
                                "key": "{consumer}",
                                "leases": ["mdm:publication:{consumer}"],
                                "checks": ["input.hash", "output.receipt"],
                            },
                        ],
                        "checks": [
                            "manifest.hash",
                            "work.accounting",
                            "journal.delivered",
                            "mdm.publication",
                        ],
                    }
                },
            },
        }
        record = {"key": "one", "name": "Fresh Journal Company"}
        artifact = book.artifacts.put_bytes(
            (tmp_path / "company.ndjson").as_uri(), canonical(record).encode() + b"\n"
        )
        publication = {"publication_key": "release-1", "revision": 1}
        prepared = normalize(
            record,
            source_code=code,
            contract=contract,
            publication={
                **publication,
                "artifact_sha256": artifact["sha256"],
                "member": artifact["uri"],
                "record_locator": artifact["sha256"] + ":line:1",
            },
        )
        identity, decision = identity_and_binding(prepared)
        batch_id = "fresh-batch-" + uuid4().hex
        command = {
            "version": 1,
            "source_input": {
                "source_code": code,
                "artifact": artifact,
                "publication": publication,
                "record_count": 1,
            },
            "command": {
                "batch_id": batch_id,
                "consumer": "fresh-company",
                "expected_checkpoint": 0,
                "checkpoint": 1,
                "policy_digest": policy,
                "as_of": AS_OF,
                "identities": [identity],
                "decisions": [decision],
            },
        }
        spec = {
            "version": 1,
            "batch_id": batch_id,
            "consumer": "journal",
            "destination": "change-journal",
        }
        inputs = book.artifacts.put(
            tmp_path.as_uri() + "/work",
            {
                "version": 2,
                "steps": {
                    "merge": [
                        {
                            "keys": {
                                "batch_id": batch_id,
                                "consumer": "fresh-company",
                                "source": name,
                                "feed": "company",
                            },
                            "input": book.artifacts.put(tmp_path.as_uri(), command),
                            "output": (tmp_path / "merge-receipt").as_uri(),
                            "cursor": 0,
                        }
                    ],
                    "publish": [
                        {
                            "keys": {
                                "consumer": "journal",
                                "batch_id": batch_id,
                                "source": name,
                                "feed": "company",
                            },
                            "input": book.artifacts.put(tmp_path.as_uri(), spec),
                            "output": (tmp_path / "publication-receipt").as_uri(),
                            "cursor": 0,
                        }
                    ],
                },
            },
        )
        saved = databases.rules.save("source", name, "1", body)
        proof = {
            "digest": saved["digest"],
            "passed": True,
            "batch_hash": inputs["sha256"],
            "acquisition": {
                "company": {
                    "manifest": inputs,
                    "counts": {"capture": {"expected": 1, "verified": 1}},
                    "checks": {"offline": True},
                }
            },
        }
        databases.rules.prove("source", name, "1", proof)
        databases.approver.approve("source", name, "1", by="operator", words="approved")
        databases.rules.activate("source", name, "1", mdm_engine=owner)
        with owner.connect() as conn:
            assert not conn.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM pg_tables WHERE tablename LIKE 'source_%')"
                )
            )
            reading = conn.scalar(
                text("SELECT body FROM mdm_v2.dataset_mapping WHERE source_code=:c"),
                {"c": code},
            )
            assert reading["registry_evidence"]["rules"]["digest"] == saved["digest"]
        rules_ref = databases.rules.resolve(
            "source", name, root=tmp_path.as_uri() + "/rules"
        )
        from edgar_warehouse.change_journal.skill import plan
        from edgar_warehouse.rules.files import dumps

        authoring = tmp_path / "authoring"
        source_file = authoring / "sources" / name / "source.yaml"
        source_file.parent.mkdir(parents=True)
        source_file.write_text(dumps(body))
        with databases.admin.connect() as conn:
            before = conn.scalar(text("SELECT count(*) FROM bookkeeping.pipeline_run"))
        bundle = plan(
            source=name,
            feed="company",
            target="mdm",
            inputs=inputs,
            rules_root=authoring,
        )
        assert set(bundle["processing_versions"]) == {"mdm.ingest", "mdm.publish"}
        with databases.admin.connect() as conn:
            assert (
                conn.scalar(text("SELECT count(*) FROM bookkeeping.pipeline_run"))
                == before
            )
        rid = book.start(
            rules_ref=rules_ref,
            inputs_ref=inputs,
            target="mdm",
            scope={"source": name, "feed": "company"},
        )
        publisher = JournalPublisher(databases.ledger, runtime, book)
        publish = publisher.publish

        def lose_ack(key, payload, sha):
            publish(key, payload, sha)
            raise ConnectionError("journal committed but acknowledgement was lost")

        publisher.publish = lose_ack
        with pytest.raises(ConnectionError):
            run(book, rid, databases.ledger)
        receipt = databases.ledger.get("mdm", "journal/" + batch_id)
        assert receipt["event"]["run_id"] == rid and receipt["event"]["source"] == name
        assert "Fresh Journal Company" not in canonical(receipt)
        publisher.publish = publish
        book.resume(rid)
        assert run(book, rid, databases.ledger)["run"]["state"] == "complete"
        assert databases.ledger.get("mdm", "journal/" + batch_id) == receipt
        # A control edit keeps the existing mapping and its registration receipt.
        changed = deepcopy(body)
        changed["bookkeeping"]["targets"]["mdm"]["retry"] = {"attempts": 2}
        newer = databases.rules.save("source", name, "2", changed)
        databases.rules.prove("source", name, "2", {**proof, "digest": newer["digest"]})
        databases.approver.approve("source", name, "2", by="operator", words="approved")
        databases.rules.activate("source", name, "2", mdm_engine=owner)
        with owner.connect() as conn:
            assert (
                conn.scalar(
                    text(
                        "SELECT count(*) FROM mdm_v2.dataset_mapping WHERE source_code=:c"
                    ),
                    {"c": code},
                )
                == 1
            )
            assert (
                conn.scalar(
                    text(
                        "SELECT body FROM mdm_v2.dataset_mapping WHERE source_code=:c"
                    ),
                    {"c": code},
                )
                == reading
            )
    finally:
        owner.dispose()
        runtime.dispose()
        with databases.destination_admin.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as conn:
            conn.exec_driver_sql(f"DROP DATABASE {dbname}")
