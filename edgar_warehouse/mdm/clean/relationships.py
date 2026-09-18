"""Typed relationship projection from immutable source endpoints."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from .evidence import instant
from .store import digest

LEGAL = {"company", "fund_structure", "government", "international_organization"}
CONTRACTS = {
    "AUDITED_BY": ({"company"}, {"company"}, None, "audit_firm"),
    "ISSUED_BY": ({"security"}, LEGAL, None, None),
    "EMPLOYED_BY": ({"person"}, {"company"}, None, None),
    "INSIDER_OF": ({"person"}, {"company"}, None, None),
    "HOLDS": ({"person", "company", "fund_structure"}, {"security"}, None, None),
    "MANAGES_FUND": (
        {"company", "person"},
        {"company", "fund_structure"},
        "adviser",
        "fund",
    ),
    "OWNERSHIP_PARENT": (LEGAL, LEGAL, None, None),
    "ACCOUNTING_PARENT": (LEGAL, LEGAL, None, None),
    "REPORTED_ULTIMATE_PARENT": (LEGAL, LEGAL, None, None),
    "IS_INTERNATIONAL_BRANCH_OF": ({"branch"}, LEGAL, None, None),
    "VENUE_OPERATOR": ({"venue"}, LEGAL, None, None),
    "VENUE_SEGMENT_OF": ({"venue"}, {"venue"}, None, None),
    "IS_SUBFUND_OF": (
        {"company", "fund_structure"},
        {"company", "fund_structure"},
        "fund",
        "fund",
    ),
    "IS_FEEDER_TO": (
        {"company", "fund_structure"},
        {"company", "fund_structure"},
        "fund",
        "fund",
    ),
    "IS_FUND-MANAGED_BY": (
        {"company", "fund_structure"},
        {"company", "person"},
        "fund",
        None,
    ),
}
HIERARCHIES = {
    "ACCOUNTING_PARENT",
    "IS_INTERNATIONAL_BRANCH_OF",
    "VENUE_SEGMENT_OF",
    "IS_SUBFUND_OF",
    "IS_FEEDER_TO",
}
MIN = datetime.min.replace(tzinfo=UTC)
MAX = datetime.max.replace(tzinfo=UTC)


def interval(edge):
    return instant(edge["valid_from"]) if edge.get("valid_from") else MIN, instant(
        edge["valid_to"]
    ) if edge.get("valid_to") else MAX


def overlap(a, b):
    lo, hi = interval(a)
    left, right = interval(b)
    return max(lo, left) < min(hi, right)


def project(
    claims: dict, state, entities: dict, as_of: str
) -> tuple[list[dict], list[dict]]:
    edges = {}
    reviews = []

    def review(reason, **context):
        reviews.append({"reason": reason, **context})

    for subject, record in sorted(claims.items()):
        for reported in record["relationships"]:
            target = reported.get("target_subject")
            kind = reported.get("type")
            contract = CONTRACTS.get(kind)
            context = {
                "assertion_id": record["assertion_id"],
                "relationship": reported,
                "subject": subject,
            }
            if not contract:
                review("unsupported_relationship", **context)
                continue
            if subject not in state.bindings or target not in state.bindings:
                review("unresolved_endpoint", **context)
                continue
            source_id = state.canonical[state.bindings[subject]]
            target_id = state.canonical[state.bindings[target]]
            if source_id == target_id:
                review("self_relationship", **context)
                continue
            source = entities[source_id]
            dest = entities[target_id]
            if source["kind"] not in contract[0] or dest["kind"] not in contract[1]:
                review("incompatible_endpoint", **context)
                continue
            if source.get("status") != "accepted" or dest.get("status") != "accepted":
                review("unresolved_endpoint_identity", **context)
                continue
            if not reported.get("valid_from"):
                review("unknown_relationship_start", **context)
                continue
            edge = {
                **reported,
                "source_id": source_id,
                "target_id": target_id,
                "derived": False,
            }
            if interval(edge)[0] >= interval(edge)[1]:
                review("invalid_relationship_interval", **context)
                continue
            required_profiles = [(source, contract[2]), (dest, contract[3])]
            eligible = True
            for entity, role in required_profiles:
                if role and not any(
                    p["role"] == role
                    and interval(p)[0] <= interval(edge)[0]
                    and interval(p)[1] >= interval(edge)[1]
                    for p in entity["profiles"]
                ):
                    review("missing_endpoint_profile", **context)
                    eligible = False
                    break
            if not eligible:
                continue
            identity = {k: v for k, v in edge.items() if k != "target_subject"}
            key = digest(identity)
            value = edges.setdefault(
                key, {**identity, "relationship_id": key, "evidence": []}
            )
            value["evidence"].append(
                {
                    "assertion_id": record["assertion_id"],
                    "source_subject": subject,
                    "target_subject": target,
                }
            )
    invalid = set()
    grouped = defaultdict(list)
    for key, e in edges.items():
        grouped[(e["type"], e.get("scope", ""))].append((key, e))
    for (kind, scope), group in grouped.items():
        if kind == "ACCOUNTING_PARENT":
            for i, (key, e) in enumerate(group):
                for other_key, other in group[i + 1 :]:
                    if (
                        e["source_id"] == other["source_id"]
                        and e["target_id"] != other["target_id"]
                        and overlap(e, other)
                    ):
                        invalid.update([key, other_key])
                        review(
                            "conflicting_accounting_parents",
                            edges=sorted([key, other_key]),
                        )
        if kind not in HIERARCHIES | {"OWNERSHIP_PARENT"}:
            continue
        adjacency = defaultdict(list)
        for key, e in group:
            adjacency[e["source_id"]].append((key, e))

        def walk(
            start, node, path, seen, lo, hi, adjacency=adjacency, kind=kind, scope=scope
        ):
            for key, e in adjacency[node]:
                a, b = interval(e)
                nlo = max(lo, a)
                nhi = min(hi, b)
                if nlo >= nhi:
                    continue
                if e["target_id"] == start:
                    cycle = sorted(set(path + [key]))
                    review("hierarchy_cycle", type=kind, scope=scope, edges=cycle)
                    if kind != "OWNERSHIP_PARENT":
                        invalid.update(cycle)
                elif e["target_id"] not in seen:
                    walk(
                        start,
                        e["target_id"],
                        path + [key],
                        seen | {e["target_id"]},
                        nlo,
                        nhi,
                    )

        for node in list(adjacency):
            walk(node, node, [], {node}, MIN, MAX)
    result = [e for key, e in edges.items() if key not in invalid]
    for e in result:
        e["evidence"] = sorted(e["evidence"], key=digest)
    # Calculated accounting ultimate parents preserve their full asserted path.
    now = instant(as_of)
    for (kind, scope), group in grouped.items():
        if kind != "ACCOUNTING_PARENT":
            continue
        eligible = {
            e["source_id"]: e
            for key, e in group
            if key not in invalid and interval(e)[0] <= now < interval(e)[1]
        }
        for source in sorted(eligible):
            path = []
            node = source
            seen = set()
            while node in eligible and node not in seen:
                seen.add(node)
                e = eligible[node]
                path.append(e["relationship_id"])
                node = e["target_id"]
            # A disputed outgoing parent leaves the ultimate parent unknown.
            if any(e["source_id"] == node and key in invalid for key, e in group):
                continue
            if node in seen:
                continue
            derived = {
                "type": "CALCULATED_ULTIMATE_PARENT",
                "source_id": source,
                "target_id": node,
                "scope": scope,
                "derived": True,
                "algorithm": "accounting-chain-v1",
                "as_of": as_of,
                "path": path,
            }
            derived["relationship_id"] = digest(derived)
            result.append(derived)
    return sorted(result, key=lambda e: e["relationship_id"]), reviews
