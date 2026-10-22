"""Frozen versioned Journal DDL; never regenerate an applied payload.

A storage change adds a new migration version. These files preserve the exact
statement bytes and checksums used by the initial native-store qualification.
"""
from pathlib import Path


BOUNDARY = "\n-- journal migration statement boundary --\n"


def statements(kind):
    if kind not in {"postgresql", "mysql", "mssql"}:
        raise ValueError("Unsupported Journal storage engine")
    return (Path(__file__).parent / "migrations" / "native" / (kind + "-v1.sql")).read_text().split(BOUNDARY)
