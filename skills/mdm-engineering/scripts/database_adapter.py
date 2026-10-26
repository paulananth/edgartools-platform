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
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from decimal import Decimal
from datetime import UTC, datetime
from itertools import permutations
from pathlib import Path
from typing import Any

from sqlalchemy import (
    BigInteger,
    String,
    case,
    cast,
    create_engine,
    delete,
    event,
    func,
    inspect,
    insert,
    literal,
    select,
    text,
    true,
    tuple_,
    union_all,
    update,
)
from sqlalchemy.engine import make_url
from sqlalchemy.dialects.postgresql import JSON as PostgreSQLJSON
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError
from sqlalchemy.schema import CreateIndex, CreateTable

if __package__:
    from .adapter_model import model, native_registry_model
    from .adapter_sql import capabilities, commit_guards, migration_guards
else:
    from adapter_model import model, native_registry_model
    from adapter_sql import capabilities, commit_guards, migration_guards


class AdapterError(ValueError):
    """A data-free capability refusal safe to include in an operational report."""


def require_registry(conn, configuration: str | None = None):
    """MySQL's native owner installation must be complete and build-pinned."""
    if conn.dialect.name == "mysql":
        if __package__:
            from .registry_migration import require_ready
        else:
            from registry_migration import require_ready
        return require_ready(conn, configuration)


def registered_policies(conn) -> list[dict]:
    """The bounded governance registry, not a read over master records."""
    require_registry(conn)
    _, tables = native_registry_model(conn.dialect.name)
    table = tables["policy"]
    return list(conn.scalars(select(table.c.body).order_by(table.c.digest)))


def registered_policy(conn, digest: str) -> dict | None:
    """Read typed policy content in the caller's transaction and database."""
    require_registry(conn)
    _, tables = native_registry_model(conn.dialect.name)
    table = tables["policy"]
    return conn.scalar(select(table.c.body).where(table.c.digest == digest))


def registered_sources(conn) -> list[str]:
    """Names from the governance catalog, not a scan of source records."""
    require_registry(conn)
    _, tables = native_registry_model(conn.dialect.name)
    table = tables["dataset"]
    rows = conn.execute(select(table)).mappings()
    result = []
    for row in rows:
        if conn.dialect.name != "postgresql" and key(row["source_code"]) != row["source_key"]:
            raise AdapterError("Registered source differs from its key")
        result.append(row["source_code"])
    return result


def dataset_contracts(conn, codes) -> dict[str, dict]:
    """Exact source contracts for a bound key collection, with no row cap."""
    require_registry(conn)
    _, tables = native_registry_model(conn.dialect.name)
    table = tables["dataset"]
    codes = sorted(set(codes))
    found = {}
    for start in range(0, len(codes), 400):
        chunk = codes[start:start + 400]
        keys = [key(code) for code in chunk]
        predicate = (table.c.source_code.in_(chunk) if conn.dialect.name == "postgresql"
                     else table.c.source_key.in_(keys))
        for row in conn.execute(select(table.c.source_code, table.c.body).where(predicate)).mappings():
            if row["source_code"] not in chunk:
                raise AdapterError("Stored source identity differs from its key")
            found[row["source_code"]] = row["body"]
    return found


def retain_policy(conn, body: dict, digest: str) -> None:
    """Retain immutable policy content in the caller's governance transaction.

    The native registry's SELECT/INSERT grants remain the authority; this
    function never opens an owner connection or commits the caller's work.
    """
    require_registry(conn)
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


def dataset_reading_statement(dialect: str, code: str, version: int | None = None):
    """The indexed native mapping query, also exposed for plan qualification."""
    _, tables = native_registry_model(dialect)
    table = tables["dataset_mapping"]
    identity = table.c.source_code == code if dialect == "postgresql" else table.c.source_key == key(code)
    statement = select(table.c.source_code, table.c.mapping_version, table.c.body, table.c.registry_version).where(identity)
    if version is not None:
        statement = statement.where(table.c.mapping_version == version)
    return statement.order_by(table.c.mapping_version.desc()).limit(1)


def dataset_reading(conn, code: str, version: int | None = None) -> dict | None:
    """One native mapping by its source key and optionally its frozen version."""
    require_registry(conn)
    row = conn.execute(dataset_reading_statement(conn.dialect.name, code, version)).mappings().first()
    if row is None:
        return None
    if row["source_code"] != code:
        raise AdapterError("Source key digest collision")
    return {name: value for name, value in row.items() if name != "source_code"}


def dataset_readings(conn, keys) -> dict:
    """Grouped exact mapping probes in the caller's snapshot, never per record."""
    require_registry(conn)
    wanted = sorted(set(keys))
    result = {}
    for offset in range(0, len(wanted), 200):
        chunk = wanted[offset:offset + 200]
        statement = union_all(*(
            dataset_reading_statement(conn.dialect.name, code, version).subquery().select()
            for code, version in chunk
        ))
        for row in conn.execute(statement).mappings():
            key = (row["source_code"], row["mapping_version"])
            if key not in chunk:
                raise AdapterError("Stored mapping identity differs from its requested key")
            result[key] = dict(row)
    return result


def retain_dataset_reading(conn, code: str, version: int, body: dict, registry: str) -> None:
    """Append a native mapping in the caller's governance transaction.

    Existing source and version keys arbitrate competing registrations. Neither
    the first source body nor an earlier mapping is ever updated in place.
    """
    require_registry(conn)
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


def connect(value: str, selected: str, *, runtime_role: str | None = None):
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
    engine = create_engine(url, hide_parameters=True, pool_pre_ping=True)
    if runtime_role is not None:
        quoted = engine.dialect.identifier_preparer.quote(runtime_role)

        @event.listens_for(engine, "connect")
        def select_runtime_principal(dbapi_connection, _):
            try:
                with dbapi_connection.cursor() as cursor:
                    if selected == "postgresql":
                        cursor.execute(f"SET ROLE {quoted}")
                    else:
                        # These stores authenticate the runtime login directly.
                        # Never emulate SET ROLE with owner-side impersonation.
                        cursor.execute("SELECT CURRENT_USER()" if selected == "mysql"
                                       else "SELECT USER_NAME(), ORIGINAL_LOGIN()")
                        principal = cursor.fetchone()
                        valid = (principal[0].rsplit("@", 1)[0] == runtime_role if selected == "mysql"
                                 else principal == (runtime_role, runtime_role))
                        if not valid:
                            raise AdapterError("Authenticate as the configured runtime principal")
                dbapi_connection.commit()
            except BaseException:
                # The pool has not adopted this connection yet. In particular,
                # pymssql must not retain a rejected login's database session.
                dbapi_connection.close()
                raise
    return engine


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
class IndexChange(Effect):
    removed: bool = False

    def wire(self, *, immutable=False):
        if type(self.removed) is not bool:
            raise AdapterError("Lookup removal must be a boolean")
        result = super().wire()
        if self.removed:
            result["body"] = None
        return result


@dataclass(frozen=True)
class ProducerPayload:
    """Opaque frozen fragments around the destination's quoted producer key."""
    before: bytes
    after: bytes

    def wire(self):
        if not isinstance(self.before, bytes) or not isinstance(self.after, bytes):
            raise AdapterError("Producer payload fragments must be bytes")
        document(self.before + b'""' + self.after)
        return {"payload": b"{}".hex(), "prefix": self.before.hex(), "suffix": self.after.hex()}


