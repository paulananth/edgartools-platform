"""Learn what a name rule must respect, from two sources' records (profiling ticket 07b).

    uv run --with duckdb --with pyyaml python skills/data-profiling/scripts/match_names.py \\
        --left <file> --left-key <col> --left-name <col> [--left-variants <col>] \\
        --right <file> --right-key <col> --right-name <col> [--right-variants <col>] \\
        [--same <left col>=<right col>] [--attribute <left col>=<right col> ...] \\
        --out <folder>

Each side is a CSV, JSON Lines or Parquet file, one record per row. Every left
row is kept; right rows only where they can pair, so put the larger file right. `--*-variants`
names a column holding other names of the same record (a list of names, or of
[type, name] pairs). `--same` names the columns whose equal values prove a left
and a right record are one entity (a shared issued id or cross-reference id).
Writes `name-matching.yaml` (for agents) and `NAME-MATCHING.md` (for the
operator). Reads local files only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import duckdb
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from profiling import name_matching as nm  # noqa: E402
from profiling.sensitivity import mask  # noqa: E402


def _reader(path: str) -> str:
    """The DuckDB reader for a file; the path is bound as the query's parameter."""
    lower = path.lower()
    if lower.endswith(".parquet"):
        return "read_parquet(?)"
    if lower.endswith(".csv"):
        return "read_csv_auto(?)"
    return "read_json_auto(?, format='newline_delimited', maximum_object_size=67108864)"


def _id(value) -> str:
    """An id as compared: trimmed, upper case; empty when unfilled."""
    return "" if value is None else str(value).strip().upper()


def _rows(con, path: str, columns: list[str], batch: int = 100_000):
    """The rows, read in batches so a large file is never held whole."""
    wanted = ", ".join('"' + c.replace('"', '""') + '"' for c in dict.fromkeys(c for c in columns if c))
    cursor = con.execute(f"SELECT {wanted} FROM {_reader(path)}", [path])
    names = [d[0] for d in cursor.description]
    while chunk := cursor.fetchmany(batch):
        for row in chunk:
            yield dict(zip(names, row))


