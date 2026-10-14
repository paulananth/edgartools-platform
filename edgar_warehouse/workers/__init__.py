"""Workers and verifiers for configured work, each in its own process.

A worker pulls task envelopes from Bookkeeping's commands, does the work,
renews its lease while it runs and reports a candidate. A verifier, a
separate run of this package, reads the destination back and reports the
step's checks. Neither ever receives Bookkeeping's engine, database or
methods: they speak only through the `python -m edgar_warehouse.bookkeeping`
commands (mastering to-do 20a). A new profile is a new module here and an
entry in PROFILES; Bookkeeping does not change. A profile may also offer
`confirm`, a check that does not redo the work; the check loop then redoes
only the step's first unit in a run and a random sample (ticket 72).
"""
from __future__ import annotations

from importlib import import_module

PROFILES = {"artifact.copy": "copy", "jsonl.count": "count", "source.read": "source_read", "source.combine": "source_combine",
            "mdm.prepare": "mdm_prepare", "mdm.merge": "mdm_merge", "mdm.publish": "mdm_publish", "provider.capture": "provider_capture",
            "journal.record": "journal_record"}


class Redo(Exception):
    """Raised by a step's `confirm` when it cannot confirm this output without
    redoing the work; the check loop then redoes it and records why (ticket 72)."""


def profile(name: str):
    if name not in PROFILES:
        raise SystemExit(f"Unknown worker profile: {name}")
    return import_module(f"{__name__}.{PROFILES[name]}")
