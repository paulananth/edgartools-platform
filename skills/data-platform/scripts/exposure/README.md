# Snowflake exposure connectivity operations

## The manifest (qualified)

`exposure_manifest.py` resolves an exposure list (the repository's is `rules/exposure.yaml`) against the
stores it names: each listed table's columns, types and comments are read from its PostgreSQL catalog,
read-only. Run it with the store's private env file, never a value on the command line:

```bash
uv run --no-project --with pyyaml --with 'psycopg[binary]' python <SKILL_DIR>/scripts/exposure/exposure_manifest.py \
  generate --config rules/exposure.yaml --env <private worker.env> --out <manifest.json>
uv run --no-project --with pyyaml python <SKILL_DIR>/scripts/exposure/exposure_manifest.py \
  check --config rules/exposure.yaml --manifest <manifest.json>
```

A table or column the store lacks, a table with no definition in the store or the list, and a name with a
dot are refused; `check` refuses a manifest its list no longer makes. A store is named by its setting
only: a driver's error can carry the address, so only its class is reported. The env files hold
SQLAlchemy addresses (`postgresql+psycopg2://`); the script drops the driver for libpq.

## The other scripts (unqualified)

`exposure_publish.py`, `autoontology.py`, `exposure_parity.py` and `exposure_operations.py` carry the open
findings of the connectivity tracker (`.scratch/snowflake-openmetadata-autoontology-connectivity-20261116/`,
tickets 02 to 05). Do not run them against a live service until their ticket is closed.

## Local verification

Use an approved manifest and credential-free metadata snapshots. Run the parity checker before any publication or schedule change:

```python
import sys
sys.path.insert(0, "<SKILL_DIR>/scripts/exposure")
from exposure_parity import check_parity
report = check_parity(manifest, snowflake=snowflake_snapshot,
                      openmetadata=openmetadata_snapshot,
                      autoontology=autoontology_snapshot)
if not report["ok"]:
    raise SystemExit(report)
```

Local checks must use invented or approved metadata only. Never paste credentials, Snowflake URLs, source rows, or API responses containing secrets into logs.

## Production contract

| Setting | Required value |
|---|---|
| Snowflake target | `EDGARTOOLS_PROD` |
| Read role | `EDGARTOOLS_PROD_READER` |
| Schema scope | `EDGARTOOLS_GOLD`, `EDGARTOOLS_SILVER` |
| Approval gate | Operator-approved production run |
| Cadence | At most once per 24 hours unless the operator approves a one-off run |

Credentials come from the approved secret store or private environment. They must not appear in command arguments, committed files, receipts, or logs.

## Run order and failure handling

1. Generate and validate the manifest.
2. Reject a manifest older than 24 hours or with a future timestamp.
3. Ingest AutoOntology using only the manifest scope.
4. Publish OpenMetadata using the manifest-owned service.
5. Capture redacted Snowflake, OpenMetadata, and AutoOntology snapshots.
6. Run parity. A non-empty mismatch report stops the cycle and prevents promotion or scheduling.
7. Emit only the manifest digest, bounded counts, mismatch kinds, owners, and remediation paths.

Publication is not considered successful until parity passes. A failed cycle produces no success receipt; rerun from a newly generated manifest after correcting the owning system.

## Ownership and rollback

- Snowflake physical schema/type drift: data-platform owner; restore or revise the Snowflake contract before rerun.
- OpenMetadata descriptions, certification, or lineage drift: catalog owner; republish the manifest-owned projection.
- AutoOntology scope or compilation drift: semantic-query owner; remove stale connections, reingest from the approved manifest, then rerun parity.
- Manifest/business-definition drift: rules owner; regenerate and review the new digest.

Rollback means stop scheduling the failing digest and restore the last parity-passing digest. Never delete Snowflake data or credentials as part of rollback.
