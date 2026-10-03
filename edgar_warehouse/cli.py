"""CLI surface: Rules, Bookkeeping, Change Journal and Clean MDM.

The legacy warehouse commands and their code are deleted (platform
validation slice 2a). Configure a source or feed through Rules and submit
work through Bookkeeping.
"""

from __future__ import annotations

import argparse
import sys


def _handle_resolve_snowflake_env(args: argparse.Namespace) -> int:
    """Print `export KEY=VALUE` shell lines for a Snowflake connection.

    Reuses SnowflakeConnectionSettings.from_env() instead of a second,
    independent password-parsing implementation.

    The resolved password DOES appear in this command's stdout -- there is no
    other way to hand a secret across a process boundary to a caller's shell.
    What keeps it off a human's screen is refusing to write that stdout to an
    interactive terminal at all: the intended usage is
    `eval "$(edgar-warehouse resolve-snowflake-env ...)"` or
    `source <(edgar-warehouse resolve-snowflake-env ...)`, where stdout is a
    pipe, not a tty. A bare interactive invocation is refused below.
    """
    import os
    import shlex
    import sys

    from edgar_warehouse.snowflake_settings import SnowflakeConnectionSettings

    if sys.stdout.isatty():
        print(
            "error: refusing to print resolved Snowflake credentials to an interactive "
            "terminal. Run this via `eval \"$(edgar-warehouse resolve-snowflake-env "
            "--connection <name>)\"` (or `source <(...)`) so the output is consumed by "
            "the shell, not displayed on screen.",
            file=sys.stderr,
        )
        return 2

    previous_connection = os.environ.get("SNOWFLAKE_CONNECTION")
    if args.connection:
        os.environ["SNOWFLAKE_CONNECTION"] = args.connection

    try:
        settings = SnowflakeConnectionSettings.from_env()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        # Resolution only needs SNOWFLAKE_CONNECTION for the instant of the
        # from_env() call above -- restore it so this command never leaves a
        # process-wide env mutation behind for whatever runs next.
        if args.connection:
            if previous_connection is None:
                os.environ.pop("SNOWFLAKE_CONNECTION", None)
            else:
                os.environ["SNOWFLAKE_CONNECTION"] = previous_connection

    lines = [
        f"export DBT_SNOWFLAKE_ACCOUNT={shlex.quote(settings.account)}",
        f"export DBT_SNOWFLAKE_USER={shlex.quote(settings.user)}",
        f"export DBT_SNOWFLAKE_PASSWORD={shlex.quote(settings.password)}",
        f"export DBT_SNOWFLAKE_DATABASE={shlex.quote(settings.database)}",
        f"export DBT_SNOWFLAKE_WAREHOUSE={shlex.quote(settings.warehouse)}",
        f"export TF_VAR_snowflake_password={shlex.quote(settings.password)}",
    ]
    if settings.role:
        lines.append(f"export DBT_SNOWFLAKE_ROLE={shlex.quote(settings.role)}")

    print("\n".join(lines))
    connection_label = args.connection or previous_connection or "(default)"
    print(f"resolved Snowflake credentials for connection '{connection_label}'", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="edgar-warehouse",
        description="Configured Rules, Bookkeeping, Change Journal, and MDM operations.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    resolve_snowflake_env = subparsers.add_parser(
        "resolve-snowflake-env",
        help="Resolve Snowflake connection settings for a named connection and print "
             "'export KEY=VALUE' shell lines (DBT_SNOWFLAKE_*, TF_VAR_snowflake_password). "
             "Resolves individual MDM_SNOWFLAKE_*/DBT_SNOWFLAKE_* env vars first, then the "
             "MDM_SNOWFLAKE_SECRET_JSON/DBT_SNOWFLAKE_SECRET_JSON blob, then SnowCLI's "
             "~/.snowflake/connections.toml. Output is shell code meant for eval \"$(...)\" -- "
             "never print it directly to a terminal a human will read.",
    )
    resolve_snowflake_env.add_argument(
        "--connection",
        help="SnowCLI connection name to resolve (sets SNOWFLAKE_CONNECTION for this process "
             "only). Defaults to the SNOWFLAKE_CONNECTION env var, then config.toml's "
             "default_connection_name, then 'snowconn'.",
    )
    resolve_snowflake_env.set_defaults(handler=_handle_resolve_snowflake_env)

    from edgar_warehouse.bookkeeping.clean.cli import register as register_bookkeeping
    from edgar_warehouse.application.journal_recovery import register as register_journal
    from edgar_warehouse.mdm.cli import register_mdm_subparser
    from edgar_warehouse.rules.cli import register as register_rules

    register_mdm_subparser(subparsers)
    register_bookkeeping(subparsers)
    register_rules(subparsers)
    register_journal(subparsers)
    from edgar_warehouse.bundle import register as register_bundle

    register_bundle(subparsers, parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["bookkeeping"]:
        # Control starts alone: building the full parser would import MDM and
        # the other domains, which Bookkeeping must never load (to-do 20a).
        from edgar_warehouse.bookkeeping.clean.cli import main as bookkeeping
        return bookkeeping(argv[1:])
    else:
        args = build_parser().parse_args(argv)
    return args.handler(args)
