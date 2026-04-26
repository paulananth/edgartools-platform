"""Tests for MDM runtime/e2e support helpers."""

from __future__ import annotations

from edgar_warehouse.cli import build_parser
from edgar_warehouse.mdm.api.auth import _parse_key_payload
from edgar_warehouse.mdm.migrations.runtime import MDM_TABLES


def test_api_key_payload_accepts_csv_and_json() -> None:
    assert _parse_key_payload("alpha,beta") == {"alpha", "beta"}
    assert _parse_key_payload('{"keys": ["alpha", " beta "]}') == {"alpha", "beta"}


def test_mdm_runtime_table_list_includes_sql_and_graph_surfaces() -> None:
    assert "mdm_company" in MDM_TABLES
    assert "mdm_relationship_instance" in MDM_TABLES
    assert "mdm_change_log" in MDM_TABLES


def test_mdm_cli_exposes_e2e_operations() -> None:
    parser = build_parser()
    for command in ("migrate", "counts", "check-connectivity", "sync-graph", "api"):
        args = parser.parse_args(["mdm", command])
        assert args.command == "mdm"
        assert args.mdm_command == command
