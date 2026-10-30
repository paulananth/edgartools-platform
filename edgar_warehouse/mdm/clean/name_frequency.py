"""Name Frequency from configured readings, never from a Python re-read.

The census (`name_census.py`) counts who else carries a name across the whole
SEC capture population and the whole GLEIF Golden Copy. Each SEC main
submissions document the population names is read from the receipt-bound raw
capture through `census-sec-names.yaml` by the `source.read` worker and its
verifier (each filer's name keys beside its CIK, up to 256 documents a unit),
and the Golden Copy arrives as one verified configured reading
(`census-complete-stream.yaml`). Each half is counted by a configured reduction
(`census-sec-reduction.yaml`, `census-name-reduction.yaml`; ticket 148), and
`name_census.counted_document` writes the census from the counts.

The GLEIF reading projected only the names the SEC population holds, so its
`wanted` lookup must equal the name keys counted here; its archive and record
count must equal the full publication's metadata.

With the matching cascade (`cascade=True`, or any pass switched on), the same
documents also run through the Company chain's own readings and combination
(`census-main.yaml`, `catalog.yaml`, `combine-census-captured.yaml` less its
census groups) and the Company Dataset Contract, so each filer reaches the
cascade as the Merge Stage holds it: its forms and tickers decide its
classification as there (rebuild priorities ticket 09). A record the contract
sets aside never stages, so it is no filer.
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
from edgar_warehouse.workers import source_combine, source_readings

from . import adapters, company_prepare, raw_capture
from . import cascade as cascaded
from . import name_census
from .gleif_publication import validate_metadata
from .matching import active_rules
from .store import Conflict, canonical, digest

SEC_READING = rules_files.ROOT / "sources/sec.submissions.company/census-sec-names.yaml"
SEC_REDUCTION = rules_files.ROOT / "sources/sec.submissions.company/census-sec-reduction.yaml"
GLEIF_READING = rules_files.ROOT / "sources/gleif/census-complete-stream.yaml"
GLEIF_REDUCTION = rules_files.ROOT / "sources/gleif/census-name-reduction.yaml"
# The saved Golden Copy reading: 13.25 GB expanded projects to about 211 MB
# and 3.3 million rows (whole-source census ticket, 2026-10-09).
# The bounds are the recipe's own spool and output limits (`max_spool_bytes`,
# `max_output_rows`), so any reading it can write can be counted.
GLEIF_BYTES = 1024**3
GLEIF_ROWS = 10_000_000
CONTRACT_BYTES = 1024**2
METADATA_BYTES = 64 * 1024
POPULATION_BYTES = 64 * 1024**2
COMPANY, COMPANY_CODE = "sec.submissions.company", "sec.submissions.company.v1"
COMPANY_ROOT = rules_files.ROOT / "sources" / COMPANY
# The run ids and times bound into the cascade's readings and combination: its rows are read
# for the cascade only, never staged.
CASCADE_RUN = "name-frequency"
CASCADE_PINS = {"capture_run": CASCADE_RUN, "catalog_run": CASCADE_RUN, "load_mode": "census", "observed_at": ""}
# A filer's record is read for the cascade only: its publication is never staged.
CASCADE_PUBLICATION = {"publication_key": "name-frequency", "revision": 0, "effective_at": None,
                       "semantics": "patch", "artifact_sha256": "0" * 64, "member": "name-frequency"}
COMBINE_BYTES = 256 * 1024**2
COMBINE_ROWS = 1_000_000


def _cascade_combination() -> dict:
    """The Company chain's own combination (`combine-census-captured.yaml`) without its
    census groups: the census is what is being written, and the cascade reads no census."""
    body = company_prepare.bind(rules_files.load(COMPANY_ROOT / "combine-census-captured.yaml"), {
        "APPROVED_COMPANY_CAPTURE_RUN": CASCADE_RUN, "APPROVED_CATALOG_CAPTURE_RUN": CASCADE_RUN})
    groups = body["combine"]["groups"]
    census = {name for name, group in groups.items() if group["source"] == "census"}
    for name in census:
        del groups[name]
    joins = body["combine"]["tables"]["company"]["joins"]
    for name in [n for n, join in joins.items() if join["group"] in census]:
        del joins[name]
    return body


def _cascade_filers(capture: Path, receipts: dict, keys: list[str], catalog: str, store: Artifacts,
                    folder: Path) -> list[cascaded.Filer]:
    """Every filer as the Merge Stage holds it: the population's documents read by the Company
    chain's `census-main.yaml`, in its units, combined with the exchange catalog (`catalog.yaml`)
    by its combination, each row normalized through the Company Dataset Contract. A record the
    contract sets aside never stages, so it is no filer."""
    main = rules_files.load(COMPANY_ROOT / "census-main.yaml")
    catalog_ref = raw_capture.document(capture, receipts, catalog)
    raw_capture.document_bytes(capture, receipts, catalog)
    _, catalog_reading = raw_capture.read_unit(store, folder, "catalog", rules_files.load(
        COMPANY_ROOT / "catalog.yaml"), [{"input": catalog_ref, "context": store.put(folder.as_uri(), {
            "version": 1, "input": catalog_ref, "values": company_prepare.catalog_context(CASCADE_PINS)})}])
    combination = _cascade_combination()
    contract = rules_files.source(COMPANY)["mdm"][COMPANY_CODE]["contract"]
    policy = rules_files.policy()
    filers = []
    for n, unit in enumerate(company_prepare.main_units(capture, receipts, keys, main["execution"]["max_artifacts"])):
        artifacts = []
        for key in unit:
            ref = raw_capture.document(capture, receipts, key)
            artifacts.append({"input": ref, "context": store.put(folder.as_uri(), {
                "version": 1, "input": ref, "values": company_prepare.main_context(key, receipts, CASCADE_PINS)})})
        _, reading = raw_capture.read_unit(store, folder, f"cascade-main-{n}", deepcopy(main), artifacts)
        combined = _combine(store, folder, f"cascade-combine-{n}", combination,
                            {"main": reading, "catalog_exchange": catalog_reading})
        for artifact, _ in source_readings.iter_artifacts(combined, store, max_bytes=COMBINE_BYTES,
                                                          max_rows=COMBINE_ROWS, allow_lookup_receipts=True):
            for row in artifact["tables"]["company"]:
                try:
                    record = adapters.normalize(row, source_code=COMPANY_CODE, contract=contract, policy=policy,
                                                publication={**CASCADE_PUBLICATION, "record_locator": str(row["cik"])})
                except adapters.UnsupportedRecord:
                    continue
                filers.append(cascaded.filer_of(record))
    return filers


def _combine(store: Artifacts, folder: Path, name: str, contract: dict, readings: dict) -> dict:
    """One `source.combine` unit, executed then verified."""
    request = store.put(folder.as_uri(), {"version": 1, "contract": store.put(folder.as_uri(), contract),
                                          "readings": readings})
    task = {"input": request, "output": (folder / f"{name}.json").as_uri(), "checks": [source_combine.CHECK],
            "keys": {}}
    candidate = source_combine.execute(task, store)
    if source_combine.verify({**task, "candidate": candidate}, store) != ({source_combine.CHECK: True}, []):
        raise ValueError("Configured combination verification failed")
    return candidate


def _population(capture: Path, population: Path, store: Artifacts, folder: Path) -> tuple[list, dict, list, dict]:
    """The population's documents read from the receipt-bound capture (`census-sec-names.yaml`:
    each filer's name keys beside its CIK): the readings, the population's summary, its
    receipt keys and the capture's receipts."""
    receipts_raw, receipts = raw_capture.receipts(capture)
    population_raw = raw_capture.read_bounded(population, POPULATION_BYTES)
    keys = json.loads(population_raw)
    if not isinstance(keys, list) or not keys or len(set(keys)) != len(keys):
        raise Conflict("A population names one or more distinct receipt keys")
    contract = rules_files.load(SEC_READING)
    readings, ciks = [], []
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
        readings.append(reading)
        for artifact in store.json(reading)["artifacts"]:
            (filer,) = artifact["tables"]["current"]
            ciks.append(filer["cik"])
    if len(set(ciks)) != len(ciks):
        raise Conflict("A filer is in the population twice")
    sec = {"receipts_sha256": hashlib.sha256(receipts_raw).hexdigest(),
           "population_sha256": hashlib.sha256(population_raw).hexdigest(), "filers": len(ciks)}
    return readings, sec, keys, receipts


