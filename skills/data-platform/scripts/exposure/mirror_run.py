"""Run one statement as the mirror operator and print its rows as JSON: `python mirror_sql.py verify | python mirror_run.py`.

It connects as the readiness gate does (the mirror operator's key pair, `~/.config/edgartools/mirror-operator/`), and prints
nothing of the login. A refusal exits 1 with Snowflake's error number only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "data-operations" / "scripts"))
import readiness  # noqa: E402


def main() -> int:
    statement = sys.stdin.read().strip()
    if not statement:
        print("no statement on standard input", file=sys.stderr)
        return 2
    try:
        rows = readiness.run_as_mirror_operator(statement)
    except readiness.SnowflakeRefused as refused:
        print(f"Snowflake error {refused}", file=sys.stderr)
        return 1
    json.dump(rows, sys.stdout, default=str, indent=1)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
