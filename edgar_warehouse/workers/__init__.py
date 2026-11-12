"""Workers for configured work, each in its own process.

A worker pulls task envelopes from Bookkeeping's commands, does the work
(`execute`), renews its lease while it runs, checks what it wrote once
(`check`) and reports both. It never receives Bookkeeping's engine, database
or methods: it speaks only through the `python -m edgar_warehouse.bookkeeping`
commands. A new profile is a new module here and an entry in PROFILES;
Bookkeeping does not change.
"""
from __future__ import annotations

from importlib import import_module

PROFILES = {"artifact.copy": "copy", "jsonl.count": "count", "source.read": "source_read", "source.combine": "source_combine",
            "mdm.prepare": "mdm_prepare", "mastering.merge": "mastering_merge", "provider.capture": "provider_capture",
            "journal.record": "journal_record", "silver.land": "silver_land", "silver.derive": "silver_derive"}


def profile(name: str):
    if name not in PROFILES:
        raise SystemExit(f"Unknown worker profile: {name}")
    return import_module(f"{__name__}.{PROFILES[name]}")
