"""GitHub: the repository's branch protection, review requirement and secret scanning, read through the gh CLI."""
from __future__ import annotations

import json
import subprocess
import sys

from .base import control

NAME = "github"


def configured(env) -> bool:
    return bool(env.get("AUDIT_GITHUB_REPO"))


def gh(*args: str):
    done = subprocess.run(["gh", "api", *args], capture_output=True, text=True, check=False)
    return None if done.returncode else json.loads(done.stdout or "null")


def collect(env, as_admin: bool = False) -> dict:
    repo = env["AUDIT_GITHUB_REPO"]
    info = gh(f"repos/{repo}")
    if info is None:
        sys.exit("the GitHub read failed (check AUDIT_GITHUB_REPO and gh auth)")
    branch = info["default_branch"]
    protection = gh(f"repos/{repo}/branches/{branch}/protection")
    reviews = (protection or {}).get("required_pull_request_reviews")
    return {
        "protected": protection is not None, "reviews_required": (reviews or {}).get("required_approving_review_count", 0),
        "status_checks": len((protection or {}).get("required_status_checks", {}).get("contexts", [])) if protection else 0,
        "secret_scanning": (info.get("security_and_analysis") or {}).get("secret_scanning", {}).get("status") == "enabled",
        "visibility": info.get("visibility"), "admin_permission": bool((info.get("permissions") or {}).get("admin")),
    }


def principals(ev: dict) -> list[str]:
    return []


def controls(ev: dict) -> list[dict]:
    c = lambda *a, **k: control(NAME, *a, **k)  # noqa: E731
    return [
        c("CHG", ev["protected"] and ev["reviews_required"] >= 1, {"default_branch_protected": ev["protected"], "required_reviews": ev["reviews_required"], "required_status_checks": ev["status_checks"]},
          "Protect the default branch: a pull request, a review and the CI checks before a merge (or record the accepted exception)",
          title="The default branch needs a pull request and a review before a change merges"),
        c("SCR", ev["secret_scanning"], {"secret_scanning": ev["secret_scanning"], "visibility": ev["visibility"]}, "Turn on secret scanning and push protection", title="Secret scanning is on for the repository"),
        c("IND", not ev["admin_permission"], {"audit_identity_is_repo_admin": ev["admin_permission"]}, "Audit with a read-only token", title="The audit identity cannot administer the repository"),
    ]
