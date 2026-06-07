-- Create the network rule + network policy required to connect to the MDM
-- Snowflake Postgres instance. CREATE POSTGRES INSTANCE accepts NETWORK_POLICY
-- as optional, but Snowflake Postgres instances reject any policy that lacks a
-- network rule with MODE = POSTGRES_INGRESS (a plain ALLOWED_IP_LIST policy is
-- not sufficient — confirmed via "must contain at least one network rule with
-- mode POSTGRES_INGRESS" compile error on attach).
--
-- Dev posture: edgartools-dev-vpc has no NAT gateway, and the MDM ECS tasks
-- run in public subnets with AssignPublicIp=ENABLED, so each task launch gets
-- an ephemeral AWS public-pool IP. There is no stable address to allowlist for
-- runtime traffic without provisioning a NAT Gateway + EIP (a separate infra
-- decision). This policy is intentionally permissive for dev (Snowflake's own
-- docs recommend against 0.0.0.0/0 for Postgres instances) and instead relies
-- on snowflake_admin/application credentials plus sslmode=require (enforced by
-- bootstrap-aws-mdm-secrets.sh) for protection.
--
-- Run with:
--   snow sql --connection snowconn --filename infra/snowflake/postgres/mdm_create_network_policy.sql

USE SCHEMA EDGARTOOLS_DEV.MDM;

CREATE NETWORK RULE IF NOT EXISTS mdm_postgres_ingress_all
  TYPE = IPV4
  MODE = POSTGRES_INGRESS
  VALUE_LIST = ('0.0.0.0/0')
  COMMENT = 'Permissive dev ingress rule for MDM Snowflake Postgres. ECS egress IPs are ephemeral (no NAT gateway in edgartools-dev-vpc); protection relies on credentials + sslmode=require, not IP allowlisting.';

CREATE NETWORK POLICY IF NOT EXISTS edgartools_dev_mdm_postgres_policy
  ALLOWED_NETWORK_RULE_LIST = ('EDGARTOOLS_DEV.MDM.mdm_postgres_ingress_all')
  COMMENT = 'Permissive dev policy for MDM Snowflake Postgres runtime connectivity.';

DESCRIBE NETWORK RULE EDGARTOOLS_DEV.MDM.mdm_postgres_ingress_all;
DESCRIBE NETWORK POLICY edgartools_dev_mdm_postgres_policy;
