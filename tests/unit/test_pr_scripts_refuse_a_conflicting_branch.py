"""A PR that conflicts with main never gets CI, so neither script may carry one quietly (operator, 2026-11-22: "ci not running").

merge_on_green.sh stops at once on a conflicting PR instead of waiting out its deadline; commit_push.sh refuses a branch that is
behind origin/main before it stamps, stages or commits anything.
"""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MERGE = ROOT / "scripts/dev/merge_on_green.sh"
COMMIT = ROOT / "scripts/dev/commit_push.sh"

# A gh whose PR is open but conflicts with main: no CI run ever starts for it.
CONFLICTING_GH = """#!/usr/bin/env bash
case "$*" in
  "pr view 7 --json state"*) echo OPEN ;;
  "pr view 7 --json headRefOid"*) echo 0123456789abcdef ;;
  "pr view 7 --json mergeStateStatus"*) echo DIRTY ;;
  "run list"*) ;;
  "pr list"*) ;;
  *) echo "unexpected gh $*" >&2; exit 9 ;;
esac
"""


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True, capture_output=True)


def fake_gh(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(CONFLICTING_GH)
    gh.chmod(0o755)
    return {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "MERGE_POLL_SECONDS": "0"}


def test_the_watcher_stops_at_once_on_a_conflicting_pr(tmp_path):
    done = subprocess.run(["bash", str(MERGE), "7", "1"], cwd=tmp_path, env=fake_gh(tmp_path), capture_output=True, text=True, timeout=30)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "conflicts with main" in done.stdout


def test_commit_push_refuses_a_branch_behind_origin_main_and_stages_nothing(tmp_path):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", "-q", str(origin), str(seed)], check=True, capture_output=True)
    git(seed, "commit", "-q", "--allow-empty", "-m", "first")
    git(seed, "push", "-q", "origin", "HEAD:main")
    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True, capture_output=True)
    git(work, "checkout", "-q", "-b", "claude/topic")
    git(seed, "commit", "-q", "--allow-empty", "-m", "main moves on")
    git(seed, "push", "-q", "origin", "HEAD:main")
    (work / "notes.txt").write_text("a change")
    message = tmp_path / "msg.txt"
    message.write_text("message")
    done = subprocess.run(["bash", str(COMMIT), str(message)], cwd=work, env=fake_gh(tmp_path), capture_output=True, text=True, timeout=60)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "behind origin/main" in done.stderr
    staged = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=work, capture_output=True, text=True).stdout
    assert staged == ""
