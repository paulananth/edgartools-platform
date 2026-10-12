"""A worker takes units one at a time (`workers/__main__.py`): a claimed unit
never waits behind another while its lease runs out, and a failure ends the
call so the failed unit is not claimed again and left held."""
import pytest

from edgar_warehouse.workers import __main__ as workers
from edgar_warehouse.workers.__main__ import one_at_a_time


def test_units_are_claimed_one_at_a_time_up_to_the_limit():
    asked, units = [], iter(range(5))

    def fetch(n):
        asked.append(n)
        return [u for u in [next(units, None)] if u is not None]

    assert list(one_at_a_time(fetch, 3)) == [0, 1, 2]
    assert asked == [1, 1, 1]


def test_claiming_stops_when_no_unit_is_ready():
    asked = []
    assert list(one_at_a_time(lambda n: asked.append(n) or [], 1000)) == []
    assert asked == [1]


@pytest.mark.parametrize("command", ["work", "verify"])
def test_a_failure_ends_the_call_before_another_claim(monkeypatch, command):
    unit = {"claim": {"step": "main", "key": "main-0", "run_id": "r"}, "heartbeat_seconds": 60, "candidate": {}}
    claims, failed = [], []

    class Failing:
        __file__ = workers.__file__

        @staticmethod
        def execute(envelope, artifacts):
            raise ValueError("unreadable")

        verify = execute

    monkeypatch.setattr(workers, "load_profile", lambda name: Failing)
    monkeypatch.setattr(workers, "runtime", lambda module: "digest")
    fetch = lambda *args: claims.append(args) or [dict(unit)]  # noqa: E731 - the failed unit comes back at once
    monkeypatch.setattr(workers.control, "claim", fetch)
    monkeypatch.setattr(workers.control, "verifications", fetch)
    monkeypatch.setattr(workers.control, "fail", lambda envelope, message: failed.append(message))
    if command == "work":
        assert workers.work("source.read", "r", 1000) == 1
    else:
        assert workers.verify("source.read", "r", "file:///reports", 1000) == 1
    assert len(claims) == 1 and failed == ["ValueError"]
