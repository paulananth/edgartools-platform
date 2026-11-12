"""The waterfall pass: pair SEC filers with GLEIF entities, strictest comparison first (ticket 202, step A).

It runs the existing passes (`cascade.assign`) over the same two whole sources. It replaces the answer that a
separate file once put on each SEC record. Its inputs are the SEC Company records already in the store and the
whole GLEIF publication, counted once. Nothing here reads a capture or a file."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import replace

from edgar_warehouse.rules import files as rules_files
from edgar_warehouse.workers import source_readings

from . import cascade
from .gleif_publication import validate_metadata
from .store import Conflict

GLEIF_READING = rules_files.ROOT / "sources/gleif/name-count-complete-stream.yaml"
# The recipe's own spool and output limits: 13.25 GB expanded projects to about 211 MB and 3.3 million rows.
GLEIF_BYTES = 1024**3
GLEIF_ROWS = 10_000_000
CONTRACT_BYTES = 1024**2


def filers_from_records(records: Iterable[dict]) -> list[cascade.Filer]:
    """The SEC Company records as the store holds them, each as the passes read a filer."""
    return [cascade.filer_of(record) for record in records]


def stored_filers(store, source_code: str) -> list[cascade.Filer]:
    """Every SEC Company record the store holds for `source_code`, each as a filer. The store keeps a record's
    body as text; one already parsed is read as it is."""
    bodies = store.rows("select body from mastering_record where source_code=%s", [source_code])
    return filers_from_records(json.loads(body) if isinstance(body, str) else body for (body,) in bodies)


def assignments(filers: Iterable[cascade.Filer], entities: Iterable[cascade.Entity], passes: list[dict], *,
                gleif_addresses: Counter, over_shared: int) -> dict[str, dict]:
    """CIK -> the entity it pairs with, one to one. An address is counted over every filer and every GLEIF
    entity, not only the candidates in hand, so `gleif_addresses` is the whole publication's count."""
    filers = list(filers)
    counts = cascade.count_addresses(f.place for f in filers) + Counter(gleif_addresses)
    return cascade.assign(filers, entities, passes, address_counts=counts, over_shared=over_shared)


def fold_reading(readings, *, cascade_wanted: set, address_counts) -> tuple[dict, dict, list]:
    """What the configured complete reading of the Golden Copy counted.

    `readings` yields the reading's tables (`name-count-complete-stream.yaml`), in
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
                    entities[lei] = cascade.Entity(lei, keys, cascade.place(seen["place"]), seen["jurisdiction"],
                                                    seen["eligible"], seen["last_update"], seen["legal"])
                    position[lei] = index
                elif index == position[lei]:
                    entities[lei] = replace(entities[lei], keys=entities[lei].keys | keys)
        for row in tables["d_addresses"]:
            address_counts[(row["street"], row["postcode"], row["country"])] += 1
    return legal, other, list(entities.values())


def wanted_names(filers: Iterable[cascade.Filer]) -> set[str]:
    """The name keys the whole-publication reading keeps: the filers' current names (an empty key is no name)."""
    return {filer.key for filer in filers} - {""}


def over_publication(filers: Iterable[cascade.Filer], readings, passes: list[dict], *, over_shared: int) -> dict:
    """The waterfall pass over the whole publication: fold its tables for the filers' names, then pair."""
    filers = list(filers)
    gleif_addresses: Counter = Counter()
    _, _, entities = fold_reading(readings, cascade_wanted=wanted_names(filers), address_counts=gleif_addresses)
    return assignments(filers, entities, passes, gleif_addresses=gleif_addresses, over_shared=over_shared)


def publication_chunks(reading: dict, artifacts, metadata: dict, wanted: set) -> tuple[dict, object]:
    """The verified Golden Copy reading, bound to its recipe, the full publication and the names asked for: the
    publication's identity and its tables in source order. The reading's `wanted` lookup must equal the names the
    pass uses, or its entities are another population's."""
    validate_metadata("level1", metadata)
    if metadata["file_content"] != "GLEIF_FULL_PUBLISHED":
        raise Conflict("The waterfall pass reads a full Golden Copy, never a delta")
    artifact, chunks = _publication_projection(reading, artifacts, metadata["record_count"], wanted)
    publication = {"archive_sha256": artifact["input"]["sha256"], "content_date": metadata["content_date"],
                   "file_content": metadata["file_content"], "record_count": artifact["record_count"]}
    return publication, chunks


def _publication_projection(reading, artifacts, expected_records, wanted):
    """The recipe, count, lookup and complete traversal checks shared by both authority paths."""
    opened = source_readings.OpenedExtract(reading, artifacts, max_bytes=GLEIF_BYTES, max_rows=GLEIF_ROWS,
                                          max_contract_bytes=CONTRACT_BYTES, allow_lookup_receipts=True)
    if opened.contract != rules_files.load(GLEIF_READING):
        raise Conflict("The Golden Copy reading was not made by name-count-complete-stream.yaml")
    (artifact,) = opened.artifacts
    if artifact["record_count"] != expected_records:
        raise Conflict("The Golden Copy reading and its publication disagree on the record count")
    if set(opened.lookup_sets(0)["wanted"]) != wanted:
        raise Conflict("The Golden Copy reading projected other names than the filers in the store hold")
    return artifact, (chunk["tables"] for _, _, chunk, _ in opened.chunks())


def pairs(filers: Iterable[cascade.Filer], reading: dict, artifacts, metadata: dict, passes: list[dict], *,
          over_shared: int) -> tuple[dict, dict]:
    """The publication's identity and the CIK -> pair answer of the whole publication, for the filers in hand."""
    filers = list(filers)
    publication, chunks = publication_chunks(reading, artifacts, metadata, wanted_names(filers))
    return publication, over_publication(filers, chunks, passes, over_shared=over_shared)


def declared_pairs(filers: Iterable[cascade.Filer], reading: dict, artifacts, expected_records: int,
                   passes: list[dict], *, over_shared: int) -> tuple[dict, dict]:
    """A source-declared complete capture, without independent publisher metadata.

    Preserve the pinned recipe, EOF/count and population checks. The receipt deliberately
    makes no publisher-time or provider-completeness claim; callers with that authority
    continue to use `pairs` and its metadata validation.
    """
    if type(expected_records) is not int or not 0 <= expected_records <= GLEIF_ROWS:
        raise Conflict("Invalid complete-capture record count")
    filers = list(filers)
    artifact, chunks = _publication_projection(reading, artifacts, expected_records, wanted_names(filers))
    publication = {"archive_sha256": artifact["input"]["sha256"], "record_count": expected_records,
                   "evidence": "source-declared-complete-capture"}
    return publication, over_publication(filers, chunks, passes, over_shared=over_shared)
