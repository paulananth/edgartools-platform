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

Both sources arrive as configured readings (`name_frequency.py`, the
`mdm name-census` command): `fold_reading` counts the Golden Copy's and
`document` writes the census. A delta publication is refused there:
uniqueness counted over a delta counts only what changed, and would let a
common name look unique.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from . import cascade as cascaded
from .primitives import NORMALIZERS
from edgar_warehouse.rules import files as rules_files
from edgar_warehouse.workers.source_mapping import read_record

VERSION = "sec-gleif-name-census-v1"
# The normalizers the census counts with, by the versions it records; a rule
# re-derives both keys through the same registered names (`matching.py`).
SEC_NORMALIZER = "normalize_text@sec-legal-form-kept-v1"
GLEIF_NORMALIZER = "normalize_text@legal-form-kept-v1"
sec_legal_form_key = NORMALIZERS[SEC_NORMALIZER]
legal_form_key = NORMALIZERS[GLEIF_NORMALIZER]
# Enough to tell one from several; the rule reads only "exactly one".
CAP = 5


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
