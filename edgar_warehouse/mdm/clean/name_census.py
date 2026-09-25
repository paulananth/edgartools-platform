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

from .gleif_source import inspect_archive
from .names import legal_form_key, sec_legal_form_key
from .store import Conflict

VERSION = "sec-gleif-name-census-v1"
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


def build(
    *,
    filers: list[tuple[str, str | None, list[str]]],
    sec_population: dict,
    gleif_archive: BinaryIO,
    gleif_metadata: dict,
    gleif_sha256: str,
) -> dict:
    """The census document, bound to the exact inputs it counted.

    `filers` is every SEC filer in the capture: (CIK, current name, former
    names). `sec_population` names that capture (run, member hashes, count).
    """
    if gleif_metadata.get("file_content") != "GLEIF_FULL_PUBLISHED":
        raise Conflict("The Name Census counts a full Golden Copy, never a delta")
    if sec_population.get("filers") != len(filers):
        raise Conflict("The Name Census SEC population disagrees with its filers")
    by_key = sec_keys(filers)
    wanted = {sec_legal_form_key(name) for _, name, _ in filers} - {""}
    legal: dict[str, dict[str, str]] = defaultdict(dict)
    other: dict[str, set] = defaultdict(set)

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
    return {
        "version": VERSION,
        "normalizers": {
            "sec": "normalize_text@sec-legal-form-kept-v1",
            "gleif": "normalize_text@legal-form-kept-v1",
        },
        "sec": sec_population,
        "gleif": {
            "archive_sha256": gleif_sha256,
            "content_date": gleif_metadata["content_date"],
            "file_content": gleif_metadata["file_content"],
            "record_count": report["record_count"],
        },
        "entries": entries,
    }


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
