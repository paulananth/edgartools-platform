"""One file of records into masters: the engine's rules around plain lookups, in one transaction."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from uuid import uuid4

from edgar_warehouse.mdm import matching
from edgar_warehouse.mdm.evidence import PROFILE_KINDS
from edgar_warehouse.mdm.identifier_types import TYPES
from edgar_warehouse.rules.source_engine import (
    link_matching_records,
    plan_record_matches,
    prepare_current_records,
    prepare_master_records,
)

NORMALIZERS = {kind.normalizer_name: kind.upper for kind in TYPES.values()}
KINDS = {role: sorted(kinds) for role, kinds in PROFILE_KINDS.items()}
WAITING = "binding_required"


@dataclass(frozen=True)
class Settings:
    policy: dict
    policy_digest: str
    kind: str
    as_of: str


def file_key(records: list[dict]) -> str:
    return hashlib.sha256("".join(sorted(r["assertion_id"] for r in records)).encode()).hexdigest()


def first(value):
    return value[0] if isinstance(value, list) else value


def name_keys(record: dict) -> list[tuple]:
    """The LEIs the record's Name Count pass found, so a name match is a lookup."""
    found = ((record.get("provenance") or {}).get("matching") or {}).get("name_count") or {}
    cascade = (found.get("cascade") or {}).get("lei")
    entries = found.get("leis") or []
    named = entries[0][0] if entries and entries[0] else None
    return [(role, value, record["subject"]) for role, value in (("cascade", cascade), ("name_count", named))
            if isinstance(value, str) and value]


def merge_file(store, settings: Settings, records: list[dict], *, again: bool = False) -> dict:
    """Merge one file, or nothing if it is done. `again` delivers a finished file a second time."""
    key = file_key(records)
    try:
        store.take_lock()
        if store.file_done(key) and not again:
            store.commit()
            return {"file": key, "skipped": True}
        counts = _merge(store, settings, records, key, again)
        store.commit()
        return {"file": key, "skipped": False, **counts}
    except BaseException:
        store.rollback()
        raise


def _merge(store, settings: Settings, records: list[dict], key: str, again: bool) -> dict:
    file_no = store.last_file() + 1
    store.load_stage([(r["assertion_id"], r["subject"], r["source_code"], first(r["identifiers"].get("lei")),
                       json.dumps(r, separators=(",", ":"))) for r in records],
                     list({k for r in records for k in name_keys(r)}))
    subjects = sorted({r["subject"] for r in records})
    bound = store.bound(subjects)
    counts = Counter()
    survivors = _match_identifiers(store, settings, records, bound, counts, file_no)
    named = _match_names(store, settings, records, bound, counts)
    bound.update(named)
    rules = _rules(settings)
    waits = {rule["source"] for rule in rules if rule.get("on_no_match") == "wait"}
    store.open_reviews(WAITING, [(r["subject"], r["assertion_id"]) for r in records
                                 if r["source_code"] in waits and r["subject"] not in bound])
    store.close_reviews(WAITING, sorted(named))
    store.save_records()
    held = {s: bound[s] for s in subjects if s in bound} | named
    if held:
        store.bind_records(held)
    touched = set(held.values()) | survivors
    if touched:
        _write_masters(store, settings, sorted(touched), file_no, counts)
    if not (again and store.file_done(key)):
        store.finish_file(key, len(records))
    return {"records": len(records), **counts}


def _rules(settings: Settings) -> list[dict]:
    return [rule for kind, rule in matching.active_rules(settings.policy) if kind == settings.kind]


