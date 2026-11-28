#!/usr/bin/env python3
"""Infer which loads depend on which from the rules files, and what may run at the same time.

    python infer_dependencies.py            a table: each target's kind, what it states, what it should follow
    python infer_dependencies.py --json     the same as data

Every line comes from what the rules declare, never from a machine's size.

  must     a load that is wrong unless another has finished first
  prefer   a load whose records wait until another has finished: never wrong, only later
  either   two loads that each prefer the other: any order is as good
  alone    loads that take turns because they share one resource of the store

Where it reads: a matching rule's `on_no_match` (`mint` creates a master; `wait` holds the record in the Merge Stage until a
master holds its value: the source named in `holder_source`, else a source whose minting rules use the same identifier
namespace, else any source that mints that kind); a contract's relationships and a silver table's links (each names the
source whose masters it points at). The links table sets no order:
it is built whole once, after the last load (`silver links`), from every stored record.
"""
import argparse
import json
from collections import defaultdict

import yaml

from edgar_warehouse.rules import files

ROOT = files.ROOT


def walk(node):
    """Every dict inside a nested document."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def infer() -> dict:
    names = sorted(p.parent.name for p in files.sources_root().glob("*/source.yaml"))
    bodies = {name: files.source(name) for name in names}
    owner = {code: name for name, body in bodies.items() for code in (body.get("dataset_contracts") or {})}
    # Each target: the dataset it prepares (if any) and the silver tables it lands.
    targets = {}
    for name, body in bodies.items():
        for target, shaped in ((body.get("bookkeeping") or {}).get("targets") or {}).items():
            item = {"source": name, "dataset": None, "silver": []}
            for step in shaped["steps"]:
                keys = (step.get("input") or {}).get("keys") or {}
                if step["operation"] == "mdm.prepare":
                    item["dataset"] = keys.get("dataset")
                elif step["operation"] == "silver.land":
                    item["silver"].append(keys.get("silver"))
            targets[f"{name}/{target}"] = item
    by_dataset = defaultdict(list)
    for key, item in targets.items():
        if item["dataset"]:
            by_dataset[item["dataset"]].append(key)
    # Merge rules: who mints and who waits, by kind and identifier namespace.
    mints, waits, holders = defaultdict(set), defaultdict(set), defaultdict(set)
    spaces = defaultdict(set)
    for path in sorted((ROOT / "merge" / "kinds").glob("*.yaml")):
        for rule in (yaml.safe_load(path.read_text()) or {}).get("rules") or []:
            code = rule.get("source")
            if code not in by_dataset:
                continue
            kind = path.stem
            found = {a["namespace"] for node in walk(rule.get("when")) for a in [node.get("args") or {}]
                     if isinstance(a, dict) and "namespace" in a}
            for key in by_dataset[code]:
                if rule.get("on_no_match") == "mint":
                    mints[key].add(kind)
                    spaces[(key, kind, "mint")] |= found
                elif rule.get("on_no_match") == "wait":
                    waits[key].add(kind)
                    spaces[(key, kind, "wait")] |= found
                    if rule.get("holder_source") in by_dataset:
                        holders[(key, kind)].add(targets[by_dataset[rule["holder_source"]][0]]["source"])
    minters = defaultdict(set)
    for key, kinds in mints.items():
        for kind in kinds:
            minters[kind].add(key)
    result = {}
    for key, item in targets.items():
        states = set()
        contract = (bodies[item["source"]].get("dataset_contracts") or {}).get(item["dataset"] or "")
        for node in walk(contract or {}):
            if node.get("target_source") in owner:
                states.add(owner[node["target_source"]])
        silver_links = set()
        for spec in sorted((files.sources_root() / item["source"]).glob("silver-*.yaml")):
            body = yaml.safe_load(spec.read_text()) or {}
            if body.get("table") in item["silver"]:
                for link in body.get("links") or []:
                    if link.get("source_code") in owner:
                        silver_links.add(owner[link["source_code"]])
                    elif link.get("identifier"):   # found on any master of its kinds: each source minting one by that identifier
                        silver_links |= {targets[k]["source"] for kind in link["kinds"] for k in minters[kind]
                                         if link["identifier"] in spaces[(k, kind, "mint")]}
        prefer = set()
        for kind in waits[key]:
            named = holders.get((key, kind), set())
            issuers = {other for other in minters[kind] - {key}
                       if spaces[(key, kind, "wait")] & spaces[(other, kind, "mint")]}
            prefer |= named or {targets[k]["source"] for k in issuers} or {targets[k]["source"] for k in minters[kind] - {key}}
        result[key] = {
            "kinds": sorted(mints[key] | waits[key]), "mints": sorted(mints[key]),
            "finds_only": sorted(waits[key] - mints[key]),
            "states_links_to": sorted(states - {item["source"]}), "silver_links_to": sorted(silver_links - {item["source"]}),
            "prefer_after": sorted(prefer - {item["source"]}),
        }
    # Two sources that each prefer the other have no order to keep.
    wanted = {key: set(item["prefer_after"]) for key, item in result.items()}
    for key, item in result.items():
        source = targets[key]["source"]
        item["either_order"] = sorted(other for other in wanted[key]
                                      if any(source in wanted[k] for k in result if targets[k]["source"] == other))
        item["prefer_after"] = sorted(wanted[key] - set(item["either_order"]))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = infer()
    if args.json:
        print(json.dumps(result, indent=1, sort_keys=True))
        return 0
    print(f"{'target':44} {'kinds':22} states links to | silver links to | prefer after | either order")
    for key, item in result.items():
        print(f"{key:44} {','.join(item['kinds']) or '-':22} {','.join(item['states_links_to']) or '-'} | "
              f"{','.join(item['silver_links_to']) or '-'} | {','.join(item['prefer_after']) or '-'} | "
              f"{','.join(item['either_order']) or '-'}")
    print("state links (mastered before the last build):", ", ".join(k for k, i in result.items() if i["states_links_to"]))
    kinds = {kind: [k for k, i in result.items() if kind in i["kinds"]] for kind in sorted({x for i in result.values() for x in i["kinds"]})}
    print("merges of one kind take turns:", json.dumps(kinds))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
