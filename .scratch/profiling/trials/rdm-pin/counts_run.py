"""Profiling ticket 02: the full mastering counts run, with the pin and with the YAML.

The Mastering Policy pins SEC place codes in RDM (`sec-place-codes` version 1,
PR #848); before, it embedded `rules/reference/sec-place-codes.yaml`. The
YAML is removed only after a full counts run shows the same counts with the
pin (docs/specs/rdm/spec.md §7). Every place-code consumer reads one map,
`names._EDGAR_ISO` (matching, cascade, quality, company source). So this run
masters the same input twice, changing only that map:

- `pin`: the map as main builds it, from the pinned RDM version;
- `yaml`: the map rebuilt from the YAML, as before PR #848.

Input: ticket 27's Proving Run cohort (company mastering), on this machine
only: the seven SEC bundles (6,414 Companies and 586 controls) and the GLEIF
Level 1 records the Name Census names for them (cached from the Golden Copy
of 2026-09-11). Each bundle's manifest names the policy it was prepared under
(`75bd2b67…`); a temporary copy names today's Company policy instead, as
ticket 05's run did. Each variant runs on its own disposable PostgreSQL 16,
the Clean MDM test fixture, and applies everything twice; the second pass
must change nothing. No request to any provider.

    COUNTS_WORK=~/.local/share/edgartools/clean-mdm/proving/cm27 COUNTS_REFERENCE=pin|yaml \\
    COUNTS_OUT=<report.json> uv run --extra mdm pytest -q -s -p no:randomly \\
        .scratch/profiling/trials/rdm-pin/counts_run.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from collections import Counter
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from edgar_warehouse.mdm.clean import names
from edgar_warehouse.mdm.clean.cli import execute_manifest
from edgar_warehouse.mdm.clean.company_source import CONTRACT, POLICY, SOURCE_CODE
from edgar_warehouse.mdm.clean.gleif_source import dataset_contract, record_evidence
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.run import RunCoordinator
from edgar_warehouse.mdm.clean.store import Store, digest, register_policy
from edgar_warehouse.rules import files
from sqlalchemy import text
from tests.integration import test_clean_mdm_postgres as core
from tests.support.rules_authority import register_dataset

postgres = core.postgres
database = core.database

GLEIF = "gleif.level1.v1"
AS_OF = "2026-09-29T15:00:00+00:00"
ARCHIVE_SHA256 = "1b6cd9cda3f94269fd406ee481842ea042b699e95eb5b8124b1496d4fda36a6a"
GLEIF_BATCH = 200


def yaml_map() -> dict:
    """The map exactly as names.py built it before PR #848 (626cf06c), from the YAML."""
    return {code: row["iso"] for code, row in files.reference("sec-place-codes")["codes"].items() if row["iso"]}


def counts(conn) -> dict:
    one = lambda sql: conn.execute(text(sql)).scalar()
    group = lambda sql: {str(k): v for k, v in conn.execute(text(sql)).all()}
    return {
        "identities": group("SELECT kind, count(*) FROM mdm.master_entity GROUP BY kind"),
        "companies_open": one("SELECT count(*) FROM mdm.current_entity WHERE kind='company' AND status<>'alias'"),
        "stage_records": group("SELECT source_code||':'||kind, count(*) FROM mdm.stage_record GROUP BY 1"),
        "stage_bound": group("SELECT source_code, count(*) FROM mdm.stage_record WHERE entity_id IS NOT NULL GROUP BY 1"),
        "waiting": group("SELECT source_code||':'||coalesce(reason,'(none)'), count(*) FROM mdm.stage_waiting GROUP BY 1"),
        "open_reviews": group("SELECT coalesce(body->>'reason','(none)'), count(*) FROM mdm.current_record "
                              "WHERE object_type='review' AND body->'open'='true'::jsonb GROUP BY 1"),
        "decisions_by_rule": group("SELECT coalesce(body->>'rule_id', body->'rule'->>'rule_id', '(none)'), count(*) "
                                   "FROM mdm.decision GROUP BY 1"),
        "relationships": group("SELECT body->>'type', count(*) FROM mdm.current_record "
                               "WHERE object_type='relationship' GROUP BY 1"),
    }


def bindings(conn) -> str:
    """Which record is bound to which master, as one digest (masters renumber per run)."""
    groups: dict[str, list[str]] = {}
    for entity, subject in conn.execute(text(
            "SELECT entity_id::text, subject FROM mdm.stage_record WHERE entity_id IS NOT NULL")):
        groups.setdefault(entity, []).append(subject)
    return digest(sorted(sorted(g) for g in groups.values()))


