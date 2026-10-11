"""L4 design check (scratch, not collected by CI): does mastering depend on batch size?

One cm27 Company bundle (chunk1, 966 records) mastered into two fresh PG16 stores:
once as its one batch, once one record per batch. Same Companies, bindings and reviews expected.
"""
import json
import os
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from edgar_warehouse.mdm.clean.cli import batch_input
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, register_policy
from edgar_warehouse.rules import files
from tests.integration import test_clean_mdm_postgres as core
from tests.support.rules_authority import register_dataset

postgres = core.postgres
database = core.database
BUNDLE = Path(os.environ.get("L4_BUNDLE", "~/.local/share/edgartools/clean-mdm/proving/cm27/bundles/chunk1")).expanduser()


def master(database, per_record):
    from edgar_warehouse.mdm.clean.company_source import CONTRACT, POLICY
    policy, dataset = POLICY, CONTRACT  # today's, as the installed proof uses
    manifest = json.loads((BUNDLE / "manifest.json").read_text())
    with database.admin.begin() as conn:
        digest = register_policy(conn, policy)
        register_dataset(conn, "sec.submissions.company.v1", str(uuid4()), dataset)
    store = Store(database.application)
    (batch,) = manifest["batches"]
    found = batch_input(batch, BUNDLE.resolve(), store, policy_digest=digest)
    stage, run = MergeStage(store), str(uuid4())
    groups = [[a] for a in found["assertions"]] if per_record else [found["assertions"]]
    deferred = found["deferred"]
    for n, group in enumerate(groups):
        stage.apply(batch_id=f"b{n}", run_id=run, consumer="trial", policy_digest=digest,
                    expected_checkpoint=n, checkpoint=n + 1, as_of=manifest["as_of"],
                    assertions=group, deferred=deferred if n == 0 else [],
                    occurrences=[o for o in found["occurrences"] if any(o.get("assertion_id") == a.get("assertion_id") for a in group)] if per_record else found["occurrences"])
    with database.application.connect() as conn:
        entities = sorted((tuple(r) for r in conn.execute(text("SELECT kind, body::text FROM mdm.current_entity")).all()), key=repr)
        bindings = sorted((tuple(r) for r in conn.execute(text("SELECT subject, entity_id IS NOT NULL FROM mdm.stage_record")).all()), key=repr)
        reviews = sorted((tuple(r) for r in conn.execute(text(
            "SELECT body->>'subject', body->>'reason', body->>'blocking' FROM mdm.current_record WHERE object_type='review'")).all()), key=repr)
        golden = sorted((tuple(r) for r in conn.execute(text(
            "SELECT (body->'fields')::text FROM mdm.current_entity")).all()), key=repr)
        sizes = conn.execute(text(
            "SELECT relname, n_live_tup, pg_total_relation_size(relid) FROM pg_stat_user_tables WHERE schemaname='mdm' AND pg_total_relation_size(relid) > 100000 ORDER BY 3 DESC")).all()
        print("record sizes:", [tuple(r) for r in sizes])
        import os as _os
        body = conn.execute(text("SELECT body::text FROM mdm.match_proposal")).scalar()
        Path("/private/tmp/claude-501/-Users-aneenaananth-projects-edgartools-platform/448ef2c8-e025-4be6-8aef-0620c44e7a52/scratchpad/proposal-" + str(BUNDLE.name if BUNDLE.name != "chunk1" or "proofwork" not in str(BUNDLE) else "raw") + ".json").write_text(body)
    return {"assertions": len(found["assertions"]), "deferred": len(deferred), "entities": len(entities),
            "bindings": bindings, "reviews": reviews, "golden": golden}


RESULTS = {}


def test_whole_batch(database):
    RESULTS["whole"] = master(database, per_record=False)


def test_one_record_per_batch(database):
    RESULTS["single"] = master(database, per_record=True)


