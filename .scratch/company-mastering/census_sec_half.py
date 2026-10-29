"""Ticket 148: the SEC half of the Name Frequency census from the configured reductions,
compared with the census recorded on 2026-10-12 (cm27-raw/census.json) over its whole
population: every current-name key, its CIK count and its five smallest CIKs. Counts only.

    uv run --no-sync python .scratch/company-mastering/census_sec_half.py <capture> <population> <census.json>
"""
import json
import sys
import tempfile
import time
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm.clean import name_frequency

capture, population, recorded = (Path(a).expanduser().resolve() for a in sys.argv[1:4])
began = time.monotonic()
census = json.loads(recorded.read_text())
store = Artifacts()
with tempfile.TemporaryDirectory(prefix=".census-sec-") as scratch:
    readings, sec, _, _ = name_frequency._population(capture, population, store, Path(scratch))
    read = time.monotonic() - began
    held, wanted = name_frequency._sec_counts(store, Path(scratch), readings)
entries = census["entries"]
differ = [key for key in sorted(wanted | set(entries))
          if key not in entries or key not in wanted
          or (entries[key]["cik_count"], entries[key]["ciks"]) != held[key]]
print(json.dumps({"filers": sec["filers"], "recorded_filers": census["sec"]["filers"],
                  "population_sha256_equal": sec["population_sha256"] == census["sec"]["population_sha256"],
                  "receipts_sha256_equal": sec["receipts_sha256"] == census["sec"]["receipts_sha256"],
                  "current_name_keys": len(wanted), "recorded_entries": len(entries), "keys_differing": len(differ),
                  "read_seconds": round(read),
                  "seconds": round(time.monotonic() - began)}, indent=1))
