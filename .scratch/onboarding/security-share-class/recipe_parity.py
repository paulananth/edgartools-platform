"""The committed 13F and N-PORT class recipes, run by the source engine over every
distinct local title, against the Python oracle (ticket 130). Counts only."""
import json, re, sys, tempfile
from pathlib import Path
sys.path.insert(0, ".")
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files
from tests.support import source_chain as chain

S = Path(sys.argv[1])
titles = json.loads((S / "all_titles.json").read_text())
sys.path.insert(0, str(S)); 
def letter(t):
    s=t.strip().upper(); s=re.sub('[^A-Z]+',' ',s); s=' '+s+' '
    s=re.sub('^.* (CL|CLASS|CLS) ','#',s); s=re.sub('^[^#].*$','',s); s=re.sub(' .*$','',s)
    s=re.sub('^#[A-Z][A-Z]+$','',s); return s.replace('#','')
t13 = files.load(files.ROOT/"sources/sec.thirteenf.information_table/source.yaml")["read"]["tables"]["sec_thirteenf_class"]
tnp = files.load(files.ROOT/"sources/sec.nport.security/source.yaml")["read"]["tables"]
# Each class table's selection reads the same recipe as its column.
assert t13["select"]["choose"]["condition"]["equal"]["left"] == t13["columns"]["share_class"]
for name in ("cusip_class", "isin_class"):
    assert tnp[name]["select"]["choose"]["condition"]["equal"]["left"] == tnp[name]["columns"]["share_class"]
    assert tnp[name]["columns"]["share_class"]["choose"]["then"]["text"]["transforms"] == t13["columns"]["share_class"]["text"]["transforms"]
t13 = t13["columns"]["share_class"]["text"]["transforms"]
root = Path(tempfile.mkdtemp(dir=S)); store = Artifacts()
body = {"source": "sec.thirteenf.information_table", "execution": {"profile": "source.read", "workers": 1, "max_artifacts": 1}, "read": {"format": "json", "limits": {"max_bytes": 33554432, "max_records": 100000},
        "tables": {"t": {"each": "titles", "columns": {"i": {"integer": {"path": "i"}}, "share_class": {"text": {"path": "t", "default": "", "transforms": t13}}}}}}}
got = {}
for i in range(0, len(titles), 20000):
    raw = store.put_bytes((root / f"t{i}.json").as_uri(), json.dumps({"titles": [{"i": i + k, "t": t} for k, t in enumerate(titles[i:i+20000])]}).encode())
    ctx = store.put(root.as_uri(), {"version": 1, "input": raw, "values": {}})
    out = chain.read(store, root / f"r{i}", body, [{"input": raw, "context": ctx}], 2)
    for a in store.json(out)["artifacts"]:
        for row in a["tables"]["t"]: got[row["i"]] = row["share_class"]
diff = [t for n, t in enumerate(titles) if got.get(n) != letter(t)]
print(json.dumps({"titles": len(titles), "read": len(got), "lettered": sum(1 for v in got.values() if v), "differ": len(diff)}))
