"""Shared fixture builders; retired calculation tests are catalogued in ticket 08."""

from __future__ import annotations

import argparse


from tests.integration import test_clean_mdm_postgres as core


DIRECT = "IS_DIRECTLY_CONSOLIDATED_BY"


def args(subject, key=None, **more):
    base = dict(search=None, limit=5, as_of=None, as_at=None, hops=1, relationship_type="", detail="brief", page=None)
    return argparse.Namespace(subject=subject, key=key, **{**base, **more})


def company(key, parent=None, **more):
    relationships = [{"type": DIRECT, "target_subject": parent["subject"], "valid_from": core.AT,
                      "valid_to": None, "scope": "consolidated"}] if parent else []
    return core.source(key, fields={"name": f"Company {key}", "description": f"About {key}"},
                       identifiers={"cik": f"000000{key}"}, relationships=relationships, **more)


def load_group(database):
    """Three companies in a parent chain (c -> b -> a), one with a tax cross-reference."""
    a = company("a")
    b = company("b", a, cross_references={"tax": "12-3"})
    c = company("c", b)
    records = [a, b, c]
    pairs = [core.identity_and_binding(r) for r in records]
    core.apply(database, 1, assertions=records, identities=[i for i, _ in pairs], decisions=[d for _, d in pairs])
    return {r["record_key"]: i["entity_id"] for r, (i, _) in zip(records, pairs)}
