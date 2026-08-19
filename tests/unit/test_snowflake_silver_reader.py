"""Tests for SnowflakeSilverReader (silver-snowflake-migration map, Ticket 12).

Covers the two Snowflake-specific behaviors the reader exists to paper over
(identifier casing, qmark paramstyle scoping) plus the deliberate absence of
a DuckDB-shaped ._conn attribute -- see snowflake_reader.py's module
docstring for why each of these is load-bearing, not incidental.
"""

from __future__ import annotations

from typing import Any

import pytest

from edgar_warehouse.silver_support.snowflake_reader import SnowflakeSilverReader
from tests.unit._fake_snowflake import FakeSnowflakeConnection


def _reader_over(table_data: dict[str, tuple[list[str], list[tuple]]]) -> tuple[SnowflakeSilverReader, FakeSnowflakeConnection]:
    connection = FakeSnowflakeConnection(table_data)
    return SnowflakeSilverReader(connection), connection


def test_fetch_lowercases_uppercase_column_names():
    # Snowflake's connector returns UPPERCASE names in cursor.description
    # for unquoted identifiers even when the SQL used lowercase -- confirmed
    # live against a real Snowflake session. Every MDM caller reads
    # lowercase keys (row["cik"]), so a reader that passed uppercase keys
    # through would KeyError at every one of ~20 call sites.
    reader, _connection = _reader_over(
        {"SEC_COMPANY": (["CIK", "ENTITY_NAME"], [(320193, "Apple Inc")])}
    )

    rows = reader.fetch("SELECT cik, entity_name FROM sec_company")

    assert rows == [{"cik": 320193, "entity_name": "Apple Inc"}]


def test_fetch_lowercasing_is_exercised_not_accidentally_already_lowercase():
    # Guards against a fake that returns lowercase keys passing while prod
    # (uppercase keys) fails -- assert the fixture itself is uppercase so
    # the lowercasing in fetch() is the thing under test, not a no-op.
    reader, connection = _reader_over(
        {"SEC_COMPANY": (["CIK"], [(320193,)])}
    )

    reader.fetch("SELECT cik FROM sec_company")

    cursor = connection.cursors[-1]
    assert cursor.description == [("CIK",)]


def test_fetch_passes_params_through_to_cursor_execute():
    reader, connection = _reader_over(
        {"SEC_COMPANY": (["CIK"], [(320193,)])}
    )

    reader.fetch("SELECT cik FROM sec_company WHERE cik = ?", [320193])

    cursor = connection.cursors[-1]
    assert cursor.last_params == [320193]


def test_fetch_defaults_params_to_empty_list_not_none():
    reader, connection = _reader_over(
        {"SEC_COMPANY": (["CIK"], [(320193,)])}
    )

    reader.fetch("SELECT cik FROM sec_company")

    cursor = connection.cursors[-1]
    assert cursor.last_params == []


def test_fetch_closes_its_own_cursor():
    reader, connection = _reader_over(
        {"SEC_COMPANY": (["CIK"], [(320193,)])}
    )

    reader.fetch("SELECT cik FROM sec_company")

    cursor = connection.cursors[-1]
    assert cursor.closed is True


def test_close_closes_the_underlying_connection():
    reader, connection = _reader_over({})

    reader.close()

    assert connection.closed is True


def test_reader_has_no_duckdb_shaped_conn_attribute():
    # seed-universe --source silver and gold_models.py's legacy path both
    # bypass .fetch() and call reader._conn.execute(...) directly against
    # ShardedSilverReader. Ticket 12 deliberately scoped those call sites
    # out -- a SnowflakeSilverReader with a ._conn would silently make that
    # mistake possible instead of failing loudly. Locks the omission in.
    reader, _connection = _reader_over({})

    assert not hasattr(reader, "_conn")


class _RecordingSettings:
    """Records the module paramstyle at the moment .connect() is called,
    so tests can assert the qmark scoping window without touching a real
    Snowflake connection or the module global outside the test's control."""

    def __init__(self, connection: FakeSnowflakeConnection) -> None:
        self._connection = connection
        self.paramstyle_during_connect: str | None = None

    def connect(self) -> FakeSnowflakeConnection:
        import snowflake.connector as sc

        self.paramstyle_during_connect = sc.paramstyle
        return self._connection


def test_connect_sets_qmark_paramstyle_only_for_the_connect_call():
    import snowflake.connector as sc

    original = sc.paramstyle
    assert original != "qmark", "test assumes qmark is not already the ambient default"

    connection = FakeSnowflakeConnection({})
    settings = _RecordingSettings(connection)

    reader = SnowflakeSilverReader.connect(settings_factory=lambda: settings)

    assert settings.paramstyle_during_connect == "qmark"
    assert sc.paramstyle == original, "global paramstyle must be restored after connect()"
    assert reader is not None


def test_connect_restores_paramstyle_even_if_connect_raises():
    import snowflake.connector as sc

    original = sc.paramstyle

    class _RaisingSettings:
        def connect(self) -> Any:
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        SnowflakeSilverReader.connect(settings_factory=lambda: _RaisingSettings())

    assert sc.paramstyle == original


def test_default_settings_factory_overrides_role_to_mdm_silver_reader(monkeypatch):
    # Exercises the real _mdm_silver_reader_settings() (the default
    # settings_factory SnowflakeSilverReader.connect() uses in production)
    # against a fake upstream silver_connection_settings(), so this test
    # fails if the role override is ever dropped or misnamed -- without
    # patching dataclasses.replace itself, which every other dataclass in
    # the process also uses.
    from edgar_warehouse.mdm.export import SnowflakeConnectionSettings
    from edgar_warehouse.silver_support.snowflake_reader import _mdm_silver_reader_settings

    fake_upstream_settings = SnowflakeConnectionSettings(
        account="acct",
        user="user",
        password="pw",
        database="EDGARTOOLS_PROD",
        schema="EDGARTOOLS_SILVER",
        warehouse="wh",
        role=None,
    )
    monkeypatch.setattr(
        "edgar_warehouse.mdm.export.silver_connection_settings",
        lambda: fake_upstream_settings,
    )

    settings = _mdm_silver_reader_settings()

    assert settings.role == "EDGARTOOLS_PROD_MDM_SILVER_READER"
    assert settings.schema == "EDGARTOOLS_SILVER"
    # replace() returns a new object; the original upstream settings must
    # be untouched (no other caller of silver_connection_settings() should
    # see its role silently mutated).
    assert fake_upstream_settings.role is None