def test_counts_run(database, tmp_path):
    variant = os.environ["COUNTS_REFERENCE"]
    work = Path(os.environ["COUNTS_WORK"]).expanduser()
    if variant == "yaml":
        names._EDGAR_ISO = yaml_map()
    elif variant != "pin":
        raise SystemExit("COUNTS_REFERENCE is pin or yaml")
    place_map = dict(names._EDGAR_ISO)
    with database.admin.begin() as conn:
        register_dataset(conn, SOURCE_CODE, database.registry, CONTRACT)
        register_dataset(conn, GLEIF, database.registry, dataset_contract("level1"))
        policy = register_policy(conn, POLICY)
    store = Store(database.application)
    coordinator, stage = RunCoordinator(store), MergeStage(store)
    bundles = []
    for n in range(1, 8):
        source, copy = work / "bundles" / f"chunk{n}", tmp_path / f"chunk{n}"
        copy.mkdir()
        for item in source.iterdir():
            if item.name != "manifest.json":
                shutil.copy2(item, copy / item.name)  # a manifest reads only files inside its folder
        manifest = json.loads((source / "manifest.json").read_text())
        manifest["policy_digest"] = policy
        (copy / "manifest.json").write_text(json.dumps(manifest))
        bundles.append(copy)
    timings = []

    def apply_sec() -> None:
        for bundle in bundles:
            started = time.monotonic()
            execute_manifest(store, coordinator, path=str(bundle / "manifest.json"), run_id=str(uuid4()),
                             stage="mastering", limit=1000)
            timings.append({"sec": bundle.name, "seconds": round(time.monotonic() - started, 1)})
            print(json.dumps(timings[-1]), flush=True)

    (cache,) = work.glob("gleif-rows-*.jsonl")
    rows = [tuple(json.loads(line)) for line in cache.open()]
    leis = {row["LEI"]["$"] for _, row in rows}
    publication = {"publication_key": "gleif-golden-copy-20260911-1600", "revision": 1,
                   "artifact_sha256": ARCHIVE_SHA256, "member": "level1"}
    assertions, deferred = [], Counter()
    contract = dataset_contract("level1")
    for ordinal, row in rows:
        kind, result = record_evidence(row, member="level1", contract=contract, source_code=GLEIF,
                                       eligible_leis=leis, publication=publication, ordinal=ordinal)
        (assertions.append(result) if kind == "assertion" else deferred.update([result["reason"]]))

    def apply_gleif(tag: str, checkpoint: int) -> int:
        for i in range(0, len(assertions), GLEIF_BATCH):
            started = time.monotonic()
            stage.apply(batch_id=f"gleif-{tag}-{i // GLEIF_BATCH + 1}", run_id=str(uuid4()), policy_digest=policy,
                        consumer="gleif-counts", expected_checkpoint=checkpoint - 1, checkpoint=checkpoint,
                        as_of=AS_OF, assertions=assertions[i:i + GLEIF_BATCH])
            timings.append({"gleif": f"{tag}-{i // GLEIF_BATCH + 1}", "seconds": round(time.monotonic() - started, 1)})
            print(json.dumps(timings[-1]), flush=True)
            checkpoint += 1
        return checkpoint

    apply_sec()
    following = apply_gleif("first", 1)
    with database.application.connect() as conn:
        first, first_bindings = counts(conn), bindings(conn)
    apply_sec()
    apply_gleif("second", following)
    with database.application.connect() as conn:
        second, second_bindings = counts(conn), bindings(conn)
    report = {
        "ticket": "profiling 02, full mastering counts run",
        "reference": variant,
        "place_map": {"codes": len(place_map), "sha256": digest(sorted(place_map.items()))},
        "policy": policy,
        "gleif_records": len(rows), "gleif_assertions": len(assertions), "gleif_set_aside": dict(deferred),
        "after_first_pass": first, "bindings": first_bindings,
        "second_pass_changed_nothing": first == second and first_bindings == second_bindings,
        "seconds": round(sum(t["seconds"] for t in timings), 1),
    }
    Path(os.environ["COUNTS_OUT"]).write_text(json.dumps(report, sort_keys=True, indent=1) + "\n")
    print(json.dumps(report, indent=1), flush=True)
    assert report["second_pass_changed_nothing"]
