"""The load profile tool shows statement shapes and step times, never a value from the data."""
import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / "skills/data-operations/scripts/profile_load.py"
spec = importlib.util.spec_from_file_location("profile_load", PATH)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def test_a_statement_shape_holds_no_literal_and_no_number():
    query = "SELECT * FROM t WHERE name = 'Invented Co' AND id = 4521 AND run = '5b1d9a52-0000-4000-8000-000000000001'"
    assert tool.shape(query) == "SELECT * FROM t WHERE name = S AND id = N AND run = S"


def test_statements_are_ranked_by_the_seconds_they_were_seen():
    seen = [("mdm", "SELECT 1 WHERE id = 7")] * 3 + [("mdm", "SELECT 1 WHERE id = 9"), ("rules", "VACUUM t")]
    assert tool.rank(seen) == [("mdm", "SELECT N WHERE id = N", 4), ("rules", "VACUUM t", 1)]


def test_a_step_takes_the_time_between_its_first_and_last_event():
    start = datetime(2026, 1, 1)
    at = lambda seconds: start + timedelta(seconds=seconds)
    rows = [("requests", 512, at(0), at(782)), ("prepare", 1, at(1100), at(1100)), ("merge", 1, at(2780), at(2780))]
    assert tool.step_table(rows) == [("requests", 512, 782.0), ("prepare", 1, 318.0), ("merge", 1, 1680.0)]
