"""Per-filer view, and which step of the live Company classification rule each
filer's record would fire. Records are built BY HAND in the reader's shape
(company_source.prepare_company_bundle: sec_company columns + forms + tickers),
because the reader needs silver landing Parquet this trial does not have.
forms come from filings.recent only (the reader also reads pagination files)."""
import json, sys, collections
from pathlib import Path
from edgar_warehouse.rules import files
from edgar_warehouse.mdm.clean.classification import fired, resolve_rule

IN = Path(sys.argv[1])
policy = files.policy()
rule = resolve_rule(policy, {"kind": "company", "rule_id": "sec-company-candidate", "version": "2026-09-25.13"})
cat = collections.defaultdict(list)
for i, r in enumerate(json.loads((IN / "tickers/company_tickers_exchange.json").read_bytes())["data"], 1):
    cat[int(r[0])].append((i, r[2]))
steps = collections.Counter()
for f in sorted((IN / "submissions").glob("*.json")):
    d = json.loads(f.read_bytes())
    rec = {"cik": int(d["cik"]), "entity_name": d.get("name"), "entity_type": d.get("entityType"),
           "sic": d.get("sic"), "sic_description": d.get("sicDescription"),
           "state_of_incorporation": d.get("stateOfIncorporation"), "category": d.get("category"),
           "fiscal_year_end": d.get("fiscalYearEnd"), "ein": d.get("ein"), "description": d.get("description"),
           "forms": sorted(set(d["filings"]["recent"]["form"])),
           "tickers": [t for _, t in sorted(cat.get(int(d["cik"]), []))]}
    verdict, step = fired(rule, rec, policy["kinds"]["company"])
    steps[(step, verdict)] += 1
    fm = rec["forms"]
    print(f"{d['cik']} {d['entityType']:9s} sic={d['sic'] or '-':5s} st={d['stateOfIncorporation'] or '-':3s} "
          f"tick={rec['tickers'] or '-'} step={step}:{verdict:8s} forms={fm[:6]}{'...' if len(fm)>6 else ''} | {d['name']}")
print(steps)
