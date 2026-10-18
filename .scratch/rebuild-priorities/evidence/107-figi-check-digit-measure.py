"""Ticket 107: FIGI's check digit measured on the local 2026-10-15 OpenFIGI capture (counts only).

Run from the repository root: `uv run --extra mdm python .scratch/rebuild-priorities/evidence/107-figi-check-digit-measure.py`.
Measured 2026-10-17: 1,618,040 distinct FIGIs (figi, compositeFIGI, shareClassFIGI); the family fails
none and "luhn over letter values" fails 1,456,578; the silver writer's `figi_valid` check flags 0 of
2,184,699 listings.
"""
import glob
import json
import sys

sys.path.insert(0, ".")
from edgar_warehouse.mdm.clean.identifier_types import FAMILIES  # noqa: E402
from edgar_warehouse.rules import files  # noqa: E402
from edgar_warehouse.silver_writer import checks  # noqa: E402

CAPTURE = "~/.local/share/edgartools/clean-mdm/captures/openfigi/2026q2-nport"


def listings():
    from pathlib import Path
    for f in glob.glob(str(Path(CAPTURE).expanduser() / "**" / "*.json"), recursive=True):
        if f.endswith("receipt.json"):
            continue
        try:
            answers = json.load(open(f))
        except ValueError:
            continue
        for answer in answers if isinstance(answers, list) else []:
            yield from (answer.get("data") or []) if isinstance(answer, dict) else []


rows = list(listings())
figis = {row[k] for row in rows for k in ("figi", "compositeFIGI", "shareClassFIGI") if row.get(k)}
print("distinct FIGIs", len(figis))
for name, test in FAMILIES.items():
    try:
        print(name, "fails", sum(not test(v) for v in figis))
    except ValueError:
        print(name, "cannot read a FIGI")
spec = files.load(files.ROOT / "sources/openfigi/silver-listing.yaml")
item = next(c for c in spec["checks"] if c["id"] == "figi_valid")
print("listings", len(rows), "figi_valid flags", len(checks._FAILS["identifier"](item, [{"figi": r.get("figi")} for r in rows])))
