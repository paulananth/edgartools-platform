"""One file of records into masters: the engine's rules around plain lookups, in one transaction."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from uuid import uuid4

from edgar_warehouse.mdm.activation import activated
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
EXACT = "exact"
NAME_ID = "name_id"  # the cross reference an exact-name rule keys on unless it names another


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


def reference_of(record: dict, namespace: str) -> str | None:
    return first((record.get("cross_references") or {}).get(namespace))


def role_of(namespace: str) -> str:
    """The name-key role of a cross reference: the name id keeps its stored role, any other is its own namespace."""
    return EXACT if namespace == NAME_ID else namespace


def exact_namespaces(settings: "Settings") -> list[str]:
    """Every cross reference an exact-name rule of this kind keys on, declared or switched on."""
    rules = settings.policy["kinds"].get(settings.kind, {}).get("rules") or []
    return sorted({NAME_ID, *(r.get("cross_reference", NAME_ID) for r in rules if r.get("family") == matching.EXACT_NAME_FAMILY)})


def name_keys(record: dict, namespaces=(NAME_ID,)) -> list[tuple]:
    """The LEIs the record's Name Count pass found, so a name match is a lookup."""
    found = ((record.get("provenance") or {}).get("matching") or {}).get("name_count") or {}
    cascade = (found.get("cascade") or {}).get("lei")
    entries = found.get("leis") or []
    named = entries[0][0] if entries and entries[0] else None
    exact = [(role_of(ns), reference_of(record, ns)) for ns in namespaces]
    return [(role, value, record["subject"]) for role, value in (("cascade", cascade), ("name_count", named), *exact)
            if isinstance(value, str) and value]


def set_aside(store, records: list[dict], quiet: dict) -> None:
    """Records no rule may master: kept with their review, blocking unless the source says otherwise."""
    store.add_deferred([(r["deferred_id"], r["source_code"], r["reason"],
                         0 if r["reason"] in quiet.get(r["source_code"], ()) else 1, json.dumps(r)) for r in records])


def merge_file(store, settings: Settings, records: list[dict], *, again: bool = False,
               deferred: list[dict] = (), quiet: dict | None = None) -> dict:
    """Merge one file, or nothing if it is done. `again` delivers a finished file a second time."""
    key = file_key([*records, *({"assertion_id": r["deferred_id"]} for r in deferred)])
    try:
        store.take_lock()
        if store.file_done(key) and not again:
            store.commit()
            return {"file": key, "skipped": True}
        delivery = _delivery(store, records, deferred)
        set_aside(store, list(deferred), quiet or {})
        counts = _merge(store, settings, records, key, again) if records else {"records": 0}
        store.add_delivery(key, delivery)
        if not records:
            store.finish_file(key, 0)
        store.commit()
        return {"file": key, "skipped": False, **counts}
    except BaseException:
        store.rollback()
        raise


def _delivery(store, records: list[dict], deferred) -> list[tuple]:
    """(source, records, already held, set aside) for what this file delivers, so a source's records can be reconciled.
    A record is already held when the store has it, or an earlier record of this file is the same assertion."""
    held = store.known_assertions(r["assertion_id"] for r in records)
    seen, delivered, repeated, aside = set(), Counter(), Counter(), Counter()
    for r in records:
        delivered[r["source_code"]] += 1
        if r["assertion_id"] in held or r["assertion_id"] in seen:
            repeated[r["source_code"]] += 1
        seen.add(r["assertion_id"])
    for r in deferred:
        aside[r["source_code"]] += 1
    return [(source, delivered[source], repeated[source], aside[source])
            for source in sorted({*delivered, *aside})]


def check_source_priorities(policy: dict, records: list[dict]) -> None:
    """A kind's fill rule must name every source of that kind among its records.

    A policy may be registered before a later source arrives, but once that source's records do, a source
    the rule leaves out fails the file, instead of silently dropping all of its fields."""
    present = defaultdict(set)
    for record in records:
        present[record["kind"]].add(record["source_code"])
    for kind, block in sorted((policy.get("kinds") or {}).items()):
        defaults = block.get("defaults")
        if defaults and (missing := present[kind] - set(defaults.get("sources", []))):
            raise ValueError(f"{kind} policy has no source priority for: " + ", ".join(sorted(missing)))


