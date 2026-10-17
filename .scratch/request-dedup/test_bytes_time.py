"""Request-dedup design check (scratch, not collected by CI): does a smaller save request save
database time? cm27 chunk 1 mastered into fresh PG16 stores, as today and with the golden
fields' repeated values removed (winner.value, per-field policy_digest and kind_version)."""
import json
import os
import time
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import event

from edgar_warehouse.mdm.clean import survivorship
from edgar_warehouse.mdm.clean.execution import batch_input
from edgar_warehouse.mdm.clean.company_source import CONTRACT, POLICY
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, register_policy
from tests.integration import test_clean_mdm_postgres as core
from tests.support.rules_authority import register_dataset

postgres = core.postgres
database = core.database
BUNDLE = Path("~/.local/share/edgartools/clean-mdm/proving/cm27/bundles/chunk1").expanduser()
ORIGINAL = survivorship._select_values


def _stripped(*args, **kwargs):
    fields, reviews = ORIGINAL(*args, **kwargs)
    for f in fields.values():
        f["winner"] = {k: v for k, v in f["winner"].items() if k != "value"}
        f.pop("policy_digest", None)
        f.pop("kind_version", None)
    return fields, reviews


def run(database, monkeypatch, strip):
    if strip:
        monkeypatch.setattr(survivorship, "_select_values", _stripped)
    calls = []
    engine = database.application

    @event.listens_for(engine, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):
        conn.info["t0"] = time.perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):
        calls.append((time.perf_counter() - conn.info.pop("t0"), len(str(parameters or "")), " ".join(statement.split())[:40]))

    manifest = json.loads((BUNDLE / "manifest.json").read_text())
    with database.admin.begin() as conn:
        digest = register_policy(conn, POLICY)
        register_dataset(conn, "sec.submissions.company.v1", str(uuid4()), CONTRACT)
    store = Store(engine)
    (batch,) = manifest["batches"]
    found = batch_input(batch, BUNDLE.resolve(), store, policy_digest=digest)
    calls.clear()
    t0 = time.perf_counter()
    MergeStage(store).apply(batch_id="b0", run_id=str(uuid4()), consumer="trial", policy_digest=digest,
                            expected_checkpoint=0, checkpoint=1, as_of=manifest["as_of"],
                            assertions=found["assertions"], deferred=found["deferred"],
                            occurrences=found["occurrences"])
    total = time.perf_counter() - t0
    named = {}
    for spent, size, statement in calls:
        for name in ("save_batch", "preview_batch", "record_match_proposal"):
            if name in statement:
                named[name] = (round(spent, 2), round(size / 1e6, 2))
    print("RESULT", json.dumps({"strip": strip, "merge_s": round(total, 2),
                                "db_s": round(sum(c[0] for c in calls), 2), **named}))


@pytest.mark.parametrize("strip", [False, True, False, True])
def test_time(database, monkeypatch, strip):
    run(database, monkeypatch, strip)