def _match_identifiers(store, settings: Settings, records, bound: dict, counts: Counter, file_no: int) -> set:
    known = [r["subject"] for r in records if r["subject"] in bound]
    plan = plan_record_matches({
        "policy": settings.policy, "assertions": records, "decisions": [], "identities": [], "bound": known,
        "bound_entities": {s: bound[s] for s in known}, "withheld": store.withheld(known), "released": [],
        "normalizers": NORMALIZERS})
    if not plan["applicable"]:
        return set()
    wanted, normal = defaultdict(set), {}
    for items in plan["applicable"].values():
        for item in items:
            wanted[item["namespace"]].add(item["value"])
            normal[(item["namespace"], item["raw"])] = item["value"]
    found = defaultdict(dict)
    for namespace, value, entity in store.holders(wanted):
        found[(namespace, value)][entity] = settings.kind
    reached = set()
    for items in plan["applicable"].values():
        hit = {e for item in items for e in found.get((item["namespace"], item["value"]), {})}
        if len(hit) > 1:
            reached |= hit
    made = link_matching_records({
        "plan": plan, "found": [{"namespace": n, "value": v, "records": r} for (n, v), r in found.items()],
        "suspended": [], "newest": {kind: None for kind in plan["kinds"]},
        "new_ids": [str(uuid4()) for _ in plan["applicable"]], "refused": [], "as_of": settings.as_of,
        "consolidations": store.decisions_about(sorted(reached)) if reached else []})
    store.add_identifiers(sorted({(m["namespace"], normal.get((m["namespace"], m["raw"]), m["raw"]), m["entity_id"])
                                  for m in made["mints"]}))
    moved, survivors = {}, set()

    def live(entity):
        while entity in moved:
            entity = moved[entity]
        return entity

    for decision in made["decisions"]:
        if decision["operation"] == "merge":
            left, right = live(decision["left"]), live(decision["right"])
            if left == right:
                continue
            stored = store.oldest([left, right])
            keep = stored[0] if stored else min(left, right)
            gone = right if keep == left else left
            store.repoint(keep, gone)
            if gone in stored:
                alias = {"entity_id": gone, "kind": settings.kind, "canonical_id": keep, "status": "alias"}
                store.write_masters([(gone, json.dumps(alias))], file_no)
            store.add_decision(decision, keep, gone)
            moved[gone] = keep
            survivors.discard(gone)
            survivors.add(keep)
            counts["merges"] += 1
    for subject, entity in list(bound.items()):
        bound[subject] = live(entity)
    for decision in made["decisions"]:
        if decision["operation"] == "bind":
            bound[decision["subject"]] = live(decision["entity_id"])
            store.add_withheld([(decision["subject"], w["namespace"], w["raw"]) for w in decision.get("withheld") or ()])
    for review in made["reviews"]:
        counts[review["reason"]] += 1
        if review.get("subject"):
            store.open_reviews(review["reason"], [(review["subject"], review.get("assertion_id"))])
    return survivors


def _match_names(store, settings: Settings, records, bound: dict, counts: Counter) -> dict:
    named, values = {}, {}
    for rule in _rules(settings):
        if rule.get("family") != matching.FAMILY:
            continue
        cascade = any(test["primitive"] == matching.cascade.TEST for test in rule["when"])
        holders = sorted(r["subject"] for r in records if r["source_code"] == rule["holder_source"])
        pairs = [(json.loads(c), json.loads(h)) for c, h in store.name_pairs(
            "cascade" if cascade else "name_count", rule["holder_source"], rule["source"], holders)]
        involved = {side["subject"] for pair in pairs for side in pair}
        bound.update(store.bound(sorted(involved - set(bound))))
        pairs = [(c, h) for c, h in pairs if c["subject"] not in bound and c["subject"] not in named and h["subject"] in bound]
        if not pairs:
            continue
        reach, lei = defaultdict(set), {}
        for (candidate, holder), (passed, flagged) in zip(
                pairs, matching.compare_candidate_records(rule, [(h, c) for c, h in pairs]), strict=True):
            if passed:
                reach[candidate["subject"]].add(bound[holder["subject"]])
                lei[candidate["subject"]] = first(candidate["identifiers"]["lei"])
            elif flagged:
                counts["cascade_flagged_pair"] += 1
        held = store.lei_held(sorted({e for found in reach.values() for e in found})) if reach else {}
        vetoes = any(test["primitive"] == matching.HELD_LEI_TEST for test in rule["when"])
        for subject, found in reach.items():
            if len(found) > 1:
                counts["ambiguous_name_match"] += 1
                continue
            entity = next(iter(found))
            if vetoes and held.get(entity, set()) - {lei[subject]}:
                continue
            held.setdefault(entity, set()).add(lei[subject])
            named[subject], values[subject] = entity, lei[subject]
    store.add_identifiers([("lei", values[s], e) for s, e in named.items()])
    return named


def _write_masters(store, settings: Settings, entities: list, file_no: int, counts: Counter) -> None:
    records = [json.loads(body) for body in store.member_bodies(entities)]
    bindings = store.members_bound(entities)
    subjects = sorted({r["subject"] for r in records})
    claims = prepare_current_records(records, settings.as_of, set())
    identities = {e: {"entity_id": e, "kind": settings.kind, "published_at": settings.as_of} for e in entities}
    masters, reviews, _ = prepare_master_records({
        "identities": identities, "canonical": {e: e for e in entities}, "bindings": bindings, "quarantined": {},
        "claims": claims, "policy": settings.policy, "overrides": store.overrides(subjects), "decisions": [],
        "as_of": settings.as_of, "policy_digest": settings.policy_digest, "withheld": store.withheld(subjects),
        "profile_kinds": KINDS})
    for review in reviews:
        counts[str(review.get("reason"))] += 1
    store.write_masters([(e, json.dumps(body)) for e, body in masters.items()], file_no)
