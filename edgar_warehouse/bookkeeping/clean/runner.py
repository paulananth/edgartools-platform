"""Configured stage order, live renewal and reconciliation before execution."""
from __future__ import annotations

import threading

from sqlalchemy import text

from .config import Blocked


class Authority:
    """Latest proof passed separately to a destination's transaction guard."""
    def __init__(self, claim):
        self.claim = claim
        self.error = None
        self.lock = threading.Lock()

    def current(self):
        with self.lock:
            if self.error is not None:
                raise Blocked("Lease renewal failed") from self.error
            return self.claim


def run(book, run_id: str, ledger, *, limit: int = 1000) -> dict:
    """Bounded worker invocation. Exhaustion retains runnable pending work."""
    if not 1 <= limit <= 10000:
        raise ValueError("Worker limit must be 1..10000")
    _, config, _, _ = book._frozen(run_id)
    processed = 0
    for step in config["steps"]:
        with book.engine.connect() as conn:
            keys = conn.scalars(text("SELECT unit_key FROM bookkeeping.work_item WHERE run_id=CAST(:r AS uuid) AND step=:s AND state<>'verified' ORDER BY ordinal LIMIT :n"), {"r": run_id, "s": step["name"], "n": limit - processed}).all()
        for key in keys:
            claim = book.claim(run_id, step["name"], key)
            if claim is None:
                continue
            authority = Authority(claim)
            stop = threading.Event()

            def renew():
                while not stop.wait(config["heartbeat_seconds"]):
                    try:
                        updated = book.heartbeat(authority.current())
                        with authority.lock:
                            authority.claim = updated
                    except Exception as exc:
                        with authority.lock:
                            authority.error = exc
                        return

            thread = threading.Thread(target=renew, name=f"bookkeeping-heartbeat-{claim.attempt}", daemon=True)
            thread.start()
            try:
                item = book.item(claim)
                book.artifacts.verified(item["unit"]["input"])
                capability = book.registry.operations[step["operation"]]
                receipt = capability.reconcile(book, item, authority)
                if receipt is None:
                    receipt = capability.execute(book, item, authority)
                # Stop renewal before completion releases authority.
                stop.set()
                thread.join()
                book.record_verified_completion(authority.current(), receipt)
                processed += 1
            except Exception as exc:
                stop.set()
                thread.join()
                try:
                    book.wait(authority.current(), type(exc).__name__)
                except Exception:
                    # A dead/stale owner cannot change the current attempt.
                    pass
                if isinstance(exc, Blocked):
                    book._call("SELECT bookkeeping.block_run(CAST(:r AS uuid),:m)", r=run_id, m=str(exc))
                raise
            finally:
                stop.set()
                thread.join()
        if processed >= limit:
            break
    # Drain only this invocation's bounded delivery envelope. If other workers
    # completed more, finalization exposes the remaining intent as incomplete.
    book.deliver(ledger, run_id, limit=min(limit, 1000))
    return book.finalize(run_id)
