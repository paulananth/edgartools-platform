"""The merge runtime identifies execution, independently of command presentation."""

from pathlib import Path

import pytest

from edgar_warehouse.mdm.clean import binding, cli, connections, execution
from edgar_warehouse.workers import mdm_merge
from edgar_warehouse.workers.__main__ import runtime


def test_command_presentation_does_not_change_the_merge_runtime(monkeypatch):
    before = runtime(mdm_merge)
    command_file = Path(cli.__file__)
    read_bytes = Path.read_bytes

    def command_edit(path):
        data = read_bytes(path)
        return data + b"\n# Command presentation changed.\n" if path == command_file else data

    monkeypatch.setattr(Path, "read_bytes", command_edit)

    assert runtime(mdm_merge) == before


@pytest.mark.parametrize("module", [execution, connections, binding])
def test_execution_connection_and_matching_code_change_the_merge_runtime(monkeypatch, module):
    before = runtime(mdm_merge)
    changed_file = Path(module.__file__)
    read_bytes = Path.read_bytes

    def execution_edit(path):
        data = read_bytes(path)
        return data + b"\n# Runtime implementation changed.\n" if path == changed_file else data

    monkeypatch.setattr(Path, "read_bytes", execution_edit)

    assert runtime(mdm_merge) != before