def _payload_wire(value):
    return value.wire() if isinstance(value, ProducerPayload) else {"payload": document(value).hex()}


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
    payloads: dict[str, Any] | None = None
    indexes: tuple[IndexChange, ...] | None = None
    publish_inputs: bool = False
    governed: bool = False
    workflow: bool = False
    required_pins: dict[str, str] | None = None

    def intent(self) -> str:
        if type(self.workflow) is not bool or self.workflow and not self.governed:
            raise AdapterError("Workflow requests require governed admission")
        if type(self.governed) is not bool:
            raise AdapterError("Governed admission must be a boolean")
        if self.required_pins is not None and not self.governed:
            raise AdapterError("Command reference approval requires governed admission")
        if not self.governed and (isinstance(self.payload, ProducerPayload) or
                isinstance(self.payloads, dict) and any(isinstance(value, ProducerPayload) for value in self.payloads.values())):
            raise AdapterError("Producer metadata requires governed admission")
        if type(self.publish_inputs) is not bool:
            raise AdapterError("Input publication must be a boolean")
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
            "payload": (b"{}" if isinstance(self.payload, ProducerPayload) else document(self.payload)).hex(),
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
        if self.payloads is not None:
            if not isinstance(self.payloads, dict) or set(self.payloads) != set(self.consumers):
                raise AdapterError("Publication payloads must name exactly the frozen consumers")
            result["version"] = "2"
            result["consumers"] = [
                {"consumer": c.encode().hex(), **_payload_wire(self.payloads[c])}
                for c in sorted(self.consumers)
            ]
        if self.indexes is not None:
            if len({(entry.type, entry.id) for entry in self.indexes}) != len(self.indexes):
                raise AdapterError("A prepared batch repeats an index key")
            result["version"] = "3"
            result["indexes"] = [entry.wire() for entry in sorted(self.indexes, key=lambda entry: (entry.type, entry.id))]
            result["consumers"] = [
                {"consumer": c.encode().hex(), **_payload_wire(self.payloads[c] if self.payloads is not None else self.payload)}
                for c in sorted(self.consumers)
            ]
        if self.publish_inputs:
            result["version"] = "4"
            result["publish_inputs"] = True
            result.setdefault("indexes", [])
            result["consumers"] = [
                {"consumer": c.encode().hex(), **_payload_wire(self.payloads[c] if self.payloads is not None else self.payload)}
                for c in sorted(self.consumers)
            ]
        if self.governed:
            # The observing/root run is admission provenance, not immutable
            # business intent. Redelivery may observe the original batch.
            result.pop("run")
            result["version"] = "6" if self.workflow else "5"
            result["required_pins"] = document(self.required_pins or {}).hex()
            result["publish_inputs"] = self.publish_inputs
            result.setdefault("indexes", [])
            result["consumers"] = [
                {"consumer": c.encode().hex(), **_payload_wire(self.payloads[c] if self.payloads is not None else self.payload)}
                for c in sorted(self.consumers)
            ]
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
        "invalid_index_version",
        "duplicate_index_key",
        "stale_index_version",
        "index_digest_collision",
        "invalid_destination_authority",
        "expired_destination_authority",
        "stale_destination_authority",
        "destination_authority_expired_before_save",
        "invalid_input_publication",
        "unsupported_index_changes",
        "scope_lease_expired_before_save",
        "unknown_publication",
        "earlier_publication_pending",
        "invalid_publication_context",
        "publication_already_leased",
        "stale_or_invalid_publication_receipt",
        "publication_lease_expired",
        "ambient_transaction_refused",
        "lease_invalid_at_commit",
        "proposal_required",
        "invalid_proposal",
        "invalid_proposal_intent",
        "proposal_content_collision",
        "proposal_not_ready",
        "assessed_effects_changed",
        "unregistered_frozen_pins",
        "invalid_metadata_mode",
        "invalid_metadata",
        "metadata_digest_collision",
        "metadata_mode_changed",
        "immutable_metadata_changed",
        "stale_metadata_version",
    }
)


def authority_wire(authority):
    if not isinstance(authority, list) or not authority:
        raise AdapterError("A nonempty destination authority proof is required")
    proofs, resources = [], set()
    for item in authority:
        try:
            if set(item) != {"resource", "token", "run_id", "attempt", "expires_at"}:
                raise ValueError
            resource = item["resource"]
            key(resource)
            if resource in resources:
                raise ValueError
            resources.add(resource)
            expires = datetime.fromisoformat(item["expires_at"].replace("Z", "+00:00"))
            if expires.tzinfo is None:
                raise ValueError
            offset = expires.astimezone(UTC) - datetime(1970,1,1,tzinfo=UTC)
            micros = (offset.days * 86400 + offset.seconds) * 1000000 + offset.microseconds
            from uuid import UUID
            proofs.append({"resource": resource.encode().hex(),
                "token": counter(item["token"], positive=True),
                "run": str(UUID(item["run_id"])).encode().hex(),
                "attempt": str(UUID(item["attempt"])).encode().hex(),
                "expires": counter(micros, positive=True)})
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            raise AdapterError("Invalid destination authority proof") from None
    return sorted(proofs, key=lambda proof: proof["resource"])


