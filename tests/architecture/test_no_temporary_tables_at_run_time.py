"""Run-time code creates no temporary table: a worker or a build issues no DDL; the schema is the owner's, made at init
(operator, 2026-11-22: "no temp table usage"). A query that needs its planner steered sets a session setting instead."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPORARY = re.compile(r"CREATE\s+(LOCAL\s+|GLOBAL\s+)?TEMP(ORARY)?\s+TABLE|prefixes=\[\s*[\"']TEMPORARY", re.IGNORECASE)


def test_no_run_time_code_creates_a_temporary_table():
    found = [f"{path.relative_to(ROOT)}:{number}"
             for path in sorted((ROOT / "edgar_warehouse").rglob("*.py"))
             for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
             if TEMPORARY.search(line)]
    assert found == [], f"a temporary table is DDL at run time: {found}"
