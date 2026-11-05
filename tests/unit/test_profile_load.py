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


def test_progress_groups_units_by_step_in_run_order_with_the_verified_share():
    rows = [("merge", 9, "pending", 3), ("requests", 1, "verified", 6), ("requests", 1, "pending", 2),
            ("requests", 1, "reported", 2), ("merge", 9, "verified", 1)]
    assert tool.progress_table(rows) == [
        ("requests", 10, {"verified": 6, "pending": 2, "reported": 2}, 0.6),
        ("merge", 4, {"pending": 3, "verified": 1}, 0.25)]


def test_failures_group_units_by_step_state_and_error_shape_without_values():
    rows = [("read", "waiting", "ValueError", 12), ("land", "waiting", "Blocked", 8),
            ("land", "waiting", "Blocked", 2), ("land", "pending", "No file 'invented.zip' at 12", 1)]
    assert tool.failure_table(rows) == [
        ("read", "waiting", "ValueError", 12), ("land", "waiting", "Blocked", 10),
        ("land", "pending", "No file S at N", 1)]
