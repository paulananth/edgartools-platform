-- Create the network rule + network policy required to connect to the MDM
-- Snowflake Postgres instance. CREATE POSTGRES INSTANCE accepts NETWORK_POLICY
-- as optional, but Snowflake Postgres instances reject any policy that lacks a
-- network rule with MODE = POSTGRES_INGRESS (a plain ALLOWED_IP_LIST policy is
-- not sufficient — confirmed via "must contain at least one network rule with
-- mode POSTGRES_INGRESS" compile error on attach).
--
-- Posture: neither edgartools-dev-vpc nor edgartools-prod-vpc has a NAT
-- gateway (both use the same shared network_runtime Terraform module), and
-- the MDM ECS tasks run in public subnets with AssignPublicIp=ENABLED in
-- both environments, so each task launch gets an ephemeral AWS public-pool
-- IP. There is no stable address to allowlist for runtime traffic in either
-- environment without provisioning a NAT Gateway + EIP (a separate infra
-- decision, out of scope here). This policy is intentionally permissive
-- (Snowflake's own docs recommend against 0.0.0.0/0 for Postgres instances)
-- and instead relies on snowflake_admin/application credentials plus
-- sslmode=require (enforced by bootstrap-aws-mdm-secrets.sh) for protection.
-- This applies equally to prod today; revisit if/when a NAT Gateway + EIP is
-- added to network_runtime.
--
-- Templated by environment via Snow CLI's Jinja substitution (-D flags).
-- Required variables: schema (e.g. EDGARTOOLS_DEV.MDM / EDGARTOOLS_PROD.MDM),
-- network_rule_name, network_policy_name.
--
-- Run with (dev):
--   snow sql --connection snowconn --filename infra/snowflake/postgres/mdm_create_network_policy.sql \
--     -D "schema=EDGARTOOLS_DEV.MDM" \
--     -D "network_rule_name=mdm_postgres_ingress_all" \
--     -D "network_policy_name=edgartools_dev_mdm_postgres_policy"
--
-- Run with (prod):
--   snow sql --connection edgartools-prod --filename infra/snowflake/postgres/mdm_create_network_policy.sql \
--     -D "schema=EDGARTOOLS_PROD.MDM" \
--     -D "network_rule_name=mdm_postgres_ingress_all" \
--     -D "network_policy_name=edgartools_prod_mdm_postgres_policy"

USE SCHEMA {{ schema }};

CREATE NETWORK RULE IF NOT EXISTS {{ network_rule_name }}
  TYPE = IPV4
  MODE = POSTGRES_INGRESS
  VALUE_LIST = ('0.0.0.0/0')
  COMMENT = 'Permissive ingress rule for MDM Snowflake Postgres. ECS egress IPs are ephemeral (no NAT gateway in this environment''s VPC); protection relies on credentials + sslmode=require, not IP allowlisting.';

CREATE NETWORK POLICY IF NOT EXISTS {{ network_policy_name }}
  ALLOWED_NETWORK_RULE_LIST = ('{{ schema }}.{{ network_rule_name }}')
  COMMENT = 'Permissive policy for MDM Snowflake Postgres runtime connectivity.';

DESCRIBE NETWORK RULE {{ schema }}.{{ network_rule_name }};
DESCRIBE NETWORK POLICY {{ network_policy_name }};
