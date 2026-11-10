"""A ticket's ET stamp later than the clock was guessed, not read (ticket 155)."""

import importlib.util
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("future_stamps", ROOT / "scripts" / "dev" / "future_stamps.py")
future_stamps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(future_stamps)

NOW = datetime(2026, 11, 1, 17, 25, tzinfo=ZoneInfo("America/New_York"))


def test_a_stamp_later_than_now_is_found_with_its_line():
    text = "- [x] done (2026-11-01 17:36 ET)\n- [x] earlier (2026-11-01 16:22 ET)\n"
    assert future_stamps.future(text, NOW) == [(1, "2026-11-01 17:36 ET")]


def test_the_current_minute_and_earlier_stamps_pass():
    assert future_stamps.future("2026-11-01 17:25 ET and 2026-10-31 23:59 ET", NOW) == []


def test_a_later_date_is_found_and_other_time_zones_and_invalid_dates_are_ignored():
    text = "2026-11-02 00:01 ET, 2026-11-01 18:00 UTC, 2026-02-31 10:00 ET"
    assert future_stamps.future(text, NOW) == [(1, "2026-11-02 00:01 ET")]


def _git(repo, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                   cwd=repo, check=True, capture_output=True)


def test_the_script_fails_on_a_future_stamp_added_to_a_tracked_or_a_new_file_and_passes_otherwise(tmp_path):
    (tmp_path / ".scratch").mkdir()
    old = tmp_path / ".scratch" / "old.md"
    old.write_text("- [x] kept (2020-01-01 09:00 ET)\n")
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")

    def run():
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "dev" / "future_stamps.py"), "HEAD"],
                              cwd=tmp_path, capture_output=True, text=True)

    assert run().returncode == 0
    old.write_text(old.read_text() + "- [x] guessed (2099-01-01 00:00 ET)\n")
    changed = run()
    assert changed.returncode == 1 and "old.md" in changed.stderr and "2099-01-01 00:00 ET" in changed.stderr
    old.write_text("- [x] kept (2020-01-01 09:00 ET)\n")
    (tmp_path / ".scratch" / "new.md").write_text("- [x] guessed (2099-01-01 00:00 ET)\n")
    created = run()
    assert created.returncode == 1 and "new.md" in created.stderr


def test_now_becomes_the_clock_and_a_later_stamp_is_pulled_back_to_it():
    text = "- [x] a ({{now}})\n- [x] b (2026-11-01 17:36 ET)\n- [x] c (2026-11-01 16:22 ET)\n"
    assert future_stamps.stamped(text, NOW) == (
        "- [x] a (2026-11-01 17:25 ET)\n- [x] b (2026-11-01 17:25 ET)\n- [x] c (2026-11-01 16:22 ET)\n")


def test_the_script_fails_on_a_now_left_unstamped_and_stamp_fixes_it_and_a_future_stamp(tmp_path):
    (tmp_path / ".scratch").mkdir()
    note = tmp_path / ".scratch" / "t.md"
    note.write_text("- [x] kept (2020-01-01 09:00 ET)\n")
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    script = str(ROOT / "scripts" / "dev" / "future_stamps.py")

    def run(*flags):
        return subprocess.run([sys.executable, script, *flags, "HEAD"], cwd=tmp_path, capture_output=True, text=True)

    note.write_text(note.read_text() + "- [x] new ({{now}})\n- [x] guessed (2099-01-01 00:00 ET)\n")
    assert run().returncode == 1
    assert run("--stamp").returncode == 0
    text = note.read_text()
    assert "{{now}}" not in text and "2099" not in text and "kept (2020-01-01 09:00 ET)" in text