class Adapter:
    """One storage interface; the caller supplies all domain decisions."""

    def __init__(self, engine, *, prefix="skill_merge", protocol=1):
        if engine.dialect.name not in {"postgresql", "mysql", "mssql"}:
            raise AdapterError("Unsupported selected database engine")
        self.engine = engine
        with engine.connect() as conn:
            self.schema = inspect(conn).default_schema_name
        self.prefix = prefix
        if type(protocol) is not int or protocol not in (1, 2, 3, 4, 5, 6):
            raise AdapterError("Unsupported storage protocol")
        if protocol >= 4 and engine.dialect.name == "mssql":
            raise AdapterError("Destination authority is not yet qualified for SQL Server")
        self.protocol = protocol
        self.metadata, self.tables = model(prefix, self.schema, protocol=protocol)
        self.routines = capabilities(engine.dialect, self.tables, prefix, protocol=protocol)
        self.commit_guards = commit_guards(engine.dialect, self.tables, prefix)
        self.migration_guards = migration_guards(engine.dialect, self.tables, prefix) if protocol >= 2 else []

    def _rpc(self, operation, values, *, authority=None):
        if authority is not None:
            minimum = 4 if operation in {"apply","preview"} else 6
            if self.protocol < minimum:
                raise AdapterError("Selected storage protocol cannot enforce authority for this operation")
            values = {**values, "authority": authority_wire(authority)}
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
                (code for code in sorted(ERRORS, key=len, reverse=True) if code in original),
                "database_operation_failed",
            )
            # MySQL replacement removes EXECUTE until migration finishes and
            # may leave the routine absent after an interruption. Classify only
            # those errors against the selected store's durable pending flag;
            # ordinary permission and connection failures remain failures.
            arguments = getattr(exc.orig, "args", ())
            if (code == "database_operation_failed" and self.engine.dialect.name == "mysql"
                    and arguments and arguments[0] in {1305, 1370}):
                try:
                    with self.engine.connect() as conn:
                        ledger = self.tables["migration"]
                        ready = conn.scalar(select(ledger.c.complete).order_by(ledger.c.version.desc()).limit(1))
                    if ready == 0:
                        code = "storage_not_initialized"
                except SQLAlchemyError:
                    pass
            raise AdapterError(code) from None

    def claim(self, scope: str, owner: str, *, seconds=300, authority=None) -> Lease:
        if authority is not None and self.protocol < 6:
            raise AdapterError("Fenced scope claims require protocol 6")
        key(scope)
        key(owner)
        row = self._rpc(
            "claim",
            {
                "scope": scope.encode().hex(),
                "owner": owner.encode().hex(),
                "seconds": counter(seconds, positive=True),
            },
            authority=authority,
        )
        return Lease(scope, owner, int(row["fence"]), int(row["expires"]))

    def apply(self, batch: PreparedBatch, lease: Lease, *, authority=None,
              proposal_key=None, proposal_body=None, observer=None) -> dict:
        if batch.scope != lease.scope:
            raise AdapterError("Lease scope differs from prepared effects")
        if batch.indexes is not None and self.protocol < 3:
            raise AdapterError("Selected storage protocol has no lookup entries")
        if (batch.publish_inputs or authority is not None) and self.protocol < 4:
            raise AdapterError("Selected storage protocol has no destination authority")
        if (batch.governed or proposal_key is not None or proposal_body is not None or observer is not None) and self.protocol < 5:
            raise AdapterError("Selected storage protocol has no governed admission")
        return self._apply_intent(
            batch.intent(), lease, expected_generation=batch.expected_generation,
            authority=authority, proposal_key=proposal_key, proposal_body=proposal_body,
            observer=batch.run if observer is None else observer,
        )

    def read_batch(self, batch: str, *, connection=None):
        """Read original committed bytes by key, including their first producer."""
        table = self.tables["batch"]
        with self.engine.connect() if connection is None else nullcontext(connection) as conn:
            row = conn.execute(select(table).where(table.c.batch_key == key(batch))).mappings().first()
            if row is None:
                return None
            if bytes(row["batch_bytes"]) != batch.encode():
                raise AdapterError("Batch key digest collision")
            return dict(row)

    def replay(self, batch: str, lease: Lease, *, observer: str, authority=None):
        """Observe a committed command without reconstructing its prepared bytes.

        The destination still validates the lease, pins, original intent and
        observer. An unknown batch is refused rather than admitted as new work.
        """
        if self.protocol < 5:
            raise AdapterError("Selected storage protocol has no governed admission")
        saved = self.read_batch(batch)
        if saved is None:
            raise AdapterError("unknown_committed_batch")
        intent = bytes(saved["intent"]).decode("ascii")
        if json.loads(intent)["scope"] != lease.scope.encode().hex():
            raise AdapterError("Lease scope differs from prepared effects")
        return self._apply_intent(intent, lease, expected_generation=saved["generation"] - 1,
                                  observer=observer, authority=authority)

    def preview(self, batch: PreparedBatch, *, proposal_body):
        if self.protocol < 5 or not batch.governed:
            raise AdapterError("Destination preview requires governed admission")
        return self._apply_intent(
            batch.intent(), Lease(batch.scope, "preview", 1, 0),
            expected_generation=batch.expected_generation, observer=batch.run,
            proposal_body=proposal_body, operation="preview",
        )

    def _apply_intent(self, intent, lease, *, expected_generation, observer,
                      authority=None, proposal_key=None, proposal_body=None, operation="apply"):
        values = {
            "intent": intent,
            "owner": lease.owner.encode().hex(),
            "fence": counter(lease.fence, positive=True),
            "expected_generation": counter(expected_generation),
        }
        if self.protocol >= 5:
            key(observer)
            values["observer"] = observer.encode().hex()
            if proposal_key is not None:
                key(proposal_key)
                values["proposal_key"] = proposal_key
            if proposal_body is not None:
                values["proposal_body"] = document(proposal_body).hex()
        if authority is not None:
            values["authority"] = authority_wire(authority)
        result = self._rpc(
            operation,
            values,
        )
        return {
            name: bool(value) if name in {"duplicate", "changed"} else int(value)
            for name, value in result.items()
        }

    def record_proposal(self, batch: str, body, observer: str, *,
                        outcome: str, expected_generation: int, intent=None, authority=None) -> str:
        if self.protocol < 5:
            raise AdapterError("Selected storage protocol has no governed admission")
        key(batch)
        key(observer)
        return self._rpc("record_proposal", {
            "batch": batch.encode().hex(), "body": document(body).hex(),
            "observer": observer.encode().hex(), "outcome": outcome,
            "expected_generation": counter(expected_generation), "intent": intent,
        },authority=authority)["proposal_key"]

    def supersede_proposal(self, proposal_key: str, observer: str, *, authority=None) -> None:
        if self.protocol < 5:
            raise AdapterError("Selected storage protocol has no governed admission")
        key(proposal_key)
        key(observer)
        self._rpc("supersede_proposal", {"proposal_key": proposal_key,
                  "observer": observer.encode().hex()},authority=authority)

    def read_proposal(self, proposal_key: str, *, connection=None):
        if self.protocol < 5:
            raise AdapterError("Selected storage protocol has no governed admission")
        table = self.tables["proposal"]
        with self.engine.connect() if connection is None else nullcontext(connection) as conn:
            row = conn.execute(select(table).where(table.c.proposal_key == proposal_key)).mappings().first()
            return None if row is None else dict(row)

    def admit_pin(self, connection, name: str, value: str, *, exclusive=False):
        """Owner-only approval; serialize activation with destination admission."""
        if self.protocol < 5:
            raise AdapterError("Selected storage protocol has no governed admission")
        if type(exclusive) is not bool:
            raise AdapterError("Exclusive pin activation must be a boolean")
        name_key, value_key = key(name), key(value)
        connection.execute(select(self.tables["gate"].c.generation)
                           .where(self.tables["gate"].c.id == 1).with_for_update()).scalar_one()
        table = self.tables["pin"]
        wanted = (table.c.name_key == name_key) & (table.c.value_key == value_key)
        old = connection.execute(select(table).where(wanted)).mappings().first()
        if old and (bytes(old["name_bytes"]) != name.encode() or bytes(old["value_bytes"]) != value.encode()):
            raise AdapterError("Frozen pin digest collision")
        if exclusive:
            connection.execute(update(table).where(table.c.name_key == name_key).values(active=0))
        if old:
            connection.execute(update(table).where(wanted).values(active=1))
        else:
            connection.execute(insert(table).values(name_key=name_key, value_key=value_key,
                name_bytes=name.encode(), value_bytes=value.encode(), active=1))

    def activate(self, connection, pins: dict[str, str], *, exclusive=()):
        """Owner finalization in the same transaction as its registry activation.

        Runtime execution is granted separately after this transaction commits.
        Already-entered calls remain fenced by the durable pending marker until
        the complete registry and its approved references become visible together.
        """
        if self.protocol < 5 or not isinstance(pins, dict) or not pins:
            raise AdapterError("Governed activation requires approved references")
        if set(exclusive) - set(pins):
            raise AdapterError("Exclusive activation must name an approved reference")
        ledger = self.tables["migration"]
        installed = {int(row.version): row for row in connection.execute(select(ledger))}
        if set(installed) != set(range(1, self.protocol + 1)) or any(
            installed[version].checksum not in _migration_checksums(
                Adapter(self.engine, prefix=self.prefix, protocol=version)
            ) for version in installed
        ):
            raise AdapterError("Installed storage migration differs from this build")
        _verify_capabilities(connection, self)
        _verify_migration_guards(connection, self)
        connection.execute(select(self.tables["gate"].c.generation)
                           .where(self.tables["gate"].c.id == 1).with_for_update()).scalar_one()
        connection.execute(update(ledger).values(complete=1))
        for name, value in pins.items():
            self.admit_pin(connection, name, value, exclusive=name in exclusive)

    def enable_runtime(self, runtime_role: str, *, runtime_host="%"):
        """Owner grants execution only after governed activation has committed."""
        if self.protocol < 5:
            raise AdapterError("Explicit runtime activation requires governed storage")
        with self.engine.begin() as connection:
            installed = list(connection.execute(select(self.tables["migration"])))
            if {int(row.version) for row in installed} != set(range(1, self.protocol + 1)) or any(
                row.complete != 1 for row in installed
            ):
                raise AdapterError("storage_not_initialized")
            _verify_capabilities(connection, self)
            _verify_migration_guards(connection, self)
            _grants(connection, self, runtime_role, runtime_host)

    def generation(self, *, connection=None) -> int:
        with self.engine.connect() if connection is None else nullcontext(connection) as conn:
            value = conn.scalar(
                select(self.tables["gate"].c.generation).where(
                    self.tables["gate"].c.id == 1
                )
            )
        if value is None:
            raise AdapterError("missing_storage_gate")
        return int(value)

    def checkpoint(self, scope: str, *, connection=None) -> int:
        table = self.tables["checkpoint"]
        with self.engine.connect() if connection is None else nullcontext(connection) as conn:
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

    def lookup_statement(self, keys, *, immutable=False, lookup=False, metadata=False):
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
        if lookup and (immutable or self.protocol < 3):
            raise AdapterError("Selected storage protocol has no lookup entries")
        if metadata and (immutable or lookup or self.protocol < 6):
            raise AdapterError("Execution metadata requires protocol 6")
        table = self.tables["metadata" if metadata else "lookup" if lookup else "evidence" if immutable else "current"]
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

    @staticmethod
    def _read_record(row) -> dict:
        body = bytes(row["body"])
        if hashlib.sha256(body).hexdigest() != row["body_hash"]:
            raise AdapterError("object_content_hash_mismatch")
        return {
            "body": body,
            "body_hash": row["body_hash"],
            **{name: int(row[name]) for name in ("version", "generation", "recorded_at") if name in row},
        }

    def read(self, keys, *, immutable=False, lookup=False, metadata=False, connection=None) -> dict[tuple[str, str], dict]:
        unique = list(dict.fromkeys(keys))
        found = {}
        # Divide the complete list below the engine's bound-parameter limit.
        for start in range(0, len(unique), 400):
            with self.engine.connect() if connection is None else nullcontext(connection) as conn:
                rows = (
                    conn.execute(self.lookup_statement(unique[start : start + 400], immutable=immutable, lookup=lookup, metadata=metadata))
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
                found[identity] = self._read_record(row)
        return found

    def type_statement(self, type: str, *, after: str | None = None, lookup=False, metadata=False):
        """One bounded seek of an opaque type's primary-key prefix."""
        if lookup and self.protocol < 3:
            raise AdapterError("Selected storage protocol has no lookup entries")
        if metadata and (lookup or self.protocol < 6):
            raise AdapterError("Execution metadata requires protocol 6")
        table = self.tables["metadata" if metadata else "lookup" if lookup else "current"]
        statement = select(table).where(table.c.type_key == self._bound_key(type))
        if after is not None:
            statement = statement.where(table.c.id_key > after)
        statement = statement.order_by(table.c.id_key).limit(400)
        if self.engine.dialect.name in {"mysql", "mssql"}:
            hint = "FORCE INDEX (PRIMARY)" if self.engine.dialect.name == "mysql" else "WITH (FORCESEEK)"
            statement = statement.with_hint(table, hint, dialect_name=self.engine.dialect.name)
        return statement

    def snapshot_statement(self, *, after=None, limit=1000):
        """Bounded primary-key pagination for an explicit whole-store export."""
        if type(limit) is not int or not 1 <= limit <= 10001:
            raise AdapterError("Invalid snapshot page size")
        table = self.tables["current"]
        query = select(table).order_by(table.c.type_key, table.c.id_key).limit(limit)
        if after is not None:
            if not isinstance(after, tuple) or len(after) != 2:
                raise AdapterError("Invalid snapshot cursor")
            query = query.where(tuple_(table.c.type_key, table.c.id_key) >
                                tuple_(self._bound_key(after[0]), self._bound_key(after[1])))
        if self.engine.dialect.name == "mysql":
            query = query.with_hint(table, "FORCE INDEX (PRIMARY)", dialect_name="mysql")
        return query

    def snapshot_page(self, *, after=None, limit=1000, connection=None):
        with self.engine.connect() if connection is None else nullcontext(connection) as conn:
            rows = conn.execute(self.snapshot_statement(after=after,limit=limit)).mappings().all()
        result = []
        for row in rows:
            identity = (bytes(row["type_bytes"]).decode(),bytes(row["id_bytes"]).decode())
            if key(identity[0]) != row["type_key"] or key(identity[1]) != row["id_key"]:
                raise AdapterError("object_digest_collision")
            result.append((identity,self._read_record(row)))
        return result

    def iter_type(self, type: str, *, lookup=False, metadata=False, connection=None):
        """Read a keyed index's opaque entries without a table scan or size cap.

        A native caller gives each lookup key its own opaque type. It must not
        use a whole entity collection to compute a batch's affected scope.
        Supply the caller's connection when its reads share a transaction.
        """
        after = None
        while True:
            with self.engine.connect() if connection is None else nullcontext(connection) as conn:
                rows = conn.execute(self.type_statement(type, after=after, lookup=lookup, metadata=metadata)).mappings().all()
            for row in rows:
                identity = (bytes(row["type_bytes"]).decode(), bytes(row["id_bytes"]).decode())
                if identity[0] != type or key(identity[1]) != row["id_key"]:
                    raise AdapterError("object_digest_collision")
                yield identity, self._read_record(row)
            if len(rows) < 400:
                return
            after = rows[-1]["id_key"]

    def lookup_groups_statement(self, types):
        """One indexed probe per requested group, compiled as a bound collection."""
        if self.protocol < 3 or not types:
            raise AdapterError("A protocol-3 lookup group collection is required")
        selections = [select(self._bound_key(type).label("type_key")) for type in types]
        wanted = (union_all(*selections) if len(selections) > 1 else selections[0]).subquery("wanted")
        table = self.tables["lookup"]
        condition = table.c.type_key == wanted.c.type_key
        if self.engine.dialect.name == "postgresql":
            probe = select(table).where(condition).offset(0).lateral("probe")
            return select(probe).select_from(wanted.join(probe, true()))
        statement = select(table).select_from(wanted.join(table, condition))
        if self.engine.dialect.name == "mysql":
            statement = statement.prefix_with("STRAIGHT_JOIN", dialect="mysql")
        hint = "FORCE INDEX (PRIMARY)" if self.engine.dialect.name == "mysql" else "WITH (FORCESEEK)"
        return statement.with_hint(table, hint, dialect_name=self.engine.dialect.name)

    def read_lookup_groups(self, types, *, connection=None):
        """Retrieve complete affected groups without one database call per record."""
        unique = list(dict.fromkeys(types))
        found = {}
        for start in range(0, len(unique), 400):
            chunk = unique[start:start + 400]
            wanted = set(chunk)
            with self.engine.connect() if connection is None else nullcontext(connection) as conn:
                result = conn.execute(self.lookup_groups_statement(chunk))
                try:
                    for row in result.mappings().yield_per(400):
                        identity = (bytes(row["type_bytes"]).decode(), bytes(row["id_bytes"]).decode())
                        if (identity[0] not in wanted or key(identity[0]) != row["type_key"]
                                or key(identity[1]) != row["id_key"]):
                            raise AdapterError("object_digest_collision")
                        found[identity] = self._read_record(row)
                finally:
                    result.close()
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

    def origin_statement(self, keys, *, generation=None, immutable=False):
        """Bound original producer reads, with one historical seek per key."""
        if self.protocol < 5:
            raise AdapterError("Record origins require governed proposal storage")
        if not keys:
            raise AdapterError("A nonempty origin key collection is required")
        if generation is not None:
            counter(generation)
        if generation is not None and not immutable:
            table = self.tables["history"]
            probes = [select(table).where(
                table.c.type_key == self._bound_key(t), table.c.id_key == self._bound_key(i),
                table.c.generation <= generation).order_by(table.c.generation.desc()).limit(1)
                .subquery().select() for t, i in keys]
            selected = (union_all(*probes) if len(probes) > 1 else probes[0]).subquery("selected")
        else:
            selected = self.lookup_statement(keys, immutable=immutable).subquery("selected")
        batch, run = self.tables["batch"], self.tables["run"]
        if self.engine.dialect.name == "postgresql":
            batch = select(batch).where(batch.c.batch_key == selected.c.batch_key).offset(0).lateral("origin_batch")
            run = select(run).where(run.c.run_key == batch.c.run_key).offset(0).lateral("origin_run")
            joined = selected.join(batch, true()).join(run, true())
        else:
            joined = selected.join(batch, batch.c.batch_key == selected.c.batch_key).join(run, run.c.run_key == batch.c.run_key)
        proposal, event = self.tables["proposal"], self.tables["proposal_event"]
        if self.engine.dialect.name == "postgresql":
            proposal = select(proposal).where(proposal.c.batch_key == selected.c.batch_key,
                proposal.c.state == "applied").offset(0).lateral("origin_proposal")
            event = select(event).where(event.c.proposal_key == proposal.c.proposal_key,
                event.c.observer_key == run.c.run_key, event.c.event == "applied").offset(0).lateral("origin_event")
            joined = joined.outerjoin(proposal, true()).outerjoin(event, true())
        else:
            joined = joined.outerjoin(proposal, (proposal.c.batch_key == selected.c.batch_key)
                & (proposal.c.state == "applied")).outerjoin(event,
                (event.c.proposal_key == proposal.c.proposal_key)
                & (event.c.observer_key == run.c.run_key) & (event.c.event == "applied"))
        statement = select(selected, batch.c.batch_bytes.label("origin_batch"),
            batch.c.generation.label("origin_generation"), batch.c.intent.label("origin_intent"),
            batch.c.request_hash.label("origin_hash"), batch.c.assessment.label("origin_assessment"),
            run.c.run_key.label("origin_run_key"), run.c.run_bytes.label("origin_run"),
            event.c.occurred.label("origin_recorded_at"),
            event.c.observer_bytes.label("origin_observer"),
            event.c.batch_key.label("origin_event_batch")).select_from(joined)
        if immutable and generation is not None:
            statement = statement.where(batch.c.generation <= generation)
        if self.engine.dialect.name == "mysql":
            statement = statement.prefix_with("STRAIGHT_JOIN", dialect="mysql")
            for table in (self.tables["batch"], self.tables["run"]):
                statement = statement.with_hint(table, "FORCE INDEX (PRIMARY)", dialect_name="mysql")
            statement = statement.with_hint(proposal, f"FORCE INDEX ({self.prefix}_proposal_batch)", dialect_name="mysql")
            statement = statement.with_hint(event, "FORCE INDEX (PRIMARY)", dialect_name="mysql")
        return statement

    def batch_metadata_statement(self, before, *, limit=100, path=()):
        """Bounded generation-key reads of recording time and one opaque scalar.

        The caller names a JSON path; storage does not interpret its meaning.
        PostgreSQL extracts from JSON text. MySQL returns original bytes for
        Python extraction: its binary JSON parser rejects valid huge integers.
        """
        counter(before)
        if type(limit) is not int or not 1 <= limit <= 1000 or any(not isinstance(p, str) for p in path):
            raise AdapterError("Invalid bounded batch metadata page")
        if self.protocol < 5:
            raise AdapterError("Batch metadata requires governed proposal storage")
        batch = self.tables["batch"]
        scalar = literal(None)
        if path:
            if self.engine.dialect.name == "postgresql":
                scalar = func.convert_from(batch.c.assessment, "UTF8").cast(PostgreSQLJSON)
                for member in path:
                    scalar = scalar[member]
                scalar = scalar.astext
            elif self.engine.dialect.name == "mysql":
                scalar = batch.c.assessment
            else:
                raise AdapterError("Batch scalar reads are not qualified on this engine")
        columns = (batch.c.generation, batch.c.batch_key, batch.c.batch_bytes,
                   batch.c.run_key, scalar.label("scalar"))
        if self.engine.dialect.name == "postgresql" and before:
            # Admission increments generation by exactly one. A short page of
            # exact generation probes avoids bitmap/whole-index plans even
            # when a small store contains fewer rows than the requested page.
            probes = [select(literal(g).label("generation"))
                      for g in range(before, max(0, before - limit), -1)]
            wanted = (union_all(*probes) if len(probes) > 1 else probes[0]).subquery("wanted_generations")
            probe = select(*columns).where(batch.c.generation == wanted.c.generation).offset(0).lateral("batch_probe")
            selected = select(probe).select_from(wanted.join(probe, true()))
        else:
            selected = select(*columns).where(batch.c.generation <= before).order_by(
                batch.c.generation.desc()).limit(limit)
        if self.engine.dialect.name == "mysql":
            selected = selected.with_hint(batch, f"FORCE INDEX ({self.prefix}_generation_unique)", dialect_name="mysql")
        selected = selected.subquery("selected_batches")
        proposal, event = self.tables["proposal"], self.tables["proposal_event"]
        if self.engine.dialect.name == "postgresql":
            proposal = select(proposal).where(proposal.c.batch_key == selected.c.batch_key,
                proposal.c.state == "applied").offset(0).lateral("applied_proposal")
            event = select(event).where(event.c.proposal_key == proposal.c.proposal_key,
                event.c.observer_key == selected.c.run_key, event.c.event == "applied").offset(0).lateral("applied_event")
            joined = selected.outerjoin(proposal, true()).outerjoin(event, true())
        else:
            joined = selected.outerjoin(proposal, (proposal.c.batch_key == selected.c.batch_key)
                & (proposal.c.state == "applied")).outerjoin(event,
                (event.c.proposal_key == proposal.c.proposal_key)
                & (event.c.observer_key == selected.c.run_key) & (event.c.event == "applied"))
        statement = select(selected, event.c.occurred, event.c.observer_bytes,
            event.c.batch_key.label("event_batch_key")).select_from(joined).order_by(selected.c.generation.desc())
        if self.engine.dialect.name == "mysql":
            statement = statement.prefix_with("STRAIGHT_JOIN", dialect="mysql")
            statement = statement.with_hint(proposal, f"FORCE INDEX ({self.prefix}_proposal_batch)", dialect_name="mysql")
            statement = statement.with_hint(event, "FORCE INDEX (PRIMARY)", dialect_name="mysql")
        return statement

    def batch_metadata(self, before, *, limit=100, path=(), connection=None):
        with self.engine.connect() if connection is None else nullcontext(connection) as conn:
            rows = conn.execute(self.batch_metadata_statement(before, limit=limit, path=path)).mappings().all()
        found = {}
        for row in rows:
            if (row["generation"] in found or row["occurred"] is None or row["occurred"] <= 0
                    or row["observer_bytes"] is None or row["event_batch_key"] != row["batch_key"]
                    or hashlib.sha256(bytes(row["batch_bytes"])).hexdigest() != row["batch_key"]
                    or hashlib.sha256(bytes(row["observer_bytes"])).hexdigest() != row["run_key"]):
                raise AdapterError("batch_metadata_origin_mismatch")
            scalar = row["scalar"]
            if path and self.engine.dialect.name == "mysql":
                try:
                    scalar = json.loads(bytes(scalar))
                    for member in path:
                        scalar = scalar.get(member) if isinstance(scalar, dict) else None
                except (TypeError, ValueError):
                    raise AdapterError("Invalid retained batch metadata") from None
            found[row["generation"]] = {"generation": int(row["generation"]),
                "recorded_at": int(row["occurred"]), "scalar": scalar}
        return list(found.values())

    def record_keys_statement(self, object_type, *, after="", limit=100):
        """A bounded page in stable storage-key order, retaining opaque IDs."""
        if not isinstance(after, str) or type(limit) is not int or not 1 <= limit <= 1001:
            raise AdapterError("Invalid bounded record key page")
        table = self.tables["current"]
        statement = select(table.c.type_bytes, table.c.id_bytes, table.c.id_key).where(
            table.c.type_key == self._bound_key(object_type),
            table.c.id_key > (self._bound_key(after) if after else ""),
        ).order_by(table.c.id_key).limit(limit)
        if self.engine.dialect.name == "mysql":
            statement = statement.with_hint(table, "FORCE INDEX (PRIMARY)", dialect_name="mysql")
        return statement

    def record_keys(self, object_type, *, after="", limit=100, connection=None):
        with self.engine.connect() if connection is None else nullcontext(connection) as conn:
            rows = conn.execute(self.record_keys_statement(object_type, after=after, limit=limit)).mappings().all()
        result = []
        for row in rows:
            raw = bytes(row["id_bytes"])
            if bytes(row["type_bytes"]) != object_type.encode() or hashlib.sha256(raw).hexdigest() != row["id_key"]:
                raise AdapterError("object_digest_collision")
            result.append(raw.decode())
        return result

    def type_count_statement(self, types):
        """Count requested opaque type prefixes, checking their original bytes."""
        if not types:
            raise AdapterError("A nonempty type collection is required")
        table = self.tables["current"]
        probes = []
        for type in types:
            statement = select(literal(type).label("type"), func.count().label("count"),
                func.sum(case((table.c.type_bytes != type.encode(), 1), else_=0)).label("invalid"))
            statement = statement.where(table.c.type_key == self._bound_key(type))
            if self.engine.dialect.name == "mysql":
                statement = statement.with_hint(table, "FORCE INDEX (PRIMARY)", dialect_name="mysql")
            probes.append(statement)
        return union_all(*probes) if len(probes) > 1 else probes[0]

    def count_types(self, types, *, connection=None):
        unique, result = list(dict.fromkeys(types)), {}
        for start in range(0, len(unique), 200):
            with self.engine.connect() if connection is None else nullcontext(connection) as conn:
                rows = conn.execute(self.type_count_statement(unique[start:start + 200])).mappings().all()
            for row in rows:
                if row["invalid"]:
                    raise AdapterError("object_digest_collision")
                result[row["type"]] = int(row["count"])
        return result

    def read_origins(self, keys, *, generation=None, immutable=False, connection=None):
        """Return exact records and the immutable batch's original producer."""
        unique, found = list(dict.fromkeys(keys)), {}
        for start in range(0, len(unique), 200):
            chunk = unique[start:start + 200]
            with self.engine.connect() if connection is None else nullcontext(connection) as conn:
                rows = conn.execute(self.origin_statement(chunk, generation=generation, immutable=immutable)).mappings().all()
            for row in rows:
                identity = bytes(row["type_bytes"]).decode(), bytes(row["id_bytes"]).decode()
                if identity not in chunk:
                    raise AdapterError("object_digest_collision")
                if identity in found:
                    raise AdapterError("ambiguous_record_origin")
                batch, run, intent = bytes(row["origin_batch"]), bytes(row["origin_run"]), bytes(row["origin_intent"])
                if (hashlib.sha256(batch).hexdigest() != row["batch_key"]
                        or hashlib.sha256(run).hexdigest() != row["origin_run_key"]
                        or hashlib.sha256(intent).hexdigest() != row["origin_hash"]
                        or row["origin_recorded_at"] is None or row["origin_recorded_at"] <= 0
                        or row["origin_event_batch"] != row["batch_key"]
                        or row["origin_observer"] is None or bytes(row["origin_observer"]) != run
                        or not immutable and row["generation"] != row["origin_generation"]):
                    raise AdapterError("record_origin_mismatch")
                found[identity] = {**self._read_record(row), "origin": {
                    "batch": batch.decode(), "run": run.decode(), "intent": intent,
                    "assessment": bytes(row["origin_assessment"]),
                    "generation": int(row["origin_generation"]),
                    "recorded_at": int(row["origin_recorded_at"]),
                }}
        return found

    def maintain_lookups(self, connection, *, expected_generation, changes, batch=None):
        """Owner-only derived-index maintenance; no batch, history or delivery.

        Direct table privileges remain with the owner. The destination gate
        fences authoritative reads and optimistic versions in this transaction.
        The caller must take that gate before preparing changes from records.
        """
        if self.protocol < 5:
            raise AdapterError("Lookup maintenance requires governed storage")
        counter(expected_generation)
        gate = self.tables["gate"]
        observed = connection.scalar(select(gate.c.generation).where(gate.c.id == 1).with_for_update())
        if observed != expected_generation:
            raise AdapterError("stale_generation")
        ledger = self.tables["migration"]
        count, ready = connection.execute(select(func.count(), func.min(ledger.c.complete))).one()
        if count != self.protocol or ready != 1:
            raise AdapterError("storage_not_initialized")
        provenance = self.tables["batch"]
        query = select(provenance.c.batch_key, provenance.c.batch_bytes, provenance.c.generation).where(
            provenance.c.batch_key == key(batch) if batch is not None else provenance.c.generation == observed)
        if batch is None and self.engine.dialect.name == "mysql":
            query = query.with_hint(provenance, f"FORCE INDEX ({self.prefix}_generation_unique)", dialect_name="mysql")
        origin = connection.execute(query).first()
        if (origin is None or origin.generation != observed
                or hashlib.sha256(bytes(origin.batch_bytes)).hexdigest() != origin.batch_key
                or batch is not None and bytes(origin.batch_bytes) != batch.encode()):
            raise AdapterError("Lookup maintenance requires current batch provenance")
        batch_key = origin.batch_key
        entries = list(changes)
        if len({(entry.type, entry.id) for entry in entries}) != len(entries):
            raise AdapterError("Duplicate lookup maintenance key")
        old = self.read([(entry.type, entry.id) for entry in entries], lookup=True, connection=connection)
        table = self.tables["lookup"]
        for entry in entries:
            entry.wire()
            held = old.get((entry.type, entry.id))
            if (held["version"] if held else 0) != entry.expected_version:
                raise AdapterError("stale_object_version")
        # Bound statement size without turning each reference into a round trip.
        for offset in range(0, len(entries), 200):
            chunk = entries[offset:offset + 200]
            removed = [entry for entry in chunk if entry.removed]
            if removed:
                selections = [select(self._bound_key(entry.type).label("type_key"),
                                     self._bound_key(entry.id).label("id_key")) for entry in removed]
                wanted = (union_all(*selections) if len(selections) > 1 else selections[0]).subquery("wanted")
                connection.execute(delete(table).where(table.c.type_key == wanted.c.type_key,
                                                       table.c.id_key == wanted.c.id_key))
            rows = []
            for entry in chunk:
                if entry.removed:
                    continue
                body = document(entry.body)
                rows.append({"type_key": key(entry.type), "id_key": key(entry.id),
                    "type_bytes": entry.type.encode(), "id_bytes": entry.id.encode(),
                    "body": body, "body_hash": hashlib.sha256(body).hexdigest(),
                    "batch_key": batch_key, "version": entry.expected_version + 1, "generation": observed})
            if rows:
                if self.engine.dialect.name == "postgresql":
                    from sqlalchemy.dialects.postgresql import insert as bulk_insert
                    statement = bulk_insert(table).values(rows)
                    statement = statement.on_conflict_do_update(
                        index_elements=[table.c.type_key, table.c.id_key],
                        set_={name: statement.excluded[name] for name in rows[0]
                              if name not in {"type_key", "id_key", "type_bytes", "id_bytes"}})
                else:
                    from sqlalchemy.dialects.mysql import insert as bulk_insert
                    statement = bulk_insert(table).values(rows)
                    statement = statement.on_duplicate_key_update(**{
                        name: statement.inserted[name] for name in rows[0]
                        if name not in {"type_key", "id_key", "type_bytes", "id_bytes"}})
                connection.execute(statement)
        return {"generation": observed, "changed": len(entries)}

    def batch_statement(self, batches, *, outboxes=False):
        """Exact batch seeks, optionally followed by its outbox primary-key prefix."""
        names = list(dict.fromkeys(batches))
        if not names:
            raise AdapterError("A nonempty batch key collection is required")
        parts = [select(self._bound_key(name).label("batch_key")) for name in names]
        wanted = (union_all(*parts) if len(parts) > 1 else parts[0]).subquery("wanted")
        batch = self.tables["batch"]
        if outboxes:
            table = self.tables["outbox"]
            columns = [*table.c, batch.c.batch_bytes, batch.c.generation]
            source = table.join(batch, table.c.batch_key == batch.c.batch_key)
        else:
            table, columns, source = batch, list(batch.c), batch
        condition = table.c.batch_key == wanted.c.batch_key
        if self.engine.dialect.name == "postgresql":
            probe = select(*columns).select_from(source).where(condition).offset(0).lateral("probe")
            return select(probe).select_from(wanted.join(probe, true()))
        return (select(*columns).select_from(wanted.join(source, condition))
                .prefix_with("STRAIGHT_JOIN", dialect="mysql")
                .with_hint(table, "FORCE INDEX (PRIMARY)", dialect_name="mysql"))

    def read_batches(self, batches, *, outboxes=False, connection=None):
        names, found = list(dict.fromkeys(batches)), []
        for offset in range(0, len(names), 400):
            chunk = names[offset:offset + 400]
            with self.engine.connect() if connection is None else nullcontext(connection) as conn:
                rows = conn.execute(self.batch_statement(chunk, outboxes=outboxes)).mappings().all()
            for row in rows:
                name = bytes(row["batch_bytes"]).decode()
                if name not in chunk or key(name) != row["batch_key"]:
                    raise AdapterError("Batch key digest collision")
                if outboxes:
                    if key(bytes(row["consumer_bytes"]).decode()) != row["consumer_key"]:
                        raise AdapterError("Publication consumer digest collision")
                    if hashlib.sha256(bytes(row["payload"])).hexdigest() != row["payload_hash"]:
                        raise AdapterError("Publication bytes differ from retained digest")
                else:
                    raw = bytes(row["intent"])
                    if hashlib.sha256(raw).hexdigest() != row["request_hash"]:
                        raise AdapterError("Batch intent differs from retained digest")
                    try:
                        assessment = bytes.fromhex(json.loads(raw)["assessment"])
                    except (KeyError,TypeError,ValueError):
                        raise AdapterError("Invalid retained batch intent") from None
                    if assessment != bytes(row["assessment"]):
                        raise AdapterError("Batch assessment differs from retained intent")
                found.append(dict(row))
        return found

    def generation_batch(self, generation, *, connection=None):
        """Seek one batch through the unique destination generation index."""
        counter(generation,positive=True)
        table = self.tables["batch"]
        query = select(table.c.batch_bytes).where(table.c.generation == generation)
        with self.engine.connect() if connection is None else nullcontext(connection) as conn:
            name = conn.scalar(query)
            return None if name is None else self.read_batches([bytes(name).decode()],connection=conn)[0]

    def observed_batches(self, observer, *, connection=None):
        if self.protocol < 6:
            raise AdapterError("Indexed observer lookup requires protocol 6")
        event, batch = self.tables["proposal_event"], self.tables["batch"]
        query = (select(event.c.observer_bytes, batch.c.batch_bytes)
                 .select_from(event.join(batch, event.c.batch_key == batch.c.batch_key))
                 .where(event.c.observer_key == self._bound_key(observer),
                        event.c.event.in_(("applied", "duplicate"))))
        if self.engine.dialect.name == "mysql":
            query = query.prefix_with("STRAIGHT_JOIN", dialect="mysql").with_hint(
                event, f"FORCE INDEX ({self.prefix}_proposal_observer)", dialect_name="mysql")
        with self.engine.connect() if connection is None else nullcontext(connection) as conn:
            rows = conn.execute(query).all()
        if any(bytes(row.observer_bytes).decode() != observer for row in rows):
            raise AdapterError("Observer key digest collision")
        return {bytes(row.batch_bytes).decode() for row in rows}

    def publication_context(self, batch, consumer, *, connection=None):
        if self.protocol < 6:
            raise AdapterError("Publication context requires protocol 6")
        table = self.tables["outbox_context"]
        query = select(table.c.body,table.c.body_hash).where(
            table.c.batch_key == self._bound_key(batch),table.c.consumer_key == self._bound_key(consumer))
        with self.engine.connect() if connection is None else nullcontext(connection) as conn:
            row = conn.execute(query).first()
        if row is None:
            return None
        body = bytes(row.body)
        if hashlib.sha256(body).hexdigest() != row.body_hash:
            raise AdapterError("Publication context differs from retained digest")
        return body

    def next_publication(self, consumer, *, connection=None):
        outbox, batch = self.tables["outbox"], self.tables["batch"]
        query = (select(batch.c.batch_bytes)
                 .select_from(outbox.join(batch, outbox.c.batch_key == batch.c.batch_key))
                 .where(outbox.c.consumer_key == self._bound_key(consumer), outbox.c.verified == 0)
                 .order_by(batch.c.generation).limit(1))
        if self.engine.dialect.name == "mysql":
            query = query.prefix_with("STRAIGHT_JOIN", dialect="mysql").with_hint(
                outbox, f"FORCE INDEX ({self.prefix}_outbox_status)", dialect_name="mysql")
        with self.engine.connect() if connection is None else nullcontext(connection) as conn:
            result = conn.scalar(query)
        return None if result is None else bytes(result).decode()

    def retain_metadata(self, type, id, body, *, expected_version=0, immutable=False, authority=None, expected_generation=None):
        """Destination-owned opaque CAS/immutable metadata; no business generation."""
        if self.protocol < 6:
            raise AdapterError("Execution metadata requires protocol 6")
        key(type)
        key(id)
        if type.__class__ is not str or immutable.__class__ is not bool:
            raise AdapterError("Invalid execution metadata")
        values = {"type": type.encode().hex(), "id": id.encode().hex(),
                  "body": document(body).hex(), "expected_version": counter(expected_version),
                  "immutable": int(immutable)}
        if authority is not None:
            values["authority"] = authority_wire(authority)
        if expected_generation is not None:
            values["expected_generation"] = counter(expected_generation)
        return int(self._rpc("retain_metadata", values)["stored_version"])

    def claim_outbox(self, batch: str, consumer: str, owner: str, *, seconds=300, authority=None, context=None):
        for value in (batch, consumer, owner):
            key(value)
        row = self._rpc(
            "claim_outbox",
            {
                "batch": batch.encode().hex(),
                "consumer": consumer.encode().hex(),
                "owner": owner.encode().hex(),
                "seconds": counter(seconds, positive=True),
                **({"context":document({} if context is None else context).hex()} if self.protocol >= 6 else {}),
            },
            authority=authority,
        )
        if row["verified"]:
            return None
        payload = bytes.fromhex(row["payload_hex"])
        if hashlib.sha256(payload).hexdigest() != row["payload_hash"]:
            raise AdapterError("Publication bytes differ from retained digest")
        if self.protocol >= 6:
            if self.publication_context(batch, consumer) is None:
                raise AdapterError("Publication context is missing")
        return {
            "payload": payload,
            "payload_hash": row["payload_hash"],
            "fence": int(row["fence"]),
            "expires": int(row["expires"]),
        }

    def ack_outbox(
        self, batch: str, consumer: str, owner: str, fence: int, receipt: str, *, authority=None
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
            authority=authority,
        )


    def release_outbox(self, batch, consumer, owner, fence, *, authority=None):
        if self.protocol < 6:
            raise AdapterError("Publication release requires protocol 6")
        for value in (batch, consumer, owner):
            key(value)
        return self._rpc("release_outbox", {"batch":batch.encode().hex(),
            "consumer":consumer.encode().hex(), "owner":owner.encode().hex(),
            "fence":counter(fence, positive=True)}, authority=authority)


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


def _grants(conn, adapter, runtime_role, runtime_host, *, runtime_execute=True):
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
            granted = conn.scalar(
                text("SELECT has_function_privilege(:r,:f,'EXECUTE')"),
                {"r": runtime_role, "f": name + "(text)"},
            )
            if not runtime_execute:
                if granted:
                    conn.exec_driver_sql(f"REVOKE EXECUTE ON FUNCTION {name}(text) FROM {role}")
                continue
            if not granted:
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
            or conn.scalar(text("SELECT @@mandatory_roles")) not in ("", "NONE")
            or conn.scalar(
                text("SELECT SUBSTRING_INDEX(CURRENT_USER(),'@',1)=:u"),
                {"u": runtime_role},
            )
        ):
            raise AdapterError("Runtime has broad or inherited privileges")
        for name in table_names:
            rights = conn.scalar(
                text(
                    "SELECT COUNT(*) FROM information_schema.TABLE_PRIVILEGES WHERE GRANTEE=:g AND TABLE_SCHEMA=:s AND TABLE_NAME=:t AND (PRIVILEGE_TYPE<>'SELECT' OR IS_GRANTABLE='YES')"
                ),
                {
                    "g": grantee,
                    "s": adapter.schema,
                    "t": name.rsplit(".", 1)[-1].strip("`"),
                },
            )
            if rights:
                raise AdapterError("Runtime already has direct storage writes")
            column_rights = conn.scalar(text(
                "SELECT COUNT(*) FROM information_schema.COLUMN_PRIVILEGES WHERE GRANTEE=:g "
                "AND TABLE_SCHEMA=:s AND TABLE_NAME=:t AND (PRIVILEGE_TYPE<>'SELECT' OR IS_GRANTABLE='YES')"),
                {"g": grantee,"s":adapter.schema,"t":name.rsplit(".",1)[-1].strip("`")})
            if column_rights:
                raise AdapterError("Runtime already has direct storage column writes")
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
            granted = conn.scalar(text(
                "SELECT COUNT(*) FROM mysql.procs_priv WHERE User=:u AND Host=:h AND Db=:s "
                "AND Routine_name=:t AND Routine_type='PROCEDURE' AND FIND_IN_SET('Grant',Proc_priv)>0"),
                {"u":runtime_role,"h":runtime_host,"s":adapter.schema,"t":name.rsplit(".",1)[-1].strip("`")})
            if granted:
                raise AdapterError("Runtime has grantable storage execution")
            if not runtime_execute:
                if conn.scalar(text(
                    "SELECT COUNT(*) FROM mysql.procs_priv WHERE User=:u AND Host=:h AND Db=:s "
                    "AND Routine_name=:t AND Routine_type='PROCEDURE'"),
                    {"u":runtime_role,"h":runtime_host,"s":adapter.schema,"t":name.rsplit(".",1)[-1].strip("`")}):
                    if getattr(adapter, "protocol", 1) < 5:
                        raise AdapterError("Runtime has unqualified storage execution")
                    conn.execute(text(f"REVOKE EXECUTE ON PROCEDURE {name} FROM :user@:host"),
                                 {"user": runtime_role, "host": runtime_host})
                continue
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


