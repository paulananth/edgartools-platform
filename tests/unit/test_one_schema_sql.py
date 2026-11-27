"""The SQL that leaves each platform database with its one schema: the ingress rule moves without a dropped connection, the
credential policies are detached before they are dropped, and no schema rules/snowflake.yaml keeps is ever dropped."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("one_schema_sql", ROOT / "skills/aws-snowflake-operations/scripts/one_schema_sql.py")
one_schema_sql = importlib.util.module_from_spec(spec)
spec.loader.exec_module(one_schema_sql)

NAMES = {"owner": "INVENTED_OWNER", "mirror": {"database": "INVENTED_MIRROR"},
         "gold": {"database": "INVENTED_GOLD", "schema": "GOLD"},
         "operations": {"database": "INVENTED_OPS", "schema": "CONTROL"}}
POLICIES = {"PASSWORD": ["INVENTED_GOLD.POLICIES.PW"], "AUTHENTICATION": ["INVENTED_GOLD.POLICIES.KEYS"]}


def render(**changes):
    args = {"names": NAMES, "network_policy": "INVENTED_POLICY", "rule": "INVENTED_GOLD.CONTROL.INGRESS", "allow": ["10.0.0.0/8"], "policies": POLICIES,
            "users": ["SVC_A", "SVC_B"], "drop": ["INVENTED_GOLD.CONTROL", "INVENTED_GOLD.POLICIES"], "auditor": "INVENTED_AUDITOR", **changes}
    return one_schema_sql.statements(**{k: args[k] for k in ("names", "network_policy", "rule", "allow", "policies", "users", "drop", "auditor")}).splitlines()


def at(lines, text):
    return next(i for i, line in enumerate(lines) if line.startswith(text))


def test_the_policy_names_both_rules_before_the_new_one_alone_and_the_old_rule_goes_last():
    lines = render()
    both = at(lines, "ALTER NETWORK POLICY INVENTED_POLICY SET ALLOWED_NETWORK_RULE_LIST = ('INVENTED_GOLD.CONTROL.INGRESS', 'INVENTED_OPS.CONTROL.INGRESS')")
    alone = at(lines, "ALTER NETWORK POLICY INVENTED_POLICY SET ALLOWED_NETWORK_RULE_LIST = ('INVENTED_OPS.CONTROL.INGRESS')")
    assert at(lines, "CREATE NETWORK RULE IF NOT EXISTS INVENTED_OPS.CONTROL.INGRESS") < both < alone < at(lines, "DROP NETWORK RULE IF EXISTS INVENTED_GOLD.CONTROL.INGRESS")


def test_each_policy_is_detached_from_the_account_and_every_user_before_it_is_dropped():
    lines = render()
    first_drop = at(lines, "DROP PASSWORD POLICY")
    for detach in ("ALTER ACCOUNT UNSET PASSWORD POLICY;", "ALTER ACCOUNT UNSET AUTHENTICATION POLICY;",
                   "ALTER USER IF EXISTS SVC_A UNSET AUTHENTICATION POLICY;", "ALTER USER IF EXISTS SVC_B UNSET AUTHENTICATION POLICY;"):
        assert at(lines, detach) < first_drop
    assert "DROP AUTHENTICATION POLICY IF EXISTS INVENTED_GOLD.POLICIES.KEYS;" in lines
    assert "DROP PASSWORD POLICY IF EXISTS INVENTED_GOLD.POLICIES.PW;" in lines


def test_only_the_named_schemas_and_each_databases_public_are_dropped():
    dropped = sorted(line for line in render() if line.startswith("DROP SCHEMA"))
    assert dropped == ["DROP SCHEMA IF EXISTS INVENTED_GOLD.CONTROL;", "DROP SCHEMA IF EXISTS INVENTED_GOLD.POLICIES;",
                       "DROP SCHEMA IF EXISTS INVENTED_GOLD.PUBLIC;", "DROP SCHEMA IF EXISTS INVENTED_OPS.PUBLIC;"]


@pytest.mark.parametrize("drop", [["INVENTED_GOLD.GOLD"], ["INVENTED_OPS.CONTROL"], ["OTHER_DB.X"]])
def test_a_kept_schema_or_one_outside_the_platform_databases_is_refused(drop):
    with pytest.raises(SystemExit):
        render(drop=["INVENTED_GOLD.CONTROL", *drop])


def test_moving_the_rule_out_of_a_schema_that_is_kept_is_refused():
    with pytest.raises(SystemExit):
        render(drop=["INVENTED_GOLD.POLICIES"])


def test_a_name_that_is_not_a_plain_identifier_is_refused():
    with pytest.raises(SystemExit):
        render(users=["SVC_A; DROP DATABASE X"])


def test_the_new_rule_allows_the_ranges_named_and_nothing_wider():
    assert any(line.endswith("VALUE_LIST = ('10.0.0.0/8') COMMENT = 'Permissive ingress rule for MDM Snowflake Postgres: protection relies on credentials and sslmode=require';")
               for line in render())
    with pytest.raises(SystemExit):
        render(allow=[])
    with pytest.raises(SystemExit):
        render(allow=["0.0.0.0/0'); DROP DATABASE X; --"])


def test_a_rule_already_in_the_operations_database_is_never_dropped():
    with pytest.raises(SystemExit):
        render(rule="INVENTED_OPS.CONTROL.INGRESS")


def test_the_policy_and_the_old_rule_are_printed_before_anything_changes():
    lines = render()
    first_change = at(lines, "CREATE DATABASE")
    assert at(lines, "DESCRIBE NETWORK RULE INVENTED_GOLD.CONTROL.INGRESS") < first_change
    assert at(lines, "DESCRIBE NETWORK POLICY INVENTED_POLICY") < first_change
