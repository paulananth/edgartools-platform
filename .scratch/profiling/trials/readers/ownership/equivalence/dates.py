"""Profiling ticket 07: every date the ownership readings read, against its raw
text, on both local sets. A date is read as its first ten characters (a calendar
date); this counts each raw shape and checks the reading changed only the values
with something after the date. Counts only.

    uv run python dates.py <bronze folder> > dates.json
"""
import collections, glob, json, re, sys
import xml.etree.ElementTree as ET
from pathlib import Path

from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine

RULES = Path(__file__).resolve().parents[6] / "rules/sources/sec.ownership"
XML, SGML = (SourceEngine(files.load(RULES / f"ownership-{s}.yaml")) for s in ("xml", "sgml"))
BRONZE = Path(sys.argv[1])
# table, the XML item, column, the element path under the item
FIELDS = [("ownership_document", ".", "period_of_report", "periodOfReport"), ("ownership_document", ".", "date_of_original_submission", "dateOfOriginalSubmission")]
for table, item in (("non_derivative_transaction", "nonDerivativeTable/nonDerivativeTransaction"), ("derivative_transaction", "derivativeTable/derivativeTransaction")):
    FIELDS += [(table, item, "transaction_date", "transactionDate/value"), (table, item, "deemed_execution_date", "deemedExecutionDate/value")]
for table, item in (("derivative_transaction", "derivativeTable/derivativeTransaction"), ("derivative_holding", "derivativeTable/derivativeHolding")):
    FIELDS += [(table, item, "exercise_date", "exerciseDate/value"), (table, item, "expiration_date", "expirationDate/value")]
FIELDS += [("owner_signature", "ownerSignature", "signature_date", "signatureDate")]


def shape(raw):
    if raw is None: return "absent"
    raw = raw.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw): return "date"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}[+-]\d{2}:\d{2}", raw): return "date with offset"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}Z", raw): return "date with Z"
    return "other"


counts = collections.Counter()
def run(which, xml_text, tables):
    root = ET.fromstring(re.sub(r"^<\?xml[^>]*\?>", "", xml_text.strip()))
    for table, item, column, path in FIELDS:
        items = [root] if item == "." else root.findall(item)
        for element, row in zip(items, tables[table]):
            found = element.find(path)
            raw = found.text if found is not None else None
            kind = shape(raw)
            read = row[column]
            expected = raw.strip()[:10] if kind != "absent" else None
            counts[(which, column, kind, "as expected" if read == expected else "unexpected")] += 1

for p in sorted(glob.glob(str(BRONZE / "filings/sec/*/*/primary/*.xml"))):
    raw = Path(p).read_bytes()
    if b"<ownershipDocument" not in raw: continue
    run("cohort", raw.decode(), XML.read(raw, context={"accession": "x"}).tables)
for p in sorted((BRONZE / "filing_artifact").iterdir()):
    raw = p.read_bytes()
    run("artifact", re.search(rb"<XML>(.*?)</XML>", raw, re.S).group(1).decode(), SGML.read(raw).tables)
out = collections.defaultdict(dict)
for (which, column, kind, outcome), n in sorted(counts.items()):
    out[which].setdefault(column, {})[f"{kind}: {outcome}"] = n
print(json.dumps(out, indent=1, sort_keys=True))