def refuse_if_split(store, merge_id: str, keep: str, gone: str) -> None:
    if any(d["operation"] == "reverse" and d["target"] == merge_id for d in store.decisions_about([keep, gone])):
        raise ValueError(f"Merge {merge_id} was already split")


def split_merge(store, settings: Settings, keep: str, gone: str, verdict: dict) -> dict:
    """Undo one merge in one transaction: the records return to the master they were first bound to, the
    reversal is stored, and both masters' records are merged again so each holds its own identifiers."""
    try:
        store.take_lock()
        refuse_if_split(store, verdict["target"], keep, gone)
        records = [json.loads(body) for _, _, body in store.split(keep, gone)]
        store.add_decision(verdict, keep, gone)
        counts = _merge(store, settings, records, file_key(records), True)
        store.commit()
        return counts
    except BaseException:
        store.rollback()
        raise


def _merge(store, settings: Settings, records: list[dict], key: str, again: bool) -> dict:
    check_source_priorities(settings.policy, records)
    file_no = store.last_file() + 1
    store.load_stage([(r["assertion_id"], r["subject"], r["source_code"], first(r["identifiers"].get("lei")),
                       json.dumps(r, separators=(",", ":"))) for r in records],
                     list({k for r in records for k in name_keys(r, exact_namespaces(settings))}))
    subjects = sorted({r["subject"] for r in records})
    bound = store.bound(subjects)
    counts = Counter()
    binds = []  # every bind decision of this file, whichever rule made it (step 6: every decision is recorded)
    survivors = _match_identifiers(store, settings, records, bound, counts, file_no, binds)
    named = _match_names(store, settings, records, bound, counts, binds)
    bound.update(named)
    exact = _match_exact_names(store, settings, records, bound, counts, binds)
    bound.update(exact)
    named |= exact
    waits = _waiting_sources(settings)
    store.open_reviews(WAITING, [(r["subject"], r["assertion_id"]) for r in records
                                 if r["source_code"] in waits and r["subject"] not in bound])
    store.close_reviews(WAITING, sorted(named))
    held = {s: bound[s] for s in subjects if s in bound} | named
    store.save_records(held)
    store.add_binds(binds)
    touched = set(held.values()) | survivors
    if touched:
        _write_masters(store, settings, sorted(touched), file_no, counts)
    if not (again and store.file_done(key)):
        store.finish_file(key, len(records))
    return {"records": len(records), **counts}


def _rules(settings: Settings) -> list[dict]:
    return [rule for kind, rule in matching.active_rules(settings.policy) if kind == settings.kind]


def _match_identifiers(store, settings: Settings, records, bound: dict, counts: Counter, file_no: int, binds: list) -> set:
    known = [r["subject"] for r in records if r["subject"] in bound]
    plan = plan_record_matches({
        "policy": settings.policy, "assertions": records, "decisions": [], "identities": [], "bound": known,
        "bound_entities": {s: bound[s] for s in known}, "withheld": store.withheld(known), "released": [],
        "normalizers": NORMALIZERS})
    if not plan["applicable"]:
        return set()
    wanted = defaultdict(set)
    for items in plan["applicable"].values():
        for item in items:
            wanted[item["namespace"]].add(item["value"])
    found = defaultdict(dict)
    held = store.holders(wanted)
    kinds = store.kinds({entity for _, _, entity in held})
    for namespace, value, entity in held:
        if kinds.get(entity) == settings.kind:  # a record joins only golden records of its own entity type
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
            binds.append({**decision, "policy_digest": settings.policy_digest})
            store.add_withheld([(decision["subject"], w["namespace"], w["raw"]) for w in decision.get("withheld") or ()])
    for review in made["reviews"]:
        counts[review["reason"]] += 1
        if review.get("subject"):
            store.open_reviews(review["reason"], [(review["subject"], review.get("assertion_id"))])
    return survivors


