"""Local PostgreSQL silver reader with the same ``.fetch()``/``.close()`` seam.

MDM pipeline SQL was written for DuckDB/Snowflake (``?`` placeholders and
``COUNT_IF``). This adapter keeps that SQL unchanged and rewrites it for
Postgres. Production keeps ``SnowflakeSilverReader`` unless
``SILVER_DATABASE_URL`` is set.

``QUALIFY`` is not rewritten here. Company mastering does not use it;
person/security/relationship SQL still needs Snowflake or a later rewrite.
"""
from __future__ import annotations

import os
import re
import threading
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


def rewrite_count_if(sql: str) -> str:
    """Translate Snowflake/DuckDB ``COUNT_IF(pred)`` to Postgres FILTER."""
    upper = sql.upper()
    out: list[str] = []
    i = 0
    while True:
        pos = upper.find("COUNT_IF", i)
        if pos < 0:
            out.append(sql[i:])
            break
        out.append(sql[i:pos])
        j = pos + len("COUNT_IF")
        while j < len(sql) and sql[j].isspace():
            j += 1
        if j >= len(sql) or sql[j] != "(":
            out.append(sql[pos:j])
            i = j
            continue
        depth = 0
        k = j
        while k < len(sql):
            if sql[k] == "(":
                depth += 1
            elif sql[k] == ")":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        out.append(f"COUNT(*) FILTER (WHERE {sql[j + 1 : k]})")
        i = k + 1
    return "".join(out)


def bind_qmark(sql: str, params: list | None) -> tuple[Any, dict]:
    converted = rewrite_count_if(sql)
    mapping: dict[str, Any] = {}
    if not params:
        return text(converted), mapping

    def _next(_match: re.Match[str]) -> str:
        key = f"p{len(mapping)}"
        mapping[key] = params[len(mapping)]
        return f":{key}"

    return text(re.sub(r"\?", _next, converted)), mapping


class PostgresSilverReader:
    """Read-only local silver exposing ``.fetch()``/``.close()``."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._connection = engine.connect()
        self._fetch_lock = threading.Lock()

    @classmethod
    def connect(cls, url: str | None = None) -> PostgresSilverReader:
        url = url or os.environ["SILVER_DATABASE_URL"]
        return cls(create_engine(url, pool_pre_ping=True))

    def fetch(self, sql: str, params: list | None = None) -> list[dict]:
        statement, mapping = bind_qmark(sql, params)
        with self._fetch_lock:
            result = self._connection.execute(statement, mapping)
            columns = [key.lower() for key in result.keys()]
            return [dict(zip(columns, row)) for row in result.fetchall()]

    def close(self) -> None:
        self._connection.close()
        self._engine.dispose()

    def __repr__(self) -> str:
        return "PostgresSilverReader(SILVER_DATABASE_URL)"
