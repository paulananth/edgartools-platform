# High-value files

Moved out of AGENTS.md (ticket 63) unchanged: the files an agent reads to find its way.

## High-Value Files

| Need | Location |
| --- | --- |
| CLI entry point | `edgar_warehouse/cli.py` |
| Source engine (reading and combining files; Rust behind a Python facade) | `crates/source-contract/`, `edgar_warehouse/rules/source_engine.py` |
| Rules: source extracts, Dataset Contracts, quality, merge rules, identifier types | `rules/`, read by `edgar_warehouse/rules/files.py` |
| Workers and Bookkeeping | `edgar_warehouse/workers/`, `edgar_warehouse/bookkeeping/` |
| MDM store and the Merge Stage | `edgar_warehouse/mdm/`, migrations in `edgar_warehouse/mdm/migrations/` |
| RDM | `edgar_warehouse/rdm/` |
| Silver writer | `edgar_warehouse/silver_writer/` |
| Agent context command | `edgar_warehouse/context.py` |
| Journal evidence and recovery | `edgar_warehouse/application/` |
| AWS account Terraform | `infra/terraform/accounts/{dev,prod}/` |
| AWS access Terraform | `infra/terraform/access/aws/accounts/{dev,prod}/` |
| AWS Terraform modules | `infra/terraform/modules/` |
| Snowflake AWS native-pull Terraform | `infra/terraform/snowflake/accounts/{dev,prod}/` |
| Snowflake access Terraform | `infra/terraform/access/snowflake/accounts/{dev,prod}/` |
| dbt gold models | `infra/snowflake/dbt/edgartools_gold/` |
| AWS image publish script | `infra/scripts/publish-warehouse-image.sh` |
| AWS MDM scripts | `infra/scripts/bootstrap-aws-mdm-secrets.sh` |
| Docker images | `Dockerfile`, `Dockerfile.warehouse-deps`, `Dockerfile.mdm-deps`, `Dockerfile.mdm-neo4j` |
| Shared local PostgreSQL | `docs/local-agent-testing.md`, `infra/scripts/local-test-stores.py` |

Large files should be read in chunks before editing: `edgar_warehouse/mastering/merge.py`, `skills/data-platform/READING.md` and `skills/data-onboarding/SKILL.md`.
