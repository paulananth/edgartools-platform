"""Ticket 47: silver's measures, built by the SQL over the line items, against the
answer key's rules (ticket 44's oracle) for every company of the cohort. Each file
is read by facts.yaml's `company_fact` into a disposable PostgreSQL 16; the line
items and then the measures are built there by their queries; the oracle reads the
same file directly. Each filer's SIC and place of incorporation are read from its
captured submissions file, as the oracle reads them (the Company master holds 30
of the 368 locally; mastering them is ticket 48's proof). Counts only, and the
first differences written to a local file.

    uv run --no-sync python .scratch/company-financials/measures/compare_key.py \
        <cohort folder> <submissions bronze folder> <differences out>
"""
import gzip
import io
import json
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from decimal import ROUND_HALF_UP, Decimal, getcontext
from pathlib import Path

from sqlalchemy import create_engine, text

COHORT, SUBMISSIONS, OUT = (Path(a).expanduser() for a in sys.argv[1:4])
sys.argv[1:] = [str(COHORT), "/nonexistent", "/nonexistent", "/nonexistent"]  # the oracle reads its paths at import
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "answer-key"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "line-items"))
import oracle  # noqa: E402
from compare_key import COLUMNS, rows_of  # noqa: E402

from edgar_warehouse.financials import line_items, measures  # noqa: E402
from tests.support import pg16  # noqa: E402

PLACES = Decimal("1e-10")


def filed(cik: str) -> tuple[str | None, str | None]:
    """A filer's SIC and place of incorporation from its latest captured submissions file."""
    found = sorted((SUBMISSIONS / f"cik={int(cik)}").rglob(f"CIK{cik}.json"))
    if not found:
        return None, None
    body = json.loads(found[-1].read_bytes())
    return (str(body["sic"]) if body.get("sic") else None, body.get("stateOfIncorporation") or None)


def expected(job: tuple[Path, tuple]) -> dict:
    path, (sic, place) = job
    # Rounded once, as silver stores it (10 places, half away from zero): the key's own 12 places, rounded
    # again to 10, can move the last digit.
    oracle.PLACES = PLACES
    getcontext().rounding = ROUND_HALF_UP
    cik = path.name[:10]
    body = json.loads(gzip.decompress(path.read_bytes()), parse_float=Decimal)
    company = oracle.Company(cik, body, sic, place)
    items = {y: {name: oracle.item(company, y, name) for name in oracle.LISTS["us-gaap"]} for y in sorted(company.years)}
    return {(cik, m["measure"], int(m["year"]), m["window"] or 1): m for m in oracle.measures(company, items)}


def main() -> None:
    began = time.monotonic()
    paths = sorted(COHORT.glob("*.json.gz"))
    items, defined = line_items.load(), measures.load()
    with ProcessPoolExecutor() as pool:
        # Read here: a worker process imports this file again, after the oracle replaced the arguments.
        companies = {p.name[:10]: filed(p.name[:10]) for p in paths}
        with pg16.server() as server:
            engine = create_engine(server.url())
            with engine.begin() as conn:
                conn.exec_driver_sql("CREATE TABLE fact (company_key text, taxonomy text, concept text, unit text, "
                                     "currency text, period_start date, period_end date, value numeric(38,10), "
                                     "accession text, filed date, form text)")
            raw = engine.raw_connection()
            try:
                with raw.cursor() as cur:
                    for chunk in pool.map(rows_of, paths, chunksize=4):
                        cur.copy_expert(f"COPY fact ({', '.join(COLUMNS)}) FROM STDIN", io.StringIO(chunk))
                raw.commit()
            finally:
                raw.close()
            with engine.connect() as conn, conn.begin():
                *steps, final = line_items.statements(items, "fact")
                for step in steps:
                    conn.execute(text(step))
                conn.execute(text(f"CREATE TABLE line AS {final}"))
            started = time.monotonic()
            with engine.connect() as conn, conn.begin():
                *steps, final = measures.statements(defined, measures.filers(companies), "line", "fact")
                for step in steps:
                    conn.execute(text(step))
                got = {(r.company_key, r.measure, r.fiscal_year, r.window_years): r for r in conn.execute(text(final))}
            query_seconds = time.monotonic() - started
            engine.dispose()
        want: dict = {}
        for part in pool.map(expected, [(p, companies[p.name[:10]]) for p in paths], chunksize=4):
            want.update(part)
    tally, reasons, differ = Counter(), Counter(), []
    for key in sorted(set(want) | set(got)):
        w, g = want.get(key), got.get(key)
        if w is None or g is None:
            tally["only in the key" if g is None else "only in silver"] += 1
            continue
        w_value = None if w["value"] is None else Decimal(w["value"])
        same = w_value == g.value and w["reason"] == g.null_reason
        tally["equal" if same else "different"] += 1
        tally["with value"] += g.value is not None
        reasons[g.null_reason] += g.value is None
        if not same and len(differ) < 200:
            differ.append({"key": key, "want": [str(w_value), w["reason"]], "got": [str(g.value), g.null_reason]})
    OUT.write_text(json.dumps(differ, indent=1, default=str))
    print(json.dumps({"files": len(paths), "companies_with_sic": sum(1 for s, _ in companies.values() if s),
                      "measures_compared": tally["equal"] + tally["different"], **tally,
                      "null_reasons": dict(reasons), "query_seconds": round(query_seconds),
                      "seconds": round(time.monotonic() - began)}, indent=1, default=str))


if __name__ == "__main__":
    main()
