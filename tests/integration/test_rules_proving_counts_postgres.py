"""Governed Proving hashes original record bytes under an explicit hash contract."""
import hashlib

from edgar_warehouse.rules import proving
from edgar_warehouse.mdm.clean.inspection import HASH_CONTRACT
from edgar_warehouse.mdm.clean.prepared_registry import require_installed
from edgar_warehouse.mdm.clean.store import canonical
from tests.integration import test_clean_mdm_postgres as core


def expected_hash(engine):
    result = hashlib.md5((HASH_CONTRACT + "\n").encode())
    with engine.connect() as conn:
        api = require_installed(conn)
        for kind in ("entity", "relationship", "review"):
            keys = api.record_keys(kind, connection=conn)
            rows = api.read([(kind, key) for key in keys], connection=conn)
            for key in keys:
                result.update(canonical([kind, key]).encode() + b":" + bytes(rows[kind, key]["body"]) + b"\n")
    return result.hexdigest()


def test_streamed_hash_preserves_publication_bytes_and_unchanged_replay(database):
    empty = proving.counts(database.application)
    assert empty["current_records_md5"] == expected_hash(database.application)
    assert empty["records_hash_contract"] == HASH_CONTRACT
    item = core.source("invented-hash", fields={"name": "Invented Société 雪", "amount": 10**80 + 7})
    identity, binding = core.identity_and_binding(item)
    command = dict(assertions=[item], identities=[identity], decisions=[binding])
    core.apply(database, 1, **command)
    before = proving.counts(database.application)
    assert before["current_records_md5"] == expected_hash(database.application)
    assert before["current_records_md5"] != empty["current_records_md5"]
    assert before["masters"] == {"company": 1}
    assert before["stage_records"] == {"fixture.primary": 1}
    assert core.apply(database, 1, **command)["duplicate"]
    assert proving.counts(database.application) == before
