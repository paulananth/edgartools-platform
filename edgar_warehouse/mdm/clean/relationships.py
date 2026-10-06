"""Typed relationship projection from immutable source endpoints."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from .evidence import instant
from .store import digest

_LEGAL = ["company", "fund_structure", "government", "international_organization"]
# The relationship types MDM masters are data: `rules/merge/relationships.yaml`,
# carried in the Mastering Policy (profiling ticket 04; operator, 2026-10-06:
# "Types as data"). A policy registered before that section existed keeps the
# table the code held then, so it masters the same links; the rules file must
# agree with it (tests/mdm/test_clean_relationship_types.py).
TYPES_V0 = {
    "AUDITED_BY": {"from": ["company"], "to": ["company"], "to_profile": "audit_firm"},
    "ISSUED_BY": {"from": ["security"], "to": _LEGAL},
    "EMPLOYED_BY": {"from": ["person"], "to": ["company"], "capacities": ["director", "employee", "officer"]},
    "CONTROLS": {"from": ["person"], "to": ["company"],
                 "capacities": ["control_person", "owner", "ten_percent_owner"]},
    "HOLDS": {"from": ["company", "fund_structure", "person"], "to": ["security"]},
    "MANAGES_FUND": {"from": ["company", "person"], "to": ["company", "fund_structure"],
                     "from_profile": "adviser", "to_profile": "fund"},
    "OWNERSHIP_PARENT": {"from": _LEGAL, "to": _LEGAL, "hierarchy": True, "cycles": "review"},
    "ACCOUNTING_PARENT": {"from": _LEGAL, "to": _LEGAL, "hierarchy": True, "cycles": "invalid",
                          "one_parent": True, "ultimate_parent": "accounting-chain-v1"},
    "IS_DIRECTLY_CONSOLIDATED_BY": {"from": ["company"], "to": ["company"], "hierarchy": True,
                                    "cycles": "invalid", "one_parent": True,
                                    "ultimate_parent": "accounting-chain-v1"},
    "IS_ULTIMATELY_CONSOLIDATED_BY": {"from": ["company"], "to": ["company"], "hierarchy": True,
                                      "cycles": "invalid", "one_parent": True},
    "REPORTED_ULTIMATE_PARENT": {"from": _LEGAL, "to": _LEGAL},
    "IS_INTERNATIONAL_BRANCH_OF": {"from": ["branch"], "to": _LEGAL, "hierarchy": True, "cycles": "invalid"},
    "VENUE_OPERATOR": {"from": ["venue"], "to": _LEGAL},
    "VENUE_SEGMENT_OF": {"from": ["venue"], "to": ["venue"], "hierarchy": True, "cycles": "invalid"},
    "IS_SUBFUND_OF": {"from": ["company", "fund_structure"], "to": ["company", "fund_structure"],
                      "from_profile": "fund", "to_profile": "fund", "hierarchy": True, "cycles": "invalid"},
    "IS_FEEDER_TO": {"from": ["company", "fund_structure"], "to": ["company", "fund_structure"],
                     "from_profile": "fund", "to_profile": "fund", "hierarchy": True, "cycles": "invalid"},
    "IS_FUND-MANAGED_BY": {"from": ["company", "fund_structure"], "to": ["company", "person"],
                           "from_profile": "fund"},
}
# The keys a type may carry, and the ultimate-parent algorithms this code runs.
_TYPE_KEYS = {"from", "to", "from_profile", "to_profile", "capacities", "hierarchy", "cycles", "one_parent",
              "ultimate_parent"}
ULTIMATE_PARENT_ALGORITHMS = {"accounting-chain-v1"}
CYCLES = {"invalid", "review"}


def types_of(policy: dict) -> dict:
    """The relationship types a policy masters: its own, or the table every
    earlier policy used."""
    return policy["relationships"]["types"] if "relationships" in policy else TYPES_V0


def check_types(section: dict) -> None:
    """Refuse a relationship-types section that could not run exactly as written."""
    from .evidence import KINDS
    from .store import Conflict

    if not isinstance(section, dict) or set(section) != {"version", "types"} or not section.get("version"):
        raise Conflict("The relationships section holds a version and its types")
    if not isinstance(section["types"], dict) or not section["types"]:
        raise Conflict("The relationships section declares at least one type")
    for name, spec in section["types"].items():
        if not isinstance(name, str) or not name or not isinstance(spec, dict):
            raise Conflict(f"Relationship type {name!r} must be a name with its rules")
        if set(spec) - _TYPE_KEYS:
            raise Conflict(f"Relationship type {name} has an unknown key: {sorted(set(spec) - _TYPE_KEYS)}")
        for end in ("from", "to"):
            kinds = spec.get(end)
            if not isinstance(kinds, list) or not kinds:
                raise Conflict(f"Relationship type {name} names at least one kind at its {end} end")
            if set(kinds) - KINDS:
                raise Conflict(f"Relationship type {name} names an unknown kind: {sorted(set(kinds) - KINDS)}")
        if "capacities" in spec and (not isinstance(spec["capacities"], list) or not spec["capacities"]):
            raise Conflict(f"Relationship type {name}: capacities is a list of names")
        if spec.get("hierarchy"):
            if spec.get("cycles") not in CYCLES:
                raise Conflict(f"Relationship type {name}: a hierarchy says what its cycles do: invalid or review")
        elif {"cycles", "one_parent", "ultimate_parent"} & set(spec):
            raise Conflict(f"Relationship type {name}: cycles, one_parent and ultimate_parent go only on a hierarchy")
        if "ultimate_parent" in spec and spec["ultimate_parent"] not in ULTIMATE_PARENT_ALGORITHMS:
            raise Conflict(f"Relationship type {name}: unknown ultimate-parent algorithm {spec['ultimate_parent']}")


MIN = datetime.min.replace(tzinfo=UTC)
MAX = datetime.max.replace(tzinfo=UTC)


# A link stated before its other end is an accepted entity waits for it,
# quietly: it is not a steward's review (mastering to-do 13).
WAITING = {"unresolved_endpoint", "unresolved_endpoint_identity"}

# What makes two statements one relationship (operator, 2026-10-01, design 1):
# its type, its two ends and its scope, and for a Person link its capacity
# (mastering to-do 14). Dates, status, title and other properties are a period
# of that relationship, so a restatement keeps the relationship's id.
IDENTITY = ("type", "source_id", "target_id", "scope", "capacity")
# What a dated sighting says: on which event date, on what basis, whether the
# capacity was held, and the title then.
SIGHTING = {"on", "basis", "held", "title"}
BASES = {"observed", "stated"}
# What a reported link names that is not a period: its identity, its ends as
# records, and the keys a projected link adds. Everything else is the period.
NOT_PERIOD = {*IDENTITY, "source_subject", "target_subject", "relationship_id", "derived",
              "periods", "evidence", "last_seen", *SIGHTING}


def interval(edge):
    return instant(edge["valid_from"]) if edge.get("valid_from") else MIN, instant(
        edge["valid_to"]
    ) if edge.get("valid_to") else MAX


def overlap(a, b):
    lo, hi = interval(a)
    left, right = interval(b)
    return max(lo, left) < min(hi, right)


def fold_sightings(sightings: list[dict]) -> tuple[list[dict], list[dict]]:
    """A link's dated sightings, folded into its periods by event date.

    A Forms 3/4/5 filing restates the owner's capacities on every filing, so
    the first sighting opens a period with an observed start, and a later one
    that drops the capacity ends it at its event date. A sighting after an
    observed end opens a new period. Silence ends nothing.

    Stated outranks observed (spec, "Conflict and review states"): on a day
    with a stated sighting, that day's observed ones are left out, and a stated
    end replaces the observed end before it. A sighting after a stated end does
    not reopen the link: it is returned as a contradiction for a steward. A
    sighting on the day of a stated end is ordinary reporting lag.
    """
    stated_days = {instant(s["on"]) for s in sightings if s["basis"] == "stated"}
    periods, contradictions = [], []
    current = stated_end = None
    # A drop on the same day as a sighting comes after it.
    for s in sorted(sightings, key=lambda s: (instant(s["on"]), not s["held"], s["assertion_id"])):
        if s["basis"] == "observed" and instant(s["on"]) in stated_days:
            continue
        if not s["held"]:
            if current:
                # Held and dropped on one day is no period.
                if instant(s["on"]) > instant(current["valid_from"]):
                    periods.append({**current, "valid_to": s["on"], "valid_to_basis": s["basis"]})
                current = None
            elif s["basis"] == "stated" and periods and periods[-1]["valid_to_basis"] == "observed":
                periods[-1] = {**periods[-1], "valid_to": s["on"], "valid_to_basis": "stated"}
            stated_end = s["on"] if s["basis"] == "stated" else None
            continue
        if not current:
            if stated_end and s["basis"] == "observed":
                if instant(s["on"]) > instant(stated_end):
                    contradictions.append({"stated_end": stated_end, "on": s["on"],
                                           "assertion_id": s["assertion_id"],
                                           "subject": s["subject"]})
                continue
            current = {"valid_from": s["on"], "valid_from_basis": s["basis"], "valid_to": None,
                       "valid_to_basis": None, "last_observed": None, "titles": []}
            stated_end = None
        if s["basis"] == "observed":
            current["last_observed"] = s["on"]
        titles = current["titles"]
        if s.get("title") and (not titles or titles[-1]["title"] != s["title"]):
            titles.append({"title": s["title"], "on": s["on"]})
    if current:
        periods.append(current)
    return periods, contradictions


def project(
    claims: dict, state, entities: dict, as_of: str, types: dict | None = None
) -> tuple[list[dict], list[dict]]:
    """Each stated link checked against its type (`types`, from the policy;
    `TYPES_V0` for a policy registered without them), folded into one
    relationship per identity, with its periods."""
    types = TYPES_V0 if types is None else types
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
            spec = types.get(kind)
            context = {
                "assertion_id": record["assertion_id"],
                "relationship": reported,
                "subject": subject,
            }
            if not spec:
                review("unsupported_relationship", **context)
                continue
            capacities = spec.get("capacities")
            if capacities and reported.get("capacity") not in capacities:
                review("unsupported_capacity", **context)
                continue
            # A Person link is stated as dated sightings, folded below; an
            # observed start is enough. Other links state their periods.
            sighting = reported.get("on")
            if capacities and not sighting:
                review("unknown_relationship_start", **context)
                continue
            if sighting and reported.get("basis", "observed") not in BASES:
                review("unknown_date_basis", **context)
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
            if source["kind"] not in spec["from"] or dest["kind"] not in spec["to"]:
                review("incompatible_endpoint", **context)
                continue
            if source.get("status") != "accepted" or dest.get("status") != "accepted":
                review("unresolved_endpoint_identity", **context,
                       missing=[end for end, entity in (("source", source), ("target", dest))
                                if entity.get("status") != "accepted"])
                continue
            if sighting:
                period = {"valid_from": sighting}
            else:
                if not reported.get("valid_from"):
                    review("unknown_relationship_start", **context)
                    continue
                period = {k: v for k, v in reported.items() if k not in NOT_PERIOD}
                if interval(period)[0] >= interval(period)[1]:
                    review("invalid_relationship_interval", **context)
                    continue
            required_profiles = [(source, spec.get("from_profile")), (dest, spec.get("to_profile"))]
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
            # Only a Person link has a capacity, so every other link keeps its id.
            if reported.get("capacity"):
                identity["capacity"] = reported["capacity"]
            key = digest([identity[k] for k in IDENTITY if k in identity])
            value = edges.setdefault(
                key,
                {**identity, "derived": False, "relationship_id": key, "periods": [],
                 "evidence": [], "last_seen": None},
            )
            if sighting:
                value.setdefault("sightings", []).append(
                    {"on": sighting, "basis": reported.get("basis", "observed"),
                     "held": reported.get("held", True), "title": reported.get("title"),
                     "assertion_id": record["assertion_id"], "subject": subject})
            elif period not in value["periods"]:
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
    for key, e in list(edges.items()):
        if "sightings" not in e:
            continue
        e["periods"], contradictions = fold_sightings(e.pop("sightings"))
        # One review per link, naming the first sighting after the stated end.
        if contradictions:
            review("contradicts_stated_end", relationship_id=key, **contradictions[0],
                   entities=sorted({e["source_id"], e["target_id"]}))
        # Only drops, and nothing ever held: no link.
        if not e["periods"]:
            del edges[key]
    invalid = set()
    grouped = defaultdict(list)
    for key, e in edges.items():
        e["periods"] = sorted(e["periods"], key=lambda p: (interval(p), digest(p)))
        # Each period is checked on its own, never merged into one span: a
        # parent held, left and held again does not overlap the one between.
        for period in e["periods"]:
            grouped[(e["type"], e["scope"])].append((key, {**e, **period}))
    for (kind, scope), group in grouped.items():
        spec = types.get(kind) or {}
        if spec.get("one_parent"):
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
        if not spec.get("hierarchy"):
            continue
        adjacency = defaultdict(list)
        for key, e in group:
            adjacency[e["source_id"]].append((key, e))

        def walk(
            start, node, path, seen, lo, hi, adjacency=adjacency, kind=kind, scope=scope, spec=spec
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
                    if spec.get("cycles") == "invalid":
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
    result += _ultimate_parents(grouped, invalid, types, as_of)
    return sorted(result, key=lambda e: e["relationship_id"]), reviews


def _ultimate_parents(grouped: dict, invalid: set, types: dict, as_of: str) -> list[dict]:
    """Calculated ultimate parents, for each hierarchy whose type names an
    algorithm (accounting-chain-v1 is the one this code runs): each record's
    current parent chain walked to its end, with the full asserted path."""
    result = []
    now = instant(as_of)
    for (kind, scope), group in grouped.items():
        if (types.get(kind) or {}).get("ultimate_parent") != "accounting-chain-v1":
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
    return result
