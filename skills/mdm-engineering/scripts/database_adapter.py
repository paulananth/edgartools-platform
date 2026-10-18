# /// script
# requires-python = ">=3.12"
# dependencies = ["SQLAlchemy==2.0.49", "psycopg2-binary>=2.9.9", "PyMySQL[rsa]>=1.1,<2", "pymssql>=2.3,<3"]
# ///
"""Persist prepared, domain-independent merge effects on a selected SQL engine.

This skill resource owns storage, not matching, source approval, or policy
interpretation. All write capabilities execute at the destination using a
restricted login; provisioning and migrations use a separate owner login.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import (
    BigInteger,
    String,
    cast,
    create_engine,
    inspect,
    insert,
    literal,
    select,
    text,
    true,
    union_all,
    update,
)
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError
from sqlalchemy.schema import CreateIndex, CreateTable

if __package__:
    from .adapter_model import model, native_registry_model
    from .adapter_sql import capabilities, commit_guards
else:
    from adapter_model import model, native_registry_model
    from adapter_sql import capabilities, commit_guards


class AdapterError(ValueError):
    """A data-free capability refusal safe to include in an operational report."""


def registered_policies(conn) -> list[dict]:
    """The bounded governance registry, not a read over master records."""
    _, tables = native_registry_model(conn.dialect.name)
    table = tables["policy"]
    return list(conn.scalars(select(table.c.body).order_by(table.c.digest)))


def retain_policy(conn, body: dict, digest: str) -> None:
    """Retain immutable policy content in the caller's governance transaction.

    The native registry's SELECT/INSERT grants remain the authority; this
    function never opens an owner connection or commits the caller's work.
    """
    if hashlib.sha256(canonical(body)).hexdigest() != digest:
        raise AdapterError("Policy content differs from its digest")
    _, tables = native_registry_model(conn.dialect.name)
    table = tables["policy"]
    # The key arbitrates competing inserts. A savepoint contains an identical
    # concurrent registration without rolling back the caller's earlier work.
    # Nothing updates an existing policy, including a nominally no-op upsert.
    prior = conn.scalar(select(table.c.body).where(table.c.digest == digest))
    if prior is not None:
        if canonical(prior) != canonical(body):
            raise AdapterError("Policy digest collision")
        return
    try:
        with conn.begin_nested():
            conn.execute(insert(table).values(digest=digest, body=body))
    except IntegrityError:
        # A shared locking read sees the winner under MySQL repeatable-read.
        # Duplicate inserts already hold shared key locks; upgrading those
        # to exclusive locks would deadlock concurrent identical registrars.
        # An unrelated integrity error still fails.
        prior = conn.scalar(select(table.c.body).where(table.c.digest == digest).with_for_update(read=True))
        if prior is None:
            raise
        if canonical(prior) != canonical(body):
            raise AdapterError("Policy digest collision") from None


def dataset_reading(conn, code: str, version: int | None = None) -> dict | None:
    """One native mapping by its source key and optionally its frozen version."""
    _, tables = native_registry_model(conn.dialect.name)
    table = tables["dataset_mapping"]
    identity = table.c.source_code == code if conn.dialect.name == "postgresql" else table.c.source_key == key(code)
    statement = select(table.c.source_code, table.c.mapping_version, table.c.body, table.c.registry_version).where(identity)
    if version is not None:
        statement = statement.where(table.c.mapping_version == version)
    row = conn.execute(statement.order_by(table.c.mapping_version.desc()).limit(1)).mappings().first()
    if row is None:
        return None
    if row["source_code"] != code:
        raise AdapterError("Source key digest collision")
    return {name: value for name, value in row.items() if name != "source_code"}


def retain_dataset_reading(conn, code: str, version: int, body: dict, registry: str) -> None:
    """Append a native mapping in the caller's governance transaction.

    Existing source and version keys arbitrate competing registrations. Neither
    the first source body nor an earlier mapping is ever updated in place.
    """
    counter(version, positive=True)
    _, tables = native_registry_model(conn.dialect.name)
    values = {"source_code": code, "registry_version": registry, "body": body}
    if conn.dialect.name != "postgresql":
        values["source_key"] = key(code)
    if version == 1:
        conn.execute(insert(tables["dataset"]).values(**values))
    conn.execute(insert(tables["dataset_mapping"]).values(**values, mapping_version=version))


def canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def document(value: Any) -> bytes:
    if isinstance(value, (str, bytes)):
        raw = value.encode("utf-8") if isinstance(value, str) else value
        json.loads(
            raw,
            parse_float=Decimal,
            parse_constant=lambda _: (_ for _ in ()).throw(
                ValueError("Nonfinite JSON")
            ),
        )
        return raw
    return canonical(value)


def key(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise AdapterError("A nonempty opaque key is required")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def counter(value: int, *, positive=False) -> str:
    if type(value) is not int or not (1 if positive else 0) <= value < 2**63:
        raise AdapterError("A signed 64-bit counter is required")
    return str(value)


def connect(value: str, selected: str):
    url = make_url(value)
    if (
        selected not in {"postgresql", "mysql", "mssql"}
        or url.get_backend_name() != selected
    ):
        raise AdapterError("Connection does not match the selected database engine")
    drivers = {
        "postgresql": "postgresql+psycopg2",
        "mysql": "mysql+pymysql",
        "mssql": "mssql+pymssql",
    }
    if "+" not in url.drivername:
        url = url.set(drivername=drivers[selected])
    return create_engine(url, hide_parameters=True, pool_pre_ping=True)


@dataclass(frozen=True)
class Effect:
    type: str
    id: str
    body: Any
    expected_version: int = 0

    def wire(self, *, immutable=False):
        key(self.type)
        key(self.id)
        result = {
            "type": self.type.encode().hex(),
            "id": self.id.encode().hex(),
            "body": document(self.body).hex(),
        }
        if not immutable:
            result["expected_version"] = counter(self.expected_version)
        return result


@dataclass(frozen=True)
class PreparedBatch:
    batch: str
    run: str
    scope: str
    pins: Any
    assessment: Any
    expected_generation: int
    expected_checkpoint: int
    checkpoint: int
    objects: tuple[Effect, ...]
    consumers: tuple[str, ...]
    payload: Any
    evidence: tuple[Effect, ...] = ()

    def intent(self) -> str:
        for value in (self.batch, self.run, self.scope):
            key(value)
        if not self.consumers or len(set(self.consumers)) != len(self.consumers):
            raise AdapterError("Distinct frozen publication consumers are required")
        for consumer in self.consumers:
            key(consumer)
        if not self.pins or not self.assessment:
            raise AdapterError(
                "Frozen pins and prepared assessment evidence are required"
            )
        for effects in (self.objects, self.evidence):
            if len({(e.type, e.id) for e in effects}) != len(effects):
                raise AdapterError("A prepared batch repeats an object key")
        result = {
            "version": "1",
            "batch": self.batch.encode().hex(),
            "run": self.run.encode().hex(),
            "scope": self.scope.encode().hex(),
            "pins": document(self.pins).hex(),
            "assessment": document(self.assessment).hex(),
            "payload": document(self.payload).hex(),
            "expected_checkpoint": counter(self.expected_checkpoint),
            "checkpoint": counter(self.checkpoint, positive=True),
            "objects": [
                e.wire() for e in sorted(self.objects, key=lambda e: (e.type, e.id))
            ],
            "evidence": [
                e.wire(immutable=True)
                for e in sorted(self.evidence, key=lambda e: (e.type, e.id))
            ],
            "consumers": [
                {"consumer": c.encode().hex()} for c in sorted(self.consumers)
            ],
        }
        # The wire document is ASCII; opaque original UTF-8 bodies remain bytes.
        return json.dumps(
            result, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )


@dataclass(frozen=True)
class Lease:
    scope: str
    owner: str
    fence: int
    expires: int


ERRORS = frozenset(
    {
        "invalid_counter",
        "missing_storage_gate",
        "storage_not_initialized",
        "invalid_scope",
        "invalid_lease_duration",
        "scope_digest_collision",
        "scope_already_leased",
        "unsupported_request_version",
        "missing_request_identity",
        "stale_scope_lease",
        "missing_prepared_evidence",
        "batch_content_collision",
        "stale_generation",
        "stale_checkpoint",
        "frozen_pins_changed",
        "invalid_consumers",
        "invalid_object_version",
        "duplicate_object_key",
        "duplicate_evidence_key",
        "stale_object_version",
        "object_digest_collision",
        "immutable_evidence_collision",
        "scope_lease_expired_before_save",
        "unknown_publication",
        "publication_already_leased",
        "stale_or_invalid_publication_receipt",
        "publication_lease_expired",
        "ambient_transaction_refused",
        "lease_invalid_at_commit",
    }
)


class Adapter:
    """One storage interface; the caller supplies all domain decisions."""

    def __init__(self, engine, *, prefix="skill_merge"):
        if engine.dialect.name not in {"postgresql", "mysql", "mssql"}:
            raise AdapterError("Unsupported selected database engine")
        self.engine = engine
        with engine.connect() as conn:
            self.schema = inspect(conn).default_schema_name
        self.prefix = prefix
        self.metadata, self.tables = model(prefix, self.schema)
        self.routines = capabilities(engine.dialect, self.tables, prefix)
        self.commit_guards = commit_guards(engine.dialect, self.tables, prefix)

    def _rpc(self, operation, values):
        name = self.routines[operation][0]
        statement = (
            f"SELECT * FROM {name}(:wire)"
            if self.engine.dialect.name == "postgresql"
            else f"CALL {name}(:wire)"
            if self.engine.dialect.name == "mysql"
            else f"EXEC {name} @p_wire=:wire"
        )
        wire = json.dumps(
            values, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
        try:
            # RPCs own their transaction. Callers cannot hold an expiry-checked
            # transaction open after the capability returns.
            with self.engine.connect().execution_options(
                isolation_level="AUTOCOMMIT"
            ) as conn:
                result = conn.execute(text(statement), {"wire": wire})
                try:
                    return dict(result.mappings().one())
                finally:
                    result.close()
        except DBAPIError as exc:
            original = str(exc.orig)
            code = next(
                (code for code in sorted(ERRORS) if code in original),
                "database_operation_failed",
            )
            raise AdapterError(code) from None

    def claim(self, scope: str, owner: str, *, seconds=300) -> Lease:
        key(scope)
        key(owner)
        row = self._rpc(
            "claim",
            {
                "scope": scope.encode().hex(),
                "owner": owner.encode().hex(),
                "seconds": counter(seconds, positive=True),
            },
        )
        return Lease(scope, owner, int(row["fence"]), int(row["expires"]))

    def apply(self, batch: PreparedBatch, lease: Lease) -> dict:
        if batch.scope != lease.scope:
            raise AdapterError("Lease scope differs from prepared effects")
        result = self._rpc(
            "apply",
            {
                "intent": batch.intent(),
                "owner": lease.owner.encode().hex(),
                "fence": counter(lease.fence, positive=True),
                "expected_generation": counter(batch.expected_generation),
            },
        )
        return {
            name: bool(value) if name in {"duplicate", "changed"} else int(value)
            for name, value in result.items()
        }

    def generation(self) -> int:
        with self.engine.connect() as conn:
            value = conn.scalar(
                select(self.tables["gate"].c.generation).where(
                    self.tables["gate"].c.id == 1
                )
            )
        if value is None:
            raise AdapterError("missing_storage_gate")
        return int(value)

    def checkpoint(self, scope: str) -> int:
        table = self.tables["checkpoint"]
        with self.engine.connect() as conn:
            value = conn.scalar(
                select(table.c.position).where(
                    table.c.scope_key == self._bound_key(scope)
                )
            )
        return 0 if value is None else int(value)

    def _bound_key(self, value):
        if self.engine.dialect.name == "mysql":
            from sqlalchemy.dialects.mysql import CHAR

            return cast(literal(key(value)), CHAR(64, charset="ascii")).collate(
                "ascii_bin"
            )
        return cast(literal(key(value)), String(64))

    def lookup_statement(self, keys):
        if not keys:
            raise AdapterError("A nonempty lookup key collection is required")

        selections = [
            select(
                self._bound_key(t).label("type_key"), self._bound_key(i).label("id_key")
            )
            for t, i in keys
        ]
        wanted = (
            union_all(*selections) if len(selections) > 1 else selections[0]
        ).subquery("wanted")
        table = self.tables["current"]
        condition = (table.c.type_key == wanted.c.type_key) & (
            table.c.id_key == wanted.c.id_key
        )
        if self.engine.dialect.name == "postgresql":
            probe = select(table).where(condition).offset(0).lateral("probe")
            return select(probe).select_from(wanted.join(probe, true()))
        statement = select(table).select_from(wanted.join(table, condition))
        if self.engine.dialect.name == "mysql":
            statement = statement.prefix_with("STRAIGHT_JOIN", dialect="mysql")
        hint = (
            "FORCE INDEX (PRIMARY)"
            if self.engine.dialect.name == "mysql"
            else "WITH (FORCESEEK)"
        )
        return statement.with_hint(table, hint, dialect_name=self.engine.dialect.name)

    def read(self, keys) -> dict[tuple[str, str], dict]:
        unique = list(dict.fromkeys(keys))
        found = {}
        # Divide the complete list below the engine's bound-parameter limit.
        for start in range(0, len(unique), 400):
            with self.engine.connect() as conn:
                rows = (
                    conn.execute(self.lookup_statement(unique[start : start + 400]))
                    .mappings()
                    .all()
                )
            for row in rows:
                identity = (
                    bytes(row["type_bytes"]).decode(),
                    bytes(row["id_bytes"]).decode(),
                )
                if identity not in unique[start : start + 400]:
                    raise AdapterError("object_digest_collision")
                found[identity] = {
                    "body": bytes(row["body"]),
                    "version": int(row["version"]),
                    "generation": int(row["generation"]),
                    "body_hash": row["body_hash"],
                }
        return found

    def history(self, type: str, id: str) -> list[dict]:
        table = self.tables["history"]
        with self.engine.connect() as conn:
            rows = (
                conn.execute(
                    select(table)
                    .where(
                        table.c.type_key == self._bound_key(type),
                        table.c.id_key == self._bound_key(id),
                    )
                    .order_by(table.c.generation)
                )
                .mappings()
                .all()
            )
        return [
            {
                "generation": int(r["generation"]),
                "version": int(r["version"]),
                "body": bytes(r["body"]),
                "body_hash": r["body_hash"],
            }
            for r in rows
        ]

    def claim_outbox(self, batch: str, consumer: str, owner: str, *, seconds=300):
        for value in (batch, consumer, owner):
            key(value)
        row = self._rpc(
            "claim_outbox",
            {
                "batch": batch.encode().hex(),
                "consumer": consumer.encode().hex(),
                "owner": owner.encode().hex(),
                "seconds": counter(seconds, positive=True),
            },
        )
        if row["verified"]:
            return None
        payload = bytes.fromhex(row["payload_hex"])
        if hashlib.sha256(payload).hexdigest() != row["payload_hash"]:
            raise AdapterError("Publication bytes differ from retained digest")
        return {
            "payload": payload,
            "payload_hash": row["payload_hash"],
            "fence": int(row["fence"]),
            "expires": int(row["expires"]),
        }

    def ack_outbox(
        self, batch: str, consumer: str, owner: str, fence: int, receipt: str
    ):
        if not re.fullmatch("[0-9a-f]{64}", receipt):
            raise AdapterError("A verified SHA-256 receipt is required")
        return self._rpc(
            "ack_outbox",
            {
                "batch": batch.encode().hex(),
                "consumer": consumer.encode().hex(),
                "owner": owner.encode().hex(),
                "fence": counter(fence, positive=True),
                "receipt": receipt,
            },
        )


@contextmanager
def _migration_lock(conn, prefix):
    token = hashlib.sha256(
        (str(conn.engine.url.database) + "/" + prefix).encode()
    ).hexdigest()
    name = conn.dialect.name
    acquired = False
    try:
        if name == "postgresql":
            number = int(token[:15], 16)
            conn.execute(text("SELECT pg_advisory_lock(:key)"), {"key": number})
        elif name == "mysql":
            if conn.scalar(text("SELECT GET_LOCK(:key,15)"), {"key": token}) != 1:
                raise AdapterError("Migration lock deadline exceeded")
        else:
            result = conn.exec_driver_sql(
                "DECLARE @r INT; EXEC @r=sys.sp_getapplock @Resource=%s,@LockMode='Exclusive',@LockOwner='Session',@LockTimeout=15000; SELECT @r",
                (token,),
            ).scalar()
            if result < 0:
                raise AdapterError("Migration lock deadline exceeded")
        acquired = True
        yield
    finally:
        if acquired:
            try:
                if name == "postgresql":
                    conn.execute(
                        text("SELECT pg_advisory_unlock(:key)"), {"key": number}
                    )
                elif name == "mysql":
                    conn.execute(text("SELECT RELEASE_LOCK(:key)"), {"key": token})
                else:
                    conn.exec_driver_sql(
                        "EXEC sys.sp_releaseapplock @Resource=%s,@LockOwner='Session'",
                        (token,),
                    )
            except DBAPIError:
                conn.invalidate()
                raise


def _grants(conn, adapter, runtime_role, runtime_host):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", runtime_role):
        raise AdapterError("A valid, pre-provisioned runtime principal is required")
    d = conn.dialect
    quote = d.identifier_preparer.quote
    role = quote(runtime_role)
    table_names = [
        d.identifier_preparer.format_table(t) for t in adapter.tables.values()
    ]
    if d.name == "postgresql":
        attributes = conn.execute(
            text(
                "SELECT rolsuper,rolcreatedb,rolcreaterole,rolbypassrls,rolreplication FROM pg_roles WHERE rolname=:r"
            ),
            {"r": runtime_role},
        ).first()
        elevated = conn.scalar(
            text(
                "SELECT current_user=:r OR pg_has_role(:r,current_user,'MEMBER') OR has_schema_privilege(:r,:s,'CREATE')"
            ),
            {"r": runtime_role, "s": adapter.schema},
        )
        if attributes is None or any(attributes) or elevated:
            raise AdapterError(
                "Separate owner and restricted runtime principal required"
            )
        if not conn.scalar(
            text("SELECT has_schema_privilege(:r,:s,'USAGE')"),
            {"r": runtime_role, "s": adapter.schema},
        ):
            conn.exec_driver_sql(
                f"GRANT USAGE ON SCHEMA {quote(adapter.schema)} TO {role}"
            )
        for name in table_names:
            if conn.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM pg_class c, LATERAL aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) a WHERE c.oid=CAST(:t AS regclass) AND a.grantee=0)"
                ),
                {"t": name},
            ):
                conn.exec_driver_sql(f"REVOKE ALL ON {name} FROM PUBLIC")
            if conn.scalar(
                text(
                    "SELECT has_table_privilege(:r,:t,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES')"
                ),
                {"r": runtime_role, "t": name},
            ):
                raise AdapterError("Runtime inherits direct storage writes")
            if not conn.scalar(
                text("SELECT has_table_privilege(:r,:t,'SELECT')"),
                {"r": runtime_role, "t": name},
            ):
                conn.exec_driver_sql(f"GRANT SELECT ON {name} TO {role}")
        for name, _ in adapter.routines.values():
            if conn.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM pg_proc p, LATERAL aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) a WHERE p.oid=CAST(:f AS regprocedure) AND a.grantee=0)"
                ),
                {"f": name + "(text)"},
            ):
                conn.exec_driver_sql(f"REVOKE ALL ON FUNCTION {name}(text) FROM PUBLIC")
            if not conn.scalar(
                text("SELECT has_function_privilege(:r,:f,'EXECUTE')"),
                {"r": runtime_role, "f": name + "(text)"},
            ):
                conn.exec_driver_sql(
                    f"GRANT EXECUTE ON FUNCTION {name}(text) TO {role}"
                )
        for function, *_ in adapter.commit_guards:
            if conn.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM pg_proc p, LATERAL aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) a WHERE p.oid=CAST(:f AS regprocedure) AND (a.grantee=0 OR a.grantee=(SELECT oid FROM pg_roles WHERE rolname=:r)))"
                ),
                {"f": function + "()", "r": runtime_role},
            ):
                conn.exec_driver_sql(
                    f"REVOKE ALL ON FUNCTION {function}() FROM PUBLIC,{role}"
                )
    elif d.name == "mysql":
        if not re.fullmatch(r"[A-Za-z0-9_.%:-]+", runtime_host):
            raise AdapterError("A valid runtime host is required")
        grantee = f"'{runtime_role}'@'{runtime_host}'"
        if (
            conn.scalar(
                text("SELECT COUNT(*) FROM mysql.user WHERE User=:u AND Host=:h"),
                {"u": runtime_role, "h": runtime_host},
            )
            != 1
        ):
            raise AdapterError("Provision the runtime account before migrating")
        global_rights = conn.scalar(
            text(
                "SELECT COUNT(*) FROM information_schema.USER_PRIVILEGES WHERE GRANTEE=:g AND PRIVILEGE_TYPE<>'USAGE'"
            ),
            {"g": grantee},
        )
        broad = conn.scalar(
            text(
                "SELECT COUNT(*) FROM information_schema.SCHEMA_PRIVILEGES WHERE GRANTEE=:g AND TABLE_SCHEMA=:s"
            ),
            {"g": grantee, "s": adapter.schema},
        )
        roles = conn.scalar(
            text(
                "SELECT COUNT(*) FROM mysql.role_edges WHERE TO_USER=:u AND TO_HOST=:h"
            ),
            {"u": runtime_role, "h": runtime_host},
        )
        if (
            global_rights
            or broad
            or roles
            or conn.scalar(
                text("SELECT SUBSTRING_INDEX(CURRENT_USER(),'@',1)=:u"),
                {"u": runtime_role},
            )
        ):
            raise AdapterError("Runtime has broad or inherited privileges")
        for name in table_names:
            rights = conn.scalar(
                text(
                    "SELECT COUNT(*) FROM information_schema.TABLE_PRIVILEGES WHERE GRANTEE=:g AND TABLE_SCHEMA=:s AND TABLE_NAME=:t AND PRIVILEGE_TYPE<>'SELECT'"
                ),
                {
                    "g": grantee,
                    "s": adapter.schema,
                    "t": name.rsplit(".", 1)[-1].strip("`"),
                },
            )
            if rights:
                raise AdapterError("Runtime already has direct storage writes")
            if not conn.scalar(
                text(
                    "SELECT COUNT(*) FROM information_schema.TABLE_PRIVILEGES WHERE GRANTEE=:g AND TABLE_SCHEMA=:s AND TABLE_NAME=:t AND PRIVILEGE_TYPE='SELECT'"
                ),
                {
                    "g": grantee,
                    "s": adapter.schema,
                    "t": name.rsplit(".", 1)[-1].strip("`"),
                },
            ):
                conn.execute(
                    text(f"GRANT SELECT ON {name} TO :user@:host"),
                    {"user": runtime_role, "host": runtime_host},
                )
        for name, _ in adapter.routines.values():
            if not conn.scalar(
                text(
                    "SELECT COUNT(*) FROM mysql.procs_priv WHERE User=:u AND Host=:h AND Db=:s AND Routine_name=:t AND Routine_type='PROCEDURE' AND FIND_IN_SET('Execute',Proc_priv)>0"
                ),
                {
                    "u": runtime_role,
                    "h": runtime_host,
                    "s": adapter.schema,
                    "t": name.rsplit(".", 1)[-1].strip("`"),
                },
            ):
                conn.execute(
                    text(f"GRANT EXECUTE ON PROCEDURE {name} TO :user@:host"),
                    {"user": runtime_role, "host": runtime_host},
                )
    else:
        linked_login = conn.scalar(
            text(
                "SELECT SUSER_SNAME(sid) FROM sys.database_principals WHERE name=:r AND type='S'"
            ),
            {"r": runtime_role},
        )
        if linked_login != runtime_role:
            raise AdapterError(
                "A restricted login and database user with the same name are required"
            )
        if conn.scalar(
            text(
                "SELECT CASE WHEN USER_NAME()=:r OR USER_ID(:r) IS NULL OR IS_ROLEMEMBER('db_owner',:r)=1 OR IS_SRVROLEMEMBER('sysadmin',:r)=1 THEN 1 ELSE 0 END"
            ),
            {"r": runtime_role},
        ):
            raise AdapterError(
                "Separate owner and restricted runtime principal required"
            )
        user_literal = str(
            literal(runtime_role).compile(
                dialect=d, compile_kwargs={"literal_binds": True}
            )
        )
        conn.exec_driver_sql(f"EXECUTE AS USER={user_literal}")
        try:
            broad = conn.scalar(
                text(
                    "SELECT COUNT(*) FROM fn_my_permissions(NULL,'DATABASE') WHERE permission_name IN ('CONTROL','ALTER','CREATE TABLE','CREATE PROCEDURE','CREATE FUNCTION','ALTER ANY USER','ALTER ANY ROLE','TAKE OWNERSHIP')"
                )
            )
        finally:
            conn.exec_driver_sql("REVERT")
        if broad:
            raise AdapterError("Runtime has broad database privileges")
        conn.exec_driver_sql(f"EXECUTE AS USER={user_literal}")
        try:
            rights = {
                name: set(
                    conn.execute(
                        text(
                            "SELECT permission_name FROM fn_my_permissions(:n,'OBJECT')"
                        ),
                        {"n": name},
                    ).scalars()
                )
                for name in table_names
                + [name for name, _ in adapter.routines.values()]
            }
        finally:
            conn.exec_driver_sql("REVERT")
        for name in table_names:
            if rights[name] - {"SELECT", "VIEW DEFINITION"}:
                raise AdapterError("Runtime already has direct storage writes")
            if "SELECT" not in rights[name]:
                conn.exec_driver_sql(f"GRANT SELECT ON OBJECT::{name} TO {role}")
        for name, _ in adapter.routines.values():
            if "EXECUTE" not in rights[name]:
                conn.exec_driver_sql(f"GRANT EXECUTE ON OBJECT::{name} TO {role}")


def provision_runtime(
    engine, *, runtime_role: str, password: str, runtime_host="%"
) -> dict:
    """Provision a separate local-test principal without changing an existing password."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", runtime_role) or not password:
        raise AdapterError(
            "A valid runtime principal and private password are required"
        )
    if not re.fullmatch(r"[A-Za-z0-9_.%:-]+", runtime_host):
        raise AdapterError("A valid runtime host is required")
    name = engine.dialect.name
    if name not in {"postgresql", "mysql", "mssql"}:
        raise AdapterError("Unsupported selected database engine")
    quote = engine.dialect.identifier_preparer.quote
    role = quote(runtime_role)
    created = False
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        if name == "postgresql":
            if conn.scalar(text("SELECT current_user=:r"), {"r": runtime_role}):
                raise AdapterError("Migration owner and runtime principal must differ")
            if not conn.scalar(
                text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:r)"),
                {"r": runtime_role},
            ):
                conn.execute(
                    text(
                        f"CREATE ROLE {role} LOGIN PASSWORD :password NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOREPLICATION"
                    ),
                    {"password": password},
                )
                created = True
        elif name == "mysql":
            if len(runtime_role) > 32 or conn.scalar(
                text("SELECT SUBSTRING_INDEX(CURRENT_USER(),'@',1)=:r"),
                {"r": runtime_role},
            ):
                raise AdapterError(
                    "A separate MySQL runtime account of at most 32 characters is required"
                )
            if not conn.scalar(
                text("SELECT COUNT(*) FROM mysql.user WHERE User=:u AND Host=:h"),
                {"u": runtime_role, "h": runtime_host},
            ):
                conn.execute(
                    text("CREATE USER :user@:host IDENTIFIED BY :password"),
                    {"user": runtime_role, "host": runtime_host, "password": password},
                )
                created = True
        else:
            if conn.scalar(
                text("SELECT CASE WHEN SUSER_SNAME()=:r THEN 1 ELSE 0 END"),
                {"r": runtime_role},
            ):
                raise AdapterError("Migration owner and runtime principal must differ")
            if not conn.scalar(
                text("SELECT COUNT(*) FROM sys.sql_logins WHERE name=:r"),
                {"r": runtime_role},
            ):
                conn.execute(
                    text(
                        f"CREATE LOGIN {role} WITH PASSWORD=:password,CHECK_POLICY=ON"
                    ),
                    {"password": password},
                )
                created = True
            if not conn.scalar(text("SELECT USER_ID(:r)"), {"r": runtime_role}):
                conn.execute(text(f"CREATE USER {role} FOR LOGIN {role}"))
    url = engine.url.set(username=runtime_role, password=password)
    if name == "mysql":
        url = url.set(database="")  # Authenticate before schema-specific grants exist.
    candidate = create_engine(url, hide_parameters=True)
    try:
        with candidate.connect() as conn:
            if conn.scalar(text("SELECT 1")) != 1:
                raise AdapterError("Runtime credential validation failed")
    except DBAPIError:
        raise AdapterError(
            "Runtime credential validation failed; existing passwords were not changed"
        ) from None
    finally:
        candidate.dispose()
    return {"created": created, "engine": name}


