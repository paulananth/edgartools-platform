"""Ticket 45: read every captured company facts file with the configured contract
and compare its facts with the same file flattened directly (exact number text).
Prints counts only; the captured data stays local."""
import collections, glob, gzip, json, sys, time
from pathlib import Path
from decimal import Decimal
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected

COHORT, CONTRACT = sys.argv[1], sys.argv[2]
engine = SourceEngine(files.load(Path(CONTRACT)))
FIELDS = ("start", "end", "val", "accn", "fy", "fp", "form", "filed", "frame")


def exact(v):
    """A figure as an exact decimal; a float is refused, since none may reach here."""
    if isinstance(v, float):
        raise TypeError("a figure arrived as a float")
    return None if v is None else Decimal(v)


def flat(taxonomy, concept, units):
    for unit, items in (units or {}).items():
        for item in items:
            yield (taxonomy, concept, unit) + tuple(exact(item.get(f)) if f in ("val",) else item.get(f) for f in FIELDS)


tally = collections.Counter()
started = time.monotonic()
for path in sorted(glob.glob(f"{COHORT}/*.json.gz")):
    raw = gzip.open(path).read()
    direct = json.loads(raw, parse_float=Decimal, parse_int=Decimal)
    try:
        reading = engine.read(raw)
    except SourceRejected as error:
        tally[f"refused {error.code}"] += 1
        continue
    tally["read"] += 1
    tables = reading.tables
    if not direct:
        tally["empty document"] += 1
    want = collections.Counter(
        (t, c) + row[2:] for t, cs in (direct.get("facts") or {}).items() for c, b in cs.items()
        for row in [(t, c) + r[2:] for r in flat(t, c, b.get("units"))])
    got = collections.Counter()
    for name, rows in tables.items():
        if name == "taxonomies":
            continue
        for row in rows:
            tally["concepts"] += 1
            if row["cik"] != int(path.rsplit("/", 1)[1][:10]):
                tally["cik differs from file name"] += 1
            taxonomy = next(t for t in (direct.get("facts") or {}) if "concepts_" + t.replace("-", "_") == name)
            got.update(flat(taxonomy, row["concept"], row["units"]))
    tally["facts"] += sum(got.values())
    tally["files equal" if got == want else "files differ"] += 1
    tally["taxonomy rows"] += len(tables["taxonomies"])
print(json.dumps(dict(sorted(tally.items())), indent=1), f"{time.monotonic() - started:.1f} s")
