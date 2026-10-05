"""A name as the basis of a designed record key (research note 02; operator ruling 2026-10-05).

A name is never a found key: it is renamed, varies, is shared by different
things and is reused. When it is a part's only unique column, the record key is
a durable id given at first appearance and kept in a key map, looked up by the
sha256 of the normalized name; a rename is kept as an alias, so the key never
changes ("same record: durable key").
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

from .identifiers import identifier_shaped
from .inputs import sql_name
from .profile import is_temporal, is_text
from .sensitivity import mask

NORMALIZATION = f"name_norm@1: NFKC, case fold, NFKC, whitespace runs to one space, trim (Unicode {unicodedata.unidata_version})"


def name_norm(value: str) -> str:
    """The one normalization every profiler and loader uses; never re-implemented in SQL."""
    folded = unicodedata.normalize("NFKC", unicodedata.normalize("NFKC", value).casefold())
    return re.sub(r"\s+", " ", folded).strip()


def name_hash(part: str, value: str) -> str:
    """sha256 hex of the part name, a separator and the normalized name: the key map's lookup column."""
    return hashlib.sha256(f"{part}\x1f{name_norm(value)}".encode("utf-8")).hexdigest()


def is_name(profile: dict) -> bool:
    """Text of more than one word with letters, not shaped like an identifier: a name, never a found key."""
    return (is_text(profile) and not profile["structure"] and profile.get("tokens", 0) > 1.0
            and not identifier_shaped(profile) and not is_temporal(profile)
            and any(ch.isalpha() for ch in (profile.get("shape") or "")))


def name_basis(con, part: str, columns: list[dict], personal: set[str]) -> dict | None:
    """The name column a designed key can rest on: always filled and unique after normalization."""
    rows = columns[0]["rows"] if columns else 0
    for column in sorted((c for c in columns if is_name(c) and c["fill"] == 1.0 and c["name"] not in personal),
                         key=lambda c: -c["distinct"]):
        raw = [r[0] for r in con.execute(f"SELECT CAST({sql_name(column['name'])} AS VARCHAR) "
                                         f"FROM {sql_name(part)}").fetchall()]
        groups: dict[str, set[str]] = {}
        for value in raw:
            groups.setdefault(name_norm(value), set()).add(value)
        if len(groups) != rows:
            continue
        folded = [sorted(v) for v in groups.values() if len(v) > 1]
        return {"column": column["name"],
                "evidence": {"unique_raw": column["distinct"] == rows, "unique_after_normalization": True,
                             "folded_collisions": {"groups": len(folded),
                                                   "examples": [[mask(v) for v in g] for g in folded[:3]]},
                             "provisional": True}}
    return None
