"""Name Frequency from configured readings, never from a Python re-read.

The census (`name_census.py`) counts who else carries a name across the whole
SEC capture population and the whole GLEIF Golden Copy. Each SEC main
submissions document the population names is read from the receipt-bound raw
capture through `census-raw.yaml` by the `source.read` worker and its verifier,
two documents a unit, and the Golden Copy arrives as one verified configured
reading (`census-complete-stream.yaml`). Both are folded and written by
`name_census.census`.

The GLEIF reading projected only the names the SEC population holds, so its
`wanted` lookup must equal the name keys counted here; its archive and record
count must equal the full publication's metadata.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files as rules_files
from edgar_warehouse.workers import source_read, source_readings

from . import raw_capture

from . import cascade as cascaded
from . import name_census
from .gleif_publication import validate_metadata
from .matching import active_rules
from .store import Conflict, canonical, digest

SEC_READING = rules_files.ROOT / "sources/sec.submissions.company/census-raw.yaml"
GLEIF_READING = rules_files.ROOT / "sources/gleif/census-complete-stream.yaml"
# The saved Golden Copy reading: 13.25 GB expanded projects to about 211 MB
# and 3.3 million rows (whole-source census ticket, 2026-10-09).
# The bounds are the recipe's own spool and output limits (`max_spool_bytes`,
# `max_output_rows`), so any reading it can write can be counted.
GLEIF_BYTES = 1024**3
GLEIF_ROWS = 10_000_000
CONTRACT_BYTES = 1024**2
METADATA_BYTES = 64 * 1024
POPULATION_BYTES = 64 * 1024**2


def _population(capture: Path, population: Path, store: Artifacts, folder: Path) -> tuple[list, dict]:
    """The filers of the population's documents, each read from the receipt-bound capture."""
    receipts_raw, receipts = raw_capture.receipts(capture)
    population_raw = raw_capture.read_bounded(population, POPULATION_BYTES)
    keys = json.loads(population_raw)
    if not isinstance(keys, list) or not keys or len(set(keys)) != len(keys):
        raise Conflict("A population names one or more distinct receipt keys")
    contract = rules_files.load(SEC_READING)
    filers = []
    for start in range(0, len(keys), contract["execution"]["max_artifacts"]):
        artifacts = []
        for key in keys[start:start + contract["execution"]["max_artifacts"]]:
            if key not in receipts or not key.startswith(raw_capture.BRONZE) or "/main/" not in key:
                raise Conflict(f"The population names a document the capture's receipts do not: {key}")
            document = raw_capture.document(capture, receipts, key)
            context = store.put(folder.as_uri(), {"version": 1, "input": document,
                                                  "values": {"cik": raw_capture.cik(key)}})
            artifacts.append({"input": document, "context": context})
        _, reading = raw_capture.read_unit(store, folder, f"population-{start}", deepcopy(contract), artifacts)
        for reading in store.json(reading)["artifacts"]:
            (filer,) = reading["tables"]["filer"]
            former = [row["name"] for row in reading["tables"]["former"] if row["name"]]
            filers.append((f"{filer['cik']:010d}", filer["name"], former))
    sec = {"receipts_sha256": hashlib.sha256(receipts_raw).hexdigest(),
           "population_sha256": hashlib.sha256(population_raw).hexdigest(), "filers": len(filers)}
    return filers, sec


def _gleif(reading: dict, store: Artifacts, metadata: dict, wanted: set) -> tuple[dict, object]:
    """The verified Golden Copy reading, bound to its recipe, the full publication
    and this population: its census header and its tables in source order."""
    validate_metadata("level1", metadata)
    if metadata["file_content"] != "GLEIF_FULL_PUBLISHED":
        raise Conflict("The Name Census counts a full Golden Copy, never a delta")
    header, _ = source_readings._index(deepcopy(reading), store, source_readings.INDEX_BYTES, True)
    recipe = rules_files.load(GLEIF_READING)
    used = store.verified(header["contract"], max_bytes=CONTRACT_BYTES).decode("utf-8")
    if rules_files.loads(used, str(GLEIF_READING)) != recipe:
        raise Conflict("The Golden Copy reading was not made by census-complete-stream.yaml")
    (artifact,) = header["artifacts"]
    if artifact["record_count"] != metadata["record_count"]:
        raise Conflict("The Golden Copy reading and its publication disagree on the record count")
    entry = {"input": artifact["input"], "context": artifact["context"], "lookups": artifact["lookups"]}
    lookups, _ = source_read._lookups({"version": 3}, entry, store, recipe)
    if set(lookups["wanted"]) != wanted:
        raise Conflict("The Golden Copy reading projected another SEC population's names")
    gleif = {"archive_sha256": artifact["input"]["sha256"], "content_date": metadata["content_date"],
             "file_content": metadata["file_content"], "record_count": artifact["record_count"]}
    return gleif, (chunk["tables"] for _, _, chunk, _ in source_readings.iter_load(
        reading, store, max_bytes=GLEIF_BYTES, max_rows=GLEIF_ROWS, allow_lookup_receipts=True))


def write_name_frequency(*, capture: str, population: str, gleif_reading: dict, gleif_metadata: str,
                         output: str) -> dict:
    """Count the SEC population and the configured Golden Copy reading into a census file.

    A name is unique only if it is unique among all SEC filers (ticket 08), so
    the population names every main submissions document counted, each by its
    receipt in the capture. The matching cascade needs a configured cascade
    reading before it can run here; switched on, it is refused. An existing
    file is never overwritten with different content.
    """
    policy = rules_files.policy()
    spec = cascaded.spec(policy)
    if spec["passes"] and any(t["primitive"] == cascaded.TEST for _, rule in active_rules(policy)
                              for t in rule["when"]):
        raise Conflict("The matching cascade is switched on; Name Frequency has no configured cascade reading yet")
    store = Artifacts()
    with tempfile.TemporaryDirectory(prefix=".name-frequency-") as scratch:
        filers, sec = _population(Path(capture).resolve(), Path(population).resolve(), store, Path(scratch))
    if len({cik for cik, _, _ in filers}) != len(filers):
        raise Conflict("A filer is in the population twice")
    held, wanted = name_census._sec_population(filers)
    metadata = json.loads(raw_capture.read_bounded(Path(gleif_metadata).resolve(), METADATA_BYTES))
    gleif, readings = _gleif(gleif_reading, store, metadata, wanted)
    census = name_census.census(sec_population=sec, gleif=gleif, held=held, wanted=wanted, readings=readings)
    data = (canonical(census) + "\n").encode()
    target = Path(output).resolve()
    if target.exists():
        if raw_capture.read_bounded(target, len(data)) != data:
            raise Conflict("Existing Name Census has different content")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    return {"version": census["version"], "sha256": digest(census), "sec": census["sec"],
            "gleif": census["gleif"], "entries": len(census["entries"])}