def _verify_migration_guards(conn, adapter, *, install=False):
    for name, function, ddl, table, body in adapter.migration_guards:
        if install and not inspect(conn).has_table(adapter.tables[table].name, schema=adapter.schema):
            continue
        values = {"schema": adapter.schema, "name": name, "table": adapter.tables[table].name}
        if conn.dialect.name == "postgresql":
            qualified = conn.dialect.identifier_preparer.format_table(adapter.tables[table])
            values.update(function=name + "_check", qualified=qualified)
            fn = conn.execute(text("SELECT p.prosrc,p.prosecdef,p.proconfig FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=:schema AND p.proname=:function AND p.pronargs=0"), values).first()
            if fn is None and install:
                conn.execute(text(function))
            elif (fn is None or fn[0] != body or not fn[1]
                  or not any(config.replace(" ", "") == "search_path=pg_catalog,pg_temp" for config in fn[2] or [])):
                raise AdapterError("Installed storage migration guard differs from this build")
            row = conn.execute(text("SELECT t.tgtype,t.tgenabled,t.tgqual,p.proname,n.nspname FROM pg_trigger t JOIN pg_proc p ON p.oid=t.tgfoid JOIN pg_namespace n ON n.oid=p.pronamespace WHERE t.tgrelid=to_regclass(:qualified) AND t.tgname=:name"), values).first()
            matches = row is not None and tuple(row) == (23, "O", None, name + "_check", adapter.schema)
        elif conn.dialect.name == "mysql":
            row = conn.execute(text("SELECT ACTION_STATEMENT,ACTION_TIMING,EVENT_MANIPULATION FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=:schema AND TRIGGER_NAME=:name AND EVENT_OBJECT_TABLE=:table"), values).first()
            matches = row is not None and tuple(row) == (body, "BEFORE", name.rsplit("_", 1)[1].upper())
        else:
            row = conn.execute(text("SELECT m.definition,m.execute_as_principal_id,t.is_disabled,t.is_instead_of_trigger FROM sys.triggers t JOIN sys.sql_modules m ON m.object_id=t.object_id JOIN sys.objects o ON o.object_id=t.parent_id JOIN sys.schemas s ON s.schema_id=o.schema_id WHERE s.name=:schema AND t.name=:name AND o.name=:table"), values).first()
            matches = row is not None and row[0].replace("\r\n", "\n").strip() == ddl.strip() and tuple(row[1:]) == (-2, False, False)
        if row is None and install:
            conn.execute(text(ddl))
        elif not matches:
            raise AdapterError("Installed storage migration guard differs from this build")


