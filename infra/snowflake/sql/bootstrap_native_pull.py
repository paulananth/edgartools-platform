"""Validate the Terraform-managed Snowflake native-pull contract."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


class NativePullValidationError(RuntimeError):
    """Raised when the Terraform-managed native-pull contract is invalid."""


def _row_value(row: dict[str, Any], key: str) -> Any:
    for candidate in (key, key.upper(), key.lower()):
        if candidate in row:
            return row[candidate]
    raise NativePullValidationError(f"Expected key {key!r} in Snowflake result row: {sorted(row)}")


def _load_terraform_outputs(root: Path) -> dict[str, Any]:
    if not root.exists():
        raise NativePullValidationError(f"Terraform root does not exist: {root}")

    command = ["terraform", f"-chdir={root}", "output", "-json"]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise NativePullValidationError(result.stderr.strip() or result.stdout.strip() or f"terraform output failed for {root}")

    raw = json.loads(result.stdout or "{}")
    return {name: payload["value"] for name, payload in raw.items()}


def _run_snow_sql(connection: str, sql_text: str, *, expect_json: bool) -> list[dict[str, Any]] | str:
    command = ["snow", "sql", "--connection", connection, "--stdin"]
    if expect_json:
        command.extend(["--format", "JSON"])
    else:
        command.append("--silent")

    result = subprocess.run(command, check=False, capture_output=True, text=True, input=sql_text)
    if result.returncode != 0:
        raise NativePullValidationError(result.stderr.strip() or result.stdout.strip() or "snow sql failed")

    if not expect_json:
        return result.stdout

    stdout = result.stdout.strip()
    return json.loads(stdout) if stdout else []


def _parse_desc_integration(rows: list[dict[str, Any]]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for row in rows:
        property_name = str(_row_value(row, "property"))
        property_value = str(_row_value(row, "property_value") or "")
        metadata[property_name] = property_value
    return metadata


def _split_list_property(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _validate_integration_metadata(
    *,
    integration_metadata: dict[str, str],
    expected_subscriber_arn: str | None,
    expected_storage_role_arn: str,
    expected_export_root_url: str,
    expected_external_id: str | None,
) -> None:
    if integration_metadata.get("STORAGE_AWS_ROLE_ARN") != expected_storage_role_arn:
        raise NativePullValidationError(
            "Storage integration role ARN mismatch: "
            f"{integration_metadata.get('STORAGE_AWS_ROLE_ARN')} != {expected_storage_role_arn}"
        )

    allowed_locations = _split_list_property(integration_metadata.get("STORAGE_ALLOWED_LOCATIONS", ""))
    if expected_export_root_url not in allowed_locations:
        raise NativePullValidationError(
            "Storage integration allowed locations do not include the Snowflake export root: "
            f"{expected_export_root_url}"
        )

    if expected_subscriber_arn is not None and integration_metadata.get("STORAGE_AWS_IAM_USER_ARN") != expected_subscriber_arn:
        raise NativePullValidationError(
            "Snowflake IAM user ARN mismatch: "
            f"{integration_metadata.get('STORAGE_AWS_IAM_USER_ARN')} != {expected_subscriber_arn}"
        )

    if expected_external_id is not None and integration_metadata.get("STORAGE_AWS_EXTERNAL_ID") != expected_external_id:
        raise NativePullValidationError(
            "Storage integration external ID mismatch: "
            f"{integration_metadata.get('STORAGE_AWS_EXTERNAL_ID')} != {expected_external_id}"
        )


def _validate_native_pull(
    *,
    connection: str,
    stage_fully_qualified_name: str,
    manifest_inbox_fully_qualified_name: str,
    database_name: str,
) -> dict[str, Any]:
    stage_rows = _run_snow_sql(connection, f"LIST @{stage_fully_qualified_name}/manifests/", expect_json=True)

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
  TABLE_NAME=>'{manifest_inbox_fully_qualified_name}',
  START_TIME=>DATEADD('day', -7, CURRENT_TIMESTAMP())
))
ORDER BY LAST_LOAD_TIME DESC
LIMIT 10
""".strip(),
        expect_json=True,
    )

    latest_row = copy_history_rows[0] if copy_history_rows else None
    if latest_row is not None:
        latest_status = str(_row_value(latest_row, "STATUS") or "").strip().lower()
        latest_error = str(_row_value(latest_row, "FIRST_ERROR_MESSAGE") or "").strip()
        if latest_status not in {"", "loaded"}:
            raise NativePullValidationError(
                f"Latest manifest copy did not succeed: status={latest_status!r}, error={latest_error!r}"
            )

    return {
        "stage_manifest_count": len(stage_rows),
        "copy_history_count": len(copy_history_rows),
        "latest_copy_history": latest_row,
    }