def _match_names(store, settings: Settings, records, bound: dict, counts: Counter, binds: list) -> dict:
    named, values = {}, {}
    for rule in _rules(settings):
        cascade = any(test["primitive"] == matching.cascade.TEST for test in rule["when"])
        holders = sorted(r["subject"] for r in records if r["source_code"] == rule["holder_source"])
        pairs = [(json.loads(c), json.loads(h)) for c, h in store.name_pairs(
            "cascade" if cascade else "name_count", rule["holder_source"], rule["source"], holders)]
        involved = {side["subject"] for pair in pairs for side in pair}
        bound.update(store.bound(sorted(involved - set(bound))))
        pairs = [(c, h) for c, h in pairs if c["subject"] not in bound and c["subject"] not in named and h["subject"] in bound]
        if not pairs:
            continue
        reach, lei, candidates = defaultdict(set), {}, {}
        for (candidate, holder), (passed, flagged) in zip(
                pairs, matching.compare_candidate_records(rule, [(h, c) for c, h in pairs]), strict=True):
            if passed:
                reach[candidate["subject"]].add(bound[holder["subject"]])
                candidates[candidate["subject"]] = candidate
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
            binds.append(_bind_decision(settings, rule, subject, candidates[subject].get("assertion_id"), entity, "name_match lei"))
    store.add_identifiers([("lei", values[s], e) for s, e in named.items()])
    return named


def _waiting_sources(settings: Settings) -> set[str]:
    """The sources of every switched-on rule of this kind, of any family, that leaves a record waiting when nothing is found."""
    return {rule["source"] for rule in settings.policy["kinds"][settings.kind].get("rules") or []
            if rule.get("on_no_match") == "wait" and activated(settings.policy, settings.kind, rule, "bind")}


def _exact_rules(settings: Settings) -> list[dict]:
    return [rule for rule in settings.policy["kinds"][settings.kind].get("rules") or []
            if rule.get("family") == matching.EXACT_NAME_FAMILY and activated(settings.policy, settings.kind, rule, "bind")]


def _match_exact_names(store, settings: Settings, records, bound: dict, counts: Counter, binds: list) -> dict:
    """A waiting record joins the one master holding its name id; several send it to review. With none, a rule
    that mints (`on_no_match: mint`) creates one golden record for the name, which the source's later records join."""
    rules = _exact_rules(settings)
    if not rules:
        return {}
    named = {}
    for rule in rules:
        namespace = rule.get("cross_reference", NAME_ID)
        here = {r["subject"]: r for r in records if reference_of(r, namespace)}
        if not here:
            continue
        here = {k: v for k, v in here.items() if k not in store.in_review(here, except_reason=WAITING)}
        if not here:
            continue
        members = {(reference_of(r, namespace), r["subject"], r["source_code"], None) for r in here.values()}
        members.update(store.named(role_of(namespace), sorted({reference_of(r, namespace) for r in here.values()})))
        mints = rule.get("on_no_match") == "mint"
        holders = {*rule["holder_sources"], *([rule["source"]] if mints else [])}
        holding, waiting, created = defaultdict(set), {}, {}
        for value, subject, source, entity in members:
            entity = entity or bound.get(subject)
            if entity and source in holders:
                holding[value].add(entity)
            elif not entity and source == rule["source"] and subject not in named:
                waiting[subject] = value
        for subject, value in waiting.items():
            found = holding[value]
            if len(found) == 1:
                named[subject] = next(iter(found))
                binds.append(_bind_decision(settings, rule, subject, (here.get(subject) or {}).get("assertion_id"), named[subject], f"exact_name {namespace}"))
            elif found:
                counts["ambiguous_name_match"] += 1
                store.open_reviews("ambiguous_name_match", [(subject, (here.get(subject) or {}).get("assertion_id"))])
            elif mints:
                named[subject] = created.setdefault(value, str(uuid4()))
                binds.append(_bind_decision(settings, rule, subject, (here.get(subject) or {}).get("assertion_id"), named[subject], f"exact_name {namespace} created"))
    return named


def _bind_decision(settings: Settings, rule: dict, subject: str, assertion_id, entity: str, reason: str) -> dict:
    """The decision a name rule made, in the shape the identifier rules return: the rule and its version, the source
    record it used and its outcome. The id covers those and not the policy digest, so a replay under a new policy
    writes the same decision once."""
    core = {"operation": "bind", "actor": f"rule:{rule['rule_id']}@{rule['version']}", "reason": reason,
            "at": settings.as_of, "subject": subject, "entity_id": entity, "evidence": [assertion_id],
            "rule_id": rule["rule_id"], "rule_version": rule["version"]}
    return {**core, "decision_id": hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest(),
            "policy_digest": settings.policy_digest}


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
    store.add_identifiers(sorted({(namespace, value, e) for e, body in masters.items()
                                  for namespace, values in body["identifiers"].items() for value in values}))
