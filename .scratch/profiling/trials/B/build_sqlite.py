"""Build Trial B's SQLite form from the Contoso V2 CSV files (outside the skill).

    uv run --with duckdb python .scratch/profiling/trials/B/build_sqlite.py <csv folder> <out.db>

Each CSV becomes one table of the same name, every type read by a full scan.
"""

import sys
from pathlib import Path

import duckdb

source, target = Path(sys.argv[1]), Path(sys.argv[2])
if target.exists():
    raise SystemExit(f"{target} exists")
con = duckdb.connect()
con.execute(f"ATTACH '{target}' AS out (TYPE sqlite)")
for csv in sorted(source.glob("*.csv")):
    con.execute(f"CREATE TABLE out.{csv.stem} AS SELECT * FROM read_csv(?, sample_size=-1)", [str(csv)])
    print(csv.stem, con.execute(f"SELECT count(*) FROM out.{csv.stem}").fetchone()[0])
