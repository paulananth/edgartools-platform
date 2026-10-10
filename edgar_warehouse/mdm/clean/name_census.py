"""The Name Census: who else carries a name, across both whole sources.

Company mastering ticket 08. The SEC-to-GLEIF matching rules bind a GLEIF
record to an SEC Company only when their names, legal form kept, are equal
and **no other** SEC filer or GLEIF legal entity carries that name. A Stage
holds a bounded scope, so it cannot count "no other". The census counts it
once, over the whole SEC capture and the whole GLEIF Golden Copy, and the SEC
bundle pins it as evidence, as ticket 12 pinned the ticker catalog.

The census only **proposes** a pair; it decides nothing. The Merge Stage
re-derives both name keys from the Stage rows and checks the jurisdiction or
postcode itself (`matching.py`).

What it counts, per the measured rules (`.scratch/company-mastering/research/
08-draft-rule.md`):
- SEC: every filer's current **and former** names;
- GLEIF: every record's legal **and other** names, branches excluded (a branch
  carries its head office's name and is not a legal entity);
- a match is the SEC current name against a GLEIF **legal** name.

It refuses a delta publication: uniqueness counted over a delta counts only
what changed, and would let a common name look unique.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from typing import BinaryIO

from . import cascade as cascaded
from .adapters import UnsupportedRecord, mapped_values
from .gleif_publication import attest_publication
from .primitives import NORMALIZERS
from edgar_warehouse.rules import files as rules_files
from edgar_warehouse.workers.source_mapping import project_record, read_record

from .store import Conflict

VERSION = "sec-gleif-name-census-v1"
# The normalizers the census counts with, by the versions it records; a rule
# re-derives both keys through the same registered names (`matching.py`).
SEC_NORMALIZER = "normalize_text@sec-legal-form-kept-v1"
GLEIF_NORMALIZER = "normalize_text@legal-form-kept-v1"
sec_legal_form_key = NORMALIZERS[SEC_NORMALIZER]
legal_form_key = NORMALIZERS[GLEIF_NORMALIZER]
# Enough to tell one from several; the rule reads only "exactly one".
CAP = 5


GLEIF_READING = rules_files.load(rules_files.ROOT / "sources/gleif/census-record.yaml")
GLEIF_IDENTITY = rules_files.load(rules_files.ROOT / "sources/gleif/census-identity.yaml")
GLEIF_UPDATE = rules_files.load(rules_files.ROOT / "sources/gleif/census-update.yaml")
SEC_READING = rules_files.load(rules_files.ROOT / "sources/sec.submissions.company/census-filer.yaml")


def _sec_population(filers):
    held: dict[str, set] = defaultdict(set)
    wanted = set()
    for cik, name, former in filers:
        reading = read_record({"name": name, "former": former}, SEC_READING)
        for table in ("current", "former"):
            for row in reading.tables[table]:
                if key := row["key"]:
                    held[key].add(cik)
                    if table == "current":
                        wanted.add(key)
    return held, wanted


def _gleif_other_keys(row):
    reading = read_record(row, GLEIF_READING)
    return [r["key"] for table in ("other", "transliterated") for r in reading.tables[table]]


def cascade_entity(row: dict, cascade: dict, wanted: set):
    """One native Level 1 record as the cascade reads it (ticket 21): through
    the GLEIF contract and its data quality rule, with its legal and other
    names; None when it is not GENERAL or the quality rule makes it an
    exception. The census and the proof (`21-cascade.py`) both read here."""
    lei = project_record(row, GLEIF_IDENTITY, column="lei")["value"]
    if not lei or project_record(row, GLEIF_IDENTITY, column="category")["value"] != "GENERAL":
        return None
    try:
        fields, matching, quality = mapped_values(row, cascade["gleif_contract"])
    except UnsupportedRecord:
        return None
    key = project_record(row, GLEIF_IDENTITY, column="key")["value"]
    other_keys = _gleif_other_keys(row)
    return cascaded.entity_of(
        cascaded.record(lei, fields, matching, quality, {"lei": lei}),
        frozenset([key, *other_keys]) & wanted,
        eligible=cascaded.eligible(fields, cascade["spec"]),
    )


def build(
    *,
    filers: list[tuple[str, str | None, list[str]]],
    sec_population: dict,
    gleif_archive: BinaryIO,
    gleif_metadata: dict,
    gleif_sha256: str,
    cascade: dict | None = None,
) -> dict:
    """The census document, bound to the exact inputs it counted.

    `filers` is every SEC filer in the capture: (CIK, current name, former
    names). `sec_population` names that capture (run, member hashes, count).

    With `cascade` ({"spec", "filers", "gleif_contract"}: the passes from the
    Company rules, every SEC filer as a `cascade.Filer`, the GLEIF Level 1
    contract), it also runs the cascade (ticket 21) over both whole sources
    and records each CIK's answer. Every GENERAL GLEIF record is read through
    the contract and its quality rule, as the reader reads it, and counts
    toward the over-shared addresses; one sharing a name with a filer is a
    candidate.
    """
    if gleif_metadata.get("file_content") != "GLEIF_FULL_PUBLISHED":
        raise Conflict("The Name Census counts a full Golden Copy, never a delta")
    if sec_population.get("filers") != len(filers):
        raise Conflict("The Name Census SEC population disagrees with its filers")
    by_key, wanted = _sec_population(filers)
    legal: dict[str, dict[str, str]] = defaultdict(dict)
    other: dict[str, set] = defaultdict(set)
    passes = bool(cascade and cascade["spec"]["passes"])
    if passes:
        cascade_wanted = {f.key for f in cascade["filers"]} - {""}
        counts = cascaded.count_addresses(f.place for f in cascade["filers"])
        entities: list = []

    def on_record(row: dict, _ordinal: int) -> None:
        if project_record(row, GLEIF_IDENTITY, column="category")["value"] == "BRANCH":
            return
        lei = project_record(row, GLEIF_IDENTITY, column="lei")["value"]
        if not lei:
            return
        key = project_record(row, GLEIF_IDENTITY, column="key")["value"]
        if key in wanted:
            last = project_record(row, GLEIF_UPDATE, column="updated")["value"]
            legal[key][lei] = last or ""
        for other_key in _gleif_other_keys(row):
            if other_key in wanted and other_key != key:
                other[other_key].add(lei)
        if passes and (found := cascade_entity(row, cascade, cascade_wanted)):
            if found.place.key:
                counts[found.place.key] += 1
            if found.keys & cascade_wanted:
                entities.append(found)

    report = attest_publication(
        gleif_archive,
        member="level1",
        metadata=gleif_metadata,
        expected_sha256=gleif_sha256,
        on_record=on_record,
    )
    gleif = {
        "archive_sha256": gleif_sha256,
        "content_date": gleif_metadata["content_date"],
        "file_content": gleif_metadata["file_content"],
        "record_count": report["record_count"],
    }
    return document(
        sec_population=sec_population,
        gleif=gleif,
        held=by_key,
        wanted=wanted,
        legal=legal,
        other=other,
        cascade=cascade if passes else None,
        entities=entities if passes else (),
        address_counts=counts if passes else None,
    )


def fold_reading(readings, *, cascade_wanted: set, address_counts) -> tuple[dict, dict, list]:
    """What the configured complete reading of the Golden Copy counted.

    `readings` yields the reading's tables (`census-complete-stream.yaml`), in
    source order: legal holders with their last update (a later record wins),
    other-name holders, and for every supported GENERAL record its cascade
    view. A candidate is an entity holding a filer's name; the same LEI later
    in the source replaces it, and its other rows in one record add their
    names. Every supported GENERAL address adds to `address_counts`.
    Returns (legal, other, candidates in first-seen order).
    """
    legal: dict[str, dict[str, str]] = defaultdict(dict)
    other: dict[str, set] = defaultdict(set)
    entities: dict = {}
    position: dict[str, int] = {}
    for tables in readings:
        for row in tables["a_legal"]:
            legal[row["key"]][row["lei"]] = row["updated"] or ""
        for table in ("b_other", "c_transliterated"):
            for row in tables[table]:
                other[row["key"]].add(row["lei"])
        for table in ("a_legal", "b_other", "c_transliterated"):
            for row in tables[table]:
                seen = row["cascade"]
                if seen is None:
                    continue
                keys = frozenset({seen["legal"], *([row["key"]] if row["key"] in cascade_wanted else [])}) - {""}
                if not keys & cascade_wanted:
                    continue
                lei, index = seen["lei"], row["source_index"]
                if index > position.get(lei, -1):
                    entities[lei] = cascaded.Entity(lei, keys, cascaded.place(seen["place"]), seen["jurisdiction"],
                                                    seen["eligible"], seen["last_update"], seen["legal"])
                    position[lei] = index
                elif index == position[lei]:
                    entities[lei] = replace(entities[lei], keys=entities[lei].keys | keys)
        for row in tables["d_addresses"]:
            address_counts[(row["street"], row["postcode"], row["country"])] += 1
    return legal, other, list(entities.values())

def document(
    *,
    sec_population: dict,
    gleif: dict,
    held: dict[str, set],
    wanted: set,
    legal: dict[str, dict[str, str]],
    other: dict[str, set],
    cascade: dict | None,
    entities,
    address_counts,
) -> dict:
    """The census document from what was counted, however it was read.

    `held` is each SEC name key's CIKs and `wanted` the current-name keys;
    `legal` each wanted key's GLEIF legal holders with their last update,
    `other` the entities holding it only as another name; with `cascade`, the
    candidate `entities` and the global `address_counts` the passes read.
    """
    entries = {}
    for key in sorted(wanted):
        leis = legal.get(key, {})
        entries[key] = {
            "ciks": sorted(held[key])[:CAP],
            "cik_count": len(held[key]),
            "leis": [[lei, leis[lei]] for lei in sorted(leis)[:CAP]],
            "lei_count": len(leis),
            # Another legal entity whose other name is this one, not counting
            # an entity that also holds it as its legal name.
            "other_name_holders": len(other.get(key, set()) - set(leis)),
        }
    result = {
        "version": VERSION,
        "normalizers": {"sec": SEC_NORMALIZER, "gleif": GLEIF_NORMALIZER},
        "sec": sec_population,
        "gleif": gleif,
        "entries": entries,
    }
    if cascade is not None:
        spec = cascade["spec"]
        result["cascade"] = {
            **spec,
            "assignments": cascaded.assign(
                cascade["filers"],
                entities,
                spec["passes"],
                address_counts=address_counts,
                over_shared=spec["over_shared"],
            ),
        }
    return result

def entry(census: dict, name: str | None, *, census_digest: str) -> dict | None:
    """What one SEC record carries: its census entry, bound to the census.

    None when the census has no entry for the name, so the rule defers. The
    digest is computed once by the caller; the census is large.
    """
    key = sec_legal_form_key(name)
    found = census["entries"].get(key)
    if not key or found is None:
        return None
    return {"census": census_digest, "version": census["version"], "key": key, **found}
