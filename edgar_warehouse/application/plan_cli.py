"""`edgar-warehouse plan`: read-only feed planning and source-onboarding routing.

`resolve-feed` names one feed's Rules digest and targets; `workflow` plans a
frozen worklist; `route` selects one onboarding owner and action from
normalized configuration and retained evidence.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _resolve_feed(args) -> int:
    from edgar_warehouse.bookkeeping.clean.feeds import resolve_feed

    try:
        result = resolve_feed(Path(args.rules_root), args.source, args.feed)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


def _plan_workflow(args) -> int:
    from edgar_warehouse.application.journal_evidence import plan
    from edgar_warehouse.bookkeeping.clean.config import canonical

    value = plan(source=args.source, feed=args.feed, target=args.target,
                 inputs={"uri": args.input_manifest, "sha256": args.input_sha256},
                 rules_root=Path(args.rules_root))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical(value) + "\n")
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0

def _route(args) -> int:
    from edgar_warehouse.application.source_route import route_next_action

    try:
        if args.request == "-":
            request = json.load(sys.stdin)
        else:
            with Path(args.request).open(encoding="utf-8") as stream:
                request = json.load(stream)
        if not isinstance(request, dict):
            raise ValueError("route request must be a JSON object")
        result = route_next_action(request)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


def register(subparsers) -> None:
    from edgar_warehouse.rules import files

    planning = subparsers.add_parser(
        "plan", help="Read-only planning: resolve a feed, plan work, or route onboarding"
    )
    steps = planning.add_subparsers(dest="plan_command", required=True)
    feed = steps.add_parser("resolve-feed", help="The Rules digest, datasets and targets of one source's feed")
    workflow = steps.add_parser("workflow", help="Plan one feed's frozen worklist from an input manifest; writes nothing else")
    for command in (feed, workflow):
        command.add_argument("--source", required=True)
        command.add_argument("--feed", required=True)
        command.add_argument("--rules-root", default=str(files.ROOT))
    feed.set_defaults(handler=_resolve_feed)
    workflow.add_argument("--target", required=True)
    workflow.add_argument("--input-manifest", required=True)
    workflow.add_argument("--input-sha256", required=True)
    workflow.add_argument("--output", required=True)
    workflow.set_defaults(handler=_plan_workflow)

    route = steps.add_parser(
        "route",
        help="Choose the next source-onboarding owner and action from supplied evidence",
    )
    route.add_argument("--request", required=True, help="JSON request file, or - for stdin")
    route.set_defaults(handler=_route)


