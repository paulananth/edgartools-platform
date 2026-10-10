"""GLEIF Golden Copy equivalence: the older reader against the configured contract (L6).

Every record of one pinned Golden Copy member is read twice, as if in scope: by
`gleif_source.record_evidence` under the approved contract, and by `adapters.normalize`
under the contract carrying the refusals, the record's own time and the whole record.
The approved contract is the configured one peeled of those additions, by the same
peel `tests/mdm/test_rules_config_digests.py` asserts. Each pair must reach the same
outcome: the same assertion id (a digest of the whole body, relationships included),
or a deferral with the same reason. Test-only; no caller changes.

    EQUIVALENCE_MEMBER=relationships EQUIVALENCE_LIMIT=20000 \
        uv run python crates/source-contract/tests/qualification/gleif_equivalence.py <out.json>

`EQUIVALENCE_MEMBER` is level1 (default), relationships or reporting_exceptions.
`EQUIVALENCE_SHARD=k/n` compares only the records whose zero-based position is k modulo n,
so n processes cover the whole file; every process still reads the whole archive.
"""
import json, os, sys, time, zipfile
from collections import Counter
from pathlib import Path

from edgar_warehouse.control_contract import digest
from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord, normalize
from edgar_warehouse.mdm.clean.gleif_source import dataset_contract, record_evidence
from edgar_warehouse.rules import source_engine
from tests.mdm.test_rules_config_digests import WITH_CONFIGURED_READING, _without_refusals

FOLDER = Path("~/.local/share/edgartools/clean-mdm/research/gleif-20260911-1600/").expanduser()
MEMBERS = {  # member: (archive, its sha256, JSON wrapper, record count, source code)
    "level1": ("01-20260911-1600-gleif-goldencopy-lei2-golden-copy.json.zip",
               "1b6cd9cda3f94269fd406ee481842ea042b699e95eb5b8124b1496d4fda36a6a", "records", 3428477),
    "relationships": ("01-20260911-1600-gleif-goldencopy-rr-golden-copy.json.zip",
                      "089a2513d2b5d78fc6359c87ef4bc25a56ac7f58d6b3cb740b954e3ecd2bd0c3", "relations", 487721),
    "reporting_exceptions": ("01-20260911-1600-gleif-goldencopy-repex-golden-copy.json.zip",
                             "f205fd8dfc8dc04587fcd2465b741562bf39af3835916314b96033982023e831", "exceptions",
                             6351397),
}

member = os.environ.get("EQUIVALENCE_MEMBER", "level1")
name, pinned, wrapper, expected = MEMBERS[member]
ARCHIVE = FOLDER / name
SOURCE = f"gleif.{member}.v1"
configured = dataset_contract(member)
approved = _without_refusals(configured)
assert digest(approved) == WITH_CONFIGURED_READING[member], digest(approved)


class Everything:
    """Every LEI is in scope: the comparison is of the readers, not of the scope."""

    def __contains__(self, _):
        return True


def sha256(path):
    import hashlib
    found = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            found.update(block)
    return found.hexdigest()


SHA256 = sha256(ARCHIVE)
assert pinned == SHA256, SHA256
PUBLICATION = {"publication_key": "gleif-golden-copy-20260911-1600", "revision": 1, "artifact_sha256": SHA256,
               "member": member}

limit = int(os.environ.get("EQUIVALENCE_LIMIT", "0"))
shard, shards = map(int, os.environ.get("EQUIVALENCE_SHARD", "0/1").split("/"))
read = 0
outcomes, differences, seen = Counter(), [], 0
started = time.perf_counter()


class Done(Exception):
    pass


def older(row, ordinal):
    kind, body = record_evidence(row, member=member, contract=approved, source_code=SOURCE,
                                 eligible_leis=Everything(), publication=PUBLICATION, ordinal=ordinal)
    return ("assertion", body["assertion_id"]) if kind == "assertion" else ("deferred", body["reason"])


def newer(row):
    try:
        return ("assertion", normalize(row, source_code=SOURCE, contract=configured,
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
        differences.append({"ordinal": ordinal, "older": a, "configured": b, "record": row})
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
        source_engine.stream_json_array(stream, wrapper=wrapper, on_record=compare,
                                        max_bytes=17179869184, max_record=1048576, max_records=10000000)
        complete = True
    except Done:
        complete = False
    except source_engine.SourceRejected:
        if not (limit and seen >= limit):
            raise
        complete = False

seconds = time.perf_counter() - started
report = {"member": member, "records": seen, "read": read, "shard": f"{shard}/{shards}", "complete": complete,
          "read_all": read == expected, "seconds": round(seconds, 1),
          "estimate_full_minutes": round(seconds / max(seen, 1) * expected / shards / 60, 1),
          "outcomes": dict(outcomes), "differences": differences, "equal": not differences,
          "approved_contract": digest(approved), "configured_contract": digest(configured), "archive_sha256": SHA256}
Path(sys.argv[1]).write_text(json.dumps(report, indent=1) + "\n")
print(json.dumps({k: v for k, v in report.items() if k != "differences"}), flush=True)
