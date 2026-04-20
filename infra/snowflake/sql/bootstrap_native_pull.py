"""Bootstrap the Snowflake native-pull path from Terraform outputs."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

BOOTSTRAP_SQL_FILES = (
    "01_source_stage.sql",
    "02_refresh_status.sql",
    "03_source_load_wrapper.sql",
    "04_refresh_wrapper.sql",
)

GOLD_DYNAMIC_TABLES = (
    "COMPANY",
    "FILING_ACTIVITY",
    "OWNERSHIP_ACTIVITY",
    "OWNERSHIP_HOLDINGS",
    "ADVISER_OFFICES",
    "ADVISER_DISCLOSURES",
    "PRIVATE_FUNDS",
    "FILING_DETAIL",
)


class BootstrapError(RuntimeError):
    """Raised when the native-pull bootstrap cannot complete."""


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def _row_value(row: dict[str, Any], key: str) -> Any:
    for candidate in (key, key.upper(), key.lower()):
        if candidate in row:
            return row[candidate]
    raise BootstrapError(f"Expected key {key!r} in Snowflake result row: {sorted(row)}")


def _load_terraform_outputs(root: Path) -> dict[str, Any]:
    if not root.exists():
        raise BootstrapError(f"Terraform root does not exist: {root}")

    command = ["terraform", f"-chdir={root}", "output", "-json"]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise BootstrapError(result.stderr.strip() or result.stdout.strip() or f"terraform output failed for {root}")

    raw = json.loads(result.stdout or "{}")
    return {name: payload["value"] for name, payload in raw.items()}


def _session_preamble(session_variables: dict[str, Any]) -> str:
    return "\n".join(f"SET {name} = {_sql_literal(value)};" for name, value in session_variables.items()) + "\n"


def _run_snow_sql(connection: str, sql_text: str, *, expect_json: bool) -> list[dict[str, Any]] | str:
    command = ["snow", "sql", "--connection", connection, "--stdin"]
    if expect_json:
        command.extend(["--format", "JSON"])
    else:
        command.append("--silent")

    result = subprocess.run(command, check=False, capture_output=True, text=True, input=sql_text)
    if result.returncode != 0:
        raise BootstrapError(result.stderr.strip() or result.stdout.strip() or "snow sql failed")

    if not expect_json:
        return result.stdout

    stdout = result.stdout.strip()
    return json.loads(stdout) if stdout else []


def _run_bootstrap_sql_file(connection: str, sql_path: Path, session_variables: dict[str, Any]) -> None:
    sql_text = _session_preamble(session_variables) + sql_path.read_text(encoding="utf-8")
    _run_snow_sql(connection, sql_text, expect_json=False)


def _parse_desc_integration(rows: list[dict[str, Any]]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for row in rows:
        property_name = str(_row_value(row, "property"))
        property_value = str(_row_value(row, "property_value") or "")
        metadata[property_name] = property_value
    return metadata


def _split_list_property(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _build_session_variables(
    *,
    aws_outputs: dict[str, Any],
    snowflake_outputs: dict[str, Any],
    storage_integration_name: str,
    storage_external_id: str | None,
) -> dict[str, Any]:
    required_aws_keys = (
        "snowflake_storage_role_arn",
        "snowflake_export_root_url",
        "snowflake_manifest_sns_topic_arn",
    )
    required_snowflake_keys = ("database_name", "schema_names", "role_names", "warehouse_names")

    for key in required_aws_keys:
        if not aws_outputs.get(key):
            raise BootstrapError(f"Missing AWS Terraform output: {key}")

    for key in required_snowflake_keys:
        if not snowflake_outputs.get(key):
            raise BootstrapError(f"Missing Snowflake Terraform output: {key}")

    schema_names = snowflake_outputs["schema_names"]
    role_names = snowflake_outputs["role_names"]
    warehouse_names = snowflake_outputs["warehouse_names"]

    return {
        "database_name": snowflake_outputs["database_name"],
        "source_schema_name": schema_names["source"],
        "gold_schema_name": schema_names["gold"],
        "deployer_role_name": role_names["deployer"],
        "storage_integration_name": storage_integration_name,
        "storage_role_arn": aws_outputs["snowflake_storage_role_arn"],
        "storage_external_id": storage_external_id,
        "export_root_url": aws_outputs["snowflake_export_root_url"],
        "stage_name": "EDGARTOOLS_SOURCE_EXPORT_STAGE",
        "parquet_file_format_name": "EDGARTOOLS_SOURCE_EXPORT_FILE_FORMAT",
        "manifest_file_format_name": "EDGARTOOLS_SOURCE_RUN_MANIFEST_FILE_FORMAT",
        "manifest_inbox_table_name": "SNOWFLAKE_RUN_MANIFEST_INBOX",
        "manifest_pipe_name": "SNOWFLAKE_RUN_MANIFEST_PIPE",
        "manifest_stream_name": "SNOWFLAKE_RUN_MANIFEST_STREAM",
        "manifest_task_name": "SNOWFLAKE_RUN_MANIFEST_TASK",
        "manifest_sns_topic_arn": aws_outputs["snowflake_manifest_sns_topic_arn"],
        "refresh_warehouse_name": warehouse_names["refresh"],
        "status_table_name": "SNOWFLAKE_REFRESH_STATUS",
        "source_load_procedure_name": "LOAD_EXPORTS_FOR_RUN",
        "refresh_procedure_name": "REFRESH_AFTER_LOAD",
        "stream_processor_procedure_name": "PROCESS_RUN_MANIFEST_STREAM",
    }


def _validate_integration_metadata(
    *,
    integration_metadata: dict[str, str],
    expected_subscriber_arn: str | None,
    expected_storage_role_arn: str,
    expected_export_root_url: str,
) -> None:
    if integration_metadata.get("STORAGE_AWS_ROLE_ARN") != expected_storage_role_arn:
        raise BootstrapError(
            "Storage integration role ARN mismatch: "
            f"{integration_metadata.get('STORAGE_AWS_ROLE_ARN')} != {expected_storage_role_arn}"
        )

    allowed_locations = _split_list_property(integration_metadata.get("STORAGE_ALLOWED_LOCATIONS", ""))
    if expected_export_root_url not in allowed_locations:
        raise BootstrapError(
            "Storage integration allowed locations do not include the Snowflake export root: "
            f"{expected_export_root_url}"
        )

    if expected_subscriber_arn is not None and integration_metadata.get("STORAGE_AWS_IAM_USER_ARN") != expected_subscriber_arn:
        raise BootstrapError(
            "Snowflake IAM user ARN mismatch: "
            f"{integration_metadata.get('STORAGE_AWS_IAM_USER_ARN')} != {expected_subscriber_arn}"
        )


def _validate_native_pull(
    *,
    connection: str,
    database_name: str,
    source_schema_name: str,
    stage_name: str,
    manifest_inbox_table_name: str,
) -> dict[str, Any]:
    stage_rows = _run_snow_sql(
        connection,
        f"LIST @{database_name}.{source_schema_name}.{stage_name}/manifests/",
        expect_json=True,
    )
    if not stage_rows:
        raise BootstrapError("LIST on the Snowflake export stage succeeded but returned no manifest files.")

    copy_history_rows = _run_snow_sql(
        connection,
        f"""