def _migration_statements(adapter) -> list[str]:
    engine = adapter.engine
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
    statements += [sql for _, function, trigger, *_ in getattr(adapter, "migration_guards", ())
                   for sql in (function, trigger) if sql is not None]
    if engine.dialect.name == "mysql":
        # SQLAlchemy orders these independent options through a set. Python's
        # hash seed must not change an immutable migration fingerprint.
        options = ("ENGINE=InnoDB", "CHARSET=ascii", "COLLATE ascii_bin")
        alternatives = "|".join(re.escape(" ".join(order)) for order in permutations(options))
        statements = [re.sub(r"(?m)\)(?:" + alternatives + r")$", ")" + " ".join(options), sql)
                      for sql in statements]
    return statements


def _migration_checksums(adapter) -> frozenset[str]:
    statements = _migration_statements(adapter)
    compiled = "\n".join(statements)
    variants = {compiled}
    if adapter.protocol == 1 and adapter.engine.dialect.name == "mysql":
        # Recognize only the exact historical compiler permutations. Retain
        # the installed ledger checksum verbatim; do not bless arbitrary DDL.
        options = ("ENGINE=InnoDB", "CHARSET=ascii", "COLLATE ascii_bin")
        variants.update(compiled.replace(")" + " ".join(options) + "\n",
                        ")" + " ".join(order) + "\n") for order in permutations(options))
    return frozenset(hashlib.sha256(sql.encode()).hexdigest() for sql in variants)


