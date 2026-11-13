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
    current_record_views,
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
    """The LEI the waterfall pass paired the record with, and its exact name ids, so a name match is a lookup."""
    found = ((record.get("provenance") or {}).get("matching") or {}).get("name_count") or {}
    cascade = (found.get("cascade") or {}).get("lei")
    exact = [(role_of(ns), reference_of(record, ns)) for ns in namespaces]
    return [(role, value, record["subject"]) for role, value in (("cascade", cascade), *exact)
            if isinstance(value, str) and value]


def apply_pairs(store, settings: Settings, source_code: str, pairs: dict[str, dict], *, source_records=None) -> dict:
    """Retain the waterfall answer on the selected original assertions and merge its lookup keys.

    An unchanged pair and its evidence need no replay; a later publication's changed evidence
    is retained even when its lookup key is already present.
    """
    held = {(subject, value) for value, subject in store.rows("select value,subject from mastering_name_key where role='cascade'")}
    changed = []
    if source_records is None:
        source_records = [json.loads(text) if isinstance(text, str) else text for (text,) in
                          store.rows("select body from mastering_record where source_code=%s", [source_code])]
        selected = {r["assertion_id"] for r in current_record_views(source_records, settings.as_of).values()}
        source_records = [r for r in source_records if r["assertion_id"] in selected]
    for record in source_records:
        if record["source_code"] != source_code or record["kind"] != settings.kind:
            raise ValueError("A pair application uses only the selected source and identity kind")
        pair = pairs.get(record["record_key"])
        if pair:
            expected = {"version": matching.cascade.VERSION, **pair}
            existing = (((record.get("provenance") or {}).get("matching") or {}).get("name_count") or {}).get("cascade")
            if (record["subject"], pair["lei"]) in held and existing == expected:
                continue
            matching_ = record.setdefault("provenance", {}).setdefault("matching", {})
            found = matching_.get("name_count") or {}
            matching_["name_count"] = {**found, "cascade": expected}
            changed.append(record)
    if not changed:
        return {"records": 0}
    # Pair evidence, lookup keys and released waiters are one transaction. A retry must never
    # see a finished pair whose waiting-record release failed after a separate commit.
    return merge_file(store, settings, changed, again=True, record_updates=changed,
                      release_identifiers={("lei", pairs[r["record_key"]]["lei"]) for r in changed})


def set_aside(store, records: list[dict], quiet: dict) -> None:
    """Records no rule may master: kept with their review, blocking unless the source says otherwise."""
    store.add_deferred([(r["deferred_id"], r["source_code"], r["reason"],
                         0 if r["reason"] in quiet.get(r["source_code"], ()) else 1, json.dumps(r)) for r in records])


def merge_file(store, settings: Settings, records: list[dict], *, again: bool = False,
               deferred: list[dict] = (), quiet: dict | None = None, record_updates=(), release_identifiers=()) -> dict:
    """Merge one file, or nothing if it is done. `again` delivers a finished file a second time."""
    key = file_key([*records, *({"assertion_id": r["deferred_id"]} for r in deferred)])
    try:
        store.take_lock(settings.kind)
        if store.file_done(key) and not again:
            store.commit()
            return {"file": key, "skipped": True}
        # A derived pair must remain on the stored holder when its other end arrives in a later file.
        # Keep its evidence and the resulting lookup keys in the same locked transaction.
        if record_updates:
            store.update_records([(r["assertion_id"], json.dumps(r, separators=(",", ":"))) for r in record_updates])
        delivery = _delivery(store, records, deferred)
        set_aside(store, list(deferred), quiet or {})
        arrived: set = set(release_identifiers)
        counts = _merge(store, settings, records, key, again, arrived) if records else {"records": 0}
        # A file of only set-aside records has no kind and nothing arrived: nothing waits for it.
        counts["released"] = _release_waiting(store, settings, arrived) if records else 0
        store.add_delivery(key, delivery)
        if not records:
            store.finish_file(key, 0)
        store.commit()
        return {"file": key, "skipped": False, **counts}
    except BaseException:
        store.rollback()
        raise


