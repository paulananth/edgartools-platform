"""merge_on_green.sh merges and leaves the worktree and branch alone (operator, 2026-11-03)."""

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/dev/merge_on_green.sh"

# A gh that says the PR is open, its CI passed, and the merge worked.
FAKE_GH = """#!/usr/bin/env bash
case "$*" in
  "pr view 7 --json state"*) echo OPEN ;;
  "pr view 7 --json headRefOid"*) echo 0123456789abcdef ;;
  "pr view 7 --json mergeStateStatus"*) echo CLEAN ;;
  "pr view 7 --json headRefName"*) echo claude/topic ;;
  "run list"*) printf 'unit\\tcompleted\\tsuccess\\n' ;;
  "pr merge"*) ;;
  *) echo "unexpected gh $*" >&2; exit 9 ;;
esac
"""


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def run_script(tmp_path, branch, dirty=False):
    main = tmp_path / "main"
    main.mkdir()
    git(main, "init", "-q", "-b", "main")
    git(main, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x")
    work = tmp_path / "work"
    git(main, "worktree", "add", "-q", str(work), "-b", branch)
    if dirty:
        (work / "unsaved.txt").write_text("not committed")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "MERGE_POLL_SECONDS": "0"}
    done = subprocess.run(["bash", str(SCRIPT), "7", "1"], cwd=work, env=env, capture_output=True, text=True)
    branches = subprocess.run(["git", "branch", "--list", branch], cwd=main, capture_output=True, text=True).stdout
    return done, work, branches


def test_the_merged_prs_worktree_and_branch_are_kept(tmp_path):
    done, work, branches = run_script(tmp_path, "claude/topic")
    assert done.returncode == 0, done.stderr
    assert "merged" in done.stdout
    assert work.exists()
    assert "claude/topic" in branches


def test_a_worktree_with_unsaved_files_is_kept(tmp_path):
    done, work, branches = run_script(tmp_path, "claude/topic", dirty=True)
    assert done.returncode == 0, done.stderr
    assert (work / "unsaved.txt").exists()
