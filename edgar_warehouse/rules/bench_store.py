"""Store one try as a draft. This file refuses, and it does not open a database."""

from __future__ import annotations


def store_draft(case) -> dict:
    """Refuse. The draft is not stored, approved, or switched on."""
    return {"refused": "Store this draft is not available yet"}