def _build_artifact(
    *,
    aws_outputs: dict[str, Any],
    snowflake_outputs: dict[str, Any],
    integration_name: str,
    integration_metadata: dict[str, str],
    native_pull_validation: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "database_name": snowflake_outputs["database_name"],
        "source_schema_name": snowflake_outputs["schema_names"]["source"],
        "gold_schema_name": snowflake_outputs["schema_names"]["gold"],
        "storage_integration_name": integration_name,
        "storage_role_arn": integration_metadata.get("STORAGE_AWS_ROLE_ARN"),
        "storage_aws_iam_user_arn": integration_metadata.get("STORAGE_AWS_IAM_USER_ARN"),
        "storage_aws_external_id": integration_metadata.get("STORAGE_AWS_EXTERNAL_ID"),
        "storage_allowed_locations": _split_list_property(integration_metadata.get("STORAGE_ALLOWED_LOCATIONS", "")),
        "manifest_sns_topic_arn": aws_outputs["snowflake_manifest_sns_topic_arn"],
        "snowflake_export_root_url": aws_outputs["snowflake_export_root_url"],
        "native_pull_ready": snowflake_outputs.get("native_pull_ready"),
        "native_pull_validation": native_pull_validation,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bootstrap_native_pull.py",
        description="Validate the Terraform-managed Snowflake native-pull path and emit a deployment artifact.",
    )
    parser.add_argument("--aws-root", required=True, type=Path, help="AWS access Terraform root with Snowflake trust outputs.")
    parser.add_argument("--snowflake-root", required=True, type=Path, help="Snowflake Terraform account root with native-pull outputs.")
    parser.add_argument("--connection", default="default", help="Snowflake connection name for SnowCLI.")
    parser.add_argument("--storage-integration-name", help="Override the integration name when validating.")
    parser.add_argument("--expected-subscriber-arn", help="Override the expected Snowflake-managed AWS principal ARN.")
    parser.add_argument("--artifact-path", type=Path, help="Optional path to write the validation artifact JSON.")
    parser.add_argument(
        "--validate-native-pull",
        action="store_true",
        default=False,
        help="Validate stage LIST and manifest COPY_HISTORY access using the deployed Terraform outputs.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        aws_outputs = _load_terraform_outputs(args.aws_root.resolve())
        snowflake_outputs = _load_terraform_outputs(args.snowflake_root.resolve())
        database_name = snowflake_outputs["database_name"]
        schema_names = snowflake_outputs["schema_names"]
        integration_name = (
            args.storage_integration_name
            or snowflake_outputs.get("native_pull_storage_integration_name")
            or f"{database_name}_EXPORT_INTEGRATION"
        )

        integration_rows = _run_snow_sql(args.connection, f"DESC INTEGRATION {integration_name}", expect_json=True)
        integration_metadata = _parse_desc_integration(integration_rows)
        expected_external_id = snowflake_outputs.get("snowflake_storage_external_id") or aws_outputs.get("snowflake_storage_external_id")
        expected_subscriber_arn = args.expected_subscriber_arn or snowflake_outputs.get("snowflake_manifest_subscriber_arn")

        _validate_integration_metadata(
            integration_metadata=integration_metadata,
            expected_subscriber_arn=expected_subscriber_arn,
            expected_storage_role_arn=aws_outputs["snowflake_storage_role_arn"],
            expected_export_root_url=aws_outputs["snowflake_export_root_url"],
            expected_external_id=expected_external_id,
        )

        native_pull_validation = None
        if args.validate_native_pull:
            stage_fqn = snowflake_outputs.get("native_pull_stage_qualified_name") or (
                f"{database_name}.{schema_names['source']}.EDGARTOOLS_SOURCE_EXPORT_STAGE"
            )
            manifest_inbox_fqn = f"{database_name}.{schema_names['source']}.SNOWFLAKE_RUN_MANIFEST_INBOX"
            native_pull_validation = _validate_native_pull(
                connection=args.connection,
                stage_fully_qualified_name=stage_fqn,
                manifest_inbox_fully_qualified_name=manifest_inbox_fqn,
                database_name=database_name,
            )

        artifact = _build_artifact(
            aws_outputs=aws_outputs,
            snowflake_outputs=snowflake_outputs,
            integration_name=integration_name,
            integration_metadata=integration_metadata,
            native_pull_validation=native_pull_validation,
        )
    except (NativePullValidationError, KeyError, json.JSONDecodeError) as exc:
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
