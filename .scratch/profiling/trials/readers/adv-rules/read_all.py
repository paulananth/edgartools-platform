"""Ticket 07: read every month of the local ADV copy through the iapd.adv readings.

    uv run --extra mdm python .scratch/profiling/trials/readers/adv-rules/read_all.py <out folder>

Writes <out>/<YYYY-MM>/{filings,custody}.json (the reading's rows) and prints counts.
A file's `published` context is the end of the month it covers, New York time.
"""
import calendar
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine

FOLDER = files.ROOT / "sources" / "iapd.adv"
B = Path.home() / ".local/share/edgartools/clean-mdm/proving/p07/inputs/warehouse/bronze/reference/iapd_adv_bulk"


def published(month: str) -> str:
    y, m = map(int, month.split("-"))
    end = datetime(y, m, calendar.monthrange(y, m)[1], 23, 59, 59, tzinfo=ZoneInfo("America/New_York"))
    return end.isoformat()


def main(out: Path):
    readings = {"filings": SourceEngine(files.load(FOLDER / "adviser-filings-csv.yaml")),
                "custody": SourceEngine(files.load(FOLDER / "custody-csv.yaml"))}
    for z in sorted(B.glob("*/*.zip")):
        data, ctx = z.read_bytes(), {"published": published(z.parent.name)}
        (out / z.parent.name).mkdir(parents=True, exist_ok=True)
        for table, engine in readings.items():
            rows = engine.read(data, context=ctx).tables[table]
            (out / z.parent.name / f"{table}.json").write_text(json.dumps(rows, ensure_ascii=False))
            print(z.parent.name, table, len(rows))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
