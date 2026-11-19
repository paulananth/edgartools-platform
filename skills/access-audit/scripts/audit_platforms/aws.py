"""AWS: root and IAM identities, keys, policies, trail, public-access block and budgets, read through the aws CLI."""
from __future__ import annotations

import base64
import csv
import io
import json
import subprocess
import sys
from datetime import datetime, timezone

from .base import control

NAME = "aws"
MAX_KEY_DAYS = 90


def configured(env) -> bool:
    return bool(env.get("AUDIT_AWS_PROFILE") or env.get("AWS_PROFILE") or env.get("AWS_ACCESS_KEY_ID"))


def aws(env, *args: str, soft: bool = False):
    command = ["aws", *args, "--output", "json"] + (["--profile", env["AUDIT_AWS_PROFILE"]] if env.get("AUDIT_AWS_PROFILE") else [])
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    if done.returncode:  # its message can quote the account
        if soft:
            return None
        sys.exit("an AWS read failed (check AUDIT_AWS_PROFILE and its read-only policy)")
    return json.loads(done.stdout or "null")


def collect(env, as_admin: bool = False) -> dict:
    who = aws(env, "sts", "get-caller-identity")
    arn, account = who["Arn"], who["Account"]
    kind = "root" if arn.endswith(":root") else ("role" if ":assumed-role/" in arn else "user")
    audit_named = any(w in arn.lower() for w in ("audit", "readonly", "read-only", "securityaudit"))
    if (kind == "root" or not audit_named) and not as_admin:
        sys.exit("the AWS identity is not a read-only audit identity: use one (its name says audit or readonly), or pass --as-admin to record the gap")
    summary = aws(env, "iam", "get-account-summary")["SummaryMap"]
    aws(env, "iam", "generate-credential-report", soft=True)
    report = aws(env, "iam", "get-credential-report", soft=True)
    users = list(csv.DictReader(io.StringIO(base64.b64decode(report["Content"]).decode()))) if report else []
    now = datetime.now(timezone.utc)

    def age(stamp: str) -> int:
        return (now - datetime.fromisoformat(stamp.replace("Z", "+00:00"))).days if stamp not in ("N/A", "not_supported", "") else 0

    humans = [u for u in users if u["user"] != "<root_account>"]
    admin_entities = aws(env, "iam", "list-entities-for-policy", "--policy-arn", "arn:aws:iam::aws:policy/AdministratorAccess", soft=True) or {}
    trails = aws(env, "cloudtrail", "describe-trails", soft=True) or {"trailList": []}
    logging = [t for t in trails["trailList"] if t.get("IsMultiRegionTrail") and (aws(env, "cloudtrail", "get-trail-status", "--name", t["TrailARN"], soft=True) or {}).get("IsLogging")]
    block = aws(env, "s3control", "get-public-access-block", "--account-id", account, soft=True)
    budgets = aws(env, "budgets", "describe-budgets", "--account-id", account, soft=True)
    return {
        "identity_kind": kind, "audit_named": audit_named,
        "root_mfa": summary.get("AccountMFAEnabled") == 1, "root_keys": summary.get("AccountAccessKeysPresent", 0),
        "console_users": sum(u["password_enabled"] == "true" for u in humans), "console_without_mfa": sum(u["password_enabled"] == "true" and u["mfa_active"] != "true" for u in humans),
        "keys_active": sum(u[f"access_key_{n}_active"] == "true" for u in humans for n in (1, 2)),
        "keys_old": sum(u[f"access_key_{n}_active"] == "true" and age(u[f"access_key_{n}_last_rotated"]) > MAX_KEY_DAYS for u in humans for n in (1, 2)),
        "admin_users": len(admin_entities.get("PolicyUsers", [])), "admin_roles": len(admin_entities.get("PolicyRoles", [])), "admin_visible": bool(admin_entities),
        "password_policy": bool(aws(env, "iam", "get-account-password-policy", soft=True)),
        "trail_logging": len(logging), "trails": len(trails["trailList"]),
        "public_block": None if block is None else all(block["PublicAccessBlockConfiguration"].values()),
        "budgets": None if budgets is None else len(budgets.get("Budgets", [])),
    }


def principals(ev: dict) -> list[str]:
    return []


def controls(ev: dict) -> list[dict]:
    c = lambda *a, **k: control(NAME, *a, **k)  # noqa: E731
    return [
        c("IND", ev["identity_kind"] != "root" and ev["audit_named"], {"identity_kind": ev["identity_kind"], "named_for_audit": ev["audit_named"]}, "Use a read-only audit identity (SecurityAudit policy)"),
        c("ADM", ev["root_mfa"] and ev["root_keys"] == 0, {"root_mfa": ev["root_mfa"], "root_access_keys": ev["root_keys"]}, "MFA on the root user; delete its access keys"),
        c("AUT", ev["console_without_mfa"] == 0, {"console_users": ev["console_users"], "without_mfa": ev["console_without_mfa"]}, "Enrol MFA for every console user"),
        c("LPR", ev["admin_users"] == 0 and ev["admin_visible"], {"users_with_administrator_access": ev["admin_users"], "roles_with_it": ev["admin_roles"]},
          "Attach AdministratorAccess to a role assumed with MFA, never to a user", tested=ev["admin_visible"]),
        c("NET", ev["public_block"] is True, {"account_public_access_block_complete": ev["public_block"]}, "Turn on all four account-level S3 public access blocks", tested=ev["public_block"] is not None),
        c("CST", (ev["budgets"] or 0) > 0, {"budgets": ev["budgets"]}, "Create a budget with an alert", tested=ev["budgets"] is not None),
        c("POL", ev["password_policy"], {"account_password_policy": ev["password_policy"]}, "Set the account password policy"),
        c("LOG", ev["trail_logging"] > 0, {"multi_region_trails_logging": ev["trail_logging"], "trails": ev["trails"]}, "Create a multi-region CloudTrail trail and keep it logging"),
        c("ROT", ev["keys_old"] == 0, {"active_keys": ev["keys_active"], "older_than_90_days": ev["keys_old"]}, "Rotate keys older than 90 days; prefer roles"),
    ]
