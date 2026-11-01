"""A ticket marked resolved has no open part (ticket 157)."""

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("open_parts", ROOT / "scripts" / "dev" / "open_parts.py")
open_parts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(open_parts)

RESOLVED = "Type: task. Status: resolved on merge of the PR below (Claude).\n"


def test_a_resolved_ticket_with_an_unchecked_part_is_found_with_its_line():
    text = RESOLVED + "- [x] done\n- [ ] still open\n"
    assert open_parts.open_parts(text) == [(3, "- [ ] still open")]


def test_a_deferred_part_a_checked_part_and_an_unresolved_ticket_pass():
    assert open_parts.open_parts(RESOLVED + "- [x] done\n- [ ] ~~moved~~ deferred to 9: why\n") == []
    assert open_parts.open_parts("Type: task. Status: claimed (Claude).\n- [ ] open\n") == []
    assert open_parts.open_parts("Type: task. Status: closed incomplete.\n- [ ] open\n") == []


def test_a_status_on_its_own_line_counts_and_a_checkbox_in_a_code_fence_does_not():
    assert open_parts.open_parts("Status: resolved (2026-11-01)\n- [ ] open\n") == [(2, "- [ ] open")]
    assert open_parts.open_parts(RESOLVED + "```\n- [ ] <part>\n```\n- [x] done\n") == []
    assert open_parts.open_parts("Type: task. Status: resolved-pending.\n- [ ] open\n") == []


def _git(repo, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                   cwd=repo, check=True, capture_output=True)


def test_the_script_checks_only_the_ticket_files_the_branch_changes(tmp_path):
    issues = tmp_path / ".scratch" / "map" / "issues"
    issues.mkdir(parents=True)
    old = issues / "1-old.md"
    old.write_text(RESOLVED + "- [ ] open long ago\n")
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")

    def run():
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "dev" / "open_parts.py"), "HEAD"],
                              cwd=tmp_path, capture_output=True, text=True)

    assert run().returncode == 0  # untouched by the branch
    new = issues / "2-new.md"
    new.write_text(RESOLVED + "- [ ] forgot\n")
    created = run()
    assert created.returncode == 1 and "2-new.md" in created.stderr and "forgot" in created.stderr
    new.write_text(RESOLVED + "- [x] done\n")
    old.write_text(old.read_text() + "touched\n")
    changed = run()
    assert changed.returncode == 1 and "1-old.md" in changed.stderr
