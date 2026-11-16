"""A refused lease says whether its renewal failed or the work met a stale lease (invented envelope).

The work waits on events the renewal thread sets, never on a clock: a slow machine changes how long a
test takes, not whether it passes."""

from __future__ import annotations

import threading

from edgar_warehouse.workers import __main__ as runner, control
from tests.support.patching import checked

ENVELOPE = {"heartbeat_seconds": 0.01, "claim": {"proof": [{"expires_at": "x"}], "step": "s", "key": "k"}}
PATIENCE = 30  # a test that is going to fail waits this long for an event that never comes


def counting(monkeypatch, behaviour, until):
    """Replace `control.renew` with `behaviour(call_number, envelope)`; the event is set at call number `until`."""
    reached, calls = threading.Event(), []

    def renew(envelope):
        calls.append(1)
        try:
            return behaviour(len(calls), envelope)
        finally:
            if len(calls) >= until:
                reached.set()

    checked(monkeypatch, control, "renew", renew)
    return reached


def test_state_reports_renewals_that_worked(monkeypatch):
    reached = counting(monkeypatch, lambda n, envelope: envelope, until=2)
    with runner.Renewal(dict(ENVELOPE)) as renewal:
        assert reached.wait(PATIENCE), "the heartbeat never renewed twice"
    assert renewal.error is None and renewal.renewed >= 2
    assert renewal.state().startswith(f"renewal ok: {renewal.renewed} renewals, last ")


def test_a_renewal_that_cannot_reach_bookkeeping_is_tried_again(monkeypatch):
    def drop_first(n, envelope):
        if n == 1:
            raise RuntimeError("SSL connection has been closed unexpectedly")
        return envelope

    reached = counting(monkeypatch, drop_first, until=3)
    with runner.Renewal(dict(ENVELOPE)) as renewal:
        assert reached.wait(PATIENCE), "the heartbeat never tried again"
    assert renewal.error is None and not renewal.lost and renewal.renewed >= 2


def test_a_refused_lease_stops_the_work_at_once(monkeypatch):
    def refuse(n, envelope):
        raise RuntimeError("(psycopg2.errors.RaiseException) Stale lease")

    counting(monkeypatch, refuse, until=1)
    work_that_would_run_on, stopped = threading.Event(), False
    try:
        with runner.Renewal(dict(ENVELOPE)) as renewal:
            work_that_would_run_on.wait(PATIENCE)  # the refusal interrupts this wait
    except KeyboardInterrupt:
        stopped = True
    assert stopped, "the work ran on after its lease was refused"
    assert renewal.lost and "Stale lease" in str(renewal.error) and renewal.renewed == 0
    assert renewal.state().startswith("renewal failed ") and "(0 renewals)" in renewal.state()


def test_work_reports_a_lost_lease_as_a_failed_unit(monkeypatch):
    class Profile:
        __file__ = runner.__file__

        @staticmethod
        def execute(envelope, artifacts):
            threading.Event().wait(PATIENCE)  # the work, which the refusal interrupts

    def refuse(n, envelope):
        raise RuntimeError("Stale lease")

    failures = []
    counting(monkeypatch, refuse, until=1)
    checked(monkeypatch, runner, "load_profile", lambda name: Profile)
    monkeypatch.setattr(runner, "Artifacts", lambda: None)
    checked(monkeypatch, control, "claim", lambda run, name, n: [dict(ENVELOPE)] if not failures else [])
    checked(monkeypatch, control, "fail", lambda envelope, message: failures.append(message))
    assert runner.work("p", "run", "file:///r", 3) == 1
    assert failures == ["RuntimeError"]
