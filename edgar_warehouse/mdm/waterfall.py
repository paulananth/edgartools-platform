"""The waterfall pass: pair SEC filers with GLEIF entities, strictest comparison first (ticket 202, step A).

It runs the existing passes (`cascade.assign`) over the same two whole sources. It replaces the answer that a
separate file once put on each SEC record. Its inputs are the SEC Company records already in the store and the
whole GLEIF publication, counted once. Nothing here reads a capture or a file."""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from . import cascade


def filers_from_records(records: Iterable[dict]) -> list[cascade.Filer]:
    """The SEC Company records as the store holds them, each as the passes read a filer."""
    return [cascade.filer_of(record) for record in records]


def assignments(filers: Iterable[cascade.Filer], entities: Iterable[cascade.Entity], passes: list[dict], *,
                gleif_addresses: Counter, over_shared: int) -> dict[str, dict]:
    """CIK -> the entity it pairs with, one to one. An address is counted over every filer and every GLEIF
    entity, not only the candidates in hand, so `gleif_addresses` is the whole publication's count."""
    filers = list(filers)
    counts = cascade.count_addresses(f.place for f in filers) + Counter(gleif_addresses)
    return cascade.assign(filers, entities, passes, address_counts=counts, over_shared=over_shared)


def differences(new: dict, stored: dict) -> dict[str, int]:
    """Counts only: how a new answer differs from the one a record already carries (by CIK). A comparison for
    the move away from the old file: it is deleted with that file in step C."""
    both = new.keys() & stored.keys()
    same = sum(new[cik]["lei"] == stored[cik]["lei"] for cik in both)
    return {"same": same, "other_lei": len(both) - same, "only_new": len(new.keys() - stored.keys()),
            "only_stored": len(stored.keys() - new.keys())}
