import collections, re, sys
from pathlib import Path
root = Path(sys.argv[1]); c = collections.Counter(); types = collections.Counter(); roots = collections.Counter()
fnames = collections.Counter(); xmldocs = collections.Counter(); crlf = 0; header_acc = 0
for p in root.iterdir():
    b = p.read_bytes(); c["files"] += 1
    if b"\r\n" in b: crlf += 1
    if not b.lstrip().startswith(b"<SEC-DOCUMENT>"): c["not_sec_document"] += 1; continue
    if re.search(rb"ACCESSION NUMBER:\s*[\d-]+", b): header_acc += 1
    docs = re.findall(rb"<DOCUMENT>(.*?)</DOCUMENT>", b, re.S)
    c[f"docs={len(docs)}"] += 1
    n = 0
    for d in docs:
        t = re.search(rb"<TYPE>([^\r\n<]*)", d); types[(t.group(1).strip().decode() if t else "?")] += 1
        if re.search(rb"<XML>", d):
            n += 1
            f = re.search(rb"<FILENAME>([^\r\n<]*)", d)
            name = f.group(1).strip().decode() if f else ""
            fnames[re.sub(r"[0-9]+", "#", name.lower())[:30]] += 1
            r = re.search(rb"<XML>\s*(?:<\?xml[^>]*\?>\s*)?<([A-Za-z:]+)", d); roots[r.group(1).decode() if r else "?"] += 1
    xmldocs[n] += 1
print(dict(c)); print("xml docs per file", dict(xmldocs)); print("crlf files", crlf, "header accession", header_acc)
print("types", types.most_common(15)); print("xml roots", roots.most_common(8)); print("xml filenames", fnames.most_common(12))