def _release_waiting(store, settings: Settings, arrived: set) -> int:
    """A record that waits for a golden record to hold an identifier moves to it when this file gives one. Nothing waits
    forever for what has arrived (operator, 2026-11-10): the records that state an arrived identifier are merged again,
    each once, and what that gives its golden records releases the next, until none is left to try."""
    waits = sorted(_waiting_sources(settings))
    if not waits:
        return 0
    tried, released = set(), 0
    while arrived:
        ready = [r for r in store.waiting_for(arrived) if r["subject"] not in tried and r["source_code"] in waits
                 and r["kind"] == settings.kind]
        if not ready:
            break
        tried.update(r["subject"] for r in ready)
        arrived = set()
        _merge(store, settings, ready, file_key(ready), True, arrived)
        released += len(store.bound([r["subject"] for r in ready]))
    return released


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
        store.take_lock(settings.kind)
        refuse_if_split(store, verdict["target"], keep, gone)
        records = [json.loads(body) for _, _, body in store.split(keep, gone)]
        store.add_decision(verdict, keep, gone)
        counts = _merge(store, settings, records, file_key(records), True)
        store.commit()
        return counts
    except BaseException:
        store.rollback()
        raise


def _merge(store, settings: Settings, records: list[dict], key: str, again: bool, arrived: set | None = None) -> dict:
    """One file of records into golden records. `arrived` collects the identifiers its golden records now hold."""
    check_source_priorities(settings.policy, records)
    store.load_stage([(r["assertion_id"], r["subject"], r["source_code"], first(r["identifiers"].get("lei")),
                       json.dumps(r, separators=(",", ":"))) for r in records],
                     list({k for r in records for k in name_keys(r, exact_namespaces(settings))}))
    subjects = sorted({r["subject"] for r in records})
    bound = store.bound(subjects)
    counts = Counter()
    binds = []  # the judgements of this file: name matches (step 6); an identifier join writes none
    survivors = _match_identifiers(store, settings, records, bound, counts, binds)
    named = _match_names(store, settings, records, bound, counts, binds)
    bound.update(named)
    exact = _match_exact_names(store, settings, records, bound, counts, binds)
    bound.update(exact)
    named |= exact
    waits = _waiting_sources(settings)
    waiting = [r for r in records if r["source_code"] in waits and r["subject"] not in bound]
    store.open_reviews(WAITING, [(r["subject"], r["assertion_id"]) for r in waiting])
    store.index_waiting(waiting)
    held = {s: bound[s] for s in subjects if s in bound} | named
    store.close_reviews(WAITING, sorted(held))  # a record that found its golden record no longer waits
    store.save_records(held)
    store.add_binds(binds)
    touched = set(held.values()) | survivors
    if touched:
        found = _write_masters(store, settings, sorted(touched), counts)
        if arrived is not None:
            arrived.update(found)
    if not (again and store.file_done(key)):
        store.finish_file(key, len(records))
    return {"records": len(records), **counts}


def _rules(settings: Settings) -> list[dict]:
    return [rule for kind, rule in matching.active_rules(settings.policy) if kind == settings.kind]


def merge_masters(store, settings: Settings, decision: dict, keep: str, gone: str, stored: bool) -> None:
    """Two golden records become one: the older keeps the other's identifiers and records, the other stays as an
    alias, and the decision is written. A rule and a data steward merge the same way."""
    store.repoint(keep, gone)
    if stored:
        alias = {"entity_id": gone, "kind": settings.kind, "canonical_id": keep, "status": "alias"}
        store.write_masters([(gone, json.dumps(alias))])
    store.add_decision(decision, keep, gone)


