"""Ticket 46: silver's line items, built by the SQL query, against the answer key's
rules (ticket 44's oracle) for every company of the cohort, not only the key's
three cases. Each file is read by facts.yaml's `company_fact` into a disposable
PostgreSQL 16; the query runs over those facts; the oracle reads the same file
directly. Counts only, and the first differences written to a local file.

    uv run --no-sync python .scratch/company-financials/line-items/compare_key.py <cohort folder> <differences out>
"""
import gzip
import io
import json
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, text

from edgar_warehouse.financials import line_items
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine
from tests.support import pg16

COHORT, OUT = Path(sys.argv[1]).expanduser(), Path(sys.argv[2]).expanduser()
sys.argv[1:] = [str(COHORT), "/nonexistent", "/nonexistent", "/nonexistent"]  # the oracle reads its paths at import
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "answer-key"))
import oracle  # noqa: E402

FOLDER = files.ROOT / "sources" / "sec.company-facts"
COLUMNS = ["company_key", "taxonomy", "concept", "unit", "currency", "period_start", "period_end", "value",
           "accession", "filed", "form"]
QUALITY = "revenue quality check"


def rows_of(path: Path) -> str:
    rows = SourceEngine(files.load(FOLDER / "facts.yaml")).read(gzip.decompress(path.read_bytes())).tables["company_fact"]
    out = io.StringIO()
    for r in rows:
        out.write("\t".join("\\N" if r[c] is None else str(r[c]) for c in COLUMNS) + "\n")
    return out.getvalue()


def expected(path: Path) -> dict:
    body = json.loads(gzip.decompress(path.read_bytes()), parse_float=Decimal)
    company = oracle.Company(path.name[:10], body, None)
    return {(company.cik, int(y), name): oracle.item(company, y, name)
            for y in company.years for name in oracle.LISTS["us-gaap"]}


def main() -> None:
    began = time.monotonic()
    paths = sorted(COHORT.glob("*.json.gz"))
    items = line_items.load()
    with pg16.server() as server:
        engine = create_engine(server.url())
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE fact (company_key text, taxonomy text, concept text, unit text, "
                                 "currency text, period_start date, period_end date, value numeric(38,10), "
                                 "accession text, filed date, form text)")
        with ProcessPoolExecutor() as pool:
            raw = engine.raw_connection()
            try:
                with raw.cursor() as cur:
                    for chunk in pool.map(rows_of, paths, chunksize=4):
                        cur.copy_expert(f"COPY fact ({', '.join(COLUMNS)}) FROM STDIN", io.StringIO(chunk))
                raw.commit()
            finally:
                raw.close()
            read = time.monotonic() - began
            with engine.connect() as conn:
                facts = conn.scalar(text("SELECT count(*) FROM fact"))
                started = time.monotonic()
                got = {(r.company_key, r.fiscal_year, r.line_item): r for r in conn.execute(text(line_items.query(items, "fact")))}
                query_seconds = time.monotonic() - started
            want: dict = {}
            for part in pool.map(expected, paths, chunksize=4):
                want.update(part)
        engine.dispose()
    tally, differ = Counter(), []
    years_got, years_want = {(c, y) for c, y, _ in got}, {(c, y) for c, y, _ in want}
    for key in sorted(set(want) & set(got)):
        w, g = want[key], got[key]
        w_value = None if w.get("value") is None else Decimal(w["value"])
        w_flags = sorted(w.get("flags") or [])
        g_flags = sorted(f for f in g.flags if f != QUALITY)
        tally["quality flagged"] += QUALITY in g.flags
        same = (w_value == g.value and w.get("unit") == g.unit and w.get("accn") == g.accession
                and (w.get("filed") or None) == (g.filed.isoformat() if g.filed else None)
                and w_flags == g_flags and w["taxonomy"] == g.taxonomy and w["end"] == g.period_end.isoformat()
                and (w.get("concept", "").startswith("computed") or w.get("concept") == g.concept))
        tally["equal" if same else "different"] += 1
        tally["with value"] += g.value is not None
        if not same and len(differ) < 200:
            differ.append({"key": key, "want": {k: w.get(k) for k in ("value", "unit", "accn", "filed", "flags", "concept",
                                                                  "taxonomy", "end")},
                           "got": {k: str(getattr(g, k)) for k in ("value", "unit", "accession", "filed", "flags",
                                                                   "concept", "taxonomy", "period_end")}})
    OUT.write_text(json.dumps(differ, indent=1, default=str))
    print(json.dumps({"files": len(paths), "facts": facts, "company_years_sql": len(years_got),
                      "company_years_key": len(years_want), "company_years_only_one_side": len(years_got ^ years_want),
                      "line_items_compared": sum(tally[k] for k in ("equal", "different")), **tally,
                      "read_seconds": round(read), "query_seconds": round(query_seconds),
                      "seconds": round(time.monotonic() - began)}, indent=1))


if __name__ == "__main__":
    main()
