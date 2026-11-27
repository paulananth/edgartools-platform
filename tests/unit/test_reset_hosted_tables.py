"""A table reset waits for the sessions that block it to leave, and names them when they stay."""
import contextlib
import importlib.util
from pathlib import Path

import pytest

from tests.support.patching import checked

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("reset_hosted_tables", ROOT / "infra/scripts/reset-hosted-tables.py")
reset = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reset)


class Engine:
    def connect(self):
        return contextlib.nullcontext(object())


def sessions(monkeypatch, answers):
    answers = iter(answers)
    checked(monkeypatch, reset, "blocking_sessions", lambda conn, mirror_suspended=False: next(answers))


def test_the_reset_starts_once_a_suspended_mirrors_walsender_has_left(monkeypatch):
    sessions(monkeypatch, ["walsender 1", "walsender 1", ""])
    reset.wait_for_quiet(Engine(), minutes=1, every=0)


def test_a_session_that_stays_past_the_bound_refuses_the_reset_and_is_named(monkeypatch):
    sessions(monkeypatch, ["walsender 1"] * 3)
    with pytest.raises(reset.BlockedError, match="walsender 1"):
        reset.wait_for_quiet(Engine(), minutes=0, every=0)


def test_a_blocked_reset_says_what_blocks_it(monkeypatch, capsys):
    import edgar_warehouse.database_connections as connections

    class Disposable(Engine):
        def dispose(self):
            pass
    sessions(monkeypatch, ["walsender 1"])
    checked(monkeypatch, reset, "load_manifest", lambda path, store: [])
    checked(monkeypatch, connections, "store_engine", lambda store: Disposable())
    code = reset.main(["--store", "mdm", "--manifest", "m.yaml", "--apply", "--words", "invented", "--plan-sha256", "0" * 64])
    assert code == 2 and "walsender 1" in capsys.readouterr().err
