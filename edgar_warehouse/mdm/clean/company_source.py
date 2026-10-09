"""Frozen census acquisition boundary and Company governance constants.

Preparation neither activates source coverage nor allocates/binds identities.
The generated contract and policy are reviewable governance inputs.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
from pathlib import Path

import pyarrow.parquet as pq

from edgar_warehouse.rules import files as rules_files

from .evidence import instant
from .matching import active_rules
from edgar_warehouse.workers.source_mapping import project_record
from .store import Conflict, canonical, digest

SOURCE_CODE = "sec.submissions.company.v1"
# The mapping and the merge rules are data in `rules/`, edited and reviewed as
# files (rules skill ticket 01): the Dataset Contract in
# `rules/sources/sec.submissions.company/source.yaml`, the Mastering Policy in
# `rules/merge/`. The names below stay importable.
CONTRACT = rules_files.mdm_contract("sec.submissions.company", SOURCE_CODE)
FIELDS = CONTRACT["adapter"]["fields"]
ADDRESS_READING = rules_files.load(rules_files.ROOT / "sources/sec.submissions.company/landed-address.yaml")
POLICY = rules_files.policy()
APPROVED_ACTIVATION = next(
    rule for rule in POLICY["automatic_rules"] if rule["rule_id"] == "sec-company-candidate"
)
PROOF = APPROVED_ACTIVATION["proof"]


def _read_bounded(path: Path, maximum: int) -> bytes:
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError(
            "Source file exceeds preparation budget; partition its publication"
        )
    return raw


def _read_manifest(root: Path, manifest: str) -> tuple[dict, bytes]:
    path = Path(manifest).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Landing manifest must be inside its root")
    raw = _read_bounded(path, 1024 * 1024)
    landing = json.loads(raw)
    if (
        landing.get("schema_version") != 1
        or landing.get("target") != "silver_landing"
        or not landing.get("run_id")
    ):
        raise ValueError("Unsupported landing manifest contract")
    return landing, raw


def _read_member(
    root: Path, landing: dict, table_name: str, required: set[str]
) -> tuple[dict, bytes, pq.ParquetFile]:
    """The one pinned file a landing run wrote for `table_name`, checked."""
    members = [t for t in landing["tables"] if t["table_name"] == table_name]
    if len(members) != 1 or members[0].get("file_count") != 1:
        raise ValueError(
            f"Require one explicit {table_name} member; multi-file landing needs "
            "a partition contract"
        )
    member = members[0]
    path = (root / member["relative_path"]).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Landing member escapes its root")
    raw = _read_bounded(path, 64 * 1024 * 1024)
    parquet = pq.ParquetFile(io.BytesIO(raw))
    if parquet.metadata.num_rows != member["row_count"]:
        raise Conflict("Landing member row count disagrees with its manifest")
    if not required <= set(parquet.schema_arrow.names):
        raise ValueError(
            f"{table_name} landing schema is missing required evidence columns"
        )
    return member, raw, parquet


def _business_addresses(landing: dict, parquet: pq.ParquetFile) -> dict[int, dict]:
    """Each CIK's business address postcode and country, from its own capture.

    SEC writes a state code where a country belongs; a state means the United
    States (`names.edgar_jurisdiction`). A foreign address carries its EDGAR
    country code in `countryCode` instead and leaves `stateOrCountry` empty
    (Shell: "X0"); the two never both hold a value, so the country is read
    from the first, else the second, as the matching rules were measured
    (ticket 14). A landing written before silver kept `country_code` has no
    such column and reads as it always did.
    """
    found: dict[int, dict] = {}
    for batch in parquet.iter_batches(batch_size=10_000):
        for row in batch.to_pylist():
            if row["last_sync_run_id"] != landing["run_id"]:
                raise Conflict("Address row belongs to a different capture run")
            if row["cik"] is None or row["address_type"] != "business":
                continue
            found[int(row["cik"])] = project_record(row, ADDRESS_READING, column="fields")
    return found




# Where each captured SEC document was written: the write receipts a capture
# run records in bookkeeping (`pipeline_run.raw_writes_json`), one per
# document (path, sha256). A Company row's raw_object_id is the sha256 of its
# submissions document, so a receipt names its exact bronze object (ticket 10).
RECEIPTS_VERSION = "sec-bronze-receipts-v1"
_SHA256 = re.compile("[0-9a-f]{64}")


def bronze_receipts(run_id: str, raw_writes: list[dict]) -> dict:
    """One capture run's bronze objects, by the sha256 of their bytes.

    A run records every write, and some (filing attachments, ADV manifests)
    carry no sha256: nothing can name them by hash, so they are left out. A
    stated sha256 that is not a lowercase digest is refused. Two receipts with
    one sha256 name byte-identical copies; the first path in sort order is
    kept, so the file is the same however the run listed them.
    """
    found: dict[str, str] = {}
    for write in raw_writes:
        if not isinstance(write, dict) or write.get("sha256") is None:
            continue
        sha, path = write["sha256"], write.get("path")
        if not isinstance(sha, str) or not _SHA256.fullmatch(sha):
            raise Conflict("A bronze write receipt has no lowercase sha256")
        if not isinstance(path, str) or not path:
            raise Conflict("A bronze write receipt names no object")
        found[sha] = min(found.get(sha, path), path)
    return {
        "version": RECEIPTS_VERSION,
        "run_id": run_id,
        "receipts": [{"sha256": k, "object": found[k]} for k in sorted(found)],
    }


def write_bronze_receipts(book, *, run_id: str, output: str) -> dict:
    """Write one capture run's bronze receipts from bookkeeping; never overwrite."""
    from sqlalchemy import text

    with book.connect() as conn:
        run = (
            conn.execute(
                text(
                    "SELECT status, raw_writes_json FROM pipeline_run "
                    "WHERE pipeline_run_id=:id"
                ),
                {"id": run_id},
            )
            .mappings()
            .one_or_none()
        )
    if run is None or run["status"] != "succeeded":
        raise Conflict(f"Capture run {run_id} did not succeed")
    raw = run["raw_writes_json"]
    if not raw:
        raise Conflict(f"Capture run {run_id} recorded no bronze writes")
    body = bronze_receipts(run_id, json.loads(raw))
    data = (canonical(body) + "\n").encode()
    target = Path(output).resolve()
    if target.exists():
        if target.read_bytes() != data:
            raise Conflict("Existing bronze receipts have different content")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)
    return {
        "version": RECEIPTS_VERSION,
        "run_id": run_id,
        "receipts": len(body["receipts"]),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _read_receipts(path: str, run_id: str) -> tuple[bytes, dict[str, str]]:
    raw = _read_bounded(Path(path).resolve(), 256 * 1024 * 1024)
    body = json.loads(raw)
    if body.get("version") != RECEIPTS_VERSION:
        raise Conflict("Unsupported bronze receipts")
    if body.get("run_id") != run_id:
        raise Conflict("The bronze receipts belong to another capture run")
    rebuilt = bronze_receipts(
        run_id,
        [
            {"path": r.get("object"), "sha256": r.get("sha256")}
            for r in body.get("receipts", [])
        ],
    )
    if rebuilt != body:
        raise Conflict("The bronze receipts are not in their canonical form")
    return raw, {r["sha256"]: r["object"] for r in body["receipts"]}


def census_filers(
    *, landing_root: str, landing_manifest: str
) -> tuple[list[tuple[str, str | None, list[str]]], dict]:
    """Every SEC filer in one capture with its former names, for the Name Census.

    The census counts the whole capture, never a sample: a name that looks
    unique in a sample may not be (ticket 08). The population it returns names
    the exact members it read, so a bundle can refuse a census of another
    capture.
    """
    root = Path(landing_root).resolve()
    landing, _ = _read_manifest(root, landing_manifest)
    _, company_raw, company = _read_member(
        root, landing, "sec_company", {"cik", "entity_name", "last_sync_run_id"}
    )
    # Captures written before #764 by the old landing writer, which skipped
    # an empty table, have no former-name member when no filer had a former
    # name: that is none, not an error (mastering to-do 05). Today's writer
    # (bookkeeping/clean/company.py) always writes the member.
    earlier: dict[int, list[str]] = {}
    former_sha256 = None
    if any(t["table_name"] == "sec_company_former_name" for t in landing["tables"]):
        _, former_raw, former = _read_member(
            root,
            landing,
            "sec_company_former_name",
            {"cik", "former_name", "last_sync_run_id"},
        )
        former_sha256 = hashlib.sha256(former_raw).hexdigest()
        for batch in former.iter_batches(batch_size=10_000):
            for row in batch.to_pylist():
                if row["last_sync_run_id"] != landing["run_id"]:
                    raise Conflict("Former-name row belongs to a different capture run")
                if row["cik"] is not None and row["former_name"]:
                    earlier.setdefault(int(row["cik"]), []).append(row["former_name"])
    filers = []
    for batch in company.iter_batches(batch_size=10_000):
        for row in batch.to_pylist():
            if row["last_sync_run_id"] != landing["run_id"]:
                raise Conflict("Company row belongs to a different capture run")
            cik = f"{int(row['cik']):010d}"
            filers.append((cik, row["entity_name"], earlier.get(int(row["cik"]), [])))
    population = {
        "capture_run_id": landing["run_id"],
        "company_member_sha256": hashlib.sha256(company_raw).hexdigest(),
        "former_name_member_sha256": former_sha256,
        "filers": len(filers),
    }
    return filers, population


_ADDRESS_COLUMNS = {
    "cik", "address_type", "street1", "street2", "city", "zip_code", "state_or_country", "last_sync_run_id",
}


def cascade_filers(*, landing_root: str, landing_manifest: str) -> tuple[list, dict]:
    """Every SEC filer in one capture as the cascade reads it (ticket 21):
    the row with its business address, through the SEC contract and its data
    quality rule, as `normalize` reads a Company record. Every filer counts,
    a Company or not: each can hold a name another would match. A filer the
    quality rule makes an exception never merges and is left out.
    """
    root = Path(landing_root).resolve()
    landing, _ = _read_manifest(root, landing_manifest)
    _, _, company = _read_member(root, landing, "sec_company", {"cik", "entity_name", "last_sync_run_id"})
    _, address_raw, addresses = _read_member(root, landing, "sec_company_address", _ADDRESS_COLUMNS)
    business = _business_addresses(landing, addresses)
    filers = []
    for batch in company.iter_batches(batch_size=10_000):
        for row in batch.to_pylist():
            if row["last_sync_run_id"] != landing["run_id"]:
                raise Conflict("Company row belongs to a different capture run")
            if found := cascade_filer(row, business.get(int(row["cik"]))):
                filers.append(found)
    return filers, {"address_member_sha256": hashlib.sha256(address_raw).hexdigest()}


def cascade_filer(row: dict, business: dict | None):
    """One landed Company row and its business address as the cascade reads
    it, through the SEC contract and its data quality rule; None when the
    quality rule makes it an exception, which never merges. The census and
    the proof (`21-cascade.py`) both read filers here."""
    from . import cascade
    from .adapters import UnsupportedRecord, mapped_values

    try:
        fields, matching, quality = mapped_values({**row, "business_address": business}, CONTRACT)
    except UnsupportedRecord:
        return None
    return cascade.filer_of(cascade.record(f"{int(row['cik']):010d}", fields, matching, quality))


def write_name_census(
    *,
    landing_root: str,
    landing_manifests: list[str],
    gleif_archive: str,
    gleif_metadata: str,
    gleif_sha256: str,
    output: str,
) -> dict:
    """Count SEC captures and one full GLEIF Golden Copy into a census file.

    A name is unique only if it is unique among all SEC filers (ticket 08), so
    a census counts every capture it is given: the whole SEC population may be
    captured in several runs of at most 1,000 filers (ticket 26). A filer in
    two captures would make its own name look shared, so it is refused. One
    capture keeps the census exactly as before.

    An existing census is never overwritten with different content.
    """
    from . import cascade as cascaded
    from .gleif_source import dataset_contract
    from .name_census import build

    if not landing_manifests:
        raise Conflict("A Name Census counts at least one SEC capture")
    filers, captures = [], []
    for landing_manifest in landing_manifests:
        counted, capture = census_filers(landing_root=landing_root, landing_manifest=landing_manifest)
        filers.extend(counted)
        captures.append(capture)
    if len(captures) > 1 and len({cik for cik, _, _ in filers}) != len(filers):
        raise Conflict("A filer is in two of the census's captures")
    population = captures[0] if len(captures) == 1 else {"captures": captures, "filers": len(filers)}
    # The cascade's passes (ticket 21), from the Company rules. The census
    # runs them only once one is switched on (ticket 20); until then it and
    # every record it feeds are as before. It runs every declared pass, in
    # order: an earlier pass's answer never depends on a later one.
    spec = cascaded.spec(POLICY)
    cascade = None
    if spec["passes"] and any(
        t["primitive"] == cascaded.TEST for _, rule in active_rules(POLICY) for t in rule["when"]
    ):
        if len(landing_manifests) != 1:
            # Ticket 20 extends the cascade's addresses to several captures.
            raise Conflict("A cascade pass needs a census of one capture")
        cascade_population, pinned = cascade_filers(
            landing_root=landing_root, landing_manifest=landing_manifests[0]
        )
        population = {**population, **pinned}
        cascade = {"spec": spec, "filers": cascade_population, "gleif_contract": dataset_contract("level1")}
    metadata = json.loads(Path(gleif_metadata).read_text())
    with Path(gleif_archive).open("rb") as archive:
        census = build(
            filers=filers,
            sec_population=population,
            gleif_archive=archive,
            gleif_metadata=metadata,
            gleif_sha256=gleif_sha256,
            cascade=cascade,
        )
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
    return {
        "version": census["version"],
        "sha256": digest(census),
        "sec": census["sec"],
        "gleif": census["gleif"],
        "entries": len(census["entries"]),
    }


# Ticket 08, the SEC-to-GLEIF matching rules, measured on bronze and the
# pinned GLEIF Golden Copy and passing (`rules/merge/pending-proofs.yaml`).
# Ticket 25 switched both on: `merge/policy.yaml` carries each proof with the
# operator's approval.
NAME_PROOFS = rules_files.pending_proofs()
