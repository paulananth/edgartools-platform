"""Contracts for Ticket 29's frozen Snowflake Gold input envelope."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from unittest.mock import patch

from edgar_warehouse.cli import build_parser
from edgar_warehouse.serving.source_dimensional_export import (
    GOLD_INPUT_COLUMNS,
    capture_gold_input_envelope,
    iter_source_export_tables,
)
from tests.unit._fake_snowflake import FakeSnowflakeConnection, FakeSnowflakeCursor


class _EnvelopeCursor(FakeSnowflakeCursor):
    def execute(self, query: str, params=None) -> None:
        super().execute(query, params)
        matched_table = next(
            table_name
            for table_name in self._table_data
            if table_name in query.upper()
        )
        if "COUNT(*)" in query.upper():
            self.description = [("ROW_COUNT",)]
            self._rows = [(len(self._table_data[matched_table][1]),)]
        self.sfqid = f"fake-query-{matched_table.lower()}"


class _EnvelopeConnection(FakeSnowflakeConnection):
    def cursor(self) -> FakeSnowflakeCursor:
        created = _EnvelopeCursor(self._table_data)
        self.cursors.append(created)
        return created


class _Settings:
    account = "test-account"
    database = "EDGARTOOLS_PROD"
    schema = "EDGARTOOLS_SILVER"

    def __init__(self, table_data):
        self.table_data = table_data
        self.connections: list[FakeSnowflakeConnection] = []

    def connect(self) -> FakeSnowflakeConnection:
        connection = _EnvelopeConnection(self.table_data)
        self.connections.append(connection)
        return connection


def _table_data():
    return {
        table_name: (list(columns), [])
        for table_name, columns in GOLD_INPUT_COLUMNS.items()
    } | {
        "SEC_EMPLOYMENT_EVENT": (
            list(GOLD_INPUT_COLUMNS["SEC_EMPLOYMENT_EVENT"]),
            [
                (
                    "0001",
                    1,
                    320193,
                    "appointed",
                    "Jane Doe",
                    "CEO",
                    None,
                    None,
                    date(2024, 3, 1),
                    "v1",
                )
            ],
        )
    }


def test_gold_refresh_cli_accepts_frozen_input_snapshot() -> None:
    args = build_parser().parse_args(
        ["gold-refresh", "--input-snapshot-at", "2026-09-11T12:00:00Z"]
    )
    assert args.input_snapshot_at == "2026-09-11T12:00:00Z"


def test_capture_gold_input_envelope_is_deterministic_and_auditable() -> None:
    settings = _Settings(_table_data())
    with patch(
        "edgar_warehouse.mdm.export.silver_connection_settings",
        return_value=settings,
    ):
        envelope = capture_gold_input_envelope("2026-09-11T08:00:00-04:00")

    assert envelope["source_system"] == "EDGARTOOLS_SILVER"
    assert envelope["database"] == "EDGARTOOLS_PROD"
    assert envelope["schema"] == "EDGARTOOLS_SILVER"
    assert envelope["snapshot_at"] == "2026-09-11T12:00:00.000000Z"
    assert {entry["table_name"] for entry in envelope["tables"]} == set(
        GOLD_INPUT_COLUMNS
    )
    employment = next(
        entry
        for entry in envelope["tables"]
        if entry["table_name"] == "SEC_EMPLOYMENT_EVENT"
    )
    assert employment["row_count"] == 1
    identity = {
        key: value
        for key, value in envelope.items()
        if key not in {"envelope_sha256", "query_ids"}
    }
    expected_digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert envelope["envelope_sha256"] == expected_digest
    assert set(envelope["query_ids"]) == set(GOLD_INPUT_COLUMNS)
    assert all(envelope["query_ids"].values())
    queries = [
        cursor.last_query
        for connection in settings.connections
        for cursor in connection.cursors
    ]
    assert len(queries) == len(GOLD_INPUT_COLUMNS)
    assert all(
        "AT (TIMESTAMP => '2026-09-11T12:00:00.000000Z'::TIMESTAMP_TZ)"
        in query
        for query in queries
    )


def test_streamed_gold_reads_use_the_same_frozen_snapshot() -> None:
    settings = _Settings(_table_data())
    with patch(
        "edgar_warehouse.mdm.export.silver_connection_settings",
        return_value=settings,
    ):
        tables = list(
            iter_source_export_tables(
                input_snapshot_at="2026-09-11T12:00:00.000000Z"
            )
        )

    assert len(tables) == len(GOLD_INPUT_COLUMNS)
    queries = [
        cursor.last_query
        for connection in settings.connections
        for cursor in connection.cursors
    ]
    assert all(
        "AT (TIMESTAMP => '2026-09-11T12:00:00.000000Z'::TIMESTAMP_TZ)"
        in query
        for query in queries
    )
