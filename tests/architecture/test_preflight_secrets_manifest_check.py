"""Tests for preflight-prod-promotion.sh's manifest-driven secret check
(Ticket 5 of the credential-isolation breakdown).

Previously a hardcoded list of 2 manifest-covered secrets -- exactly how the
dbt/snowflake gap (no creation path anywhere in the repo, Ticket 3/4) went
uncaught pre-promotion. Now iterates secrets-manifest.json: every entry's
container must exist (describe-secret), and entries with populated_in_prod
true must additionally show a value has ever been written (describe-secret's
own VersionIdsToStages field -- still metadata, never get-secret-value).

Real AWS is out of reach for an automated test, so behavior is exercised via
a fake `aws` on PATH (mirroring tests/architecture/test_install_wizard.py's
pattern) that serves canned describe-secret responses per secret id.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "infra" / "scripts" / "preflight-prod-promotion.sh"

FAKE_AWS_TEMPLATE = """#!/usr/bin/env bash
args="$*"
if [[ "$args" == *"sts"*"get-caller-identity"* ]]; then
  echo "123456789012"
  exit 0
fi
if [[ "$args" == *"s3api"*"head-bucket"* ]]; then
  exit 0
fi
if [[ "$args" == *"ecr"*"describe-images"* ]]; then
  exit 0
fi
if [[ "$args" == *"secretsmanager"*"describe-secret"* ]]; then
{secret_cases}
  exit 254
fi
exit 0
"""


def _make_fake_aws(tmp_path: Path, secret_responses: dict[str, str | None]) -> Path:
    """secret_responses maps a secret-id substring to either a describe-secret
    JSON response body, or None to simulate describe-secret failing (missing).
    """
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    cases = []
    for substring, response in secret_responses.items():
        if response is None:
            cases.append(f'  if [[ "$args" == *"{substring}"* ]]; then exit 254; fi')
        else:
            cases.append(f"  if [[ \"$args\" == *\"{substring}\"* ]]; then echo '{response}'; exit 0; fi")
    script = FAKE_AWS_TEMPLATE.format(secret_cases="\n".join(cases))
    aws_path = fakebin / "aws"
    aws_path.write_text(script, encoding="utf-8", newline="\n")
    aws_path.chmod(0o755)

    # preflight-prod-promotion.sh also runs `snow sql` -- fake it too so the
    # real binary (if present) never blocks on a live connection attempt.
    # Returns no rows: exercises the script's own "no databases -> fail
    # closed" path, which is a real, always-true assertion for these tests
    # (they aren't testing the Snowflake-inventory checks) rather than an
    # untested no-op.
    snow_path = fakebin / "snow"
    snow_path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8", newline="\n")
    snow_path.chmod(0o755)

    return fakebin


POPULATED = '{"Name":"x","VersionIdsToStages":{"AWSCURRENT":["v1"]}}'
EMPTY_CONTAINER = '{"Name":"x","VersionIdsToStages":{}}'

ALL_POPULATED = {
    "edgartools-prod-edgar-identity": POPULATED,
    "mdm/postgres_dsn": POPULATED,
    "mdm/snowflake": POPULATED,
    "mdm/neo4j": EMPTY_CONTAINER,
    "mdm/api_keys": EMPTY_CONTAINER,
    "dbt/snowflake": POPULATED,
}


def _run(tmp_path: Path, secret_responses: dict[str, str | None]) -> subprocess.CompletedProcess[str]:
    fakebin = _make_fake_aws(tmp_path, secret_responses)
    env = os.environ.copy()
    env["PATH"] = f"{fakebin}{os.pathsep}{env['PATH']}"
    return subprocess.run(
        ["bash", str(SCRIPT), "--aws-account-id", "123456789012", "--aws-region", "us-east-1"],
        capture_output=True,
        text=True,
        env=env,
    )


def test_script_has_valid_bash_syntax():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_all_manifest_secrets_populated_or_correctly_empty_passes(tmp_path):
    result = _run(tmp_path, ALL_POPULATED)
    combined = result.stdout + result.stderr
    assert "PASS: secret container exists: edgartools-prod/mdm/postgres_dsn" in combined
    assert "PASS: secret has a value: edgartools-prod/mdm/postgres_dsn" in combined
    assert "PASS: secret container exists: edgartools-prod/mdm/snowflake" in combined
    assert "PASS: secret has a value: edgartools-prod/mdm/snowflake" in combined
    assert "PASS: secret container exists: edgartools-prod/mdm/neo4j" in combined
    assert "PASS: secret container exists: edgartools-prod/mdm/api_keys" in combined
    # Never-populated secrets are never checked for a value -- only existence.
    assert "secret has a value: edgartools-prod/mdm/neo4j" not in combined
    assert "secret has a value: edgartools-prod/mdm/api_keys" not in combined
    assert "PASS: secret container exists: edgartools-prod/dbt/snowflake" in combined
    assert "PASS: secret has a value: edgartools-prod/dbt/snowflake" in combined
    assert "PASS: secret container exists: edgartools-prod-edgar-identity" in combined


def test_missing_dbt_snowflake_container_fails_the_gate(tmp_path):
    """The exact regression this ticket exists to catch: dbt/snowflake never
    provisioned at all.
    """
    responses = dict(ALL_POPULATED)
    responses["dbt/snowflake"] = None
    result = _run(tmp_path, responses)
    assert result.returncode == 1
    assert "FAIL: missing secret container: edgartools-prod/dbt/snowflake" in result.stderr
    assert "Preflight failed" in result.stderr


def test_container_exists_but_never_populated_fails_for_a_populated_in_prod_secret(tmp_path):
    responses = dict(ALL_POPULATED)
    responses["dbt/snowflake"] = EMPTY_CONTAINER
    result = _run(tmp_path, responses)
    assert result.returncode == 1
    assert "PASS: secret container exists: edgartools-prod/dbt/snowflake" in (result.stdout + result.stderr)
    assert "FAIL: secret container exists but has never been populated: edgartools-prod/dbt/snowflake" in result.stderr


def test_mdm_neo4j_missing_the_container_entirely_still_fails(tmp_path):
    """Never-populated doesn't mean never-checked -- the Terraform-created
    container must still exist even if nothing has been written to it.
    """
    responses = dict(ALL_POPULATED)
    responses["mdm/neo4j"] = None
    result = _run(tmp_path, responses)
    assert result.returncode == 1
    assert "FAIL: missing secret container: edgartools-prod/mdm/neo4j" in result.stderr


def test_never_calls_get_secret_value(tmp_path):
    """Ticket 5's own constraint: describe-secret metadata only, no secret
    value is ever read.
    """
    result = _run(tmp_path, ALL_POPULATED)
    assert "get-secret-value" not in (result.stdout + result.stderr)
