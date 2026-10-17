"""GLEIF's sub-fund pairs (ticket 23): each fund and the umbrella it is a sub-fund of.

gleif/subfund-pairs.yaml on an invented relationship file: only an active
IS_SUBFUND_OF record gives a pair, from its start node (the fund) to its end
node (the umbrella). Invented LEIs only.
"""

from __future__ import annotations

import io
import json
import zipfile

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files
from edgar_warehouse.workers import source_read, source_readings

FUND, UMBRELLA, OTHER = "9999000000EXAMPLE016", "9999000000EXAMPLE113", "9999000000EXAMPLE210"


def relation(start: str, end: str, kind: str, status: str) -> dict:
    return {"RelationshipRecord": {"Relationship": {
        "StartNode": {"NodeID": {"$": start}, "NodeIDType": {"$": "LEI"}},
        "EndNode": {"NodeID": {"$": end}, "NodeIDType": {"$": "LEI"}},
        "RelationshipType": {"$": kind}, "RelationshipStatus": {"$": status}}}}


def test_only_an_active_subfund_record_gives_a_fund_and_its_umbrella(tmp_path):
    body = io.BytesIO()
    with zipfile.ZipFile(body, "w") as z:
        z.writestr("rr.json", json.dumps({"relations": [
            relation(FUND, UMBRELLA, "IS_SUBFUND_OF", "ACTIVE"),
            relation(OTHER, UMBRELLA, "IS_SUBFUND_OF", "INACTIVE"),
            relation(OTHER, FUND, "IS_FUND-MANAGED_BY", "ACTIVE")]}))
    store = Artifacts()
    raw = store.put_bytes((tmp_path / "rr.zip").as_uri(), body.getvalue())
    contract = store.put(tmp_path.as_uri(), files.load(files.ROOT / "sources/gleif/subfund-pairs.yaml"))
    context = store.put(tmp_path.as_uri(), {"version": 1, "input": raw, "values": {}})
    manifest = store.put(tmp_path.as_uri(), {"version": 2, "contract": contract,
                                             "artifacts": [{"input": raw, "context": context}]})
    task = {"input": manifest, "output": (tmp_path / "reading.json").as_uri(), "checks": ["source.output"]}
    out = source_read.execute(task, store)
    assert source_read.verify({**task, "candidate": out}, store) == ({"source.output": True}, [])
    (artifact,) = source_readings.load(out, store, max_bytes=1 << 24, max_rows=100)[0]["artifacts"]
    assert artifact["tables"]["subfund"] == [{"fund": FUND, "umbrella": UMBRELLA}]
