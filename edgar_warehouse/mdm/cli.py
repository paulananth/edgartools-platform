"""CLI subcommand: `edgar-warehouse mdm ...`, Clean MDM only.

Five commands: migrate, check-connectivity, counts, prepare-clean-company and
name-census. The legacy MDM commands and their tables are deleted (platform
validation slice 2a).
"""
from __future__ import annotations

import argparse
import json
import time
from typing import Callable

from edgar_warehouse.mdm.observability import elapsed_ms, emit_mdm_event


def register_mdm_subparser(subparsers: argparse._SubParsersAction) -> None:
    mdm = subparsers.add_parser("mdm", help="Clean MDM: migration, connectivity, counts, and preparation")
    mdm_sub = mdm.add_subparsers(dest="mdm_command", required=True)

    migrate = mdm_sub.add_parser("migrate", help="Create or upgrade the Clean MDM schema")
    migrate.add_argument("--application-role", default="application")
    migrate.set_defaults(handler=_logged_handler("migrate", _handle_migrate))

    prepare = mdm_sub.add_parser("prepare-clean-company", help="Pin a bounded local Company landing snapshot without writing master state")
    prepare.add_argument("--landing-root", required=True)
    prepare.add_argument("--landing-manifest", required=True)
    prepare.add_argument("--ticker-manifest", required=True, help="Landing manifest of the SEC ticker catalog run (sec_company_ticker)")
    prepare.add_argument("--name-census", required=True, help="Name Census file that counted this capture (mdm name-census)")
    prepare.add_argument("--output", required=True)
    prepare.add_argument("--as-of", required=True)
    prepare.add_argument("--revision", type=int, required=True)
    prepare.add_argument("--limit", type=int, default=100)
    prepare.add_argument("--bronze-receipts", help="Bronze receipts of this same capture run: each record names its bronze object")
    prepare.set_defaults(handler=_logged_handler("prepare-clean-company", _clean("prepare_clean_company")))

    census = mdm_sub.add_parser("name-census", help="Count SEC captures and one configured full GLEIF Golden Copy "
                                "reading into a Name Census file")
    census.add_argument("--landing-root", required=True)
    census.add_argument("--landing-manifest", dest="landing_manifests", required=True, action="append",
                        help="Landing manifest of an SEC capture (sec_company, sec_company_former_name); repeat it "
                             "for each capture of the population, which together must be every SEC filer")
    census.add_argument("--gleif-reading", required=True,
                        help="The verified source.read output of rules/sources/gleif/census-complete-stream.yaml "
                             "over a full Golden Copy (its reading.json)")
    census.add_argument("--gleif-reading-sha256", required=True)
    census.add_argument("--gleif-metadata", required=True, help="JSON file: the archive's verified publication metadata")
    census.add_argument("--output", required=True)
    census.set_defaults(handler=_logged_handler("name-census", _clean("name_census")))

    counts = mdm_sub.add_parser("counts", help="Print Clean MDM entity and record counts")
    counts.set_defaults(handler=_logged_handler("counts", _clean("counts")))

    check = mdm_sub.add_parser("check-connectivity", help="Check the Clean MDM database connection and schema")
    check.set_defaults(handler=_logged_handler("check-connectivity", _clean("check_connectivity")))


def _handle_migrate(args: argparse.Namespace) -> int:
    from edgar_warehouse.mdm.clean.cli import engine_from_env
    from edgar_warehouse.mdm.clean.store import migrate

    engine = engine_from_env("MDM_DATABASE_URL", restricted=False)
    try:
        payload = migrate(engine, application_role=args.application_role)
    finally:
        engine.dispose()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _clean(name: str) -> Callable[[argparse.Namespace], int]:
    """The Clean MDM command function, imported when the command runs."""
    def run(args: argparse.Namespace) -> int:
        from edgar_warehouse.mdm.clean import cli

        return getattr(cli, name)(args)

    return run


def _logged_handler(command_name: str, handler: Callable[[argparse.Namespace], int]) -> Callable[[argparse.Namespace], int]:
    def _wrapped(args: argparse.Namespace) -> int:
        started_at = time.monotonic()
        emit_mdm_event("mdm_command_started", command=command_name, arguments=_safe_arguments(args))
        try:
            exit_code = handler(args)
        except Exception as exc:
            emit_mdm_event(
                "mdm_command_failed",
                command=command_name,
                duration_ms=elapsed_ms(started_at),
                error=exc.__class__.__name__,
            )
            raise
        emit_mdm_event(
            "mdm_command_completed",
            command=command_name,
            duration_ms=elapsed_ms(started_at),
            exit_code=exit_code,
        )
        return exit_code

    return _wrapped


def _safe_arguments(args: argparse.Namespace) -> dict[str, object]:
    safe: dict[str, object] = {}
    blocked_fragments = ("password", "secret", "token", "key")
    for name, value in vars(args).items():
        if name == "handler" or any(fragment in name.lower() for fragment in blocked_fragments):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[name] = value
        elif isinstance(value, (list, tuple)):
            safe[name] = [str(item) for item in value]
        else:
            safe[name] = str(value)
    return safe