def migrate(
    engine, *, runtime_role: str, runtime_host="%", prefix="skill_merge", protocol=1,
    runtime_execute=True, defer_ready=False,
) -> dict:
    if type(protocol) is not int or protocol not in (1, 2, 3, 4, 5, 6):
        raise AdapterError("Unsupported storage protocol")
    if type(defer_ready) is not bool or defer_ready and (protocol < 5 or runtime_execute):
        raise AdapterError("Deferred activation requires governed storage without runtime execution")
    if type(runtime_execute) is not bool or not runtime_execute and engine.dialect.name != "mysql" and protocol < 5:
        raise AdapterError("Deferred runtime execution is qualified only for MySQL")
    builds = {version: Adapter(engine, prefix=prefix, protocol=version) for version in range(1, protocol + 1)}
    checksums = {version: hashlib.sha256("\n".join(_migration_statements(build)).encode()).hexdigest()
                 for version, build in builds.items()}
    adapter = builds[protocol]
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
        rows = conn.execute(select(ledger)).mappings().all()
        installed = {int(row["version"]): row for row in rows}
        if (len(installed) != len(rows) or set(installed) - set(builds)
                or any(row["checksum"] not in _migration_checksums(builds[version]) for version, row in installed.items())
                or installed and set(installed) != set(range(1, max(installed) + 1))):
            raise AdapterError("Installed storage migration differs from this build")
        fresh = any(version not in installed or not installed[version]["complete"] for version in builds)
        if installed and all(row["complete"] for row in installed.values()):
            _verify_capabilities(conn, builds[max(installed)])
        for version, build in builds.items():
            prior = installed.get(version)
            if prior is not None and prior["complete"]:
                continue
            if prior is None:
                if version >= 2:
                    _verify_migration_guards(conn, build, install=True)
                # Publish the pending version and disable old write routines
                # in one transaction, before any DDL (which may auto-commit).
                # Otherwise old routines can still write during a half-upgrade.
                with engine.begin() as barrier:
                    barrier.execute(update(ledger).values(complete=0))
                    barrier.execute(insert(ledger).values(version=version, checksum=checksums[version], complete=0))
            adapter.metadata.create_all(conn)
            if version >= 6:
                previous_indexes = {index.name for table in builds[version-1].tables.values()
                                    for index in table.indexes}
                for table in build.tables.values():
                    for index in table.indexes:
                        if index.name not in previous_indexes:
                            index.create(conn,checkfirst=True)
            if version >= 5:
                _verify_migration_guards(conn, build, install=True)
            gate = adapter.tables["gate"]
            if conn.scalar(select(gate.c.id).where(gate.c.id == 1)) is None:
                conn.execute(insert(gate).values(id=1, generation=0))
            for name, sql in build.routines.values():
                if engine.dialect.name == "mysql":
                    conn.exec_driver_sql(f"DROP PROCEDURE IF EXISTS {name}")
                conn.execute(text(sql))
            for _, function, trigger, table, trigger_name, _ in build.commit_guards:
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
        _verify_migration_guards(conn, adapter)
        _grants(conn, adapter, runtime_role, runtime_host, runtime_execute=runtime_execute)
        conn.execute(update(ledger).where(ledger.c.version.in_(builds)).values(complete=0 if defer_ready else 1))
    return {
        "initialized": fresh,
        "migration": protocol,
        "tables": len(adapter.tables),
        "engine": engine.dialect.name,
    }


