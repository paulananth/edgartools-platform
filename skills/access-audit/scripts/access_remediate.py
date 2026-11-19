#!/usr/bin/env python3
"""Close access findings as code: bootstrap the access-admin identity, plan, apply with a recorded approval, then re-audit.

Usage: access_remediate.py bootstrap | plan | apply --words "<the operator's words>" [--allow-destroy]

The Terraform root is infra/terraform/access/snowflake/accounts/prod. It runs as a dedicated key-pair service identity
(ACCESS_ADMIN_USER, ACCESS_ADMIN_ROLE, ACCESS_ADMIN_PRIVATE_KEY_FILE, SNOWFLAKE_ORGANIZATION, SNOWFLAKE_ACCOUNT_NAME), never as a
person's account. A plan that would touch the operator's own administrator account, or destroy anything, is refused.
`bootstrap` prints the one-time SQL that creates that identity (its public key only) for an administrator to run once.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROTECTED_USERS = {"ANANP11"}
ROOT = Path("infra/terraform/access/snowflake/accounts/prod")
ADMIN_ROLE = "EDGARTOOLS_PROD_ACCESS_ADMIN"
KEY = Path.home() / ".snowflake" / "keys" / "edgartools_access_admin.p8"


def bootstrap_sql(public_key: str) -> str:
    """The least privilege the Terraform root needs: create roles and users, grant them, attach policies. Not ACCOUNTADMIN."""
    return f"""-- One-time setup of the access-admin identity. Run once, as an administrator, by whoever owns the account.
create role if not exists {ADMIN_ROLE} comment = 'Applies the access controls in Terraform; not an administrator';
grant create role, create user, create database, manage grants, apply password policy, apply authentication policy on account to role {ADMIN_ROLE};
grant usage on warehouse COMPUTE_WH to role {ADMIN_ROLE};
create user if not exists {ADMIN_ROLE} type = service default_role = {ADMIN_ROLE} default_warehouse = COMPUTE_WH rsa_public_key = '{public_key}'
  statement_timeout_in_seconds = 900 comment = 'Terraform access controls';
grant role {ADMIN_ROLE} to user {ADMIN_ROLE};
"""


def summarize(plan: dict, allow_destroy: bool = False) -> dict:
    changes = plan.get("resource_changes", [])
    counts = {"create": 0, "update": 0, "delete": 0}
    for change in changes:
        actions = change["change"]["actions"]
        counts["create"] += "create" in actions
        counts["update"] += "update" in actions
        counts["delete"] += "delete" in actions
    touched = [c["address"] for c in changes if c["change"]["actions"] != ["no-op"]
               and any(user in json.dumps(c["change"], default=str).upper() for user in PROTECTED_USERS)]
    if touched:
        sys.exit(f"the plan touches the operator's own administrator account ({len(touched)} resources): refused")
    if counts["delete"] and not allow_destroy:
        sys.exit(f"the plan would destroy {counts['delete']} resources: refused without --allow-destroy and the operator's words")
    return counts


def terraform(*args: str, env=None) -> subprocess.CompletedProcess:
    return subprocess.run(["terraform", f"-chdir={ROOT}", *args], capture_output=True, text=True, env=env, check=False)


def tf_env() -> dict:
    env = dict(os.environ)
    for source, target in (("SNOWFLAKE_ORGANIZATION", "TF_VAR_organization_name"), ("SNOWFLAKE_ACCOUNT_NAME", "TF_VAR_account_name"),
                           ("ACCESS_ADMIN_USER", "TF_VAR_access_admin_user"), ("ACCESS_ADMIN_ROLE", "TF_VAR_access_admin_role"),
                           ("ACCESS_ADMIN_PRIVATE_KEY_FILE", "TF_VAR_access_admin_private_key_file")):
        if not env.get(source):
            sys.exit(f"{source} is not set: run `bootstrap`, then export the access-admin identity")
        env[target] = env[source]
    if env["ACCESS_ADMIN_USER"].upper() in PROTECTED_USERS:
        sys.exit("the operator's overall administrator account is never the access admin")
    return env


def record(path: Path, words: str, counts: dict) -> None:
    stamp = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M ET")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps({"at": stamp, "words": words, "plan": counts}) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["bootstrap", "plan", "apply"])
    parser.add_argument("--words", help="apply: the operator's exact words approving this plan")
    parser.add_argument("--allow-destroy", action="store_true")
    parser.add_argument("--approvals", default=".scratch/access-audit/approvals.jsonl")
    args = parser.parse_args(argv)
    if args.command == "bootstrap":
        if not KEY.exists():
            KEY.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(f"openssl genrsa 2048 2>/dev/null | openssl pkcs8 -topk8 -nocrypt -inform PEM -out {KEY}", shell=True, check=True)
            KEY.chmod(0o600)
        pub = subprocess.run(["openssl", "rsa", "-in", str(KEY), "-pubout"], capture_output=True, text=True, check=True).stdout
        print(bootstrap_sql("".join(line for line in pub.splitlines() if "-----" not in line)))
        return 0
    env = tf_env()
    for step in (["init", "-input=false", "-reconfigure"] if os.environ.get("TF_BACKEND_CONFIG") is None else ["init", "-input=false", "-backend-config=" + os.environ["TF_BACKEND_CONFIG"]], ["plan", "-input=false", "-out=access.plan"]):
        done = terraform(*step, env=env)
        if done.returncode:
            sys.exit(f"terraform {step[0]} failed (its output can name the account, so it is not shown)")
    counts = summarize(json.loads(terraform("show", "-json", "access.plan", env=env).stdout), args.allow_destroy)
    print(f"plan: {counts['create']} to create, {counts['update']} to update, {counts['delete']} to destroy")
    if args.command == "apply":
        if not args.words:
            sys.exit("apply needs --words: the operator's exact words approving this plan")
        record(Path(args.approvals), args.words, counts)
        if terraform("apply", "-input=false", "access.plan", env=env).returncode:
            sys.exit("terraform apply failed (its output can name the account, so it is not shown)")
        print("applied; run access_audit.py to re-audit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
