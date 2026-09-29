"""The operator's approval, recorded as the rules skill does: of the version
and test run `rules pending` showed."""
from __future__ import annotations

from sqlalchemy import text

from edgar_warehouse.rules.db import EVIDENCE_HASH


def approve(rules, kind, name, version, *, by="operator", words="approved", overrule=None):
    with rules.engine.connect() as conn:
        shown = conn.scalar(text(f"SELECT {EVIDENCE_HASH} FROM rules.rule_version WHERE kind=:k AND name=:n AND version=:v"),
                            {"k": kind, "n": name, "v": version})
    return rules.approve(kind, name, version, evidence=shown, by=by, words=words, overrule=overrule)
