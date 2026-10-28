"""Ticket 46: every captured company facts file through facts.yaml's `company_fact`,
compared fact by fact with the file read directly in exact decimals; the silver
key never repeats; every row fits silver-company-fact.yaml. Counts only.

    uv run --no-sync python .scratch/company-financials/reader/fact_rows.py <cohort folder>
"""
import gzip
import json
import sys
import time
from decimal import Decimal
from pathlib import Path

from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine
from edgar_warehouse.silver_writer import spec as silver_spec

FOLDER = files.ROOT / "sources" / "sec.company-facts"
engine = SourceEngine(files.load(FOLDER / "facts.yaml"))
spec = silver_spec.check(files.load(FOLDER / "silver-company-fact.yaml"))
columns = {c["name"] for c in spec["columns"]}
key = spec["key"]
began, facts, keys, unequal, currencies = time.monotonic(), 0, set(), 0, {}
for path in sorted(Path(sys.argv[1]).expanduser().glob("*.json.gz")):
    raw = gzip.decompress(path.read_bytes())
    rows = engine.read(raw).tables["company_fact"]
    direct = json.loads(raw, parse_float=str, parse_int=str)
    expected = sorted((tax, concept, unit, f.get("start") or "", f["end"], Decimal(f["val"]), f["accn"], f["filed"])
                      for tax, concepts in (direct.get("facts") or {}).items()
                      for concept, body in concepts.items()
                      for unit, rows_ in (body.get("units") or {}).items() for f in rows_)
    got = sorted((r["taxonomy"], r["concept"], r["unit"], r["period_start"] or "", r["period_end"], Decimal(str(r["value"])),
                  r["accession"], r["filed"]) for r in rows)
    unequal += got != expected
    assert all(set(r) == columns for r in rows)
    for r in rows:
        k = tuple(r[c] for c in key)
        assert k not in keys, "repeated key"
        keys.add(k)
        currencies[r["currency"]] = currencies.get(r["currency"], 0) + 1
    facts += len(rows)
print(json.dumps({"files": len(list(Path(sys.argv[1]).expanduser().glob("*.json.gz"))), "facts": facts,
                  "distinct_keys": len(keys), "files_unequal": unequal, "with_currency": facts - currencies.get(None, 0),
                  "currencies": len([c for c in currencies if c]), "seconds": round(time.monotonic() - began)}))
