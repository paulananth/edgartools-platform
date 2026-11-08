# OpenMetadata 2.0.2 → 2.0.7 upgrade research

**Scope:** Official OpenMetadata documentation and tagged 2.0.7 project sources, checked 2026-11-07. This is a compatibility and sequence summary, not an execution record.

## Findings

- **Versioned application image:** The official 2.0.7 PostgreSQL Quickstart Compose file pins both the migration container and server to `docker.getcollate.io/openmetadata/server:2.0.7`. Its migration service runs `./bootstrap/openmetadata-ops.sh migrate`; the server is ordered after this migration service. Use matching 2.0.7 server and migration artifacts, not a mixed-version server/migrator. [Tagged 2.0.7 PostgreSQL Quickstart Compose](https://github.com/open-metadata/OpenMetadata/blob/2.0.7-release/docker/docker-compose-quickstart/docker-compose-postgres.yml)

- **Bundled PostgreSQL image:** That Compose file pins `docker.getcollate.io/openmetadata/postgresql:2.0.7`. The tag's Dockerfile is `FROM postgres:15`, and the v2.0 requirements list PostgreSQL **15 or higher**. Thus the bundled 2.0.7 database image is based on PostgreSQL 15; the supported requirement is PostgreSQL 15+. Do not interpret the image tag as PostgreSQL engine version 2.0.7. [Tagged Compose](https://github.com/open-metadata/OpenMetadata/blob/2.0.7-release/docker/docker-compose-quickstart/docker-compose-postgres.yml) · [Tagged PostgreSQL Dockerfile](https://github.com/open-metadata/OpenMetadata/blob/2.0.7-release/docker/postgresql/Dockerfile_postgres) · [v2.0 Minimum Requirements](https://docs.open-metadata.org/v2.0.x/deployment/minimum-requirements)

- **Elasticsearch compatibility:** v2.0 requirements specify Elasticsearch **9.x, minimum 9.0.0, recommended 9.3.0**. The tagged 2.0.7 PostgreSQL Compose example pins `docker.elastic.co/elasticsearch/elasticsearch:9.3.0`. For existing/external clusters, validate the documented range; bundled example's exact Elasticsearch image is 9.3.0. [v2.0 Minimum Requirements](https://docs.open-metadata.org/v2.0.x/deployment/minimum-requirements) · [Tagged 2.0.7 PostgreSQL Quickstart Compose](https://github.com/open-metadata/OpenMetadata/blob/2.0.7-release/docker/docker-compose-quickstart/docker-compose-postgres.yml)

- **Required migration and ordering:** The Docker upgrade guide says that through 2.0 maintenance releases, run the normal database migration **before starting the upgraded server**. The 2.0.7 tagged PostgreSQL Compose captures that order: `execute-migrate-all` runs `./bootstrap/openmetadata-ops.sh migrate` using the 2.0.7 server image, then the application server runs. Migration updates the DB schema and search-index mappings. Follow this explicit migrate-before-new-server sequence for 2.0.2 → 2.0.7; do not skip migrations or make manual schema edits. [Docker Upgrade Guide (v2.0)](https://docs.open-metadata.org/v2.0.x/deployment/upgrade/docker) · [Tagged 2.0.7 PostgreSQL Quickstart Compose](https://github.com/open-metadata/OpenMetadata/blob/2.0.7-release/docker/docker-compose-quickstart/docker-compose-postgres.yml)

- **Migration changes relevant to this span:** The 2.0 upgrade guide calls out the 2.0.2 migration that cleans invalid direct-user memberships on non-Group teams, and the 2.0.3 migration that repairs the `CreateTask` rule on `DataConsumerPolicy` and widens `entity_extension.extension` to `VARCHAR(512)`. It explicitly says these repairs run through upgrade migrations and not to make manual schema changes. [Docker Upgrade Guide (v2.0)](https://docs.open-metadata.org/v2.0.x/deployment/upgrade/docker) · [2.0.2 release notes](https://github.com/open-metadata/OpenMetadata/releases/tag/2.0.2-release)

- **Backup and rollback constraints:** The upgrade guide recommends backing up metadata before upgrade. OpenMetadata's upgrade/backup explanation says the database schema is tightly coupled to server version; a backup represents the schema shape of its source version. To return to a prior version, restore into a clean database migrated to the **same version as the backup**, with that version's server. Do **not** restore an old-version backup into a database already shaped by a newer version; restore is for recovery/going back in time, not part of forward upgrade. Keep the backup for the recovery path; the docs do not describe an in-place reverse migration. [How do Upgrade & Backup work? (v2.0)](https://docs.open-metadata.org/v2.0.x/deployment/upgrade/how-does-it-work) · [Docker Upgrade Guide (v2.0)](https://docs.open-metadata.org/v2.0.x/deployment/upgrade/docker)

- **Post-upgrade search step:** The Docker guide marks reindexing as required after upgrade: run Search Indexing with **Recreate Indexes** enabled and all entities selected (or use the documented `openmetadata-ops.sh reindex`). [Docker Upgrade Guide (v2.0)](https://docs.open-metadata.org/v2.0.x/deployment/upgrade/docker)

## Safe upgrade outline

1. Confirm the deployment uses supported PostgreSQL (15+) and Elasticsearch (9.x, ≥9.0.0; 9.3.0 recommended), then take a recoverable pre-upgrade metadata backup.
2. Use the 2.0.7 compose/image configuration, adapting it to the existing deployment without replacing persistent database data with an empty/new database.
3. Run the 2.0.7 migration command, `./bootstrap/openmetadata-ops.sh migrate`, **before** starting the 2.0.7 server.
4. After upgrade, recreate/reindex all search indexes. If rollback is necessary, restore the pre-upgrade backup to a clean database at its source schema/version and run the matching prior-version server; don't restore it into the migrated 2.0.7 database.

## Sources

- [Docker upgrade guide, OpenMetadata v2.0.x](https://docs.open-metadata.org/v2.0.x/deployment/upgrade/docker)
- [Upgrade/backup behavior, OpenMetadata v2.0.x](https://docs.open-metadata.org/v2.0.x/deployment/upgrade/how-does-it-work)
- [Minimum requirements, OpenMetadata v2.0.x](https://docs.open-metadata.org/v2.0.x/deployment/minimum-requirements)
- [Tagged 2.0.7 PostgreSQL Quickstart Compose](https://github.com/open-metadata/OpenMetadata/blob/2.0.7-release/docker/docker-compose-quickstart/docker-compose-postgres.yml)
- [Tagged 2.0.7 PostgreSQL image Dockerfile](https://github.com/open-metadata/OpenMetadata/blob/2.0.7-release/docker/postgresql/Dockerfile_postgres)
- [OpenMetadata 2.0.2 release notes](https://github.com/open-metadata/OpenMetadata/releases/tag/2.0.2-release)
- [OpenMetadata 2.0.7 release notes](https://github.com/open-metadata/OpenMetadata/releases/tag/2.0.7-release)
