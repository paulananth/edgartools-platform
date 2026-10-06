"""Ticket 04, check on real data, step 2: the MDM parent chain against GLEIF's own ultimate parents.

Copied into tests/integration for one run (it uses the PG16 test fixtures), then removed:

    cp .scratch/profiling/trials/relationships/check_chains.py tests/integration/test_zz_chain_check.py
    SLICE=<slice folder> OUT=<out folder> uv run --extra mdm pytest -q tests/integration/test_zz_chain_check.py -s

Loads the slice's Level 1 and relationship records through the real GLEIF
contracts and the Mastering Policy in rules/ (with its relationship types),
binds each Level 1 record to its own Company (a steward's decision, as GLEIF
records create no Company by themselves), then, for every sampled entity,
compares where `mdm.relationship_chain` ends with the ultimate parent GLEIF
states, and with the one the engine calculates. Writes chain-check.json.
"""

from __future__ import annotations

import collections
import json
import os
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from edgar_warehouse.mdm.clean import gleif_source
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, digest, register_policy
from edgar_warehouse.rules import files
from tests.integration import test_clean_mdm_postgres as core
from tests.support.rules_authority import register_dataset

postgres = core.postgres
database = core.database
DIRECT, ULTIMATE = "IS_DIRECTLY_CONSOLIDATED_BY", "IS_ULTIMATELY_CONSOLIDATED_BY"


def readings(member, rows, leis):
    found, refused = [], collections.Counter()
    for n, row in enumerate(rows):
        publication = {"publication_key": f"slice/gleif/{member}", "revision": 1, "artifact_sha256": digest(row),
                       "member": member, "record_locator": str(n)}
        outcome, reading = gleif_source.record_evidence(
            row, member=member, contract=gleif_source.dataset_contract(member), source_code=f"gleif.{member}.v1",
            eligible_leis=leis, publication=publication, ordinal=n)
        if outcome == "assertion":
            found.append(reading)
        else:
            refused[str(reading.get("reason", outcome))] += 1
    return found, refused


def test_chain_check(database):
    folder, out = Path(os.environ["SLICE"]), Path(os.environ["OUT"])
    chosen = json.loads((folder / "slice.json").read_text())
    leis = set(chosen["leis"])
    level1_rows = [json.loads(line) for line in (folder / "level1.jsonl").open()]
    link_rows = [json.loads(line) for line in (folder / "relationships.jsonl").open()]
    level1, level1_refused = readings("level1", level1_rows, leis)
    links, links_refused = readings("relationships", link_rows, leis)
    with database.admin.begin() as conn:
        policy = register_policy(conn, files.policy())
        for member in ("level1", "relationships"):
            register_dataset(conn, f"gleif.{member}.v1", str(uuid4()), gleif_source.dataset_contract(member))
    pairs = [core.identity_and_binding(r) for r in level1]
    stage = MergeStage(Store(database.application))
    common = {"run_id": str(uuid4()), "consumer": "chain-check", "policy_digest": policy, "as_of": "2026-09-11T16:00:00+00:00"}
    stage.apply(batch_id="entities", expected_checkpoint=0, checkpoint=1, assertions=level1,
                identities=[i for i, _ in pairs], decisions=[d for _, d in pairs], **common)
    stage.apply(batch_id="links", expected_checkpoint=1, checkpoint=2, assertions=links, **common)
    with database.application.connect() as conn:
        entity = dict(conn.execute(text(
            "SELECT record_key, entity_id::text FROM mdm.stage_record WHERE source_code = 'gleif.level1.v1'")).all())
        calculated = dict(conn.execute(text(
            "SELECT source_id, target_id FROM (SELECT body->>'source_id' source_id, body->>'target_id' target_id, "
            "body->>'type' t, body->>'scope' s FROM mdm.current_record WHERE object_type='relationship') x "
            "WHERE t = 'CALCULATED_ULTIMATE_PARENT'")).all())
        reviews = collections.Counter(conn.execute(text(
            "SELECT body->>'reason' FROM mdm.current_record WHERE object_type='review'")).scalars())
        outcome, examples, per_child = collections.Counter(), collections.defaultdict(list), {}
        for child in chosen["sample"]:
            stated = chosen["stated_ultimate"][child]
            if child not in entity or stated not in entity:
                outcome["an end has no Level 1 record in MDM"] += 1
                per_child[child] = "not in MDM"
                continue
            walked = conn.execute(text("SELECT to_entity_id, cycle FROM mdm.relationship_chain(:e, :t, 50)"),
                                  {"e": entity[child], "t": DIRECT}).all()
            end = walked[-1][0] if walked else None
            if end == entity[stated]:
                outcome["chain ends at the stated ultimate parent"] += 1
                key = "matches"
            elif not walked:
                outcome["no current direct parent in MDM"] += 1
                key = "no chain"
            else:
                outcome["chain ends elsewhere"] += 1
                key = "elsewhere"
            per_child[child] = key
            if len(examples[key]) < 5:
                examples[key].append({"child": child, "stated_ultimate": stated, "hops": len(walked),
                                      "engine_calculated_equals_chain_end": calculated.get(entity[child]) == end})
        agree = sum(1 for child in chosen["sample"] if child in entity and
                    calculated.get(entity[child]) is not None and
                    calculated.get(entity[child]) == entity.get(chosen["stated_ultimate"][child]))
    result = {"sample": len(chosen["sample"]), "level1_records": len(level1), "level1_refused": level1_refused,
              "relationship_records": len(links), "relationships_refused": links_refused,
              "outcome": outcome, "per_child": per_child, "engine_calculated_equals_stated": agree, "reviews": reviews, "examples": examples}
    out.mkdir(parents=True, exist_ok=True)
    (out / "chain-check.json").write_text(json.dumps(result, indent=1, default=dict))
    print(json.dumps({k: v for k, v in result.items() if k not in {"per_child", "examples"}}, indent=1, default=dict))