def _names(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return [value]
    found = []
    for item in value or []:
        if isinstance(item, (list, tuple)) and item:
            item = item[-1]
        if isinstance(item, dict):
            item = item.get("name")
        if item:
            found.append(str(item))
    return found


def side(con, path, key, name, variants, attributes, same, keep=None) -> dict:
    """One source's current names and own variants; whole rows only where
    `keep(row)` says they can pair with the other side (all when it is None)."""
    current, own, kept = [], [], []
    for r in _rows(con, path, [key, name, variants, same, *attributes]):
        if r.get(key) is None or not r.get(name):
            continue
        current.append((str(r[key]), str(r[name])))
        if variants:
            own.extend((str(r[name]), other) for other in _names(r.get(variants)))
        if keep is None or keep(r):
            kept.append({k: v for k, v in r.items() if k != variants})
    return {"rows": kept, "current": current, "own_variants": own}


SIZE = re.compile(r"\d+(\.\d+)?\s*(KB|MB|GB|TB|KiB|MiB|GiB|TiB)", re.IGNORECASE)


def run(args) -> dict:
    con = duckdb.connect()
    # Bounded, so a large source spills to a capped folder instead of filling memory or disk.
    for setting, size in (("memory_limit", args.memory), ("max_temp_directory_size", args.spill)):
        if not SIZE.fullmatch(size):
            raise SystemExit(f"{size!r} is not a size such as 2GB")
        con.execute(f"SET {setting} = '{size}'")
    lefts = [a.split("=", 1)[0] for a in args.attribute]
    rights = [a.split("=", 1)[1] for a in args.attribute]
    same_left, same_right = (args.same.split("=", 1) if args.same else (None, None))
    left = side(con, args.left, args.left_key, args.left_name, args.left_variants, lefts, same_left)
    left_ids = {_id(r.get(same_left)) for r in left["rows"]} - {""}
    left_names = {" ".join(nm.tokens(n)) for _, n in left["current"]}

    def pairs_with_left(r) -> bool:
        return (bool(same_right) and _id(r.get(same_right)) in left_ids) or \
            " ".join(nm.tokens(r.get(args.right_name) or "")) in left_names

    right = side(con, args.right, args.right_key, args.right_name, args.right_variants, rights, same_right,
                 keep=pairs_with_left)
    apart = nm.distinguishing(con, left["current"])
    other = nm.distinguishing(con, right["current"])
    for key, value in other.counts.items():
        apart.counts[key] += value
        apart.examples[key] = (apart.examples[key] + other.examples[key])[:nm.EXAMPLES]
    pairs, near = [], []
    if args.same:
        by_value = {}
        for r in right["rows"]:
            if _id(r.get(same_right)):
                by_value.setdefault(_id(r[same_right]), []).append(r)
        for r in left["rows"]:
            for match in by_value.get(_id(r.get(same_left)), []):
                pairs.append((r, match))
    cross = [(a[args.left_name], b[args.right_name]) for a, b in pairs if a.get(args.left_name) and b.get(args.right_name)]
    alike = nm.variants(left["own_variants"] + right["own_variants"] + cross)
    clashes = nm.conflicts(apart, alike)
    folded_right = {}
    for r in right["rows"]:
        if r.get(args.right_name):
            folded_right.setdefault(" ".join(nm.tokens(r[args.right_name])), []).append(r)
    proven = {(str(a[args.left_key]), str(b[args.right_key])) for a, b in pairs}
    for r in left["rows"]:
        for match in folded_right.get(" ".join(nm.tokens(r.get(args.left_name) or "")), []):
            if (str(r[args.left_key]), str(match[args.right_key])) not in proven and args.same and \
                    _id(r.get(same_left)) and _id(match.get(same_right)) and _id(r[same_left]) != _id(match[same_right]):
                near.append((r, match))
    attributes = nm.support(pairs, near, list(zip(lefts, rights)))
    risk = {"left": nm.homonyms(left["current"]), "right": nm.homonyms(right["current"])}
    worst = max(risk["left"], risk["right"], key=lambda r: r["rate"])
    rules = nm.folds(alike, apart)
    by_name = nm.join_by_name(left["current"], right["current"], [])
    folded = nm.join_by_name(left["current"], right["current"], rules)
    proved = {}
    for a, b in pairs:
        proved.setdefault(str(a[args.left_key]), set()).add(str(b[args.right_key]))
    right_ids = {str(r[args.right_key]): _id(r.get(same_right)) for r in right["rows"]} if args.same else {}
    checked = Counter()
    wrong = []
    for name, (lk, rk) in by_name["joined"].items():
        if lk in proved:
            ok = rk in proved[lk]
            checked["agree" if ok else "contradict"] += 1
            if not ok and len(wrong) < nm.EXAMPLES:
                wrong.append({"name": name, "left": lk, "right": rk, "right_should_be": sorted(proved[lk])})
        elif args.same and right_ids.get(rk):
            checked["right has an id, left states none the right holds"] += 1
    joined_left = {lk for lk, _ in by_name["joined"].values()}
    missed = sum(1 for lk in proved if lk not in joined_left)
    return {
        "name_id": {
            "use_only_when": "no record of either side carries an id the other side also carries",
            "recipe": nm.NAME_ID,
            "cross_reference": "a contract maps the name to cross_references: {name_id: <name path>} with "
                               "cross_reference_formats: {name_id: name_id@1}; lookup only, never a join",
            "variants_not_folded": [list(f) for f in rules[:40]],
            "joined_one_to_one_if_folded": len(folded["joined"]),
            "joined_one_to_one": len(by_name["joined"]),
            "not_joined_name_held_twice": len(by_name["ambiguous"]),
            "on_pairs_an_id_proves": dict(checked),
            "contradictions": wrong,
            "proved_pairs_not_joined": missed,
        },
        "inputs": {"left": args.left, "right": args.right, "same": args.same, "attributes": args.attribute},
        "token_normalization": nm.TOKEN_NORMALIZATION,
        "records": {"left": len(left["current"]), "right": len(right["current"])},
        "proved_pairs": len(pairs),
        "near_homonym_pairs": len(near),
        "distinguishing": apart.top(),
        "distinguishing_by_class": nm.by_class(apart),
        "variants": alike.top(),
        "conflicts": clashes[:25],
        "supporting_attributes": attributes,
        "homonyms": risk,
        "proposal": nm.proposal(apart, alike, clashes, attributes, worst),
    }


def _md(found: dict) -> str:
    p = found["proposal"]
    lines = ["# Name matching: what a rule must respect", "",
             f"Records: {found['records']['left']:,} left, {found['records']['right']:,} right. "
             f"Pairs a shared id proves: {found['proved_pairs']:,}. Near-homonyms (equal folded names, "
             f"different ids): {found['near_homonym_pairs']:,}.", "",
             "## Compare exactly (these tell entities apart)", "",
             "| Token classes | After | Records | Pairs |", "|---|---|---|---|"]
    lines += [f"| {' / '.join(r['classes'])} | {r['after']} | {r['count']} | {', '.join('/'.join(x) for x in r['pairs'])} |"
              for r in p["compare_exactly"][:15]]
    lines += ["", "## May fold (variants of one entity, never seen apart)", "",
              ", ".join(f"{'/'.join(x['pair']) or '(none)'} ({x['count']})" for x in p["may_fold"][:20]) or "None.",
              "", "## Name alone cannot decide (seen both ways)", "",
              ", ".join("/".join(x) for x in p["needs_a_supporting_attribute"][:20]) or "None.",
              "", "## Supporting attributes", "",
              "| Left | Right | Agrees on proved pairs | Separates near-homonyms |", "|---|---|---|---|"]
    lines += [f"| {a['left']} | {a['right']} | {a['agrees_on_same']} ({a['same_compared']}) | "
              f"{a['separates_near_homonyms']} ({a['near_compared']}) |" for a in found["supporting_attributes"]]
    n = found["name_id"]
    lines += ["", "## An id from the name (only where no id exists)", "",
              f"Recipe: {n['recipe']}. Joined one to one: {n['joined_one_to_one']:,}; names held twice, "
              f"not joined: {n['not_joined_name_held_twice']:,}. On pairs an id proves: {n['on_pairs_an_id_proves']}; "
              f"records an id pairs that the name id does not: {n['proved_pairs_not_joined']:,}.",
              "", f"It goes into the cross-reference table ({n['cross_reference']}).",
              "", f"Variants the id does not fold (with them folded, {n['joined_one_to_one_if_folded']:,} "
              "would join one to one): " + (", ".join(f"{a} -> {b or '(dropped)'}" for a, b in n["variants_not_folded"][:20]) or "none.")]
    lines += ["", f"Homonym rate (folded names held by more than one record): left "
              f"{found['homonyms']['left']['rate']:.2%}, right {found['homonyms']['right']['rate']:.2%}.",
              "", p["note"], ""]
    return "\n".join(lines)


# Keys whose strings are names or parts of names.
NAMED = {"name", "names", "pair", "pairs", "token", "after", "needs_a_supporting_attribute", "variants_not_folded"}


def _mask_all(value):
    if isinstance(value, str):
        return mask(value)
    if isinstance(value, (list, tuple)):
        return [_mask_all(x) for x in value]
    return _masked(value, True)


def _masked(found, personal: bool):
    """Example names keep their shape only when the names are personal."""
    if not personal:
        return found
    if isinstance(found, dict):
        return {k: _mask_all(v) if k in NAMED else _masked(v, True) for k, v in found.items()}
    if isinstance(found, list):
        return [_masked(x, True) for x in found]
    return found


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    for s in ("left", "right"):
        parser.add_argument(f"--{s}", required=True)
        parser.add_argument(f"--{s}-key", required=True)
        parser.add_argument(f"--{s}-name", required=True)
        parser.add_argument(f"--{s}-variants")
    parser.add_argument("--same")
    parser.add_argument("--attribute", action="append", default=[])
    parser.add_argument("--personal", action="store_true", help="The names are people's: examples keep their shape only")
    parser.add_argument("--memory", default="2GB", help="DuckDB memory limit")
    parser.add_argument("--spill", default="1GB", help="Most DuckDB may write to its temporary folder")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    found = _masked(run(args), args.personal)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "name-matching.yaml").write_text(yaml.safe_dump(found, sort_keys=False, allow_unicode=True))
    (args.out / "NAME-MATCHING.md").write_text(_md(found))
    print(json.dumps({k: found[k] for k in ("records", "proved_pairs", "near_homonym_pairs")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
