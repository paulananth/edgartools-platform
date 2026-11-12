"""The worker's command line, shared by `python -m edgar_warehouse.workers`
and `edgar-warehouse workers` (mastering to-do 21)."""
from __future__ import annotations

import argparse
import json

ROLES = ("work", "describe")


def arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """The worker's arguments, shared by `python -m edgar_warehouse.workers`
    and `edgar-warehouse workers`."""
    parser.add_argument("role", choices=ROLES)
    parser.add_argument("profile")
    parser.add_argument("run_id", nargs="?")
    parser.add_argument("--reports", help="Where the worker writes its check reports")
    parser.add_argument("--limit", type=int, default=10)
    parser.set_defaults(handler=lambda args: run(args, parser))
    return parser


def run(args, parser) -> int:
    from . import profile as load_profile
    from .__main__ import runtime, work

    if args.role == "describe":
        print(json.dumps({"profile": args.profile, "runtime": runtime(load_profile(args.profile))}))
        return 0
    if not args.reports:
        parser.error("work needs --reports")
    return work(args.profile, args.run_id, args.reports, args.limit)
