"""Tests for connect_with_qmark_paramstyle (edgar_warehouse.silver_support.snowflake_reader).

Extracted from SnowflakeSilverReader.connect() (silver-snowflake-migration
map, Ticket 12) once a second call site (mdm_entity_backfill.py's
run_mdm_entity_backfill_sweep) needed the identical connect-time
paramstyle-scoping dance -- see the function's own docstring for why
mutating snowflake.connector.paramstyle after connect() has no effect (it
is read once and cached on the connection object at connect time).
SnowflakeSilverReader.connect()'s own tests (test_snowflake_silver_reader.py)
continue to prove it delegates to this function correctly; these tests
cover the shared function directly so a third call site can rely on it
without re-proving the underlying Snowflake connector quirk itself.
"""

from __future__ import annotations

import pytest

from edgar_warehouse.silver_support.snowflake_reader import connect_with_qmark_paramstyle
from tests.unit._fake_snowflake import (
    FakeSnowflakeConnection,
    RaisingConnectSettings,
    RecordingConnectSettings,
)


def test_sets_qmark_paramstyle_only_for_the_connect_call():
    sc = pytest.importorskip("snowflake.connector")

    original = sc.paramstyle
    assert original != "qmark", "test assumes qmark is not already the ambient default"

    connection = FakeSnowflakeConnection({})
    settings = RecordingConnectSettings(connection)

    result = connect_with_qmark_paramstyle(lambda: settings)

    assert settings.paramstyle_during_connect == "qmark"
    assert sc.paramstyle == original, "global paramstyle must be restored after connect()"
    assert result is connection


def test_restores_paramstyle_even_if_connect_raises():
    sc = pytest.importorskip("snowflake.connector")

    original = sc.paramstyle

    with pytest.raises(RuntimeError, match="boom"):
        connect_with_qmark_paramstyle(lambda: RaisingConnectSettings())

    assert sc.paramstyle == original
