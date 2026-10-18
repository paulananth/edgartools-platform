"""Rank several sources of one kind by how well each states each field.

    uv run --with duckdb --with pyyaml python skills/data-profiling/scripts/rank_sources.py \\
        --source <name>=<file>:<key column> [--source ...] \\
        --field <field>=<source>:<column or dotted path>[,<source>:<column>...] [--field ...] \\
        --out <folder>

Each source is a JSON Lines, JSON, CSV or Parquet file of its records, keyed by the
identifier the sources share. A key may repeat (one row per delivery or per
filer), so a source that disagrees with itself shows it. A field names, for
each source that holds it, a column or a dotted path into nested records (a
list on the way is walked). Values are compared normalised: upper case,
punctuation and spaces folded.

For each field and source it measures:
- coverage: the keys it fills, of all keys any source fills for that field;
- one value: of the keys it fills, those with exactly one value;
- agreement, pair by pair: of the keys two sources both fill, those where
  they share a value. Never agreement with a majority: two sources repeating
  one origin's words can agree and both be wrong.

It recommends a source order per field, by one value and then coverage: the
first source wins wherever it fills a field, so it should state one value;
the next fills its gaps. Writes `ranking.yaml` (for agents) and `RANKING.md`
(for the operator), names and counts only. Advice only: it changes no rule.
Give each source its source code as its name, so the order can be pasted into the
kind file (`merge_rules` in the output). Reads local files only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import yaml

_FOLD = re.compile(r"[\W_]+", re.UNICODE)


def normalise(value) -> str:
    """A value as compared: upper case, every run of punctuation or space one space, trimmed.
    A whole number stored as a float is the number (12.0 is 12), so a key typed as a number in
    one file and as text in another still joins; a number loses its leading zeros either way."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return _FOLD.sub(" ", str(value)).strip().upper()


def walk(record, path: list[str]):
    """Every plain value at a dotted path; a list on the way is walked."""
    if isinstance(record, list):
        for item in record:
            yield from walk(item, path)
        return
    if not path:
        if record is not None and not isinstance(record, dict):
            yield record
        return
    if isinstance(record, dict) and path[0] in record:
        yield from walk(record[path[0]], path[1:])


def records(path: str):
    """The records of a file, one at a time. JSON is read as written (an array, or one record a
    line), never retyped; CSV as text."""
    lower = path.lower()
    if lower.endswith((".jsonl", ".ndjson", ".json")):
        with open(path, encoding="utf-8") as text:
            first = text.read(1)
            while first.isspace():
                first = text.read(1)
            text.seek(0)
            if first == "[":
                yield from json.load(text)
                return
            for line in text:
                if line.strip():
                    yield json.loads(line)
        return
    import duckdb

    reader = "read_parquet(?)" if lower.endswith(".parquet") else "read_csv_auto(?, all_varchar=true)"
    cursor = duckdb.connect().execute(f"SELECT * FROM {reader}", [path])
    names = [d[0] for d in cursor.description]
    while chunk := cursor.fetchmany(100_000):
        for row in chunk:
            yield dict(zip(names, row))


def collect(path: str, key: str, fields: dict[str, str]) -> dict[str, dict[str, set[str]]]:
    """field -> key -> the normalised values the source states for it, over every row of that key.
    Reading streams; what is kept grows with the distinct keys and values, not the rows."""
    found: dict[str, dict[str, set[str]]] = {field: defaultdict(set) for field in fields}
    key_path = key.split(".")
    split = {field: column.split(".") for field, column in fields.items()}
    for record in records(path):
        for k in {normalise(v) for v in walk(record, key_path)} - {""}:
            for field, column in split.items():
                values = {normalise(v) for v in walk(record, column)} - {""}
                if values:
                    found[field][k] |= values
    return found


