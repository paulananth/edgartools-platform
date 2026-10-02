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
    "IS_DIRECTLY_CONSOLIDATED_BY": ({"company"}, {"company"}, None, None),
    "IS_ULTIMATELY_CONSOLIDATED_BY": ({"company"}, {"company"}, None, None),
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
    "IS_DIRECTLY_CONSOLIDATED_BY",
    "IS_ULTIMATELY_CONSOLIDATED_BY",
    "IS_INTERNATIONAL_BRANCH_OF",
    "VENUE_SEGMENT_OF",
    "IS_SUBFUND_OF",
    "IS_FEEDER_TO",
}
MIN = datetime.min.replace(tzinfo=UTC)
MAX = datetime.max.replace(tzinfo=UTC)


# A link stated before its other end is an accepted entity waits for it,
# quietly: it is not a steward's review (mastering to-do 13).
WAITING = {"unresolved_endpoint", "unresolved_endpoint_identity"}

# What makes two statements one relationship (operator, 2026-10-01, design 1):
# its type, its two ends and its scope. Dates, status and other properties are
# a period of that relationship, so a restatement keeps the relationship's id.
IDENTITY = ("type", "source_id", "target_id", "scope")
# What a reported link names that is not a period: its identity, its ends as
# records, and the keys a projected link adds. Everything else is the period.
NOT_PERIOD = {*IDENTITY, "source_subject", "target_subject", "relationship_id", "derived",
              "periods", "evidence", "last_seen"}


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
        # A review names a `subject` or the `entities` it is about, so a later
        # save finds it (`merge.review_scope`). A link checked once per period
        # can find one problem twice.
        if {"reason": reason, **context} not in reviews:
            reviews.append({"reason": reason, **context})

    for subject, record in sorted(claims.items()):
        for reported in record["relationships"]:
            # A link starts at the reading's own record unless it names another
            # (a GLEIF relationship record starts at its child's Level 1 record).
            start = reported.get("source_subject") or subject
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
            if start not in state.bindings or target not in state.bindings:
                review("unresolved_endpoint", **context,
                       missing=[end for end, key in (("source", start), ("target", target))
                                if key not in state.bindings])
                continue
            source_id = state.canonical[state.bindings[start]]
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
                review("unresolved_endpoint_identity", **context,
                       missing=[end for end, entity in (("source", source), ("target", dest))
                                if entity.get("status") != "accepted"])
                continue
            if not reported.get("valid_from"):
                review("unknown_relationship_start", **context)
                continue
            period = {k: v for k, v in reported.items() if k not in NOT_PERIOD}
            if interval(period)[0] >= interval(period)[1]:
                review("invalid_relationship_interval", **context)
                continue
            required_profiles = [(source, contract[2]), (dest, contract[3])]
            eligible = True
            for entity, role in required_profiles:
                if role and not any(
                    p["role"] == role
                    and interval(p)[0] <= interval(period)[0]
                    and interval(p)[1] >= interval(period)[1]
                    for p in entity["profiles"]
                ):
                    review("missing_endpoint_profile", **context)
                    eligible = False
                    break
            if not eligible:
                continue
            identity = {
                "type": kind,
                "source_id": source_id,
                "target_id": target_id,
                "scope": reported.get("scope", ""),
            }
            key = digest([identity[k] for k in IDENTITY])
            value = edges.setdefault(
                key,
                {**identity, "derived": False, "relationship_id": key, "periods": [],
                 "evidence": [], "last_seen": None},
            )
            if period not in value["periods"]:
                value["periods"].append(period)
            seen = record.get("source_meta", {}).get("effective_at")
            # Absence never closes a link (design 2): readers compare when it
            # was last stated with the latest publication.
            if seen and (value["last_seen"] is None or instant(seen) > instant(value["last_seen"])):
                value["last_seen"] = seen
            value["evidence"].append(
                {
                    "assertion_id": record["assertion_id"],
                    "source_subject": start,
                    "target_subject": target,
                }
            )
    invalid = set()
    grouped = defaultdict(list)
    for key, e in edges.items():
        e["periods"] = sorted(e["periods"], key=lambda p: (interval(p), digest(p)))
        # Each period is checked on its own, never merged into one span: a
        # parent held, left and held again does not overlap the one between.
        for period in e["periods"]:
            grouped[(e["type"], e["scope"])].append((key, {**e, **period}))
    for (kind, scope), group in grouped.items():
        if kind in {
            "ACCOUNTING_PARENT",
            "IS_DIRECTLY_CONSOLIDATED_BY",
            "IS_ULTIMATELY_CONSOLIDATED_BY",
        }:
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
                            entities=sorted({e["source_id"], e["target_id"], other["target_id"]}),
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
                    ends = {edges[k][end] for k in cycle for end in ("source_id", "target_id")}
                    review(
                        "hierarchy_cycle",
                        type=kind,
                        scope=scope,
                        edges=cycle,
                        entities=sorted(ends),
                    )
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
        if kind not in {"ACCOUNTING_PARENT", "IS_DIRECTLY_CONSOLIDATED_BY"}:
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
