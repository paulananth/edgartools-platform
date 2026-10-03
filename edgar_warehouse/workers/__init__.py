"""Workers and verifiers for configured work, each in its own process.

A worker pulls task envelopes from Bookkeeping's commands, does the work,
renews its lease while it runs and reports a candidate. A verifier, a
separate run of this package, reads the destination back and reports the
step's checks. Neither ever receives Bookkeeping's engine, database or
methods: they speak only through the `python -m edgar_warehouse.bookkeeping`
commands (mastering to-do 20a). A new profile is a new module here and an
entry in PROFILES; Bookkeeping does not change.
"""
from __future__ import annotations

from importlib import import_module

PROFILES = {"artifact.copy": "copy", "jsonl.count": "count"}


def profile(name: str):
    if name not in PROFILES:
        raise SystemExit(f"Unknown worker profile: {name}")
    return import_module(f"{__name__}.{PROFILES[name]}")
