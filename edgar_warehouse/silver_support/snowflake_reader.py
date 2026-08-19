"""Snowflake-backed silver reader satisfying ShardedSilverReader's read seam.

``SnowflakeSilverReader`` implements exactly the two methods MDM's pipeline
code calls through (``.fetch(sql, params) -> list[dict]`` and ``.close()``),
so ``silver-snowflake-migration`` map Ticket 12's env-var flip
(``MDM_SILVER_READ_TARGET=duckdb|snowflake``) can swap the object
``_silver_reader()`` returns without touching any of the ~20 call sites in
``edgar_warehouse/mdm/pipeline.py``/``adv_bulk.py``/``coverage.py`` that only
ever call ``.fetch()``.

Deliberately does NOT expose a DuckDB-shaped ``._conn`` attribute like
``ShardedSilverReader`` does. A handful of call sites (``seed-universe
--source silver``, ``source_dimensional_export.py``) bypass ``.fetch()`` entirely and call
``reader._conn.execute(...)`` directly -- those are out of this ticket's
scope and would silently break against a Snowflake connection object. Not
exposing ``._conn`` at all makes that mistake fail loudly (AttributeError)
instead of quietly returning wrong results.

Two Snowflake-specific behaviors this module exists to paper over:

1. Identifier casing: Snowflake's connector returns UPPERCASE column names
   in ``cursor.description`` for unquoted identifiers, even when the SQL
   itself used lowercase (confirmed live against PRJEDJU-QJB05385,
   2026-08-18). Every MDM caller reads lowercase keys (``row["cik"]``,
   ``row.get("party_cik")``) -- ``fetch()`` lowercases every column name
   before building the row dicts.

2. Bind-parameter style: MDM's SQL uses ``?`` positional placeholders
   throughout (DuckDB's native style). snowflake-connector-python defaults
   to ``pyformat`` (``%s``) and does not accept ``paramstyle`` as a
   per-connection ``connect()`` kwarg -- it is a module-level global, read
   once and cached on the connection object at connect time (confirmed
   live: flipping it after connect has no effect on that connection).
   ``connect()`` below flips the global to ``"qmark"`` for the single
   ``connect()`` call and restores it immediately after, so the mutation
   window is a few milliseconds around one call rather than a persistent
   process-wide change that could affect ``mdm export``/``sync-graph``/
   ``verify-graph``'s own pyformat-style Snowflake usage if they ever share
   a process with this reader.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol


class _ConnectionSettings(Protocol):
    def connect(self) -> Any: ...


def _mdm_silver_reader_settings() -> _ConnectionSettings:
    """EDGARTOOLS_SILVER connection settings, scoped to MDM's dedicated
    read-only role.

    Reuses ``edgar_warehouse.mdm.export.silver_connection_settings()``
    (already schema-scoped to EDGARTOOLS_SILVER, shared with
    ``mdm_entity_backfill.py``'s sweep and ``source_dimensional_export.py``'s
    Snowflake-silver-reading builders) and overrides only the role --
    a new function rather than changing that shared helper's default,
    since its other two callers were never scoped to
    EDGARTOOLS_PROD_MDM_SILVER_READER and don't need to be for this ticket.
    """
    from dataclasses import replace

    from edgar_warehouse.mdm.export import silver_connection_settings

    return replace(silver_connection_settings(), role="EDGARTOOLS_PROD_MDM_SILVER_READER")


class SnowflakeSilverReader:
    """Read-only EDGARTOOLS_SILVER reader, duck-type compatible with
    ``ShardedSilverReader``'s ``.fetch()``/``.close()`` interface."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    @classmethod
    def connect(
        cls,
        settings_factory: Callable[[], _ConnectionSettings] = _mdm_silver_reader_settings,
    ) -> "SnowflakeSilverReader":
        """Build a settings object via ``settings_factory`` and connect,
        with the module-global ``paramstyle`` scoped to ``"qmark"`` for
        exactly the ``connect()`` call (see module docstring, point 2).
        """
        import snowflake.connector as sc

        settings = settings_factory()
        original_paramstyle = sc.paramstyle
        sc.paramstyle = "qmark"
        try:
            connection = settings.connect()
        finally:
            sc.paramstyle = original_paramstyle
        return cls(connection)

    def fetch(self, sql: str, params: list | None = None) -> list[dict]:
        cursor = self._connection.cursor()
        try:
            cursor.execute(sql, params or [])
            columns = [description[0].lower() for description in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            cursor.close()

    def close(self) -> None:
        self._connection.close()

    def __repr__(self) -> str:
        return "SnowflakeSilverReader(EDGARTOOLS_SILVER)"