def _verify_capabilities(conn, adapter):
    """Check the installed body/security boundary, not just its ledger row."""
    for operation, (_, expected) in adapter.routines.items():
        values = {"schema": adapter.schema, "name": adapter.prefix + "_" + operation}
        if conn.dialect.name == "postgresql":
            row = conn.execute(
                text(
                    "SELECT p.prosrc,p.prosecdef,p.proconfig FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=:schema AND p.proname=:name AND p.pronargs=1 AND p.proargtypes='25'::oidvector"
                ),
                values,
            ).first()
            wanted = (
                expected.split("AS $capability$", 1)[1]
                .rsplit("$capability$", 1)[0]
                .strip()
            )
            matches = (
                row is not None
                and row[0].strip() == wanted
                and row[1]
                and any(
                    config.replace(" ", "") == "search_path=pg_catalog,pg_temp"
                    for config in row[2] or []
                )
            )
        elif conn.dialect.name == "mysql":
            row = conn.execute(
                text(
                    "SELECT ROUTINE_DEFINITION,SECURITY_TYPE FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=:schema AND ROUTINE_NAME=:name AND ROUTINE_TYPE='PROCEDURE'"
                ),
                values,
            ).first()
            wanted = "capability: BEGIN" + expected.split("capability: BEGIN", 1)[1]
            matches = (
                row is not None
                and row[0].strip() == wanted.strip()
                and row[1] == "DEFINER"
            )
        else:
            row = conn.execute(
                text(
                    "SELECT m.definition,m.execute_as_principal_id FROM sys.sql_modules m JOIN sys.objects o ON o.object_id=m.object_id JOIN sys.schemas s ON s.schema_id=o.schema_id WHERE s.name=:schema AND o.name=:name AND o.type='P'"
                ),
                values,
            ).first()
            normalize = lambda sql: (
                re.sub(
                    r"CREATE\s+(?:OR\s+ALTER\s+)?PROCEDURE",
                    "CREATE PROCEDURE",
                    sql,
                    count=1,
                    flags=re.IGNORECASE,
                )
                .replace("\r\n", "\n")
                .strip()
            )
            matches = (
                row is not None
                and normalize(row[0]) == normalize(expected)
                and row[1] == -2
            )
        if not matches:
            raise AdapterError("Installed storage capability differs from this build")
    for function, _, _, table, trigger, body in adapter.commit_guards:
        row = conn.execute(
            text(
                "SELECT p.prosrc,p.prosecdef FROM pg_proc p WHERE p.oid=to_regprocedure(:name)"
            ),
            {"name": function + "()"},
        ).first()
        installed = conn.execute(
            text(
                "SELECT t.tgdeferrable,t.tginitdeferred,t.tgenabled FROM pg_trigger t WHERE t.tgrelid=to_regclass(:table) AND t.tgname=:trigger"
            ),
            {
                "table": conn.dialect.identifier_preparer.format_table(
                    adapter.tables[table]
                ),
                "trigger": trigger,
            },
        ).first()
        if (
            row is None
            or row[0] != body
            or not row[1]
            or installed is None
            or tuple(installed) != (True, True, "O")
        ):
            raise AdapterError("Installed storage commit guard differs from this build")


