"""Name Frequency from configured readings, never from a Python re-read.

The census (`name_census.py`) counts who else carries a name across the whole
SEC capture population and the whole GLEIF Golden Copy. Here each SEC capture
is read through its configured Rules (`census-landed-company.yaml`,
`census-landed-former.yaml`, the business address of
`landed-preparation.yaml`) by the `source.read` worker and its verifier, and
the Golden Copy arrives as one verified configured reading
(`census-complete-stream.yaml`). Both are folded and written by the same
`name_census.document` the original builder uses.

The GLEIF reading projected only the names the SEC population holds, so its
`wanted` lookup must equal the name keys counted here; its archive and record
count must equal the full publication's metadata.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files as rules_files
from edgar_warehouse.workers import source_read, source_readings

from . import cascade as cascaded
from . import name_census
from .company_source import POLICY, _read_manifest, _read_member, cascade_filer
from .matching import active_rules
from .store import Conflict, canonical, digest

SEC = rules_files.ROOT / "sources/sec.submissions.company"
GLEIF_READING = rules_files.ROOT / "sources/gleif/census-complete-stream.yaml"
# The saved Golden Copy reading: 13.25 GB expanded projects to about 211 MB
# and 3.3 million rows (whole-source census ticket, 2026-10-09).
GLEIF_BYTES = 1024**3
GLEIF_ROWS = 10_000_000


def _read(store: Artifacts, folder: Path, name: str, raw: bytes, contract: dict) -> dict:
    """One member through its configured reading, executed then verified."""
    source = store.put_bytes((folder / f"{name}.input").as_uri(), raw)
    contract["execution"]["input_sha256s"] = [source["sha256"]]
    request = store.put(folder.as_uri(), {"version": 1, "contract": store.put(folder.as_uri(), contract),
                                          "artifacts": [source]})
    task = {"input": request, "output": (folder / f"{name}.reading.json").as_uri(), "checks": ["source.output"]}
    candidate = source_read.execute(task, store)
    if source_read.verify({**task, "candidate": candidate}, store) != ({"source.output": True}, []):
        raise ValueError("Configured reading verification failed")
    (artifact,) = store.json(candidate)["artifacts"]
    return artifact


def _capture(root: Path, manifest: str, store: Artifacts, folder: Path) -> tuple[list, list, dict, str]:
    """One capture's filers, its cascade filers, its population and address digest."""
    landing, _ = _read_manifest(root, manifest)
    run = landing["run_id"]
    _, company_raw, _ = _read_member(root, landing, "sec_company", {"cik", "entity_name", "last_sync_run_id"})
    company = _read(store, folder, f"{run}-company", company_raw,
                    rules_files.load(SEC / "census-landed-company.yaml"))["tables"]["company"]
    earlier: dict[int, list[str]] = defaultdict(list)
    former_sha256 = None
    # A capture written before #764 has no former-name member when no filer had
    # one: that is none, not an error (mastering to-do 05).
    if any(t["table_name"] == "sec_company_former_name" for t in landing["tables"]):
        _, former_raw, _ = _read_member(root, landing, "sec_company_former_name",
                                        {"cik", "former_name", "last_sync_run_id"})
        former_sha256 = hashlib.sha256(former_raw).hexdigest()
        for row in _read(store, folder, f"{run}-former", former_raw,
                         rules_files.load(SEC / "census-landed-former.yaml"))["tables"]["former"]:
            row = row["row"]
            if row["last_sync_run_id"] != run:
                raise Conflict("Former-name row belongs to a different capture run")
            if row["cik"] is not None and row["former_name"]:
                earlier[int(row["cik"])].append(row["former_name"])
    _, address_raw, address = _read_member(root, landing, "sec_company_address",
                                           {"cik", "address_type", "last_sync_run_id"})
    contract = deepcopy(rules_files.load(SEC / "landed-preparation.yaml")["business_address"])
    if "country_code" in address.schema_arrow.names:
        contract["read"]["parquet"]["columns"].append("country_code")
    business = {int(row["cik"]): row["business_address"]
                for row in _read(store, folder, f"{run}-address", address_raw, contract)["tables"]["business_address"]
                if row["business_address"] is not None}
    filers, candidates = [], []
    for row in company:
        landed = row["row"]
        if landed["last_sync_run_id"] != run:
            raise Conflict("Company row belongs to a different capture run")
        cik = int(landed["cik"])
        filers.append((f"{cik:010d}", landed["entity_name"], earlier.get(cik, [])))
        if found := cascade_filer(landed, business.get(cik)):
            candidates.append(found)
    population = {"capture_run_id": run, "company_member_sha256": hashlib.sha256(company_raw).hexdigest(),
                  "former_name_member_sha256": former_sha256, "filers": len(filers)}
    return filers, candidates, population, hashlib.sha256(address_raw).hexdigest()


