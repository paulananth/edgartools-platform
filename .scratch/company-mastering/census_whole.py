"""Ticket 148: the whole Name Frequency census, written by the configured reductions,
against the census recorded on 2026-10-12 (`cm27-raw/census.json`), byte for byte.

The GLEIF half reads the captured Golden Copy of 2026-09-11 16:00 through its
configured complete reading (`census-complete-stream.yaml`, the `source.read`
worker and its verifier), projected to the current-name keys the SEC half counts.
The publication metadata is the four values the recorded census holds. Local files
only, no provider request; prints counts and digests only.

    uv run --no-sync python .scratch/company-mastering/census_whole.py \
        <capture> <population> <gleif archive> <recorded census> <work folder>
"""
import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm.clean import name_frequency
from edgar_warehouse.rules import files
from edgar_warehouse.workers import source_read

CAPTURE, POPULATION, ARCHIVE, RECORDED, WORK = (Path(a).expanduser() for a in sys.argv[1:6])
began = time.monotonic()
stamp = lambda: round((time.monotonic() - began) / 60, 1)  # noqa: E731
recorded = json.loads(RECORDED.read_text())
WORK.mkdir(parents=True, exist_ok=True)

# The SEC half's current-name keys: the set the GLEIF reading projects to.
store = Artifacts()
with tempfile.TemporaryDirectory() as scratch:
    readings, _, _, _ = name_frequency._population(CAPTURE, POPULATION, store, Path(scratch))
    _, wanted = name_frequency._sec_counts(store, Path(scratch), readings)
print(json.dumps({"stage": "sec", "wanted": len(wanted), "minutes": stamp()}), flush=True)

# The Golden Copy through its configured reading, executed then verified.
metadata = {"format": "json.zip", "cdf_version": "LEI_3.1", "content_date": recorded["gleif"]["content_date"],
            "file_content": recorded["gleif"]["file_content"], "delta_start": None,
            "record_count": recorded["gleif"]["record_count"]}
(WORK / "metadata.json").write_text(json.dumps(metadata))
source = store.put_bytes(ARCHIVE.as_uri(), ARCHIVE.read_bytes())
assert source["sha256"] == recorded["gleif"]["archive_sha256"], "not the recorded Golden Copy"
context = store.put(WORK.as_uri(), {"version": 1, "input": source,
                                    "values": {"publication_count": metadata["record_count"]}})
lookups = store.put(WORK.as_uri(), {"version": 1, "input": source, "sets": {"wanted": sorted(wanted)}})
contract = store.put(WORK.as_uri(), files.load(name_frequency.GLEIF_READING))
request = store.put(WORK.as_uri(), {"version": 3, "contract": contract,
                                    "artifacts": [{"input": source, "context": context, "lookups": lookups}]})
task = {"input": request, "output": (WORK / "reading.json").as_uri(), "checks": ["source.output"]}
candidate = source_read.execute(task, store)
print(json.dumps({"stage": "gleif read", "minutes": stamp()}), flush=True)
assert source_read.verify({**task, "candidate": candidate}, store) == ({"source.output": True}, [])
print(json.dumps({"stage": "gleif verified", "minutes": stamp()}), flush=True)

# The census, written by the configured reductions, against the recorded bytes.
output = WORK / "census.json"
name_frequency.write_name_frequency(capture=str(CAPTURE), population=str(POPULATION),
                                    gleif_metadata=str(WORK / "metadata.json"), gleif_reading=candidate,
                                    output=str(output))
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()  # noqa: E731
written = json.loads(output.read_text())
print(json.dumps({"stage": "census", "bytes_equal": output.read_bytes() == RECORDED.read_bytes(),
                  "sha256": digest(output), "recorded_sha256": digest(RECORDED),
                  "entries": len(written["entries"]), "recorded_entries": len(recorded["entries"]),
                  "entries_differing": sum(1 for k in set(written["entries"]) | set(recorded["entries"])
                                           if written["entries"].get(k) != recorded["entries"].get(k)),
                  "minutes": stamp()}), flush=True)
