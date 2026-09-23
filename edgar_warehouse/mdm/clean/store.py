"""PostgreSQL transaction boundary and durable publication capabilities.

Pure projection code prepares bounded effects; only commit_batch may persist
master changes. Network publication always runs outside that transaction.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine


class Conflict(ValueError):
    """Evidence or a checkpoint disagrees with retained history."""


def canonical(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def rows(conn: Connection, sql: str, **params: Any) -> list[dict]:
    return [dict(r) for r in conn.execute(text(sql), params).mappings()]


def migrate(engine: Engine, *, application_role: str) -> dict:
    """Explicit isolated migration with checksum validation, never legacy DDL.

    The acquisition registry may live in its own database. Role provisioning
    stays outside this function; deployments provide the restricted login role.
    """
    if engine.dialect.name != "postgresql":
        raise ValueError("Clean MDM requires PostgreSQL 16")
    path = Path(__file__).parents[1] / "migrations" / "023_clean_mdm.sql"
    source = path.read_text()
    checksum = hashlib.sha256(source.encode()).hexdigest()
    quote = engine.dialect.identifier_preparer.quote
    with engine.begin() as conn:
        if int(conn.scalar(text("SHOW server_version_num"))) // 10000 != 16:
            raise ValueError("Clean MDM requires PostgreSQL 16")
        conn.execute(text("SELECT pg_advisory_xact_lock(730233)"))
        if conn.scalar(text("SELECT current_user")) == application_role:
            raise ValueError("Migration owner and runtime role must differ")
        role = rows(
            conn,
            "SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=:name",
            name=application_role,
        )
        if not role or any(role[0].values()):
            raise ValueError(
                "Runtime role must exist without superuser/database/role creation privileges"
            )
        installed = conn.scalar(text("SELECT to_regclass('mdm_v2.migration')"))
        if installed:
            saved = conn.scalar(
                text("SELECT checksum FROM mdm_v2.migration WHERE name=:name"),
                {"name": path.name},
            )
            if saved != checksum:
                raise Conflict("Installed migration checksum differs")
        else:
            # Execute the real SQL file, including PL/pgSQL bodies, atomically.
            conn.execute(text(source))
            conn.execute(
                text(
                    "INSERT INTO mdm_v2.migration(name,checksum) VALUES(:name,:checksum)"
                ),
                {"name": path.name, "checksum": checksum},
            )
        for name in (
            "025_clean_mdm_indexes.sql",
            "026_clean_mdm_attempts.sql",
            "027_clean_mdm_deferred.sql",
            "028_clean_mdm_assessment.sql",
            "029_clean_mdm_family_checkpoint.sql",
            "030_clean_mdm_evidence_disposition.sql",
            "031_clean_mdm_mapping_version.sql",
        ):
            extra = path.with_name(name)
            extra_source = extra.read_text()
            extra_hash = hashlib.sha256(extra_source.encode()).hexdigest()
            saved = conn.scalar(
                text("SELECT checksum FROM mdm_v2.migration WHERE name=:n"),
                {"n": extra.name},
            )
            if saved is None:
                conn.execute(text(extra_source))
                conn.execute(
                    text("INSERT INTO mdm_v2.migration(name,checksum) VALUES(:n,:h)"),
                    {"n": extra.name, "h": extra_hash},
                )
            elif saved != extra_hash:
                raise Conflict("Installed migration checksum differs")
        for inherited in ("PUBLIC", application_role, "snowflake_write"):
            if inherited == "PUBLIC" or conn.scalar(
                text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:r)"),
                {"r": inherited},
            ):
                role_sql = "PUBLIC" if inherited == "PUBLIC" else quote(inherited)
                conn.exec_driver_sql(
                    f"REVOKE ALL ON ALL TABLES IN SCHEMA mdm_v2 FROM {role_sql}"
                )
                conn.exec_driver_sql(
                    f"REVOKE ALL ON ALL FUNCTIONS IN SCHEMA mdm_v2 FROM {role_sql}"
                )
                conn.exec_driver_sql(f"REVOKE ALL ON SCHEMA mdm_v2 FROM {role_sql}")
        runtime = quote(application_role)
        conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA mdm_v2 TO {runtime}")
        conn.exec_driver_sql(
            f"GRANT SELECT ON ALL TABLES IN SCHEMA mdm_v2 TO {runtime}"
        )
        for signature in (
            "commit_batch(text,uuid)",
            "claim_publication(text,text,integer)",
            "finish_publication(text,text,bigint,text,text)",
            "record_attempt(uuid,uuid,text,text,jsonb)",
            "assessment_snapshot(jsonb)",
            "record_assessment(text,uuid)",
            "supersede_assessment(text,uuid)",
            "preview_batch(text,uuid)",
        ):
            conn.exec_driver_sql(
                f"GRANT EXECUTE ON FUNCTION mdm_v2.{signature} TO {runtime}"
            )
        if conn.scalar(
            text("SELECT has_schema_privilege(:r,'mdm_v2','CREATE')"),
            {"r": application_role},
        ):
            raise ValueError(
                "Runtime role inherits schema ownership or CREATE privilege"
            )
        leaked = conn.scalar(
            text("""SELECT count(*) FROM pg_tables WHERE schemaname='mdm_v2'
            AND has_table_privilege(:r,format('%I.%I',schemaname,tablename),'INSERT,UPDATE,DELETE,TRUNCATE')"""),
            {"r": application_role},
        )
        if leaked:
            raise ValueError("Runtime role inherits direct Clean MDM writes")
    return {
        "migration": path.name,
        "checksum": checksum,
        "installed": not bool(installed),
    }


def register_policy(conn: Connection, body: dict) -> str:
    """Migration/governance owner only; runtime has no INSERT privilege."""
    if body.get("automatic_rules"):
        raise ValueError("No qualified automatic matching rules are installed")
    consumers = body.get("required_consumers", [])
    if (
        not consumers
        or len(set(consumers)) != len(consumers)
        or not all(isinstance(c, str) and c for c in consumers)
    ):
        raise ValueError("A policy requires distinct nonempty consumer names")
    key = digest(body)
    conn.execute(
        text(
            "INSERT INTO mdm_v2.policy VALUES(:key,CAST(:body AS jsonb)) ON CONFLICT DO NOTHING"
        ),
        {"key": key, "body": canonical(body)},
    )
    return key


def register_dataset(
    conn: Connection,
    code: str,
    registry_version: str,
    body: dict,
    *,
    registry_connection: Connection | None = None,
) -> None:
    """Pin metadata from existing registry authority; do not create a new registry.

    Deployment can read CHANGE_LEDGER_DATABASE_URL and write MDM_DATABASE_URL.
    The immutable attestation is a replay input, not another activation switch.
    """
    reasons = body.get("nonblocking_deferred_reasons", [])
    if (
        not isinstance(reasons, list)
        or any(not isinstance(r, str) or not r for r in reasons)
        or len(set(reasons)) != len(reasons)
    ):
        raise ValueError("nonblocking_deferred_reasons requires distinct reason names")
    adapter = body.get("adapter", {})
    formats = [
        adapter.get("record_key_format"),
        *adapter.get("identifier_formats", {}).values(),
    ]
    if any(f not in {None, "sec_cik", "lei"} for f in formats):
        raise ValueError("Unknown identifier format in Dataset Contract")
    registry_connection = (
        registry_connection if registry_connection is not None else conn
    )
    authority = rows(
        registry_connection,
        """SELECT v.version_id::text,v.status,
      v.operator_authorization_reference,c.source_family,c.coverage_action
      FROM public.source_registry_version v JOIN public.source_registry_coverage c USING(version_id)
      WHERE v.version_id=CAST(:v AS uuid) AND c.source_family=:family""",
        v=registry_version,
        family=body["family"],
    )
    if (
        len(authority) != 1
        or authority[0]["status"] != "active"
        or authority[0]["coverage_action"] == "remove"
    ):
        raise Conflict("Dataset requires active acquisition registry coverage")
    body = {**body, "registry_evidence": authority[0]}
    current = rows(
        conn,
        """SELECT body,registry_version::text,mapping_version FROM mdm_v2.dataset_mapping
        WHERE source_code=:code ORDER BY mapping_version DESC LIMIT 1""",
        code=code,
    )
    if current:
        if (
            current[0]["body"] == body
            and current[0]["registry_version"] == registry_version
        ):
            return
        protected_change(current[0]["body"], body)
        conn.execute(
            text("""INSERT INTO mdm_v2.dataset_mapping(source_code,mapping_version,body,registry_version)
            VALUES(:code,:version,CAST(:body AS jsonb),:registry)"""),
            {
                "code": code,
                "version": current[0]["mapping_version"] + 1,
                "body": canonical(body),
                "registry": str(UUID(registry_version)),
            },
        )
        return
    conn.execute(
        text("INSERT INTO mdm_v2.dataset VALUES(:code,:registry,CAST(:body AS jsonb))"),
        {
            "code": code,
            "registry": str(UUID(registry_version)),
            "body": canonical(body),
        },
    )
    conn.execute(
        text("""INSERT INTO mdm_v2.dataset_mapping(source_code,mapping_version,body,registry_version)
        VALUES(:code,1,CAST(:body AS jsonb),:registry)"""),
        {
            "code": code,
            "registry": str(UUID(registry_version)),
            "body": canonical(body),
        },
    )


# Changing any of these makes the contract describe a different dataset, so a
# record would bind to a different subject. That is the one case a new
# source_code is right; everything else is a new reading of the same source
# (company mastering ticket 01, decision 5).
PROTECTED_CONTRACT_PARTS = ("record_key", "publication_key")
PROTECTED_ADAPTER_PARTS = (
    "record_key",
    "record_key_format",
    "identifiers",
    "identifier_formats",
)


def protected_change(current: dict, proposed: dict) -> None:
    """Refuse a mapping version that would move a record's identity.

    The engine compares the parts itself, so the protection never rests on how
    an author labels the change.
    """
    moved = [
        part
        for part in PROTECTED_CONTRACT_PARTS
        if current.get(part) != proposed.get(part)
    ]
    moved += [
        f"adapter.{part}"
        for part in PROTECTED_ADAPTER_PARTS
        if current.get("adapter", {}).get(part) != proposed.get("adapter", {}).get(part)
    ]
    if moved:
        raise Conflict(
            "Dataset identity is immutable within one source code; "
            f"register a new source code: {', '.join(sorted(moved))}"
        )


class Publisher(Protocol):
    def publish(self, key: str, payload: dict, expected_hash: str) -> None: ...
    def verify(self, key: str, payload: dict, expected_hash: str) -> str: ...


class Store:
    def __init__(self, engine: Engine):
        if engine.dialect.name != "postgresql":
            raise ValueError("Clean MDM requires PostgreSQL")
        self.engine = engine

    def commit(self, conn: Connection, request: dict, run_id: str) -> dict:
        return conn.scalar(
            text("SELECT mdm_v2.commit_batch(:request,CAST(:run AS uuid))"),
            {"request": canonical(request), "run": str(UUID(run_id))},
        )

    def deliver_one(
        self,
        consumer: str,
        worker: str,
        publisher: Publisher,
        *,
        lease_seconds: int = 300,
    ) -> bool:
        with self.engine.begin() as conn:
            claim = conn.scalar(
                text("SELECT mdm_v2.claim_publication(:c,:w,:seconds)"),
                {"c": consumer, "w": worker, "seconds": lease_seconds},
            )
        if claim is None:
            return False
        key = f"{consumer}/{claim['batch_id']}"
        try:
            publisher.publish(key, claim["payload"], claim["payload_hash"])
            receipt = publisher.verify(key, claim["payload"], claim["payload_hash"])
        except Exception as exc:
            with self.engine.begin() as conn:
                conn.execute(
                    text("SELECT mdm_v2.finish_publication(:b,:c,:f,NULL,:err)"),
                    {
                        "b": claim["batch_id"],
                        "c": consumer,
                        "f": claim["fence"],
                        "err": type(exc).__name__,
                    },
                )
            raise
        with self.engine.begin() as conn:
            conn.execute(
                text("SELECT mdm_v2.finish_publication(:b,:c,:f,:h,NULL)"),
                {
                    "b": claim["batch_id"],
                    "c": consumer,
                    "f": claim["fence"],
                    "h": receipt,
                },
            )
        return True

    def run_status(self, run_id: str) -> dict:
        """Observation for Bookkeeping; never declares an empty run complete."""
        with self.engine.connect() as conn:
            result = rows(
                conn,
                """SELECT count(DISTINCT o.batch_id) AS batches,
              count(*) FILTER(WHERE p.verified_at IS NULL) AS pending
              FROM mdm_v2.observation o JOIN mdm_v2.publication p USING(batch_id)
              WHERE o.run_id=CAST(:run AS uuid)""",
                run=run_id,
            )[0]
        return {
            **result,
            "publication_complete": result["batches"] > 0 and result["pending"] == 0,
        }