def _match_identifiers(store, settings: Settings, records, bound: dict, counts: Counter, binds: list) -> set:
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
    counts.update(_hold_conflicts(store, settings, plan, records, found))
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
            merge_masters(store, settings, decision, keep, gone, gone in stored)
            moved[gone] = keep
            survivors.discard(gone)
            survivors.add(keep)
            counts["merges"] += 1
    for subject, entity in list(bound.items()):
        bound[subject] = live(entity)
    for decision in made["decisions"]:
        if decision["operation"] == "bind":
            # A join by an identifier is no judgement: the record's own `bound_id` says where it went (operator,
            # 2026-11-10: "Yes, stop the plain ones"). Only name matches, conflicts and a steward's bind are decisions.
            bound[decision["subject"]] = live(decision["entity_id"])
            store.add_withheld([(decision["subject"], w["namespace"], w["raw"]) for w in decision.get("withheld") or ()])
    for review in made["reviews"]:
        counts[review["reason"]] += 1
        if review.get("subject"):
            store.open_reviews(review["reason"], [(review["subject"], review.get("assertion_id"))])
    return survivors


def _hold_conflicts(store, settings: Settings, plan: dict, records, found: dict) -> Counter:
    """A record whose identifier finds a golden record that holds another value of an identifier its contract says
    must agree (a share class FIGI whose Security holds another CUSIP) joins nothing and goes to review (step 4)."""
    contracts = ((settings.policy.get("kinds") or {}).get(settings.kind) or {}).get("identifiers") or {}
    agree = {namespace: contract["conflicts_with"] for namespace, contract in contracts.items() if contract.get("conflicts_with")}
    held_by = {}
    if agree:
        wanted = {entity for (namespace, _), holders in found.items() if namespace in agree for entity in holders}
        held_by = store.identifiers_of(wanted, sorted({n for names in agree.values() for n in names}))
    stated = {r["subject"]: r for r in records}
    values = lambda ids: {str(v).upper() for v in (ids if isinstance(ids, list) else [ids]) if v}
    seen, counts = defaultdict(list), Counter()  # what the records of this file that went on already state, per value
    for subject in sorted(plan["applicable"]):
        mine = {n: values(stated[subject]["identifiers"].get(n)) for names in agree.values() for n in names}
        keys = [(item["namespace"], item["value"]) for item in plan["applicable"][subject] if item["namespace"] in agree]
        peers = {key: [held_by.get(entity, {}) for entity in found.get(key, {})] + seen[key] for key in keys}
        if any(mine[n] and peer.get(n) and not mine[n] & peer[n]
               for key in keys for peer in peers[key] for n in agree[key[0]]):
            store.open_reviews("conflicting_identifiers", [(subject, stated[subject]["assertion_id"])])
            counts["conflicting_identifiers"] += 1
            del plan["applicable"][subject]
        else:
            for key in keys:
                seen[key].append(mine)
    return counts


def _match_names(store, settings: Settings, records, bound: dict, counts: Counter, binds: list) -> dict:
    named, values = {}, {}
    for rule in _rules(settings):
        holders = sorted(r["subject"] for r in records if r["source_code"] == rule["holder_source"])
        pairs = [(json.loads(c), json.loads(h)) for c, h in store.name_pairs(
            "cascade", rule["holder_source"], rule["source"], holders)]
        current = current_record_views([side for pair in pairs for side in pair], settings.as_of)
        pairs = list({(c["subject"], h["subject"]): (current[c["subject"]], current[h["subject"]])
                      for c, h in pairs if c["subject"] in current and h["subject"] in current}.values())
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
        held = store.in_review(here, except_reason=WAITING)  # asked once for the batch, never once a record
        here = {k: v for k, v in here.items() if k not in held}
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


def _write_masters(store, settings: Settings, entities: list, counts: Counter) -> set:
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
    store.write_masters([(e, json.dumps(body)) for e, body in masters.items()])
    held = sorted({(namespace, value, e) for e, body in masters.items()
                   for namespace, values in body["identifiers"].items() for value in values})
    store.add_identifiers(held)
    return {(namespace, value) for namespace, value, _ in held}