def share(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def rank_field(stated: dict[str, dict[str, set[str]]]) -> dict:
    """The measures and the recommended order for one field, from each source's stated values."""
    every = set().union(*(set(v) for v in stated.values()))
    sources = {}
    for name, values in stated.items():
        one = sum(1 for v in values.values() if len(v) == 1)
        sources[name] = {"keys": len(values), "coverage": share(len(values), len(every)),
                         "one_value_keys": one, "one_value": share(one, len(values))}
    agreement = []
    for left, right in combinations(sorted(stated), 2):
        both = set(stated[left]) & set(stated[right])
        agree = sum(1 for k in both if stated[left][k] & stated[right][k])
        agreement.append({"sources": [left, right], "keys_both": len(both), "agree": agree,
                          "agreement": share(agree, len(both))})
    measure = {n: (sources[n]["one_value"], sources[n]["coverage"]) for n in sources}
    order = sorted(sources, key=lambda n: (-measure[n][0], -measure[n][1], n))
    # Sources equal on both measures are ordered by name only: the operator decides between them.
    tied = [list(group) for group in {measure[n]: [m for m in order if measure[m] == measure[n]] for n in order}.values()
            if len(group) > 1]
    return {"keys": len(every), "sources": sources, "agreement": agreement, "recommended": order, "tied": tied}


def defaults_order(fields: dict[str, dict]) -> list[str]:
    """One order for every field: each source's mean place in the fields' orders, then its name."""
    places = defaultdict(list)
    for result in fields.values():
        for place, name in enumerate(result["recommended"]):
            places[name].append(place)
    return sorted(places, key=lambda n: (sum(places[n]) / len(places[n]), n))


def rank(sources: dict[str, tuple[str, str]], fields: dict[str, dict[str, str]]) -> dict:
    """sources: name -> (file, key); fields: field -> source -> column. The whole ranking."""
    by_source = {name: {f: cols[name] for f, cols in fields.items() if name in cols} for name in sources}
    stated = {name: collect(path, key, by_source[name]) for name, (path, key) in sources.items() if by_source[name]}
    results = {field: rank_field({name: stated[name][field] for name in cols}) for field, cols in fields.items()}
    defaults = defaults_order(results)
    return {
        "sources": {name: {"file": path, "key": key} for name, (path, key) in sources.items()},
        "normalised": "upper case; every run of punctuation or space folded to one space; trimmed",
        "fields": results,
        "recommended_defaults": defaults,
        "rule": "order by one value, then coverage: the first source wins where it fills a field",
        "merge_rules": merge_rules(defaults, results),
    }


def merge_rules(defaults: list[str], fields: dict[str, dict]) -> dict:
    """The order in the kind file's own shape: `defaults.sources`, and `fields.<field>.sources` for
    each field whose order differs. The source names are the ones given, so give the source codes."""
    body = {"defaults": {"sources": defaults}}
    differ = {f: {"sources": r["recommended"]} for f, r in fields.items()
              if r["recommended"] != [n for n in defaults if n in r["recommended"]]}
    if differ:
        body["fields"] = differ
    return body


def markdown(ranking: dict) -> str:
    lines = ["# Source ranking", "",
             f"Values compared {ranking['normalised']}. {ranking['rule'].capitalize()}.", "",
             f"Recommended order for every field: {', '.join(ranking['recommended_defaults'])}.", ""]
    for field, result in ranking["fields"].items():
        lines += [f"## {field}", "", f"{result['keys']:,} keys filled by at least one source. "
                  f"Recommended order: {', '.join(result['recommended'])}.", "",
                  "| Source | Keys | Coverage | One value |", "|---|---:|---:|---:|"]
        for name in result["recommended"]:
            s = result["sources"][name]
            lines.append(f"| {name} | {s['keys']:,} | {s['coverage']:.1%} | {s['one_value']:.1%} |")
        lines += ["", "| Sources | Keys both fill | Agree |", "|---|---:|---:|"]
        for pair in result["agreement"]:
            lines.append(f"| {' and '.join(pair['sources'])} | {pair['keys_both']:,} | {pair['agreement']:.1%} |")
        for group in result["tied"]:
            lines.append(f"\nTied on both measures, ordered by name only: {', '.join(group)}. The operator decides.")
        lines.append("")
    snippet = yaml.safe_dump(ranking["merge_rules"], sort_keys=False).rstrip()
    lines += ["## In the kind file", "", "```yaml", snippet, "```", ""]
    return "\n".join(lines)


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="rank_sources.py", description=__doc__.split("\n\n")[0])
    parser.add_argument("--source", action="append", required=True, metavar="NAME=FILE:KEY")
    parser.add_argument("--field", action="append", required=True, metavar="FIELD=SOURCE:COLUMN[,SOURCE:COLUMN]")
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    sources = {}
    for item in args.source:
        name, rest = item.split("=", 1)
        path, key = rest.rsplit(":", 1)
        sources[name] = (path, key)
    fields: dict[str, dict[str, str]] = {}
    for item in args.field:
        field, rest = item.split("=", 1)
        for pair in rest.split(","):
            name, column = pair.split(":", 1)
            if name not in sources:
                raise SystemExit(f"--field {field}: no --source named {name}")
            fields.setdefault(field, {})[name] = column
    ranking = rank(sources, fields)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "ranking.yaml").write_text(yaml.safe_dump(ranking, sort_keys=False, allow_unicode=True),
                                           encoding="utf-8")
    (args.out / "RANKING.md").write_text(markdown(ranking), encoding="utf-8")
    print(f"wrote {args.out / 'ranking.yaml'} and {args.out / 'RANKING.md'}; "
          f"order for every field: {', '.join(ranking['recommended_defaults'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
