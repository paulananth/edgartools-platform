"""Company facts in long form, one row per fact, for profiling (ticket 05).

    uv run --with duckdb python -I to_facts_parquet.py <capture folder> <out folder>

Company facts holds each concept as an object key (`facts.<taxonomy>.<concept>.units.<unit>[]`);
the profiler reads object keys as columns, so this workaround writes the keys as values:
facts.parquet (cik, taxonomy, concept, unit, start, end, val, accn, fy, fp, form, filed, frame),
concepts.parquet (taxonomy, concept, label, description; one row per concept seen) and
entities.parquet (cik, entityName).

`val` is the value exactly as filed, as text (ticket 44): a float would round a
figure past 15 to 17 significant digits, and one cohort fact is beyond 64 bits
(ticket 128). Read it with an exact decimal type, never a float.
"""

import gzip
import json
import sys
from pathlib import Path

import duckdb

FIELDS = ("start", "end", "val", "accn", "fy", "fp", "form", "filed", "frame")


def main(capture: str, out: str) -> int:
    folder, target = Path(capture).expanduser(), Path(out).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    concepts, entities = {}, []
    staged = target / "facts.jsonl.gz"  # streamed, then read once by DuckDB
    with gzip.open(staged, "wt", encoding="utf-8", compresslevel=1) as handle:
        for path in sorted(folder.glob("*.json.gz")):
            # Numbers keep their exact text: never a float (ticket 44).
            document = json.loads(gzip.decompress(path.read_bytes()), parse_float=str, parse_int=str)
            cik = path.name.split(".")[0]
            if not document.get("facts"):  # SEC answered with an empty document: no facts
                print(f"no facts in {path.name}")
                continue
            entities.append({"cik": cik, "entityName": document.get("entityName")})
            for taxonomy, named in (document.get("facts") or {}).items():
                for concept, body in named.items():
                    concepts.setdefault((taxonomy, concept), (body.get("label"), body.get("description")))
                    for unit, facts in (body.get("units") or {}).items():
                        for fact in facts:
                            row = {"cik": cik, "taxonomy": taxonomy, "concept": concept, "unit": unit}
                            row.update({k: fact.get(k) for k in FIELDS})
                            row["fy"] = int(row["fy"]) if row["fy"] is not None else None
                            handle.write(json.dumps(row) + "\n")
    columns = ("{cik: 'VARCHAR', taxonomy: 'VARCHAR', concept: 'VARCHAR', unit: 'VARCHAR', start: 'VARCHAR', "
               "\"end\": 'VARCHAR', val: 'VARCHAR', accn: 'VARCHAR', fy: 'BIGINT', fp: 'VARCHAR', form: 'VARCHAR', "
               "filed: 'VARCHAR', frame: 'VARCHAR'}")
    con.execute(f"COPY (SELECT * FROM read_json('{staged}', format='newline_delimited', columns={columns})) "
                f"TO '{target / 'facts.parquet'}' (FORMAT parquet)")
    staged.unlink()
    (target / "concepts.jsonl").write_text("".join(
        json.dumps({"taxonomy": t, "concept": c, "label": l, "description": d}) + "\n"
        for (t, c), (l, d) in concepts.items()))
    (target / "entities.jsonl").write_text("".join(json.dumps(e) + "\n" for e in entities))
    for name in ("concepts", "entities"):
        con.execute(f"COPY (SELECT * FROM read_json('{target / (name + '.jsonl')}')) TO '{target / (name + '.parquet')}' (FORMAT parquet)")
        (target / (name + ".jsonl")).unlink()
    for name in ("facts", "concepts", "entities"):
        print(name, con.execute(f"SELECT count(*) FROM '{target / (name + '.parquet')}'").fetchone()[0])
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
