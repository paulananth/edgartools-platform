import re
from pathlib import Path

import pytest


@pytest.mark.parametrize("database_name", ["EXAMPLE_OPERATIONS_A", "EXAMPLE_OPERATIONS_B"])
def test_mdm_network_policy_needs_only_approved_control_location(database_name):
    template_path = (
        Path(__file__).parents[2]
        / "skills/aws-snowflake-operations/scripts/mdm_create_network_policy.sql"
    )
    template = template_path.read_text()
    variables = {
        "database_name": database_name,
        "control_schema": "CONTROL",
        "network_rule_name": "MDM_POSTGRES_INGRESS_ALL",
        "network_policy_name": "EDGARTOOLS_PROD_MDM_POSTGRES_POLICY",
    }
    rendered = template
    for name, value in variables.items():
        rendered = re.sub(r"{{\s*" + re.escape(name) + r"\s*}}", value, rendered)

    assert "{{" not in rendered
    assert f"CREATE DATABASE IF NOT EXISTS {database_name};" in rendered
    assert re.findall(r"^CREATE SCHEMA IF NOT EXISTS (.+);$", rendered, re.MULTILINE) == [
        f"{database_name}.CONTROL"
    ]
    assert "MODE = POSTGRES_INGRESS" in rendered
    assert "VALUE_LIST = ('0.0.0.0/0')" in rendered
    assert (
        "ALLOWED_NETWORK_RULE_LIST = "
        f"('{database_name}.CONTROL.MDM_POSTGRES_INGRESS_ALL')"
    ) in rendered
    assert "EDGARTOOLS_PROD.MDM" not in rendered
    assert "DROP DATABASE" not in rendered
