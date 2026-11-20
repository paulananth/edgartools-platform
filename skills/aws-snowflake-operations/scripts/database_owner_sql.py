"""Print the SQL that makes the platform's owner role own databases (the skill's "Database ownership" rule). Connects to nothing.

    python database_owner_sql.py --names <names file> --database <database> [--database <database> ...] > owner.sql

The owner role comes from the `owner` key of the names file; a database is named by the caller (the `gold.database` key
or any other). Run the output as an administrator, with the operator's approval. Each statement is safe to repeat.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def statements(owner: str, databases: list[str], administrator_role: str) -> str:
    lines = [f"CREATE ROLE IF NOT EXISTS {owner};", f"GRANT ROLE {owner} TO ROLE {administrator_role};"]
    lines += [f"GRANT OWNERSHIP ON DATABASE {name} TO ROLE {owner} COPY CURRENT GRANTS;" for name in databases]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> str:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--names", required=True, type=Path)
    parser.add_argument("--database", action="append", required=True)
    parser.add_argument("--administrator-role", required=True, help="the role that keeps control of the owner role")
    args = parser.parse_args(argv)
    owner = yaml.safe_load(args.names.read_text(encoding="utf-8"))["owner"]
    return statements(owner, args.database, args.administrator_role)


if __name__ == "__main__":
    import sys

    sys.stdout.write(main())