def _reduced(store: Artifacts, folder: Path, name: str, recipe: Path, readings: dict) -> dict[str, list]:
    """A configured reduction (`source.combine`), executed then verified: its groups' rows."""
    contract = rules_files.load(recipe)
    combined = _combine(store, folder, name, contract, readings)
    bound = contract["reduce"]["max_output_bytes"]
    (artifact,) = [artifact for artifact, _ in source_readings.iter_artifacts(
        combined, store, max_bytes=bound, max_rows=contract["reduce"]["max_output_rows"],
        allow_lookup_receipts=True)]
    return artifact["tables"]


def _sec_counts(store: Artifacts, folder: Path, readings: list) -> tuple[dict, set]:
    """Who holds each SEC name key (its CIK count and five smallest CIKs) and the
    current-name keys, from `census-sec-reduction.yaml`. An empty key is no name."""
    tables = _reduced(store, folder, "sec-census", SEC_REDUCTION, {"names": readings})
    held = {row["key"]: (row["cik_count"], [item["cik"] for item in row["ciks"]]) for row in tables["held"]}
    return held, {row["key"] for row in tables["wanted"]} - {""}


def _gleif_counts(store: Artifacts, folder: Path, reading: dict) -> tuple[dict, dict]:
    """Each name key's GLEIF legal holders (count and five smallest with their last
    update) and its other-name holders who are not legal holders, from
    `census-name-reduction.yaml`."""
    tables = _reduced(store, folder, "gleif-census", GLEIF_REDUCTION, {"names": reading})
    legal = {row["key"]: (row["count"], [[item["lei"], item["updated"]] for item in row["holders"]])
             for row in tables["legal"]}
    return legal, {row["key"]: row["count"] for row in tables["other"]}