SELECT
  FILE_NAME,
  STATUS,
  LAST_LOAD_TIME,
  ROW_COUNT,
  ERROR_COUNT,
  FIRST_ERROR_MESSAGE
FROM TABLE({database_name}.INFORMATION_SCHEMA.COPY_HISTORY(
  TABLE_NAME=>'{database_name}.{source_schema_name}.{manifest_inbox_table_name}',
  START_TIME=>DATEADD('day', -7, CURRENT_TIMESTAMP())
))
ORDER BY LAST_LOAD_TIME DESC
LIMIT 10
""".strip(),
        expect_json=True,
    )
    if not copy_history_rows:
        raise BootstrapError("No Snowflake COPY_HISTORY rows were found for the manifest inbox table.")

    latest_row = copy_history_rows[0]
    latest_status = str(_row_value(latest_row, "STATUS") or "").strip().lower()
    latest_error = str(_row_value(latest_row, "FIRST_ERROR_MESSAGE") or "").strip()
    if latest_status != "loaded":
        raise BootstrapError(f"Latest manifest copy did not succeed: status={latest_status!r}, error={latest_error!r}")

    return {
        "stage_manifest_count": len(stage_rows),
        "latest_copy_history": latest_row,
    }


def _build_handshake_artifact(
    *,
    session_variables: dict[str, Any],
    aws_outputs: dict[str, Any],
    integration_metadata: dict[str, str],
    native_pull_validation: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "database_name": session_variables["database_name"],
        "source_schema_name": session_variables["source_schema_name"],
        "gold_schema_name": session_variables["gold_schema_name"],
        "storage_integration_name": session_variables["storage_integration_name"],
        "storage_role_arn": integration_metadata.get("STORAGE_AWS_ROLE_ARN"),
        "storage_aws_iam_user_arn": integration_metadata.get("STORAGE_AWS_IAM_USER_ARN"),
        "storage_aws_external_id": integration_metadata.get("STORAGE_AWS_EXTERNAL_ID"),
        "storage_allowed_locations": _split_list_property(integration_metadata.get("STORAGE_ALLOWED_LOCATIONS", "")),
        "manifest_sns_topic_arn": aws_outputs["snowflake_manifest_sns_topic_arn"],
        "snowflake_export_root_url": aws_outputs["snowflake_export_root_url"],
        "gold_dynamic_tables": list(GOLD_DYNAMIC_TABLES),
        "next_terraform_input": {
            "snowflake_storage_external_id": integration_metadata.get("STORAGE_AWS_EXTERNAL_ID"),
        },
        "native_pull_validation": native_pull_validation,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bootstrap_native_pull.py",
        description="Bootstrap the Snowflake-native pull path from AWS and Snowflake Terraform outputs.",
    )
    parser.add_argument("--aws-root", required=True, type=Path, help="AWS Terraform account root with runtime outputs.")
    parser.add_argument("--snowflake-root", required=True, type=Path, help="Snowflake Terraform account root with baseline outputs.")
    parser.add_argument("--connection", default="default", help="Snowflake connection name for SnowCLI.")
    parser.add_argument("--storage-integration-name", help="Override the storage integration name.")
    parser.add_argument("--storage-external-id", help="Existing Snowflake storage external ID for the second-pass apply.")
    parser.add_argument("--expected-subscriber-arn", help="Expected Snowflake-managed AWS IAM user ARN from DESC INTEGRATION.")
    parser.add_argument("--artifact-path", type=Path, help="Optional path to write the bootstrap handshake artifact JSON.")
    parser.add_argument(
        "--validate-native-pull",
        action="store_true",
        default=False,
        help="Run LIST and COPY_HISTORY validation after bootstrap completes.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        aws_outputs = _load_terraform_outputs(args.aws_root.resolve())
        snowflake_outputs = _load_terraform_outputs(args.snowflake_root.resolve())
        database_name = snowflake_outputs["database_name"]
        storage_integration_name = args.storage_integration_name or f"{database_name}_EXPORT_INTEGRATION"
        session_variables = _build_session_variables(
            aws_outputs=aws_outputs,
            snowflake_outputs=snowflake_outputs,
            storage_integration_name=storage_integration_name,
            storage_external_id=args.storage_external_id,
        )

        sql_dir = Path(__file__).resolve().parent / "bootstrap"
        for sql_file_name in BOOTSTRAP_SQL_FILES:
            _run_bootstrap_sql_file(args.connection, sql_dir / sql_file_name, session_variables)

        integration_rows = _run_snow_sql(
            args.connection,
            f"DESC INTEGRATION {storage_integration_name}",
            expect_json=True,
        )
        integration_metadata = _parse_desc_integration(integration_rows)
        _validate_integration_metadata(
            integration_metadata=integration_metadata,
            expected_subscriber_arn=args.expected_subscriber_arn or aws_outputs.get("snowflake_manifest_subscriber_arn"),
            expected_storage_role_arn=aws_outputs["snowflake_storage_role_arn"],
            expected_export_root_url=aws_outputs["snowflake_export_root_url"],
        )

        native_pull_validation = None
        if args.validate_native_pull:
            native_pull_validation = _validate_native_pull(
                connection=args.connection,
                database_name=session_variables["database_name"],
                source_schema_name=session_variables["source_schema_name"],
                stage_name=session_variables["stage_name"],
                manifest_inbox_table_name=session_variables["manifest_inbox_table_name"],
            )

        artifact = _build_handshake_artifact(
            session_variables=session_variables,
            aws_outputs=aws_outputs,
            integration_metadata=integration_metadata,
            native_pull_validation=native_pull_validation,
        )
    except (BootstrapError, KeyError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"{exc}\n")
        return 2

    artifact_text = json.dumps(artifact, indent=2, sort_keys=True)
    sys.stdout.write(artifact_text + "\n")

    if args.artifact_path is not None:
        args.artifact_path.parent.mkdir(parents=True, exist_ok=True)
        args.artifact_path.write_text(artifact_text + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
