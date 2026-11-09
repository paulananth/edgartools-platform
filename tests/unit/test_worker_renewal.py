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


def test_state_reports_a_renewal_that_failed(monkeypatch):
    def refuse(envelope):
        raise RuntimeError("Stale lease")

    monkeypatch.setattr(control, "renew", refuse)
    with runner.Renewal(dict(ENVELOPE)) as renewal:
        time.sleep(0.3)
    assert str(renewal.error) == "Stale lease" and renewal.renewed == 0
    assert renewal.state().startswith("renewal failed ") and "(0 renewals)" in renewal.state()
