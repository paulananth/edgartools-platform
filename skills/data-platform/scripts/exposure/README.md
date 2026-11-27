# Snowflake exposure connectivity operations

## The manifest (qualified)

`exposure_manifest.py` resolves an exposure list (the repository's is `destination/authorised_data_sharing.yaml`) against the
stores it names: each listed table's columns, types and comments are read from its PostgreSQL catalog,
read-only. Run it with the store's private env file, never a value on the command line:

```bash
uv run --no-project --with pyyaml --with 'psycopg[binary]' python <SKILL_DIR>/scripts/exposure/exposure_manifest.py \
  generate --config destination/authorised_data_sharing.yaml --env <private worker.env> --out <manifest.json>
uv run --no-project --with pyyaml python <SKILL_DIR>/scripts/exposure/exposure_manifest.py \
  check --config destination/authorised_data_sharing.yaml --manifest <manifest.json>
```

A table or column the store lacks, a table with no definition in the store or the list, and a name with a
dot are refused; `check` refuses a manifest its list no longer makes. A store is named by its setting
only: a driver's error can carry the address, so only its class is reported. The env files hold
SQLAlchemy addresses (`postgresql+psycopg2://`); the script drops the driver for libpq.

## The OpenMetadata publication (qualified)

`exposure_publish.py` projects a manifest into one database service it owns (named by `--service`)
through the repository's catalog publisher, then reads it back. Inside that service it is the whole truth:
a table the manifest drops is deleted there. Each table gets exactly `exposure.approved` and its layer's data
class among the two classifications this publication owns; any other tag, such as a steward's, is kept. The
data class tags must already exist (the rules catalog defines them). No glossary term or certification is
published. A repeat publish changes no table's version.

```bash
set +x; set -a; source <private OpenMetadata env file>; set +a
uv run --no-project --with pyyaml python <SKILL_DIR>/scripts/exposure/exposure_publish.py \
  --manifest <manifest.json> --config destination/authorised_data_sharing.yaml   # add --check to read back only
```

An expired token answers HTTP 401 on every call but `/system/version`: renew the token, and never print it.

## The mirror SQL (qualified)

`mirror_sql.py create|alter|verify|readback|check|retire|release|suspend|restart|resume|status` prints the mirror skill's `CREATE_MIRROR` (Iceberg, Snowflake-managed storage), `ALTER_MIRROR`,
`LIST_MIRRORED_TABLES` and `DROP_MIRROR(<mirror>, TRUE)` text. Its tables are the ones `sources/managed-mirror.yaml` lists (`--managed`), each of which must
be on the exposure list (`--exposure`); an exposed table the record does not list is not mirrored, and `check --reads` fails when Gold reads one the record lacks. `alter` takes the mirror's read-back table list
(`--mirrored`) and adds and removes the difference; `readback --listing` takes the listing as `{table, state}` rows and fails until the mirror is exactly the record, all `REPLICATING`. The target database comes from `rules/snowflake.yaml`. It connects to nothing; run its output as the mirror
operator after the pre-flight and the operator's approval ([HOSTED-MIRRORING](../../HOSTED-MIRRORING.md)).

## The other scripts (unqualified)

`autoontology.py`, `exposure_parity.py` and `exposure_operations.py` are not qualified yet.
Do not run them against a live service.

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

`run_exposure_cycle` takes the target as an argument (database, read role, schema scope and approval gate, read from the
configuration, never written in the script) and repeats it in the receipt. A run is operator-approved, and runs at most once per 24 hours
unless the operator approves a one-off run.

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

`mirror_run.py` runs one statement from standard input as the mirror operator and prints its rows as JSON; a refusal exits 1
with Snowflake's error number only (`mirror_sql.py verify | mirror_run.py > listing.json`).
