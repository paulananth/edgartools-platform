"""PROTOTYPE — runs a Source Contract's `expect.merge` cases through Clean MDM's
real Merge Stage in a throwaway PostgreSQL 16 container (ticket 05 Q2; research 03).

Seeds (`given.identities`) go through the same contract and a first Merge Stage
batch with a declared Steward binding — never inserted rows. Identities are
named by the case. Known limit: automatic rules are refused today
(store.py:160-161), so `bound` checks a *declared* binding.
Knows no source: the policy comes from the Rules Database stand-in
(prototype/policies/<kind>.yaml), authored in the same YAML convention (Q2a).
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from uuid import uuid4

AT = "2026-01-01T00:00:00+00:00"
AS_OF = "2026-09-18T00:00:00+00:00"
IMAGE = "postgres:16-alpine"


def _docker(*args):
    env = {**os.environ, "DOCKER_HOST": os.environ.get("DOCKER_HOST", f"unix://{Path.home()}/.colima/default/docker.sock")}
    return subprocess.run(["docker", *args], check=True, capture_output=True, text=True, env=env).stdout.strip()


class Postgres:
    def __enter__(self):
        from sqlalchemy import create_engine, text
        from sqlalchemy.exc import DBAPIError
        from edgar_warehouse.mdm.migrations.runtime import _apply_source_registry_migration
        import socket
        self.name = f"source-contract-proving-{uuid4().hex[:8]}"
        _docker("run", "-d", "--rm", "--name", self.name, "-p", "127.0.0.1::5432", "-e", "POSTGRES_PASSWORD=test", IMAGE)
        port = _docker("port", self.name, "5432/tcp").rsplit(":", 1)[1]
        # the runner blocks the network; localhost Postgres is the one allowed peer
        socket.socket.connect = _REAL_CONNECT
        self.admin = create_engine(f"postgresql+psycopg2://postgres:test@127.0.0.1:{port}/postgres")
        deadline = time.time() + 60  # research 03: an 8 s wait failed 4 of 7 runs on Colima
        while True:
            try:
                with self.admin.connect() as c:
                    c.execute(text("SELECT 1"))
                break
            except DBAPIError:
                if time.time() > deadline:
                    raise
                time.sleep(0.5)
        with self.admin.begin() as c:
            c.execute(text("CREATE ROLE clean_application LOGIN PASSWORD 'test' NOSUPERUSER NOCREATEDB NOCREATEROLE"))
        _apply_source_registry_migration(self.admin)
        self.app = create_engine(f"postgresql+psycopg2://clean_application:test@127.0.0.1:{port}/postgres")
        return self

    def __exit__(self, *exc):
        self.app.dispose()
        self.admin.dispose()
        _docker("stop", self.name)


import socket as _socket  # noqa: E402
_REAL_CONNECT = _socket.socket.connect


def _fresh(pg, source_code: str, dataset: dict, policy: dict) -> str:
    from sqlalchemy import text
    from edgar_warehouse.mdm.clean.store import migrate, register_dataset, register_policy
    with pg.admin.begin() as c:
        c.execute(text("DROP SCHEMA IF EXISTS mdm_v2 CASCADE"))
        c.execute(text("DELETE FROM source_registry_coverage"))
        c.execute(text("DELETE FROM source_registry_version"))
        version = str(uuid4())
        c.execute(text("INSERT INTO source_registry_version(version_id,status,operator_authorization_reference,activated_at) "
                       "VALUES(:v,'active','proving-run',now())"), {"v": version})
        c.execute(text("INSERT INTO source_registry_coverage(version_id,source_family,coverage_action,acquisition_mode,"
                       "completeness_policy,discovery_policy,coverage_start_date) "
                       "VALUES(:v,:f,'carry_forward','proving-run','proving-run','proving-run','2026-01-01')"),
                  {"v": version, "f": dataset["family"]})
    migrate(pg.admin, application_role="clean_application")
    with pg.admin.begin() as c:
        digest = register_policy(c, policy)
        register_dataset(c, source_code, version, dataset)
    return digest


def run_merge_case(engine, case: dict, policy: dict, pg) -> list[dict]:
    """Returns failures for one case's expect.merge list."""
    from sqlalchemy import text
    from edgar_warehouse.mdm.clean.evidence import decision, subject_key
    from edgar_warehouse.mdm.clean.merge import MergeStage
    from edgar_warehouse.mdm.clean.store import Store

    src = engine.contract["source"]
    digest = _fresh(pg, src, engine.contract["dataset"]["contract"], policy)
    n = 0

    def apply(**kw):
        nonlocal n
        n += 1
        return MergeStage(Store(pg.app)).apply(batch_id=f"proving-{n}", run_id=str(uuid4()), policy_digest=digest,
                                               consumer="proving-run", expected_checkpoint=n - 1, checkpoint=n,
                                               as_of=AS_OF, **kw)

    def assertions(fixture):
        return [a for a in engine.to_assertions(engine.parse((engine.dir / fixture).read_bytes())) if "deferred" not in a]

    named: dict[str, str] = {}
    seed_assertions, identities, decisions = [], [], []
    for name, seed in (case.get("given", {}).get("identities") or {}).items():
        a = next(x for x in assertions(seed["fixture"]) if x["record_key"] == str(seed["record"]))
        named[name] = str(uuid4())
        seed_assertions.append(a)
        identities.append({"entity_id": named[name], "kind": a["kind"], "published_at": AT})
        decisions.append(decision("bind", actor="steward", reason="seed declared by the case", at=AT,
                                  subject=a["subject"], entity_id=named[name], evidence=[a["assertion_id"]]))
    if seed_assertions:
        apply(assertions=seed_assertions, identities=identities, decisions=decisions)
    case_assertions = [a for a in assertions(case["fixture"]) if a["assertion_id"] not in {s["assertion_id"] for s in seed_assertions}]
    if case_assertions:
        apply(assertions=case_assertions)

    with pg.app.connect() as c:
        docs = {(r[0], r[1]): r[2] for r in c.execute(text("SELECT object_type, object_id, body FROM mdm_v2.projection"))}
    entities = {oid: b for (t, oid), b in docs.items() if t == "entity"}
    reviews = [b for (t, _), b in docs.items() if t == "review"]
    by_name = {v: k for k, v in named.items()}

    failures = []
    for j, e in enumerate(case["expect"]["merge"]):
        ptr = f"/expect/merge/{j}"
        if "record" in e:
            subj = subject_key(src, str(e["record"]))
            if e["outcome"] == "bound":
                ent = entities.get(named.get(e["to"], ""))
                ok = ent is not None and subj in str(ent)
                actual = "bound" if ok else ("binding_required" if any(subj in str(r) for r in reviews) else "absent")
            elif e["outcome"] == "binding_required":
                ok = any(r.get("reason") == "binding_required" and subj in str(r) for r in reviews)
                actual = "binding_required" if ok else next((f"bound to {by_name.get(k, k)}" for k, b in entities.items() if subj in str(b)), "absent")
            else:
                ok, actual = False, f"outcome {e['outcome']!r} is not supported by the prototype"
            if not ok:
                failures.append({"pointer": ptr, "diff": [{"column": f"record {e['record']}", "expected": e["outcome"], "actual": actual}]})
        elif "identity" in e:
            ent = entities.get(named.get(e["identity"], "")) or {}
            got = ((ent.get("fields") or {}).get(e["field"]) or {})
            diff = []
            if got.get("value") != e.get("value"):
                diff.append({"column": f"{e['identity']}.{e['field']}", "expected": e.get("value"), "actual": got.get("value")})
            if "winner" in e and e["winner"] not in str(got):
                diff.append({"column": f"{e['identity']}.{e['field']} winner", "expected": e["winner"], "actual": str(got)[:120]})
            if diff:
                failures.append({"pointer": ptr, "diff": diff})
    return failures, {"entities": len(entities), "reviews": len(reviews), "batches": n}
