"""A refused lease says whether its renewal failed or the work met a stale lease (invented envelope)."""

from __future__ import annotations

import time

from edgar_warehouse.workers import __main__ as runner, control

ENVELOPE = {"heartbeat_seconds": 0.05, "claim": {"proof": [{"expires_at": "x"}], "step": "s", "key": "k"}}


def test_state_reports_renewals_that_worked(monkeypatch):
    monkeypatch.setattr(control, "renew", lambda envelope: envelope)
    with runner.Renewal(dict(ENVELOPE)) as renewal:
        time.sleep(0.3)
    assert renewal.error is None and renewal.renewed >= 2
    assert renewal.state().startswith(f"renewal ok: {renewal.renewed} renewals, last ")


def test_a_renewal_that_cannot_reach_bookkeeping_is_tried_again(monkeypatch):
    calls = []

    def drop_once(envelope):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("SSL connection has been closed unexpectedly")
        return envelope

    monkeypatch.setattr(control, "renew", drop_once)
    with runner.Renewal(dict(ENVELOPE)) as renewal:
        time.sleep(0.3)
    assert renewal.error is None and not renewal.lost and renewal.renewed >= 2
    assert renewal.state().startswith(f"renewal ok: {renewal.renewed} renewals, last ")


def test_a_refused_lease_stops_the_work_at_once(monkeypatch):
    def refuse(envelope):
        raise RuntimeError("(psycopg2.errors.RaiseException) Stale lease")

    monkeypatch.setattr(control, "renew", refuse)
    started, stopped = time.monotonic(), False
    try:
        with runner.Renewal(dict(ENVELOPE)) as renewal:
            time.sleep(5)  # the work, which would run on
    except KeyboardInterrupt:
        stopped = True
    assert stopped and time.monotonic() - started < 2
    assert renewal.lost and "Stale lease" in str(renewal.error) and renewal.renewed == 0
    assert renewal.state().startswith("renewal failed ") and "(0 renewals)" in renewal.state()


def test_work_reports_a_lost_lease_as_a_failed_unit(monkeypatch, capsys):
    class Profile:
        __file__ = runner.__file__

        @staticmethod
        def execute(envelope, artifacts):
            time.sleep(5)

    def refuse(envelope):
        raise RuntimeError("Stale lease")

    failures = []
    monkeypatch.setattr(runner, "load_profile", lambda name: Profile)
    monkeypatch.setattr(runner, "Artifacts", lambda: None)
    monkeypatch.setattr(control, "claim", lambda run, name, n: [dict(ENVELOPE)] if not failures else [])
    monkeypatch.setattr(control, "renew", refuse)
    monkeypatch.setattr(control, "fail", lambda envelope, message: failures.append(message))
    assert runner.work("p", "run", "file:///r", 3) == 1
    assert failures == ["RuntimeError"]
    assert "s/k: Stale lease [renewal failed " in capsys.readouterr().err
