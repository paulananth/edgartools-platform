"""The Company policy's switched-off additions, newest first.

Each ticket that declares rules switched off (or adds a table) is one layer:
peeling it must give back the digest the operator approved before it. A new
layer is one entry in `LAYERS`, and every pinned test sees it.
"""

from __future__ import annotations

import json

from edgar_warehouse.mdm.clean.store import canonical, digest


def _copy(policy: dict) -> dict:
    return json.loads(canonical(policy))


def without_cik(policy: dict) -> dict:
    """Company mastering ticket 15: the CIK matching rule and its Identifier
    Contract."""
    body = _copy(policy)
    company = body["kinds"]["company"]
    company["rules"] = [r for r in company["rules"] if r["rule_id"] != "company-cik"]
    company.pop("identifiers")
    return body


def without_cascade(policy: dict) -> dict:
    """Company mastering ticket 21: the cascade's seven passes."""
    body = _copy(policy)
    company = body["kinds"]["company"]
    company["rules"] = [r for r in company["rules"] if not r["rule_id"].startswith("sec-gleif-cascade-")]
    return body


def without_place_codes(policy: dict) -> dict:
    """Rules skill ticket 08: the reference tables in the policy body."""
    return {k: v for k, v in _copy(policy).items() if k != "reference"}


LAYERS = [without_cik, without_cascade, without_place_codes]


def peel(policy: dict) -> dict:
    """The policy with every layer peeled: what the operator approved."""
    for layer in LAYERS:
        policy = layer(policy)
    return policy


def digests(policy: dict) -> list[str]:
    """The policy's digest, then its digest after each layer is peeled."""
    found = [digest(policy)]
    for layer in LAYERS:
        policy = layer(policy)
        found.append(digest(policy))
    return found
