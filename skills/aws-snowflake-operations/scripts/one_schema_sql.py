"""Print the SQL that leaves each platform database with its one schema (`rules/snowflake.yaml`). Connects to nothing.

    python one_schema_sql.py --names rules/snowflake.yaml --network-policy <policy> --rule <database.schema.rule> --allow <cidr> ... \
        --password-policy <database.schema.policy> --authentication-policy <database.schema.policy> --user <service user> ... --auditor-role <role> --drop-schema <database.schema> ... > one_schema.sql

The hosted Postgres ingress rule moves into the operations database's schema: the network policy names the old and the new rule,
then the new one only, so no connection drops. The credential policies are detached from the account and every named user, then
dropped: a service user (TYPE = SERVICE) cannot sign in with a password, so none is kept. Then each named schema is dropped, and
each platform database's PUBLIC schema, so each holds only the schema rules/snowflake.yaml names. The new rule allows the ranges
--allow names: copy them from the old rule (`DESCRIBE NETWORK RULE`), and the policy's rule list from `DESCRIBE NETWORK POLICY`, since
the list is set whole; the output prints both before it changes anything. Run it as an administrator, with the operator's approval.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

CIDR = re.compile(r"^(\d{1,3}\.){3}\d{1,3}/\d{1,2}$")
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*(\.[A-Za-z_][A-Za-z0-9_$]*)*$")


def name(value: str, parts: int | None = None) -> str:
    if not IDENTIFIER.match(value) or (parts and value.count(".") + 1 != parts):
        raise SystemExit(f"not a plain {parts or ''}-part name: {value}")
    return value.upper()


def statements(names: dict, network_policy: str, rule: str, allow: list[str], policies: dict[str, list[str]], users: list[str],
               drop: list[str], auditor: str) -> str:
    places = {part: (name(block["database"], 1), name(block["schema"], 1)) for part, block in names.items()
              if isinstance(block, dict) and "schema" in block}
    database, schema = places["operations"]
    old, new = name(rule, 3), f"{database}.{schema}.{name(rule, 3).split('.')[-1]}"
    if old == new:
        raise SystemExit(f"the rule is already in {database}.{schema}: nothing to move, and its drop would cut the store off")
    ranges = [r for r in allow if CIDR.match(r)]
    if not allow or len(ranges) != len(allow):
        raise SystemExit("name the old rule's ranges with --allow, each an IPv4 CIDR such as 10.0.0.0/8")
    kept = {f"{d}.{s}" for d, s in places.values()}
    dropped = [name(s, 2) for s in drop]
    refused = [s for s in dropped if s in kept or s == f"{database}.{schema}" or s.split(".")[0] not in {d for d, _ in places.values()}]
    if refused:
        raise SystemExit(f"a schema rules/snowflake.yaml keeps, or one outside its databases, is never dropped: {', '.join(refused)}")
    if old.rsplit(".", 1)[0] not in dropped:
        raise SystemExit(f"the rule moves out of {old.rsplit('.', 1)[0]}: name that schema with --drop-schema")
    lines = [f"DESCRIBE NETWORK RULE {old};",
             f"DESCRIBE NETWORK POLICY {name(network_policy, 1)};",
             f"CREATE DATABASE IF NOT EXISTS {database};",
             f"CREATE SCHEMA IF NOT EXISTS {database}.{schema};",
             f"CREATE NETWORK RULE IF NOT EXISTS {new} TYPE = IPV4 MODE = POSTGRES_INGRESS VALUE_LIST = ({', '.join(repr(r) for r in ranges)})"
             " COMMENT = 'Permissive ingress rule for MDM Snowflake Postgres: protection relies on credentials and sslmode=require';",
             f"ALTER NETWORK POLICY {name(network_policy, 1)} SET ALLOWED_NETWORK_RULE_LIST = ('{old}', '{new}');",
             f"ALTER NETWORK POLICY {name(network_policy, 1)} SET ALLOWED_NETWORK_RULE_LIST = ('{new}');",
             f"DESCRIBE NETWORK POLICY {name(network_policy, 1)};",
             f"DROP NETWORK RULE IF EXISTS {old};"]
    kinds = ("PASSWORD", "AUTHENTICATION")
    lines += [f"ALTER ACCOUNT UNSET {kind} POLICY;" for kind in kinds]
    lines += [f"ALTER USER IF EXISTS {name(user, 1)} UNSET {kind} POLICY;" for user in users for kind in kinds]
    lines += [f"DROP {kind} POLICY IF EXISTS {name(policy, 3)};" for kind in kinds for policy in policies.get(kind, [])]
    lines += [f"DROP SCHEMA IF EXISTS {s};" for s in dropped]
    lines += [f"DROP SCHEMA IF EXISTS {d}.PUBLIC;" for d in sorted({d for d, _ in places.values()})]
    lines += [f"GRANT USAGE ON DATABASE {database} TO ROLE {name(auditor, 1)};",
              f"GRANT USAGE ON ALL SCHEMAS IN DATABASE {database} TO ROLE {name(auditor, 1)};",
              f"GRANT USAGE ON FUTURE SCHEMAS IN DATABASE {database} TO ROLE {name(auditor, 1)};",
              f"GRANT OWNERSHIP ON DATABASE {database} TO ROLE {name(names['owner'], 1)} COPY CURRENT GRANTS;"]
    lines += [f"SHOW SCHEMAS IN DATABASE {d};" for d in sorted({d for d, _ in places.values()})]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> str:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--names", required=True, type=Path)
    parser.add_argument("--network-policy", required=True, help="the network policy the Postgres instance uses")
    parser.add_argument("--rule", required=True, help="the ingress rule where it is now, database.schema.rule")
    parser.add_argument("--allow", action="append", default=[], help="a range the old rule allows, as an IPv4 CIDR")
    parser.add_argument("--password-policy", action="append", default=[], help="a password policy to drop, database.schema.policy")
    parser.add_argument("--authentication-policy", action="append", default=[], help="an authentication policy to drop, database.schema.policy")
    parser.add_argument("--user", action="append", default=[], help="a user a credential policy is attached to")
    parser.add_argument("--auditor-role", required=True, help="the audit role, which reads the operations database's schemas")
    parser.add_argument("--drop-schema", action="append", default=[], help="a schema to drop, database.schema")
    args = parser.parse_args(argv)
    names = yaml.safe_load(args.names.read_text(encoding="utf-8"))
    policies = {"PASSWORD": args.password_policy, "AUTHENTICATION": args.authentication_policy}
    return statements(names, args.network_policy, args.rule, args.allow, policies, args.user, args.drop_schema, args.auditor_role)


if __name__ == "__main__":
    import sys

    sys.stdout.write(main())
