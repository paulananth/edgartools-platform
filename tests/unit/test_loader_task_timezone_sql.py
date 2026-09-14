"""Regression test for duckdb-retirement-cutover Ticket 22.

Both Snowflake loaders copy Parquet files with ``COPY INTO ... MATCH_BY_COLUMN_NAME``
through file formats whose ``USE_LOGICAL_TYPE`` is false. Under that setting Snowflake
reads a Parquet UTC timestamp as a zone-less clock time and labels it with the session
``TIMEZONE``, which defaults to ``America/Los_Angeles``: every landed ``TIMESTAMP_TZ``
was 7-8 hours late. Proven live 2026-09-14 with a one-row file: the same load stores the
right instant when the session ``TIMEZONE`` is ``UTC``.

The fix pins ``TIMEZONE = 'UTC'`` on each loading task (an owner's-rights procedure uses
its caller's session ``TIMEZONE``). ``SNOWFLAKE_RUN_MANIFEST_TASK`` has three definitions
(Terraform, ``deploy-snowflake-stack.sh`` and ``04_refresh_wrapper.sql``), and whichever
runs last replaces the task, so every definition must carry the pin or a redeploy brings
the bug back.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = REPO_ROOT / "infra" / "snowflake" / "sql" / "bootstrap"
NATIVE_PULL_TF = REPO_ROOT / "infra" / "terraform" / "snowflake" / "modules" / "native_pull" / "main.tf"
DEPLOY_SCRIPT = REPO_ROOT / "infra" / "scripts" / "deploy-snowflake-stack.sh"


def _task_definition(text: str, start_pattern: str) -> str:
    """The task definition from start_pattern through the end of its body.

    A SQL task ends at the line holding its ``CALL ...;`` body, not at the first
    semicolon: a COMMENT string may contain one (13_silver_landing_ingest.sql's
    does). A Terraform resource ends at its closing brace in column 0.
    """
    match = re.search(start_pattern, text)
    assert match, f"definition not found: {start_pattern!r}"
    rest = text[match.start() :]
    if rest.startswith("resource "):
        end = re.search(r"^}", rest, re.MULTILINE)
    else:
        end = re.search(r"\bCALL\b[^\n]*;", rest)
    assert end, f"unterminated definition: {start_pattern!r}"
    return rest[: end.end()]


def _pins_utc_before_body(definition: str, utc_literal: str) -> bool:
    """TIMEZONE = <utc_literal> appears in the clause list, before ``AS``."""
    body = re.search(r"^\s*AS\s*$", definition, re.MULTILINE)
    clauses = definition[: body.start()] if body else definition
    pin = rf"\bTIMEZONE\s*=\s*{re.escape(utc_literal)}"
    return re.search(pin, clauses, re.IGNORECASE) is not None


def test_silver_landing_task_is_created_with_utc_session():
    sql = (BOOTSTRAP / "13_silver_landing_ingest.sql").read_text()
    create = _task_definition(sql, r"CREATE TASK IF NOT EXISTS LOAD_SILVER_LANDING_TASK")
    assert "CALL LOAD_SILVER_LANDING();" in create, "definition boundary is wrong"
    assert _pins_utc_before_body(create, "'UTC'"), create


def test_silver_landing_task_utc_session_is_applied_to_an_existing_task():
    """CREATE TASK IF NOT EXISTS is a no-op on an installed task, so the pin must also
    be applied by an ALTER that sits between the SUSPEND and the RESUME."""
    sql = (BOOTSTRAP / "13_silver_landing_ingest.sql").read_text()
    suspend = sql.index("ALTER TASK LOAD_SILVER_LANDING_TASK SUSPEND;")
    resume = sql.index("ALTER TASK LOAD_SILVER_LANDING_TASK RESUME;")
    alter = re.search(r"ALTER TASK LOAD_SILVER_LANDING_TASK SET TIMEZONE\s*=\s*'UTC';", sql)
    assert alter, "missing ALTER TASK LOAD_SILVER_LANDING_TASK SET TIMEZONE = 'UTC';"
    assert suspend < alter.start() < resume


def test_manifest_task_terraform_resource_pins_utc():
    tf = NATIVE_PULL_TF.read_text()
    resource = _task_definition(tf, r'resource "snowflake_task" "manifest_processor" \{')
    assert re.search(r'^\s*timezone\s*=\s*"UTC"\s*$', resource, re.MULTILINE), resource


def test_manifest_task_deploy_script_definition_pins_utc():
    script = DEPLOY_SCRIPT.read_text()
    create = _task_definition(
        script, r"CREATE OR REPLACE TASK \$\{db\}\.EDGARTOOLS_GOLD\.SNOWFLAKE_RUN_MANIFEST_TASK"
    )
    assert "PROCESS_RUN_MANIFEST_STREAM();" in create, "definition boundary is wrong"
    assert _pins_utc_before_body(create, "'UTC'"), create


def test_manifest_task_bootstrap_sql_definition_pins_utc():
    sql = (BOOTSTRAP / "04_refresh_wrapper.sql").read_text()
    create = _task_definition(sql, r"'CREATE OR REPLACE TASK ' \|\| \$manifest_task_name")
    assert "$stream_processor_procedure_name" in create, "definition boundary is wrong"
    # The task text is built inside a quoted string, so the literal is doubled: ''UTC''.
    assert _pins_utc_before_body(create, "''UTC''"), create