def _gleif(reading: dict, store: Artifacts, metadata: dict, wanted: set, cascade_wanted: set, counts) -> tuple:
    """Fold the verified Golden Copy reading, bound to the full publication and this population."""
    if metadata.get("file_content") != "GLEIF_FULL_PUBLISHED":
        raise Conflict("The Name Census counts a full Golden Copy, never a delta")
    header, _ = source_readings._index(deepcopy(reading), store, source_readings.INDEX_BYTES, True)
    (artifact,) = header["artifacts"]
    if artifact["record_count"] != metadata.get("record_count"):
        raise Conflict("The Golden Copy reading and its publication disagree on the record count")
    recipe = rules_files.load(GLEIF_READING)
    entry = {"input": artifact["input"], "context": artifact["context"], "lookups": artifact["lookups"]}
    lookups, _ = source_read._lookups({"version": 3}, entry, store, recipe)
    if set(lookups["wanted"]) != wanted:
        raise Conflict("The Golden Copy reading projected another SEC population's names")
    chunks = (chunk["tables"] for _, _, chunk, _ in source_readings.iter_load(
        reading, store, max_bytes=GLEIF_BYTES, max_rows=GLEIF_ROWS, allow_lookup_receipts=True))
    legal, other, entities = name_census.fold_reading(chunks, cascade_wanted=cascade_wanted, address_counts=counts)
    gleif = {"archive_sha256": artifact["input"]["sha256"], "content_date": metadata["content_date"],
             "file_content": metadata["file_content"], "record_count": artifact["record_count"]}
    return gleif, legal, other, entities


def write_name_frequency(*, landing_root: str, landing_manifests: list[str], gleif_reading: dict,
                         gleif_metadata: str, output: str) -> dict:
    """Count the SEC captures and the configured Golden Copy reading into a census file.

    A name is unique only if it is unique among all SEC filers (ticket 08), so
    every capture given is counted; a filer in two captures would make its own
    name look shared and is refused. With the Company rules' cascade switched
    on, it runs every declared pass over the whole population. An existing
    file is never overwritten with different content.
    """
    if not landing_manifests:
        raise Conflict("A Name Census counts at least one SEC capture")
    root = Path(landing_root).resolve()
    store = Artifacts()
    filers, candidates, captures, addresses = [], [], [], []
    with tempfile.TemporaryDirectory(prefix=".name-frequency-") as scratch:
        folder = Path(scratch)
        for manifest in landing_manifests:
            counted, found, population, address = _capture(root, manifest, store, folder)
            filers.extend(counted)
            candidates.extend(found)
            captures.append(population)
            addresses.append(address)
    if len({cik for cik, _, _ in filers}) != len(filers):
        raise Conflict("A filer is in two of the census's captures")
    sec = captures[0] if len(captures) == 1 else {"captures": captures, "filers": len(filers)}
    spec = cascaded.spec(POLICY)
    on = spec["passes"] and any(t["primitive"] == cascaded.TEST for _, rule in active_rules(POLICY)
                                for t in rule["when"])
    if on and len(captures) == 1:
        sec = {**sec, "address_member_sha256": addresses[0]}
    held, wanted = name_census._sec_population(filers)
    counts = cascaded.count_addresses(f.place for f in candidates) if on else Counter()
    metadata = json.loads(Path(gleif_metadata).read_text())
    gleif, legal, other, entities = _gleif(gleif_reading, store, metadata, wanted,
                                           {f.key for f in candidates} - {""}, counts)
    census = name_census.document(
        sec_population=sec, gleif=gleif, held=held, wanted=wanted, legal=legal, other=other,
        cascade={"spec": spec, "filers": candidates} if on else None,
        entities=entities if on else (), address_counts=counts if on else None)
    data = (canonical(census) + "\n").encode()
    target = Path(output).resolve()
    if target.exists():
        if target.read_bytes() != data:
            raise Conflict("Existing Name Census has different content")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    return {"version": census["version"], "sha256": digest(census), "sec": census["sec"],
            "gleif": census["gleif"], "entries": len(census["entries"])}
