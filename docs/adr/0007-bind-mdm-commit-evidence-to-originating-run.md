# Bind MDM commit evidence to its originating run

MDM entity-change and relationship-version evidence stores a nullable `run_id` that identifies the originating MDM Run Identity; current-state tables do not carry this identity. Application write paths supply or create one identity for all new evidence in an operation, historical rows remain unknown, later mutation or export never replaces the origin, and repeatable Snowflake mirror DDL adds the same column without manual schema changes.