def test_batch_size_does_not_change_mastering():
    whole, single = RESULTS["whole"], RESULTS["single"]
    print({k: (v if isinstance(v, int) else len(v)) for k, v in whole.items()})
    for key in ("entities", "bindings", "reviews", "golden"):
        assert whole[key] == single[key], key


NEW = Path(os.environ.get("L4_NEW_BUNDLE", "/nonexistent"))


def master_bundle(database, bundle):
    """One bundle mastered as its manifest says, into a fresh store, today's policy and contract."""
    global BUNDLE
    saved, BUNDLE = BUNDLE, bundle
    try:
        return master(database, per_record=False)
    finally:
        BUNDLE = saved


def test_landed_bundle(database):
    RESULTS["landed"] = master_bundle(database, BUNDLE)


def test_raw_bundle(database):
    RESULTS["raw"] = master_bundle(database, NEW)


def test_raw_bundle_masters_as_the_landed_one():
    landed, raw = RESULTS["landed"], RESULTS["raw"]
    print({"landed": {k: (v if isinstance(v, int) else len(v)) for k, v in landed.items()},
           "raw": {k: (v if isinstance(v, int) else len(v)) for k, v in raw.items()}})
    for key in ("bindings", "reviews"):
        assert landed[key] == raw[key], key

    def strip(value):
        # The assertion id hashes the delivered record, whose provenance differs by design.
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k != "assertion_id"}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value

    old = sorted(json.dumps(strip(json.loads(g[0])), sort_keys=True) for g in landed["golden"])
    new = sorted(json.dumps(strip(json.loads(g[0])), sort_keys=True) for g in raw["golden"])
    fields = {}
    for a, b in zip(old, new):
        a, b = json.loads(a), json.loads(b)
        for f in set(a) | set(b):
            if a.get(f) != b.get(f):
                fields.setdefault(f, [a.get(f), b.get(f)])
    print("differing golden fields:", json.dumps(fields, default=str)[:3000])
    assert old == new


def test_time_split(database):
    """Where mastering's time goes: database calls (wall time from execute to result) against the rest."""
    import time
    from sqlalchemy import event
    calls = {"n": 0, "db": 0.0}
    engine = database.application

    @event.listens_for(engine, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):
        conn.info["t0"] = time.perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):
        calls["n"] += 1
        spent = time.perf_counter() - conn.info.pop("t0")
        calls["db"] += spent
        size = len(str(parameters)) if parameters else 0
        calls.setdefault("each", []).append((round(spent, 2), size, " ".join(statement.split())[:70]))

    from edgar_warehouse.mdm.clean.company_source import CONTRACT, POLICY
    manifest = json.loads((BUNDLE / "manifest.json").read_text())
    with database.admin.begin() as conn:
        digest = register_policy(conn, POLICY)
        register_dataset(conn, "sec.submissions.company.v1", str(uuid4()), CONTRACT)
    store = Store(engine)
    (batch,) = manifest["batches"]
    t0 = time.perf_counter()
    found = batch_input(batch, BUNDLE.resolve(), store, policy_digest=digest)
    t1 = time.perf_counter()
    read_db = calls["db"]
    MergeStage(store).apply(batch_id="b0", run_id=str(uuid4()), consumer="trial", policy_digest=digest,
                            expected_checkpoint=0, checkpoint=1, as_of=manifest["as_of"],
                            assertions=found["assertions"], deferred=found["deferred"],
                            occurrences=found["occurrences"])
    t2 = time.perf_counter()
    merge_db = calls["db"] - read_db
    print("TIMING", json.dumps({
        "records": len(found["assertions"]),
        "prepare_input_s": round(t1 - t0, 2), "prepare_input_db_s": round(read_db, 2),
        "merge_s": round(t2 - t1, 2), "merge_db_s": round(merge_db, 2),
        "merge_python_s": round(t2 - t1 - merge_db, 2),
        "merge_db_pct": round(100 * merge_db / (t2 - t1), 1), "db_calls": calls["n"]}))
    for row in sorted(calls["each"], reverse=True)[:8]:
        print("CALL", row)
