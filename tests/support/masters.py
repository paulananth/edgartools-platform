"""Masters for a test: invented records merged as a worker merges a file, and what a test asks of them."""

from __future__ import annotations

import json
from collections import defaultdict
from contextlib import contextmanager

from edgar_warehouse.mastering import links as link_builder, lookups, merge
from edgar_warehouse.mastering.store import open_store
from edgar_warehouse.mdm.identifier_types import TYPES
from edgar_warehouse.rules import files
from edgar_warehouse.silver_writer.writer import MdmIds

AS_OF = "2026-11-06T12:00:00+00:00"


def figi(stem: str) -> str:
    """An invented FIGI with a valid check digit."""
    for digit in "0123456789":
        if TYPES["figi"].refusal(f"BBG{stem}{digit}")[1] is None:
            return f"BBG{stem}{digit}"
    raise AssertionError(stem)


@contextmanager
def opened(engine):
    store = open_store(engine)
    try:
        yield store
    finally:
        store.rollback()
        store.close()


def seed(engine, records: list[dict], policy: dict | None = None) -> dict[str, str]:
    """Merge `records` under the real rules, one file per kind; answer {record_key: master id}."""
    kinds, keys = defaultdict(list), defaultdict(set)
    for record in records:
        kinds[record["kind"]].append(record)
        keys[record["source_code"], record["kind"]].add(record["record_key"])
    with opened(engine) as store:
        for kind, batch in kinds.items():
            merge.merge_file(store, merge.Settings(policy or files.policy(), "invented-digest", kind, AS_OF), batch)
    ids, found = MdmIds(engine), {}
    for (code, kind), wanted in keys.items():
        found.update(ids(code, kind, wanted))
    return found


def bodies(engine) -> dict[str, dict]:
    """Every master row, merged-away ones included, by id."""
    with opened(engine) as store:
        return {entity: json.loads(body) for entity, body in store.rows("select entity_id,body from mastering_master")}


def reviews(engine) -> list[str]:
    """The reason of each open review."""
    with opened(engine) as store:
        return [reason for reason, in store.rows("select reason from mastering_review where open_review=1")]


def cross_referencing(engine, namespace: str, value: str) -> list[str]:
    """The masters whose records carry the cross reference, once the lookups are built."""
    with opened(engine) as store:
        lookups.build(store)
        return lookups.cross_referencing(store, namespace, value)


def link_run(engine, policy: dict | None = None, as_of: str = "2026-12-31T00:00:00+00:00", last: list[dict] | None = None):
    """What the link step builds from the stored records: the links, and how many reported ones wait, by reason.
    `last` is the previous run's links, so a link keeps a start its record no longer shows."""
    with opened(engine) as store:
        return link_builder.calculate(store, policy or files.policy(), as_of,
                                      link_builder.stored_of(link_builder.rows_of(last or [])))


def links(engine, policy: dict | None = None, as_of: str = "2026-12-31T00:00:00+00:00", of_type: str = "",
          last: list[dict] | None = None) -> list[dict]:
    """Every link the stored records report, as the link step builds them: source and target master ids, periods."""
    edges, _ = link_run(engine, policy, as_of, last)
    return [edge for edge in edges if not of_type or edge["type"] == of_type]


def names(engine) -> dict[str, str]:
    """Each live master's name, by master id."""
    return {entity: body["fields"]["name"]["value"] for entity, body in bodies(engine).items()
            if body.get("status") != "alias" and body.get("fields", {}).get("name")}
