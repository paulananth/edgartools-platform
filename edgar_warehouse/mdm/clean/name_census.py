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
from collections.abc import Iterable
from typing import BinaryIO

from . import cascade as cascaded
from .adapters import UnsupportedRecord, mapped_values
from .gleif_source import inspect_archive
from .primitives import NORMALIZERS
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


def _text(node) -> str | None:
    value = node.get("$") if isinstance(node, dict) else node
    return value.strip() if isinstance(value, str) and value.strip() else None


def _other_names(entity: dict) -> list[str]:
    names = []
    for container, item in (
        ("OtherEntityNames", "OtherEntityName"),
        ("TransliteratedOtherEntityNames", "TransliteratedOtherEntityName"),
    ):
        found = (entity.get(container) or {}).get(item) or []
        for name in found if isinstance(found, list) else [found]:
            if text := _text(name):
                names.append(text)
    return names


def sec_keys(filers: Iterable[tuple[str, str | None, list[str]]]) -> dict[str, set]:
    """Each name key and the CIKs whose current or former name carries it."""
    held: dict[str, set] = defaultdict(set)
    for cik, name, former in filers:
        for text in [name, *former]:
            if key := sec_legal_form_key(text):
                held[key].add(cik)
    return held


def cascade_entity(row: dict, cascade: dict, wanted: set):
    """One native Level 1 record as the cascade reads it (ticket 21): through
    the GLEIF contract and its data quality rule, with its legal and other
    names; None when it is not GENERAL or the quality rule makes it an
    exception. The census and the proof (`21-cascade.py`) both read here."""
    entity = row.get("Entity") or {}
    lei = _text(row.get("LEI"))
    if not lei or _text(entity.get("EntityCategory")) != "GENERAL":
        return None
    try:
        fields, matching, quality = mapped_values(row, cascade["gleif_contract"])
    except UnsupportedRecord:
        return None
    names = [_text(entity.get("LegalName")), *_other_names(entity)]
    return cascaded.entity_of(
        cascaded.record(lei, fields, matching, quality, {"lei": lei}),
        frozenset(legal_form_key(n) for n in names) & wanted,
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
    by_key = sec_keys(filers)
    wanted = {sec_legal_form_key(name) for _, name, _ in filers} - {""}
    legal: dict[str, dict[str, str]] = defaultdict(dict)
    other: dict[str, set] = defaultdict(set)
    passes = bool(cascade and cascade["spec"]["passes"])
    if passes:
        cascade_wanted = {f.key for f in cascade["filers"]} - {""}
        counts = cascaded.count_addresses(f.place for f in cascade["filers"])
        entities: list = []

    def on_record(row: dict, _ordinal: int) -> None:
        entity = row.get("Entity") or {}
        if _text(entity.get("EntityCategory")) == "BRANCH":
            return
        lei = _text(row.get("LEI"))
        if not lei:
            return
        key = legal_form_key(_text(entity.get("LegalName")))
        if key in wanted:
            last = _text((row.get("Registration") or {}).get("LastUpdateDate"))
            legal[key][lei] = last or ""
        for name in _other_names(entity):
            other_key = legal_form_key(name)
            if other_key in wanted and other_key != key:
                other[other_key].add(lei)
        if passes and (found := cascade_entity(row, cascade, cascade_wanted)):
            if found.place.key:
                counts[found.place.key] += 1
            if found.keys & cascade_wanted:
                entities.append(found)

    report = inspect_archive(
        gleif_archive,
        member="level1",
        metadata=gleif_metadata,
        expected_sha256=gleif_sha256,
        on_record=on_record,
    )
    entries = {}
    for key in sorted(wanted):
        leis = legal.get(key, {})
        entries[key] = {
            "ciks": sorted(by_key[key])[:CAP],
            "cik_count": len(by_key[key]),
            "leis": [[lei, leis[lei]] for lei in sorted(leis)[:CAP]],
            "lei_count": len(leis),
            # Another legal entity whose other name is this one, not counting
            # an entity that also holds it as its legal name.
            "other_name_holders": len(other.get(key, set()) - set(leis)),
        }
    document = {
        "version": VERSION,
        "normalizers": {"sec": SEC_NORMALIZER, "gleif": GLEIF_NORMALIZER},
        "sec": sec_population,
        "gleif": {
            "archive_sha256": gleif_sha256,
            "content_date": gleif_metadata["content_date"],
            "file_content": gleif_metadata["file_content"],
            "record_count": report["record_count"],
        },
        "entries": entries,
    }
    if passes:
        spec = cascade["spec"]
        document["cascade"] = {
            **spec,
            "assignments": cascaded.assign(
                cascade["filers"],
                entities,
                spec["passes"],
                address_counts=counts,
                over_shared=spec["over_shared"],
            ),
        }
    return document


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
