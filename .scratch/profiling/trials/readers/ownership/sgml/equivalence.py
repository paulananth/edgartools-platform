"""Profiling 07: the SGML container reads every fallback ownership file as the trial's
converter does (to_jsonl.py: the accession from the header, the XML between <XML> and
</XML>). The same columns are read twice: through `container: sgml`, and from the
converter's extracted XML with its accession as caller context. Counts only."""
import collections, json, re, sys
from pathlib import Path
from edgar_warehouse.control_contract import digest
from edgar_warehouse.rules.source_engine import SourceEngine

def contract(container: bool) -> dict:
    accession = {"type": "text", "sgml_header": "ACCESSION NUMBER"} if container else {"type": "text"}
    text = lambda p: {"text": {"path": p}}
    return {"read": {"format": "xml", **({"container": "sgml"} if container else {}), "root": "ownershipDocument",
        "context": {"accession": accession}, "limits": {"max_bytes": 33554432},
        "tables": {
            "filing": {"each": ".", "columns": {"accession": {"context": {"name": "accession"}},
                "form": text("documentType.$"), "period": text("periodOfReport.$"), "issuer": text("issuer.issuerCik.$")}},
            "owners": {"each": "reportingOwner", "columns": {"cik": text("reportingOwnerId.rptOwnerCik.$")}},
            "nonderivative": {"each": "nonDerivativeTable.nonDerivativeTransaction", "columns": {
                "date": text("transactionDate.value.$"), "code": text("transactionCoding.transactionCode.$"),
                "swap": text("transactionCoding.equitySwapInvolved.$")}},
            "derivative": {"each": "derivativeTable.derivativeTransaction", "columns": {
                "date": text("transactionDate.value.$"), "code": text("transactionCoding.transactionCode.$")}}}}}

sgml, plain = SourceEngine(contract(True)), SourceEngine(contract(False))
counts = collections.Counter(); first = []
for path in sorted(Path(sys.argv[1]).iterdir()):
    raw = path.read_bytes()
    accession = re.search(rb"ACCESSION NUMBER:\s*([\d-]+)", raw).group(1).decode()
    xml = re.search(rb"<XML>(.*?)</XML>", raw, re.S).group(1).strip()
    a = sgml.read(raw).tables
    b = plain.read(xml, context={"accession": accession}).tables
    counts["files"] += 1
    counts["equal" if digest(a) == digest(b) else "differ"] += 1
    for t in ("owners", "nonderivative", "derivative"): counts[t] += len(a[t])
    if digest(a) != digest(b) and len(first) < 3: first.append(path.name)
print(json.dumps({"counts": dict(counts), "first_differences": first}, indent=1, sort_keys=True))
