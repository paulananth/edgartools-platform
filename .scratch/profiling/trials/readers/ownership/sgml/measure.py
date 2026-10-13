"""Profiling 07: the shape of the fallback ownership files (SGML submission files).

Counts only: a <TYPE> or <FILENAME> can carry a person's name, so neither is
printed. Read-only over the local copy; no requests.

    uv run --no-sync python -I measure.py <filing_artifact folder> > measure.json
"""
import collections, json, re, sys
from pathlib import Path

root = Path(sys.argv[1]); c = collections.Counter(); per_file = collections.Counter()
xml_per_file = collections.Counter(); roots = collections.Counter()
for p in root.iterdir():
    b = p.read_bytes(); c["files"] += 1
    c["crlf"] += b"\r\n" in b
    if not b.lstrip().startswith(b"<SEC-DOCUMENT>"):
        c["not_a_submission"] += 1
        continue
    c["header_names_accession_once"] += len(re.findall(rb"ACCESSION NUMBER:", b.split(b"</SEC-HEADER>")[0])) == 1
    docs = re.findall(rb"<DOCUMENT>(.*?)</DOCUMENT>", b, re.S)
    per_file[len(docs)] += 1
    xml = [d for d in docs if re.search(rb"<TEXT>\s*<XML>", d)]
    xml_per_file[len(xml)] += 1
    for d in xml:
        r = re.search(rb"<XML>\s*(?:<\?xml[^>]*\?>\s*)?<([A-Za-z:]+)", d)
        roots[r.group(1).decode() if r else "?"] += 1
print(json.dumps({"counts": dict(c), "documents_per_file": dict(sorted(per_file.items())),
                  "xml_documents_per_file": dict(xml_per_file), "xml_roots": dict(roots)}, indent=1, sort_keys=True))
