"""After a load, the mirror applies its pending changes now, not at its next interval: `python mirror_refresh.py`.

It runs as the mirror operator (`mirror_run.py`'s login), calls REFRESH_MIRROR on the mirror the record names, and waits until
LIST_MIRRORS shows that mirror's last apply time set again and moved (the refresh clears it, the apply sets it), so Gold reads the
load once it returns 0. Exit 1: refused, or not applied
within the minutes given; the mirror then applies the load at its interval.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "data-operations" / "scripts"))
import mirror_sql  # noqa: E402
import readiness  # noqa: E402


def last_apply(rows: list[dict], mirror: str):
    return next((row["LAST_APPLY_TIME"] for row in rows if row["MIRROR_NAME"] == mirror), None)


def refresh(mirror: str, run, wait, minutes: int, every: int):
    """The mirror's new last apply time once the refresh has applied, or None when it has not within `minutes`."""
    listing = mirror_sql.lifecycle({"mirror": mirror}, "status")
    before = last_apply(run(listing), mirror)
    run(mirror_sql.lifecycle({"mirror": mirror}, "refresh"))
    for _ in range(minutes * 60 // every):
        wait(every)
        after = last_apply(run(listing), mirror)
        if after is not None and after != before:
            return after
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--managed", type=Path, default=mirror_sql.MANAGED, help="the managed mirror record")
    parser.add_argument("--minutes", type=int, default=15, help="how long to wait for the apply")
    args = parser.parse_args(argv)
    mirror = mirror_sql.load(args.managed)["mirror"]
    try:
        applied = refresh(mirror, readiness.run_as_mirror_operator, time.sleep, args.minutes, every=15)
    except readiness.SnowflakeRefused as refused:
        print(f"mirror: not refreshed: Snowflake error {refused}", file=sys.stderr)
        return 1
    if applied is None:
        print(f"mirror: refresh dispatched, no apply within {args.minutes} minutes (a mirror with nothing pending applies nothing): "
              "it applies at its interval", file=sys.stderr)
        return 1
    print(f"mirror: applied at {applied} (Snowflake's session time): Gold reads the load")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
