"""Shared FastAPI dependencies: DB session, Neo4j client."""
from __future__ import annotations

import os
from typing import Iterator, Optional

from sqlalchemy.orm import Session

from edgar_warehouse.mdm.database import get_engine, get_session
from edgar_warehouse.mdm.graph import Neo4jGraphClient


_engine = None


def get_db() -> Iterator[Session]:
    global _engine
    if _engine is None:
        _engine = get_engine()
    s = get_session(_engine)
    try:
        yield s
    finally:
        s.close()


def get_neo4j() -> Optional[Neo4jGraphClient]:
    uri = os.environ.get("NEO4J_URI")
    user = os.environ.get("NEO4J_USER")
    password = os.environ.get("NEO4J_PASSWORD")
    if not (uri and user and password):
        return None
    return Neo4jGraphClient(uri=uri, user=user, password=password)
