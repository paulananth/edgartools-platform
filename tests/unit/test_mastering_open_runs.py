"""`build-lookups` and `clear` refuse while Bookkeeping holds an open run of a mastering target (ticket mastering-locks/03).

A worker between two merge transactions holds no kind lock, so the lock check alone cannot tell that a load is still running.
"""
import json

import pytest

from edgar_warehouse.bookkeeping.clean import cli as bookkeeping_cli
from edgar_warehouse.mastering import lookups, store as stores
from edgar_warehouse.mdm import commands
from tests.support.patching import checked


class Book:
    def __init__(self, runs):
        self._runs, self.closed = runs, False

    def runs(self, *, limit=100, state=None):
        assert state == "running" and limit == 1000
        return self._runs

    def close(self):
        self.closed = True


class Engine:
    def dispose(self):
        pass


class Db:
    def close(self):
        pass


@pytest.fixture
def lookups_command(monkeypatch):
    built = []
    checked(monkeypatch, commands, "mdm_engine", lambda **kw: Engine())
    checked(monkeypatch, stores, "open_store", lambda engine: Db())
    checked(monkeypatch, lookups, "build", lambda db, progress=None: built.append(1) or {"masters": 0, "file": 0})
    return built


def test_the_lookups_are_not_built_while_a_mastering_run_is_open(monkeypatch, lookups_command, capsys):
    book = Book([{"run_id": "r1", "name": "gleif", "target": "mastering", "state": "running"},
                 {"run_id": "r2", "name": "x", "target": "silver", "state": "running"}])
    checked(monkeypatch, bookkeeping_cli, "configured_bookkeeping", lambda: book)
    assert commands.build_lookups(None) == 1
    assert lookups_command == [] and book.closed
    assert "r1" in capsys.readouterr().err


def test_the_lookups_are_built_when_only_other_targets_run(monkeypatch, lookups_command, capsys):
    checked(monkeypatch, bookkeeping_cli, "configured_bookkeeping",
            lambda: Book([{"run_id": "r2", "name": "x", "target": "silver", "state": "running"}]))
    assert commands.build_lookups(None) == 0
    assert lookups_command == [1] and json.loads(capsys.readouterr().out)["masters"] == 0


def test_clear_is_refused_while_a_mastering_run_is_open(monkeypatch, capsys):
    checked(monkeypatch, bookkeeping_cli, "configured_bookkeeping",
            lambda: Book([{"run_id": "r1", "name": "gleif", "target": "mastering", "state": "running"}]))
    checked(monkeypatch, commands, "mdm_engine", lambda **kw: pytest.fail("the store was opened"))
    assert commands.clear_source(type("A", (), {"source": "s", "confirm": True})()) == 1
    assert "r1" in capsys.readouterr().err
