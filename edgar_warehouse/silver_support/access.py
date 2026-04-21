"""Legacy accessors that isolate direct SilverDatabase internals."""

from __future__ import annotations

from typing import Any


def get_connection(db: Any):
    return db._conn