def migrate(
    engine, *, runtime_role: str, runtime_host="%", prefix="skill_merge"
) -> dict:
    adapter = Adapter(engine, prefix=prefix)
    statements = [
        str(CreateTable(t).compile(dialect=engine.dialect))
        for t in adapter.metadata.sorted_tables
    ]
    statements += [
        str(CreateIndex(index).compile(dialect=engine.dialect))
        for t in adapter.metadata.sorted_tables
        for index in t.indexes
    ]
    statements += [sql for _, sql in adapter.routines.values()]
    statements += [
        sql
        for _, function, trigger, *_ in adapter.commit_guards
        for sql in (function, trigger)
    ]
    checksum = hashlib.sha256("\n".join(statements).encode()).hexdigest()
    ledger = adapter.tables["migration"]
    with (
        engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn,
        _migration_lock(conn, prefix),
    ):
        if engine.dialect.name == "postgresql":
            if int(conn.scalar(text("SHOW server_version_num"))) // 10000 != 16:
                raise AdapterError("This adapter is qualified for PostgreSQL 16")
        elif engine.dialect.name == "mysql":
            version = str(conn.scalar(text("SELECT VERSION()")))
            numbers = tuple(
                int(n) for n in re.match(r"^(\d+)\.(\d+)\.(\d+)", version).groups()
            )
            if "mariadb" in version.lower() or not (8, 0, 21) <= numbers < (9, 0, 0):
                raise AdapterError("This adapter requires a supported MySQL 8 server")
        elif (
            int(conn.scalar(text("SELECT SERVERPROPERTY('ProductMajorVersion')"))) != 16
        ):
            raise AdapterError("This adapter is qualified for SQL Server 2022")
        inspector = inspect(conn)
        exists = inspector.has_table(ledger.name, schema=adapter.schema)
        if not exists:
            if any(
                inspector.has_table(t.name, schema=adapter.schema)
                for k, t in adapter.tables.items()
                if k != "migration"
            ):
                raise AdapterError("Refusing untracked storage objects")
            ledger.create(conn)
            conn.execute(
                insert(ledger).values(version=1, checksum=checksum, complete=0)
            )
        rows = conn.execute(select(ledger)).mappings().all()
        if len(rows) != 1 or rows[0]["version"] != 1 or rows[0]["checksum"] != checksum:
            raise AdapterError("Installed storage migration differs from this build")
        fresh = not bool(rows[0]["complete"])
        if fresh:
            adapter.metadata.create_all(conn)
            gate = adapter.tables["gate"]
            if conn.scalar(select(gate.c.id).where(gate.c.id == 1)) is None:
                conn.execute(insert(gate).values(id=1, generation=0))
            for name, sql in adapter.routines.values():
                if engine.dialect.name == "mysql":
                    conn.exec_driver_sql(f"DROP PROCEDURE IF EXISTS {name}")
                conn.execute(text(sql))
            for _, function, trigger, table, trigger_name, _ in adapter.commit_guards:
                conn.execute(text(function))
                conn.execute(
                    text(
                        f"DROP TRIGGER IF EXISTS {engine.dialect.identifier_preparer.quote(trigger_name)} ON {engine.dialect.identifier_preparer.format_table(adapter.tables[table])}"
                    )
                )
                conn.execute(text(trigger))
        inspector = inspect(conn)
        for table in adapter.tables.values():
            columns = inspector.get_columns(table.name, schema=adapter.schema)
            if {c["name"] for c in columns} != set(table.c.keys()):
                raise AdapterError(
                    "Installed storage columns differ from the logical model"
                )
            if inspector.get_pk_constraint(table.name, schema=adapter.schema)[
                "constrained_columns"
            ] != [c.name for c in table.primary_key]:
                raise AdapterError(
                    "Installed storage key differs from the logical model"
                )
            for column in columns:
                expected = table.c[column["name"]]
                if (
                    column["nullable"] != expected.nullable
                    or column["type"].python_type != expected.type.python_type
                ):
                    raise AdapterError(
                        "Installed storage column contract differs from the logical model"
                    )
                if isinstance(expected.type, BigInteger) and not isinstance(
                    column["type"], BigInteger
                ):
                    raise AdapterError("A storage counter is not signed 64-bit")
                if (
                    isinstance(expected.type, String)
                    and column["type"].length != expected.type.length
                ):
                    raise AdapterError(
                        "Installed storage key width differs from the logical model"
                    )
            expected_indexes = {
                index.name: [c.name for c in index.columns] for index in table.indexes
            }
            actual_indexes = {
                index["name"]: index["column_names"]
                for index in inspector.get_indexes(table.name, schema=adapter.schema)
            }
            if any(
                actual_indexes.get(name) != columns
                for name, columns in expected_indexes.items()
            ):
                raise AdapterError("Required storage lookup index is absent or changed")
            if (
                engine.dialect.name == "mysql"
                and inspector.get_table_options(table.name, schema=adapter.schema).get(
                    "mysql_engine"
                )
                != "InnoDB"
            ):
                raise AdapterError("Storage requires transactional InnoDB tables")
        _verify_capabilities(conn, adapter)
        _grants(conn, adapter, runtime_role, runtime_host)
        conn.execute(update(ledger).where(ledger.c.version == 1).values(complete=1))
    return {
        "initialized": fresh,
        "migration": 1,
        "tables": len(adapter.tables),
        "engine": engine.dialect.name,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--engine", required=True, choices=("postgresql", "mysql", "mssql")
    )
    parser.add_argument(
        "--connection-env",
        required=True,
        help="Name of a private connection environment variable",
    )
    parser.add_argument("--prefix", default="skill_merge")
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("migrate")
    setup.add_argument("--runtime-role", required=True)
    setup.add_argument("--runtime-host", default="%")
    principal = sub.add_parser(
        "provision",
        help="Provision a separate test runtime principal; preserve existing passwords",
    )
    principal.add_argument("--runtime-role", required=True)
    principal.add_argument("--runtime-host", default="%")
    principal.add_argument("--password-env", required=True)
    apply = sub.add_parser(
        "apply", help="Persist an already assessed batch of shared merge effects"
    )
    apply.add_argument("--input", required=True, type=Path)
    apply.add_argument("--owner", required=True)
    sub.add_parser("status")
    args = parser.parse_args(argv)
    engine = None
    try:
        value = os.environ.get(args.connection_env)
        if not value:
            raise AdapterError(
                "Set the selected connection variable in your own terminal"
            )
        engine = connect(value, args.engine)
        if args.command == "provision":
            password = os.environ.get(args.password_env)
            if not password:
                raise AdapterError(
                    "Set the selected private password variable in your own terminal"
                )
            output = provision_runtime(
                engine,
                runtime_role=args.runtime_role,
                password=password,
                runtime_host=args.runtime_host,
            )
        elif args.command == "migrate":
            output = migrate(
                engine,
                runtime_role=args.runtime_role,
                runtime_host=args.runtime_host,
                prefix=args.prefix,
            )
        else:
            adapter = Adapter(engine, prefix=args.prefix)
            if args.command == "status":
                output = {"engine": args.engine, "generation": adapter.generation()}
            else:
                raw = json.loads(args.input.read_bytes())

                def effects(name):
                    return tuple(
                        Effect(
                            e["type"],
                            e["id"],
                            e["body_json"] if "body_json" in e else e["body"],
                            e.get("expected_version", 0),
                        )
                        for e in raw.get(name, [])
                    )

                batch = PreparedBatch(
                    batch=raw["batch"],
                    run=raw["run"],
                    scope=raw["scope"],
                    pins=raw["pins"],
                    assessment=raw["assessment"],
                    expected_generation=raw["expected_generation"],
                    expected_checkpoint=raw["expected_checkpoint"],
                    checkpoint=raw["checkpoint"],
                    objects=effects("objects"),
                    evidence=effects("evidence"),
                    consumers=tuple(raw["consumers"]),
                    payload=raw.get("payload_json", raw.get("payload")),
                )
                lease = adapter.claim(batch.scope, args.owner)
                output = adapter.apply(batch, lease)
        print(json.dumps(output, sort_keys=True))
        return 0
    except (
        AdapterError,
        ValueError,
        TypeError,
        KeyError,
        OSError,
        ImportError,
        SQLAlchemyError,
    ) as exc:
        # Never render driver URLs, SQL parameters, source values or credentials.
        message = str(exc) if isinstance(exc, AdapterError) else type(exc).__name__
        print(json.dumps({"ok": False, "error": message}, sort_keys=True))
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
