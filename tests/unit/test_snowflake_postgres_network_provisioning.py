import re
from pathlib import Path


def test_mdm_network_policy_bootstraps_in_writable_gold_control_schema():
    template_path = (
        Path(__file__).parents[2]
        / "skills/aws-snowflake-operations/scripts/mdm_create_network_policy.sql"
    )
    template = template_path.read_text()
    variables = {
        "database_name": "DB_EDGARTOOLS_GOLD",
        "control_schema": "CONTROL",
        "gold_schema": "GOLD",
        "network_rule_name": "MDM_POSTGRES_INGRESS_ALL",
        "network_policy_name": "EDGARTOOLS_PROD_MDM_POSTGRES_POLICY",
    }
    rendered = template
    for name, value in variables.items():
        rendered = re.sub(r"{{\s*" + re.escape(name) + r"\s*}}", value, rendered)

    assert "{{" not in rendered
    assert "CREATE DATABASE IF NOT EXISTS DB_EDGARTOOLS_GOLD;" in rendered
    assert "CREATE SCHEMA IF NOT EXISTS DB_EDGARTOOLS_GOLD.CONTROL;" in rendered
    assert "CREATE SCHEMA IF NOT EXISTS DB_EDGARTOOLS_GOLD.GOLD;" in rendered
    assert "MODE = POSTGRES_INGRESS" in rendered
    assert "VALUE_LIST = ('0.0.0.0/0')" in rendered
    assert (
        "ALLOWED_NETWORK_RULE_LIST = "
        "('DB_EDGARTOOLS_GOLD.CONTROL.MDM_POSTGRES_INGRESS_ALL')"
    ) in rendered
    assert "EDGARTOOLS_PROD.MDM" not in rendered
    assert "DROP DATABASE" not in rendered
