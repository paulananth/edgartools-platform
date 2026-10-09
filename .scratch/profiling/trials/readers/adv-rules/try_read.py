import sys, glob, json, time
from pathlib import Path
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine
contract = files.load(Path(sys.argv[1]))
engine = SourceEngine(contract)
B = Path.home()/".local/share/edgartools/clean-mdm/proving/p07/inputs/warehouse/bronze/reference/iapd_adv_bulk"
for z in sorted(B.glob("*/*.zip"))[: int(sys.argv[2]) if len(sys.argv) > 2 else 99]:
    t = time.monotonic()
    ctx = {"published": f"{z.parent.name}"}
    r = engine.read(z.read_bytes(), context=ctx) if "context" in contract.get("read", {}) else engine.read(z.read_bytes())
    tables = r.tables if hasattr(r, "tables") else r["tables"]
    for name, rows in tables.items():
        print(z.parent.name, name, len(rows), f"{time.monotonic()-t:.2f}s", json.dumps(rows[0], ensure_ascii=False)[:300])
