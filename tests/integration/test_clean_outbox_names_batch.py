"""An outbox row names its batch instead of holding a copy of it (014)."""

from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from edgar_warehouse.mdm.clean.store import Store, register_policy
from tests.integration import test_clean_mdm_postgres as core

postgres = core.postgres
database = core.database
MIGRATIONS = Path(__file__).parents[2] / "edgar_warehouse" / "mdm" / "migrations"


class Destination:
    def __init__(self):
        self.sent = {}

    def publish(self, key, payload, expected_hash):
        self.sent[key] = (payload, expected_hash)

    def verify(self, key, payload, expected_hash):
        assert self.sent[key] == (payload, expected_hash)
        return expected_hash


def journal_policy(database) -> str:
    """The fixture's policy, with the Change Journal among its required consumers."""
    with database.admin.begin() as conn:
        body = conn.scalar(text("SELECT body FROM mdm.policy WHERE digest=:d"), {"d": database.policy})
        return register_policy(conn, {**body, "required_consumers": ["export", "graph", "journal"]})


def rows(database):
    with database.admin.connect() as conn:
        return [dict(r) for r in conn.execute(text(
            "SELECT batch_id, consumer, payload, payload_hash, mdm.outbox_payload(batch_id, consumer) AS sent, "
            "encode(sha256(convert_to(mdm.outbox_payload(batch_id, consumer)::text,'UTF8')),'hex') AS sent_hash "
            "FROM mdm.outbox ORDER BY batch_id, consumer")).mappings()]


def test_a_new_row_keeps_only_the_hash_and_sends_what_its_batch_holds(database):
    policy = journal_policy(database)
    store = Store(database.application)
    with database.application.begin() as conn:
        store.commit(conn, core.request(database, policy_digest=policy), str(uuid4()))
    found = rows(database)
    assert found and all(r["payload"] is None and r["sent_hash"] == r["payload_hash"] for r in found)
    with database.admin.connect() as conn:
        batch = conn.execute(text("SELECT generation, run_id::text, effects FROM mdm.batch")).one()
    for r in found:
        assert r["sent"]["objects"] == batch.effects["projections"]
        assert r["sent"]["generation"] == batch.generation and r["sent"]["run_id"] == batch.run_id
        assert ("effects" in r["sent"]) == (r["consumer"] == "journal")
    sent = Destination()
    assert store.deliver_one("export", "worker", sent)
    ((payload, expected),) = sent.sent.values()
    assert payload == next(r["sent"] for r in found if r["consumer"] == "export")
    assert expected == next(r["payload_hash"] for r in found if r["consumer"] == "export")


def test_a_row_saved_before_keeps_and_sends_its_own_payload(database):
    """A populated store: rows written by the 001 write_batch keep their payload,
    are sent as stored after 014, and a later batch's row holds only its hash."""
    baseline = (MIGRATIONS / "001_mdm.sql").read_text()
    start = baseline.index("CREATE FUNCTION mdm.write_batch(")
    old = baseline[start:baseline.index("$$;\n", start) + 4].replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    with database.admin.begin() as conn:
        conn.exec_driver_sql(old.replace("%", "%%"))  # psycopg2 formats a bare %
    policy = journal_policy(database)
    store = Store(database.application)
    with database.application.begin() as conn:
        store.commit(conn, core.request(database, policy_digest=policy), str(uuid4()))
    with database.admin.begin() as conn:
        conn.execute(text((MIGRATIONS / "014_outbox_names_batch.sql").read_text()))
    with database.application.begin() as conn:
        store.commit(conn, core.request(database, policy_digest=policy, batch_id="batch-2", expected_generation=1,
                                        expected_checkpoint=1, checkpoint=2), str(uuid4()))
    found = {(r["batch_id"], r["consumer"]): r for r in rows(database)}
    old_rows = [r for (b, _), r in found.items() if b == "batch-1"]
    new_rows = [r for (b, _), r in found.items() if b == "batch-2"]
    assert old_rows and all(r["payload"] is not None and r["sent"] == r["payload"] for r in old_rows)
    assert all(r["sent_hash"] == r["payload_hash"] for r in old_rows)
    assert new_rows and all(r["payload"] is None and r["sent_hash"] == r["payload_hash"] for r in new_rows)
    sent = Destination()
    assert store.deliver_one("export", "worker", sent) and store.deliver_one("export", "worker", sent)
    assert sent.sent["export/batch-1"] == (found[("batch-1", "export")]["payload"], found[("batch-1", "export")]["payload_hash"])
    assert sent.sent["export/batch-2"][1] == found[("batch-2", "export")]["payload_hash"]


def test_what_014_builds_equals_what_001_stored(database):
    """The same saved batch: the payload the 001 write_batch stored, and its hash,
    equal what 014 builds from the batch row, for every consumer."""
    baseline = (MIGRATIONS / "001_mdm.sql").read_text()
    start = baseline.index("CREATE FUNCTION mdm.write_batch(")
    old = baseline[start:baseline.index("$$;\n", start) + 4].replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    with database.admin.begin() as conn:
        conn.exec_driver_sql(old.replace("%", "%%"))  # psycopg2 formats a bare %
    policy = journal_policy(database)
    store = Store(database.application)
    with database.application.begin() as conn:
        store.commit(conn, core.request(database, policy_digest=policy), str(uuid4()))
    with database.admin.connect() as conn:
        found = conn.execute(text(
            "SELECT consumer, payload = mdm.outbox_payload_of(batch_id, consumer) AS same, payload_hash = "
            "encode(sha256(convert_to(mdm.outbox_payload_of(batch_id, consumer)::text,'UTF8')),'hex') AS same_hash "
            "FROM mdm.outbox")).mappings().all()
    assert {r["consumer"] for r in found} == {"journal", "export", "graph"}
    assert all(r["same"] and r["same_hash"] for r in found)
