"""Level 1 Golden Copy equivalence: the older reader against the configured contract (L6).

Every record of the pinned Golden Copy is read twice, as if its LEI were in scope:
by `gleif_source.record_evidence` under the approved contract (f53c9c42...), and by
`adapters.normalize` under the contract carrying the refusals, the record's own time
and the whole record. Each pair must reach the same outcome: the same assertion id,
or a deferral with the same reason. Test-only; no caller changes.

    EQUIVALENCE_LIMIT=20000 uv run python crates/source-contract/tests/qualification/gleif_level1_equivalence.py <out.json>

`EQUIVALENCE_SHARD=k/n` compares only the records whose zero-based position is k modulo n,
so n processes cover the whole file; every process still reads the whole archive.
"""
import copy, hashlib, json, os, sys, time, zipfile
from collections import Counter
from pathlib import Path

from edgar_warehouse.control_contract import digest
from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord, normalize
from edgar_warehouse.mdm.clean.gleif_source import dataset_contract, record_evidence
from edgar_warehouse.rules import source_engine

ARCHIVE = Path("~/.local/share/edgartools/clean-mdm/research/gleif-20260911-1600/"
               "01-20260911-1600-gleif-goldencopy-lei2-golden-copy.json.zip").expanduser()
SHA256 = "1b6cd9cda3f94269fd406ee481842ea042b699e95eb5b8124b1496d4fda36a6a"
APPROVED = "f53c9c428b65440b18a4567d363c0075d372fa9db1d661dec5b415d974d73ffe"
PUBLICATION = {"publication_key": "gleif-golden-copy-20260911-1600", "revision": 1, "artifact_sha256": SHA256,
               "member": "level1"}

configured = dataset_contract("level1")
approved = copy.deepcopy(configured)
adapter = approved["adapter"]
adapter.pop("effective_at")
adapter["provenance"] = {"native_record": "_native"}
mapped = adapter["reading"]["read"]["tables"]["mapped"]
mapped.pop("checks")
mapped["columns"] = {k: v for k, v in mapped["columns"].items() if not k.startswith("_")}
assert digest(approved) == APPROVED, digest(approved)

limit = int(os.environ.get("EQUIVALENCE_LIMIT", "0"))
shard, shards = map(int, os.environ.get("EQUIVALENCE_SHARD", "0/1").split("/"))
read = 0
outcomes, differences, seen = Counter(), [], 0
started = time.perf_counter()


class Done(Exception):
    pass


def lei_of(row):
    found = row.get("LEI") if isinstance(row, dict) else None
    found = found.get("$") if isinstance(found, dict) else found
    return found.strip() if isinstance(found, str) else ""


def older(row, ordinal):
    kind, body = record_evidence(row, member="level1", contract=approved, source_code="gleif.level1.v1",
                                 eligible_leis={lei_of(row)}, publication=PUBLICATION, ordinal=ordinal)
    return ("assertion", body["assertion_id"]) if kind == "assertion" else ("deferred", body["reason"])


def newer(row):
    try:
        return ("assertion", normalize(row, source_code="gleif.level1.v1", contract=configured,
                                       publication={**PUBLICATION, "effective_at": None})["assertion_id"])
    except (UnsupportedRecord, ValueError, TypeError) as error:
        return ("deferred", getattr(error, "reason", "invalid_native_field"))


def compare(row, ordinal):
    global seen, read
    read += 1
    if ordinal % shards != shard:
        return
    a, b = older(row, ordinal), newer(row)
    outcomes[f"{a[0]}:{a[1] if a[0] == 'deferred' else 'id'}"] += 1
    if a != b and len(differences) < 50:
        differences.append({"ordinal": ordinal, "lei": lei_of(row), "older": a, "configured": b})
    elif a != b:
        outcomes["more_differences"] += 1
    seen += 1
    if seen % 100000 == 0:
        print(json.dumps({"records": seen, "seconds": round(time.perf_counter() - started), "differences": len(differences)}),
              flush=True)
    if limit and seen >= limit:
        raise Done()


with zipfile.ZipFile(ARCHIVE) as archive, archive.open(archive.infolist()[0]) as stream:
    try:
        receipt = source_engine.stream_json_array(stream, wrapper="records", on_record=compare,
                                                  max_bytes=17179869184, max_record=1048576, max_records=10000000)
        complete = True
    except Done:
        complete = False
    except source_engine.SourceRejected as error:
        if not (limit and seen >= limit):
            raise
        complete = False

seconds = time.perf_counter() - started
report = {"records": seen, "read": read, "shard": f"{shard}/{shards}", "complete": complete, "seconds": round(seconds, 1),
          "estimate_full_minutes": round(seconds / max(seen, 1) * 3428477 / shards / 60, 1),
          "outcomes": dict(outcomes), "differences": differences, "equal": not differences,
          "approved_contract": APPROVED, "configured_contract": digest(configured), "archive_sha256": SHA256}
Path(sys.argv[1]).write_text(json.dumps(report, indent=1) + "\n")
print(json.dumps({k: v for k, v in report.items() if k != "differences"}), flush=True)
