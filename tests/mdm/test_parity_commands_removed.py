"""silver-merge-engine-migration Ticket 08: the DuckDB-vs-Snowflake parity
commands are deleted. No writer produces DuckDB silver rows any more, so
there is nothing on the DuckDB side to compare against EDGARTOOLS_SILVER.
Cross-store comparison evidence (duckdb-retirement-cutover Tickets 19/21)
uses ``table-reconcile``, which does not depend on this tooling.
"""

from __future__ import annotations

import argparse
import importlib.util

import pytest

from edgar_warehouse.mdm import cli as mdm_cli


def _mdm_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers()
    mdm_cli.register_mdm_subparser(sub)
    return parser


@pytest.mark.parametrize("command", ["verify-silver-parity", "verify-resolver-input-parity"])
def test_parity_command_is_not_registered(command):
    with pytest.raises(SystemExit):
        _mdm_parser().parse_args(["mdm", command])


def test_silver_parity_module_is_gone():
    assert importlib.util.find_spec("edgar_warehouse.mdm.silver_parity") is None


def test_duckdb_silver_reader_helpers_are_gone():
    assert not hasattr(mdm_cli, "_duckdb_silver_reader")
    assert not hasattr(mdm_cli, "_require_duckdb_silver_reader")
