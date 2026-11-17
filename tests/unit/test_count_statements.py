"""count_statements.py reads a statement log with the prefix its procedure sets, and with the default one."""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "skills/data-operations/scripts/count_statements.py"
spec = importlib.util.spec_from_file_location("count_statements", SCRIPT)
count_statements = importlib.util.module_from_spec(spec)
spec.loader.exec_module(count_statements)

STAMP = "2026-01-01 00:00:00.000 UTC"


@pytest.mark.parametrize("prefix, database", [
    ("", None),                          # the server's default prefix
    ("mdm ", "mdm"),                     # %d, as the procedure sets it
    ("change_journal app ", "change_journal"),  # %d %u
    ("store-one app ", "store-one"),     # a database name with a hyphen
])
def test_every_statement_is_counted_with_its_database_when_the_prefix_names_it(prefix, database):
    lines = [f"{STAMP} [11] {prefix}LOG:  statement: BEGIN",
             f"{STAMP} [11] {prefix}LOG:  execute <unnamed>: SELECT * FROM mastering_record WHERE subject = $1",
             f"{STAMP} [12] {prefix}LOG:  statement: COMMIT",
             f"{STAMP} [12] {prefix}LOG:  connection received: host=example"]
    total, sessions, counts, databases, _ = count_statements.tally(lines)
    assert total == 3 and sessions == {"11", "12"}
    assert counts["SELECT mastering_record"] == 1
    assert dict(databases) == ({database: 3} if database else {})
