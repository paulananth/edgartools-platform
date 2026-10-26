# Ticket 138 part B3: counts the ticker-root currency rule on the captures (counts only).
import json, os, zipfile, collections
cap = os.path.expanduser("~/.local/share/edgartools/clean-mdm/captures/openfigi/2026q2-nport")
nport = os.path.expanduser("~/.local/share/edgartools/clean-mdm/captures/sec.nport-datasets/2026q2/2026q2_nport.zip")
codes = set()
with zipfile.ZipFile(nport) as z, z.open("FUND_REPORTED_HOLDING.tsv") as f:
    i = f.readline().decode().rstrip("\n").split("\t").index("CURRENCY_CODE")
    for line in f:
        v = line.decode("utf-8", "replace").rstrip("\n").split("\t")[i]
        if len(v) == 3 and v.isalpha() and v.isupper(): codes.add(v)
c = collections.Counter()
for kind in ("id_cusip", "id_isin"):
    d = os.path.join(cap, kind)
    for name in os.listdir(d):
        if name.endswith(".request.json"): continue
        for ans in json.load(open(os.path.join(d, name))):
            by = collections.defaultdict(list)
            for l in ans.get("data", []):
                by[l.get("exchCode")].append(l.get("ticker") or "")
            for ex, ts in by.items():
                c["lines"] += len(ts)
                if len(ts) < 2:
                    c["single-line exchange: lines"] += len(ts)
                    if len(ts[0]) > 3 and ts[0][-3:] in codes: c["single line ending in a code (not read)"] += 1
                    continue
                c["multi-line groups"] += 1
                ok = all(len(t) > 3 and t[-3:] in codes for t in ts)
                roots = {t[:-3] for t in ts} if ok else set()
                cur = [t[-3:] for t in ts] if ok else []
                if ok and len(roots) == 1 and len(set(cur)) == len(cur):
                    c["groups: one root, a distinct code each"] += 1
                    c["lines given a currency"] += len(ts)
                elif ok and len(roots) == 1:
                    c["groups: one root, a code repeated"] += 1
                elif ok:
                    c["groups: codes but several roots"] += 1
                else:
                    coded = [t for t in ts if len(t) > 3 and t[-3:] in codes]
                    plain = [t for t in ts if t not in coded]
                    r = {t[:-3] for t in coded}
                    if coded and len(r) == 1 and set(plain) <= r and len(plain) == 1 and len({t[-3:] for t in coded}) == len(coded):
                        c["groups: the root alone plus coded lines"] += 1
                        c["lines given a currency there"] += len(coded)
                    c["groups: some line without a code"] += 1
                    c["lines in such groups"] += len(ts)
for k, v in c.items(): print(f"{k}: {v:,}")
