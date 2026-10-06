"""Ticket 05, check on real data: the `context` command over the ticket 04 GLEIF slice.

Copied into tests/integration for one run (it uses the PG16 test fixtures), then removed:

    cp .scratch/profiling/trials/context/check_context.py tests/integration/test_zz_context_check.py
    SLICE=<slice folder> OUT=<out folder> uv run --extra mdm pytest -q tests/integration/test_zz_context_check.py -s

Loads the slice exactly as ticket 04's check_chains.py does (the real GLEIF
contracts and the Mastering Policy in rules/), then asks the command, for each
of 60 seeded entities: a lookup by id, a lookup by its LEI, a search by the
first word of its name, an --as-at lookup at the first batch, an --as-of
lookup, and the relationship walk at 1, 2 and 3 hops. Records each answer's
size in bytes, whether it found the entity, and the time it took. Writes
context-check.json.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import random
import time
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from edgar_warehouse.context import LIMIT_BYTES, Context, ContextError
from edgar_warehouse.mdm.clean import gleif_source
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, digest, register_policy
from edgar_warehouse.rules import files
from tests.integration import test_clean_mdm_postgres as core
from tests.support.rules_authority import register_dataset

postgres = core.postgres
database = core.database


def readings(member, rows, leis):
    found = []
    for n, row in enumerate(rows):
        publication = {"publication_key": f"slice/gleif/{member}", "revision": 1, "artifact_sha256": digest(row),
                       "member": member, "record_locator": str(n)}
        outcome, reading = gleif_source.record_evidence(
            row, member=member, contract=gleif_source.dataset_contract(member), source_code=f"gleif.{member}.v1",
            eligible_leis=leis, publication=publication, ordinal=n)
        if outcome == "assertion":
            found.append(reading)
    return found


def ask(context, subject, key=None, **more):
    base = dict(search=None, limit=5, as_of=None, as_at=None, hops=1, relationship_type="", detail="brief", page=None)
    started = time.perf_counter()
    try:
        answer = context.answer(argparse.Namespace(subject=subject, key=key, **{**base, **more}))
    except ContextError as error:
        answer = {"error": str(error), "try": error.command}
    return answer, len(json.dumps(answer, ensure_ascii=False).encode()), time.perf_counter() - started


def test_context_check(database):
    folder, out = Path(os.environ["SLICE"]), Path(os.environ["OUT"])
    chosen = json.loads((folder / "slice.json").read_text())
    leis = set(chosen["leis"])
    level1 = readings("level1", [json.loads(line) for line in (folder / "level1.jsonl").open()], leis)
    links = readings("relationships", [json.loads(line) for line in (folder / "relationships.jsonl").open()], leis)
    with database.admin.begin() as conn:
        policy = register_policy(conn, files.policy())
        for member in ("level1", "relationships"):
            register_dataset(conn, f"gleif.{member}.v1", str(uuid4()), gleif_source.dataset_contract(member))
    pairs = [core.identity_and_binding(r) for r in level1]
    stage = MergeStage(Store(database.application))
    common = {"run_id": str(uuid4()), "consumer": "context-check", "policy_digest": policy}
    stage.apply(batch_id="entities", expected_checkpoint=0, checkpoint=1, assertions=level1,
                identities=[i for i, _ in pairs], decisions=[d for _, d in pairs],
                as_of="2026-09-11T16:00:00+00:00", **common)
    stage.apply(batch_id="links", expected_checkpoint=1, checkpoint=2, assertions=links,
                as_of="2026-09-12T16:00:00+00:00", **common)
    with database.application.connect() as conn:
        entity = dict(conn.execute(text(
            "SELECT record_key, entity_id::text FROM mdm.stage_record WHERE source_code = 'gleif.level1.v1'")).all())
        first_batch = conn.scalar(text("SELECT created_at FROM mdm.batch WHERE generation = 1"))
        views = conn.scalar(text("SELECT count(*) FROM mdm.entity_context"))
    context = Context(database.application)
    sample = random.Random(5).sample(sorted(entity), min(60, len(entity)))
    sizes, seconds, outcome, examples = [], collections.defaultdict(list), collections.Counter(), {}
    for lei in sample:
        entity_id = entity[lei]
        by_id, size, took = ask(context, "company", entity_id)
        sizes.append(size), seconds["lookup"].append(took)
        outcome["lookup found"] += by_id.get("entity_id") == entity_id
        by_lei, size, took = ask(context, "company", f"lei:{lei}")
        sizes.append(size), seconds["lookup by lei"].append(took)
        outcome["lookup by lei found the same entity"] += by_lei.get("entity_id") == entity_id
        name = by_id.get("name") or ""
        if name:
            found, size, took = ask(context, "company", search=name.split()[0], limit=20)
            sizes.append(size), seconds["search"].append(took)
            outcome["search by first word lists it"] += entity_id in {m["entity_id"] for m in found.get("matches", [])}
            outcome["searched"] += 1
        at, size, took = ask(context, "company", entity_id, as_at=first_batch.isoformat())
        sizes.append(size), seconds["as-at"].append(took)
        outcome["as-at answered (generation 1)"] += at.get("trust", {}).get("generation") == 1
        of, size, took = ask(context, "company", entity_id, as_of="2026-09-11T20:00:00+00:00")
        sizes.append(size), seconds["as-of"].append(took)
        outcome["as-of answered (generation 1)"] += of.get("trust", {}).get("generation") == 1
        for hops in (1, 2, 3):
            walked, size, took = ask(context, "relationship", entity_id, hops=hops)
            sizes.append(size), seconds[f"hops {hops}"].append(took)
            outcome[f"hops {hops} answered"] += "related" in walked
            outcome[f"hops {hops} truncated"] += bool(walked.get("truncated"))
        if not examples:
            examples = {"lookup": by_id, "relationship hops 2": ask(context, "relationship", entity_id, hops=2)[0]}
    result = {
        "entities_in_view": views, "asked_about": len(sample), "answers": len(sizes),
        "largest_answer_bytes": max(sizes), "over_8kb": sum(s > LIMIT_BYTES for s in sizes),
        "outcome": outcome,
        "seconds": {k: {"median": sorted(v)[len(v) // 2], "max": max(v)} for k, v in seconds.items()},
        "examples": examples,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "context-check.json").write_text(json.dumps(result, indent=1, default=str, ensure_ascii=False))
    print(json.dumps({k: v for k, v in result.items() if k != "examples"}, indent=1, default=str))
