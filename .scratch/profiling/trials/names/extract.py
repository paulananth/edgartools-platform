"""Ticket 07b trial, step 1: flat local extracts of SEC filers and GLEIF records for match_names.py.

    python .scratch/profiling/trials/names/extract.py <out folder>

Reads the local captures only (no request to any provider): every SEC
submissions file of the all-76230 capture, and the full GLEIF Level 1 extract
made for company mastering ticket 08 (cm08-gleif-all.jsonl, from the
2026-09-11 16:00 UTC Golden Copy). Writes sec.jsonl and gleif.jsonl.

GLEIF keeps only records that can pair with a filer (its LEI is a filer's, or
one of its folded names is a filer's current or former name): the full 3.4
million records outgrow this machine's memory and disk.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "skills/data-profiling/scripts"))
from profiling.name_matching import tokens  # noqa: E402

HOME = Path.home() / ".local/share/edgartools/clean-mdm"
SEC = HOME / "captures/sec.submissions.company/all-76230/bronze/submissions/sec"
GLEIF = HOME / "research/cm08-gleif-all.jsonl"

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
leis, names = set(), set()
with (out / "sec.jsonl").open("w") as handle:
    for folder in sorted(SEC.glob("cik=*")):
        path = max(folder.glob("**/*.json"))  # the newest capture of each filer
        d = json.loads(path.read_text())
        business = (d.get("addresses") or {}).get("business") or {}
        handle.write(json.dumps({
            "cik": d["cik"], "name": d.get("name"), "entity_type": d.get("entityType"),
            "former_names": [f.get("name") for f in d.get("formerNames") or [] if f.get("name")],
            "state": d.get("stateOfIncorporation") or None, "zip": business.get("zipCode"),
            "lei": (d.get("lei") or "").strip().upper() or None}) + "\n")
        leis.add((d.get("lei") or "").strip().upper())
        names.update(" ".join(tokens(n)) for n in [d.get("name") or "", *(f.get("name") or "" for f in d.get("formerNames") or [])])
names.discard("")
with GLEIF.open() as source, (out / "gleif.jsonl").open("w") as handle:
    for line in source:
        g = json.loads(line)
        own = [g.get("legal_name") or "", *(o[-1] if isinstance(o, list) else (o.get("name") if isinstance(o, dict) else o) or "" for o in g.get("other_names") or [])]
        if g["lei"] not in leis and not any(" ".join(tokens(n)) in names for n in own):
            continue
        handle.write(json.dumps({
            "lei": g["lei"], "legal_name": g.get("legal_name"), "other_names": g.get("other_names") or [],
            "category": g.get("category"), "jurisdiction": g.get("jurisdiction"),
            "hq_postal": (g.get("hq") or {}).get("postal"), "legal_postal": (g.get("legal") or {}).get("postal")}) + "\n")
