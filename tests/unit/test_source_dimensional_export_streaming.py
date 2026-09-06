from __future__ import annotations

import itertools
from unittest.mock import MagicMock, call, patch

import pyarrow as pa

from edgar_warehouse.serving.source_dimensional_export import (
    _release_source_export_memory,
    build_source_export,
    iter_source_export_tables,
)
from tests.unit._fake_snowflake import (
    EMPTY_ORPHAN_EVIDENCE_TABLE_DATA,
    FakeSnowflakeConnectionSettings,
)

# dbt-gold-silver-rewiring Ticket 07 retired every builder that used to read
# a local DuckDB `db` fixture -- the 5 remaining here (Ticket 06/08) all read
# Snowflake's EDGARTOOLS_SILVER directly, so there is no DuckDB fixture left
# to build against at all.
_patch_silver_connection = patch(
    "edgar_warehouse.mdm.export.silver_connection_settings",
    return_value=FakeSnowflakeConnectionSettings(EMPTY_ORPHAN_EVIDENCE_TABLE_DATA),
)


EXPECTED_GOLD_TABLE_NAMES = {
    "sec_subsidiary_evidence",
    "sec_auditor_report_evidence",
    "sec_employment_event",
    "sec_adv_firm_roster",
    "sec_adv_private_fund",
}


def test_iter_source_export_tables_produces_the_full_expected_table_set() -> None:
    """Guards against the streaming refactor silently dropping, renaming, or
    reordering a builder -- pinned against a hardcoded name set independent
    of build_source_export()'s own implementation, so this can't pass by construction
    the way an iter_source_export_tables()-vs-build_source_export() comparison alone would."""
    with _patch_silver_connection:
        names = [name for name, _ in iter_source_export_tables()]

    assert set(names) == EXPECTED_GOLD_TABLE_NAMES
    assert len(names) == len(set(names)), "duplicate table name in iter_source_export_tables()"


def test_iter_source_export_tables_matches_build_source_export_with_real_rows() -> None:
    """iter_source_export_tables() must be a drop-in streaming equivalent of
    build_source_export(): same table names, same per-table schema and row counts,
    exercised against at least one non-empty table (not just the degenerate
    empty-schema case, which every builder returns identically regardless of
    how it's invoked)."""
    non_empty_data = {
        **EMPTY_ORPHAN_EVIDENCE_TABLE_DATA,
        "SEC_EMPLOYMENT_EVENT": (
            [
                "accession_number", "event_index", "cik", "event_type",
                "person_name", "exec_role", "previous_role",
                "compensation_amount", "effective_date", "parser_version",
            ],
            [("0000320193-24-000123", 0, 320193, "appointment", "Jane Doe",
              "CFO", None, None, "2024-09-28", "v1")],
        ),
    }
    with patch(
        "edgar_warehouse.mdm.export.silver_connection_settings",
        return_value=FakeSnowflakeConnectionSettings(non_empty_data),
    ):
        streamed = dict(iter_source_export_tables())
        materialized = build_source_export()

    assert set(streamed.keys()) == set(materialized.keys()) == EXPECTED_GOLD_TABLE_NAMES

    assert (
        streamed["sec_employment_event"].num_rows
        == materialized["sec_employment_event"].num_rows
        == 1
    )

    for name, streamed_table in streamed.items():
        materialized_table = materialized[name]
        assert isinstance(streamed_table, pa.Table)
        assert streamed_table.schema.equals(materialized_table.schema), name
        assert streamed_table.num_rows == materialized_table.num_rows, name


def test_iter_source_export_tables_is_lazy() -> None:
    """Builders must not run until the generator is actually advanced to
    them -- the whole point of streaming is that a later table isn't built
    while earlier tables are still being written out."""
    with patch(
        "edgar_warehouse.serving.source_dimensional_export._build_sec_adv_private_fund_passthrough"
    ) as mock_last, _patch_silver_connection:
        gen = iter_source_export_tables()
        mock_last.assert_not_called()

        # sec_adv_private_fund is the last entry in the builder registry --
        # consuming only the first 3 must not reach it.
        list(itertools.islice(gen, 3))
        mock_last.assert_not_called()

        # Draining the rest of the generator does reach it.
        list(gen)
        mock_last.assert_called_once()


def test_iter_source_export_tables_releases_memory_between_loads() -> None:
    first = pa.table({"value": [1]})
    second = pa.table({"value": [2]})
    cleanup = MagicMock()

    with (
        patch(
            "edgar_warehouse.serving.source_dimensional_export._source_export_table_builders",
            return_value=[("first", lambda: first), ("second", lambda: second)],
        ),
        patch(
            "edgar_warehouse.serving.source_dimensional_export._release_source_export_memory",
            cleanup,
        ),
    ):
        tables = iter_source_export_tables()
        cleanup.assert_not_called()

        assert next(tables) == ("first", first)
        assert cleanup.call_args_list == [call()]

        assert next(tables) == ("second", second)
        assert cleanup.call_args_list == [call(), call()]

        tables.close()
        assert cleanup.call_args_list == [call(), call(), call()]


def test_release_source_export_memory_collects_python_and_arrow_allocations() -> None:
    pool = MagicMock()
    with (
        patch("edgar_warehouse.serving.source_dimensional_export.gc.collect") as collect,
        patch(
            "edgar_warehouse.serving.source_dimensional_export.pa.default_memory_pool",
            return_value=pool,
        ),
    ):
        _release_source_export_memory()

    collect.assert_called_once_with()
    pool.release_unused.assert_called_once_with()