def storage_version(conn, *, prefix="mdm_store") -> int:
    """Read the installed protocol marker by its small migration ledger."""
    schema = inspect(conn).default_schema_name
    _, tables = model(prefix, schema, protocol=1)
    ledger = tables["migration"]
    if not inspect(conn).has_table(ledger.name, schema=schema):
        return 0
    return int(conn.scalar(select(func.max(ledger.c.version))) or 0)


def migrate_registry(engine, *, runtime_role, configuration, kinds, runtime_host="%", prepared=False, prepared_protocol=5, runtime_execute=True):
    """Install the native governed registry through its owning command."""
    if __package__:
        from .registry_migration import migrate as migrate_native
    else:
        from registry_migration import migrate as migrate_native
    return migrate_native(engine, runtime_role=runtime_role, runtime_host=runtime_host,
                          configuration=configuration, kinds=kinds, prepared=prepared,
                          prepared_protocol=prepared_protocol, runtime_execute=runtime_execute)


def verify_native_registry(conn):
    if __package__:
        from .registry_migration import verify_postgres_registry
    else:
        from registry_migration import verify_postgres_registry
    return verify_postgres_registry(conn)


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
    setup.add_argument("--protocol", type=int, choices=(1, 2, 3, 4), default=1)
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
    apply.add_argument("--protocol", type=int, choices=(1, 2, 3, 4), default=1)
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
                protocol=args.protocol,
            )
        else:
            adapter = Adapter(engine, prefix=args.prefix, protocol=getattr(args, "protocol", 1))
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
                    payloads=raw.get("payloads_json", raw.get("payloads")),
                    indexes=tuple(IndexChange(
                        entry["type"], entry["id"], entry.get("body_json", entry.get("body")),
                        entry.get("expected_version", 0), entry.get("removed", False),
                    ) for entry in raw["indexes"]) if "indexes" in raw else None,
                    publish_inputs=raw.get("publish_inputs", False),
                )
                lease = adapter.claim(batch.scope, args.owner)
                output = adapter.apply(batch, lease, authority=raw.get("authority"))
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
