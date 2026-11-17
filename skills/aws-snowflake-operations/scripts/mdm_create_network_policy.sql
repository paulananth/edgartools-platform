-- Create the approved writable control database/schema and the network rule
-- + policy required to connect to the MDM Snowflake Postgres instance.
-- This connectivity helper does not create Gold schemas or select a dbt target.
-- Keep the rule outside EDGARTOOLS_PROD so that database can be retired.
-- CREATE POSTGRES INSTANCE accepts NETWORK_POLICY as optional, but Snowflake
-- Postgres instances reject any policy that lacks a network rule with MODE =
-- POSTGRES_INGRESS (a plain ALLOWED_IP_LIST policy is not sufficient —
-- confirmed via "must contain at least one network rule with mode
-- POSTGRES_INGRESS" compile error on attach).
--
-- Posture: prod MDM ECS tasks run in public subnets with
-- AssignPublicIp=ENABLED and no stable NAT egress IP. This policy is
-- intentionally permissive and relies on credentials plus sslmode=require;
-- revisit it if stable egress is provisioned. Preserve the current rule
-- values during a schema/database relocation; narrowing ingress is a separate
-- security decision.
--
-- Templated by Snow CLI's Jinja substitution (-D flags). Set database_name,
-- control_schema, network_rule_name and network_policy_name from the approved
-- operational configuration. Validate all names as simple unquoted identifiers
-- before rendering. Existing objects do not establish Gold naming approval.
--
-- Invocation shape (replace placeholders with approved operational names):
--   snow sql --connection <connection> --enable-templating JINJA --filename skills/aws-snowflake-operations/scripts/mdm_create_network_policy.sql \
--     -D "database_name=<approved_control_database>" \
--     -D "control_schema=<approved_control_schema>" \
--     -D "network_rule_name=<approved_network_rule>" \
--     -D "network_policy_name=<approved_network_policy>"

CREATE DATABASE IF NOT EXISTS {{ database_name }};
CREATE SCHEMA IF NOT EXISTS {{ database_name }}.{{ control_schema }};

USE SCHEMA {{ database_name }}.{{ control_schema }};

CREATE NETWORK RULE IF NOT EXISTS {{ network_rule_name }}
  TYPE = IPV4
  MODE = POSTGRES_INGRESS
  VALUE_LIST = ('0.0.0.0/0')
  COMMENT = 'Permissive ingress rule for MDM Snowflake Postgres. ECS egress IPs are ephemeral (no NAT gateway in this environment''s VPC); protection relies on credentials + sslmode=require, not IP allowlisting.';

CREATE NETWORK POLICY IF NOT EXISTS {{ network_policy_name }}
  ALLOWED_NETWORK_RULE_LIST = ('{{ database_name }}.{{ control_schema }}.{{ network_rule_name }}')
  COMMENT = 'Permissive policy for MDM Snowflake Postgres runtime connectivity.';

-- Existing policy objects are not rewritten by CREATE ... IF NOT EXISTS.
-- During relocation, add the new rule, verify the policy references both
-- rules, then remove the old rule in a separate reviewed SQL call.
DESCRIBE NETWORK RULE {{ database_name }}.{{ control_schema }}.{{ network_rule_name }};
DESCRIBE NETWORK POLICY {{ network_policy_name }};