def _gleif(reading: dict, store: Artifacts, metadata: dict, wanted: set) -> tuple[dict, object]:
    """The verified Golden Copy reading, bound to its recipe, the full publication
    and this population: its census header and its tables in source order."""
    validate_metadata("level1", metadata)
    if metadata["file_content"] != "GLEIF_FULL_PUBLISHED":
        raise Conflict("The Name Census counts a full Golden Copy, never a delta")
    opened = source_readings.OpenedExtract(reading, store, max_bytes=GLEIF_BYTES, max_rows=GLEIF_ROWS,
                                          max_contract_bytes=CONTRACT_BYTES, allow_lookup_receipts=True)
    recipe = rules_files.load(GLEIF_READING)
    if opened.contract != recipe:
        raise Conflict("The Golden Copy reading was not made by census-complete-stream.yaml")
    (artifact,) = opened.artifacts
    if artifact["record_count"] != metadata["record_count"]:
        raise Conflict("The Golden Copy reading and its publication disagree on the record count")
    lookups = opened.lookup_sets(0)
    if set(lookups["wanted"]) != wanted:
        raise Conflict("The Golden Copy reading projected another SEC population's names")
    gleif = {"archive_sha256": artifact["input"]["sha256"], "content_date": metadata["content_date"],
             "file_content": metadata["file_content"], "record_count": artifact["record_count"]}
    return gleif, (chunk["tables"] for _, _, chunk, _ in opened.chunks())


def write_name_frequency(*, capture: str, population: str, gleif_reading: dict, gleif_metadata: str,
                         output: str, cascade: bool = False, catalog: str | None = None) -> dict:
    """Count the SEC population and the configured Golden Copy reading into a census file.

    A name is unique only if it is unique among all SEC filers (ticket 08), so
    the population names every main submissions document counted, each by its
    receipt in the capture. The matching cascade runs when asked (`cascade`)
    and always once a pass is switched on, and reads each filer's tickers from
    the capture's exchange `catalog` (its receipt key); the census then holds
    its answers.
    An existing file is never overwritten with different content.
    """
    policy = rules_files.policy()
    spec = cascaded.spec(policy)
    switched_on = any(t["primitive"] == cascaded.TEST for _, rule in active_rules(policy) for t in rule["when"])
    if (cascade or switched_on) and not spec["passes"]:
        raise Conflict("The matching cascade was asked for, and the Company rules declare no pass")
    runs = cascade or switched_on
    if runs and not catalog:
        raise Conflict("The matching cascade reads each filer's tickers: name the capture's exchange catalog")
    store = Artifacts()
    metadata = json.loads(raw_capture.read_bounded(Path(gleif_metadata).resolve(), METADATA_BYTES))
    with tempfile.TemporaryDirectory(prefix=".name-frequency-") as scratch:
        folder = Path(capture).resolve()
        readings, sec, keys, receipts = _population(folder, Path(population).resolve(), store, Path(scratch))
        cascade_filers = _cascade_filers(folder, receipts, keys, catalog, store, Path(scratch)) if runs else []
        held, wanted = _sec_counts(store, Path(scratch), readings)
        gleif, chunks = _gleif(gleif_reading, store, metadata, wanted)
        legal, other = _gleif_counts(store, Path(scratch), gleif_reading)
        # The cascade's candidates and address counts are its own fold over the same reading.
        cascade, entities, counts = None, (), None
        if runs:
            counts = cascaded.count_addresses(f.place for f in cascade_filers)
            _, _, entities = name_census.fold_reading(
                chunks, cascade_wanted={f.key for f in cascade_filers} - {""}, address_counts=counts)
            cascade = {"spec": spec, "filers": cascade_filers}
    census = name_census.counted_document(sec_population=sec, gleif=gleif, wanted=wanted, held=held, legal=legal,
                                          other=other, cascade=cascade, entities=entities, address_counts=counts)
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
