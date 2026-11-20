"""The rules MDM registered: each Mastering Policy under its digest, each reading of a Dataset Contract
under its version, in the Rules Database (the control database's `rules` schema).

The merge reads them here by digest and by version; `rules register` adds to them through
`edgar_warehouse.mdm.store`, which checks each body first. A row is never changed: a policy is its digest,
and a corrected mapping is the next reading.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import func, select

from edgar_warehouse.control_contract import Blocked

from .db import tables


def _canonical(body: dict) -> str:
    """The text a body is stored as: the form its digest is taken of."""
    from edgar_warehouse.mdm.store import canonical

    return canonical(body)


def engine(environment=None):
    """The Rules Database, as the duty file sourced: the loader reads it, the governance login adds to it."""
    from edgar_warehouse.database_connections import store_engine

    return store_engine("rules", environment=environment)


def policy(conn, digest: str) -> dict | None:
    table = tables(conn.dialect.name)["policy"]
    found = conn.scalar(select(table.c.body).where(table.c.digest == digest))
    return None if found is None else json.loads(found)


def policies(conn) -> list[dict]:
    table = tables(conn.dialect.name)["policy"]
    return [json.loads(body) for body in conn.scalars(select(table.c.body).order_by(table.c.digest))]


def add_policy(conn, body: dict) -> str:
    """Register a policy under its digest; one already registered is left as it is."""
    from edgar_warehouse.mdm.store import digest

    table = tables(conn.dialect.name)["policy"]
    key = digest(body)
    held = conn.scalar(select(table.c.body).where(table.c.digest == key))
    if held is None:
        conn.execute(table.insert().values(digest=key, body=_canonical(body), registered_at=datetime.now(UTC)))
    elif held != _canonical(body):
        raise Blocked("Policy digest collision")
    return key


def reading(conn, code: str, version: int | None = None) -> dict | None:
    """A source's reading: the one named, or the latest. Its `mapping_version`, `registry_version` and `body`."""
    table = tables(conn.dialect.name)["dataset_reading"]
    query = select(table.c.mapping_version, table.c.registry_version, table.c.body).where(table.c.source_code == code)
    if version is None:
        query = query.where(table.c.mapping_version == select(func.max(table.c.mapping_version))
                            .where(table.c.source_code == code).scalar_subquery())
    else:
        query = query.where(table.c.mapping_version == version)
    row = conn.execute(query).mappings().first()
    return None if row is None else {**row, "body": json.loads(row["body"])}


def add_reading(conn, code: str, version: int, body: dict, registry_version: str) -> None:
    """Append a source's next reading; its number is one more than the latest (1 for a new source)."""
    latest = reading(conn, code)
    if version != (1 if latest is None else latest["mapping_version"] + 1):
        raise Blocked(f"Dataset {code}: reading {version} does not follow the latest")
    conn.execute(tables(conn.dialect.name)["dataset_reading"].insert().values(
        source_code=code, mapping_version=version, registry_version=registry_version, body=_canonical(body),
        registered_at=datetime.now(UTC)))


def first_contracts(conn, codes) -> dict[str, dict]:
    """Each source's contract as first registered (its reading 1), by source code."""
    table = tables(conn.dialect.name)["dataset_reading"]
    wanted = sorted(set(codes))
    found = {}
    for start in range(0, len(wanted), 400):
        rows = conn.execute(select(table.c.source_code, table.c.body).where(
            table.c.source_code.in_(wanted[start:start + 400]), table.c.mapping_version == 1))
        found.update({code: json.loads(body) for code, body in rows})
    return found
