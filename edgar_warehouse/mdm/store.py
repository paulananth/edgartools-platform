"""Governed transaction boundary and durable publication capabilities.

Pure projection code prepares bounded effects; only the destination capability may persist
master changes. Network publication always runs outside that transaction.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine


class Conflict(ValueError):
    """Evidence or a checkpoint disagrees with retained history."""


def identifier_values(item: Any) -> list[str]:
    """The values one identifier holds: a text value, or a nonempty list of
    them (a FIGI per listing, ticket 138). `None` holds none. The source
    engine reads them by the same rule (`read_identifier_values`)."""
    if item is None:
        return []
    if isinstance(item, str):
        return [item]
    if isinstance(item, list) and item and all(isinstance(one, str) for one in item):
        return list(item)
    raise Conflict("An identifier holds a text value or a nonempty list of them")


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


# The current schema, then each later file once, in order, by checksum.
# A later change to the schema is a new numbered file added to MIGRATIONS.
BASELINE = "schema.sql"
MIGRATIONS: tuple[str, ...] = ()


def migrate(engine: Engine, *, application_role: str) -> dict:
    """The init stamp (PostgreSQL's `mdm` schema), then the mastering tables every merge writes."""
    result = _stamp(engine, application_role=application_role) if engine.dialect.name == "postgresql" else {}
    from edgar_warehouse.mastering import store as mastering

    mastering.install(engine, runtime_role=application_role)
    return result


def _stamp(engine: Engine, *, application_role: str) -> dict:
    """Record once which schema init installed, by its checksum; a store holding another one is refused.
    Role provisioning stays outside this function; deployments provide the restricted login role."""
    if engine.dialect.name != "postgresql":
        raise ValueError("MDM requires PostgreSQL 16")
    path = Path(__file__).parent / "migrations" / BASELINE
    source = path.read_text()
    checksum = hashlib.sha256(source.encode()).hexdigest()
    quote = engine.dialect.identifier_preparer.quote
    with engine.begin() as conn:
        if int(conn.scalar(text("SHOW server_version_num"))) // 10000 != 16:
            raise ValueError("MDM requires PostgreSQL 16")
        conn.execute(text("SELECT pg_advisory_xact_lock(730233)"))
        # Saves take this lock before touching master tables. Take it before
        # migration DDL too, so table locks cannot invert that order.
        conn.execute(text("SELECT pg_advisory_xact_lock(730234)"))
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
        installed = conn.scalar(text("SELECT to_regclass('mdm.migration')"))
        if installed:
            saved = conn.scalar(
                text("SELECT checksum FROM mdm.migration WHERE name=:name"),
                {"name": path.name},
            )
            if saved is None:
                raise Conflict("This MDM store does not hold this build's schema; rebuild the store")
            if saved != checksum:
                raise Conflict("Installed migration checksum differs")
        else:
            if conn.scalar(text("SELECT to_regnamespace('mdm')")):
                raise Conflict("This MDM store does not hold this build's schema; rebuild the store")
            # Execute the real SQL file, including PL/pgSQL bodies, atomically.
            conn.exec_driver_sql(source.replace("%", "%%"))
            conn.execute(
                text("INSERT INTO mdm.migration(name,checksum) VALUES(:name,:checksum)"),
                {"name": path.name, "checksum": checksum},
            )
        for name in MIGRATIONS:
            extra = path.with_name(name)
            extra_source = extra.read_text()
            extra_hash = hashlib.sha256(extra_source.encode()).hexdigest()
            saved = conn.scalar(
                text("SELECT checksum FROM mdm.migration WHERE name=:n"),
                {"n": extra.name},
            )
            if saved is None:
                conn.execute(text(extra_source))
                conn.execute(
                    text("INSERT INTO mdm.migration(name,checksum) VALUES(:n,:h)"),
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
                    f"REVOKE ALL ON ALL TABLES IN SCHEMA mdm FROM {role_sql}"
                )
                conn.exec_driver_sql(
                    f"REVOKE ALL ON ALL FUNCTIONS IN SCHEMA mdm FROM {role_sql}"
                )
                conn.exec_driver_sql(f"REVOKE ALL ON SCHEMA mdm FROM {role_sql}")
        runtime = quote(application_role)
        conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA mdm TO {runtime}")
        conn.exec_driver_sql(f"GRANT SELECT ON ALL TABLES IN SCHEMA mdm TO {runtime}")
        if conn.scalar(
            text("SELECT has_schema_privilege(:r,'mdm','CREATE')"),
            {"r": application_role},
        ):
            raise ValueError(
                "Runtime role inherits schema ownership or CREATE privilege"
            )
        leaked = conn.scalar(
            text("""SELECT count(*) FROM pg_tables WHERE schemaname='mdm'
            AND (has_table_privilege(:r,format('%I.%I',schemaname,tablename),'INSERT,UPDATE,DELETE,TRUNCATE')
              OR has_any_column_privilege(:r,format('%I.%I',schemaname,tablename),'INSERT,UPDATE'))"""),
            {"r": application_role},
        )
        if leaked:
            raise ValueError("Runtime role inherits direct MDM writes")
    return {"migration": path.name, "checksum": checksum, "installed": not bool(installed)}


def register_policy(conn: Connection, body: dict) -> str:
    """On a Rules Database connection of the governance login; the loader cannot add to the registry.

    A body is refused, by name and with its reason, unless every rule in it is
    well formed and every `automatic_rules` entry names a rule version it holds
    (`activation.check_policy`).
    """
    from .activation import check_policy, rule_version_conflicts

    from edgar_warehouse.rules import registry

    check_policy(body)
    registered = [b for b in registry.policies(conn) if "kinds" in b]
    reused = rule_version_conflicts(body, registered)
    if reused:
        # A rule version names one exact set of steps (§10 check 9). A new
        # version is free; reusing one for different steps would let one record
        # classify two ways with no trace.
        raise Conflict(
            "Rule version already registered with different steps: "
            + ", ".join(f"{k}/{r}@{v}" for k, r, v in reused)
        )
    # A kind's field rules live in one place. Refuse the ambiguity at
    # registration rather than mid-merge, so a body that would silently prefer
    # one block never reaches a batch (company mastering ticket 02, decision 1).
    if body.get("kinds") and body.get("fields"):
        raise ValueError("A kind's field rules belong in one place, not two")
    consumers = body.get("required_consumers", [])
    if (
        not consumers
        or len(set(consumers)) != len(consumers)
        or not all(isinstance(c, str) and c for c in consumers)
    ):
        raise ValueError("A policy requires distinct nonempty consumer names")
    return registry.add_policy(conn, body)


def _issued_namespaces(conn: Connection | None, code: str) -> frozenset[str]:
    """Every namespace an Identifier Contract in any registered policy names
    this dataset as issuing. Without a connection, none."""
    if conn is None:
        return frozenset()
    from edgar_warehouse.rules import registry

    bodies = registry.policies(conn)
    return frozenset(
        namespace
        for body in bodies
        for block in (body.get("kinds") or {}).values()
        for namespace, contract in (block.get("identifiers") or {}).items()
        if code in (contract.get("sources") or ())
    )


def _check_cross_references(adapter: dict, issued: frozenset[str]) -> None:
    """A cross-reference is lookup only (profiling ticket 03): it is never a
    master's identifier. A namespace that is also one of the contract's
    identifiers is refused, and so is one the dataset itself issues
    (`issued`), whose value belongs among its identifiers. A namespace another
    source issues is the filer's copy: a matching rule on it finds the master
    holding it, never gives it (Design 5, operator 2026-10-26: "Lookup only")."""
    from .activation import NAMESPACE

    names = adapter.get("cross_references", {})
    formats = adapter.get("cross_reference_formats", {})
    if not isinstance(names, dict) or not isinstance(formats, dict):
        raise ValueError("cross_references and cross_reference_formats map a namespace to a path or a format")
    for namespace in names:
        if not isinstance(namespace, str) or not NAMESPACE.fullmatch(namespace):
            raise ValueError(f"A cross-reference namespace is lower-case words: {namespace!r}")
        if namespace in adapter.get("identifiers", {}):
            raise ValueError(f"Cross-reference {namespace} is also an identifier of this contract")
        if namespace in issued:
            raise ValueError(f"Cross-reference {namespace} names a namespace this dataset issues; map it as an identifier")
    if set(formats) - set(names):
        raise ValueError(f"A format for no cross-reference: {sorted(set(formats) - set(names))}")


def _check_details(adapter: dict) -> None:
    """A configured detail list names its row key and the reading's details column."""
    from .activation import NAMESPACE

    keys = adapter.get("detail_keys")
    if keys is None:
        return
    if not isinstance(keys, dict) or not keys or any(
            not isinstance(name, str) or not NAMESPACE.fullmatch(name) or not isinstance(key, str) or not key
            for name, key in keys.items()):
        raise ValueError("detail_keys maps each detail list, lower-case words, to the field that keys its rows")
    if "kind" not in adapter:
        raise ValueError("Detail lists require a stated kind")
    columns = ((adapter.get("reading") or {}).get("read", {}).get("tables", {}).get("mapped", {}).get("columns", {}))
    if "details" not in columns:
        raise ValueError("A contract with detail_keys states its rows in the reading's details column")


def register_dataset(
    conn: Connection,
    code: str,
    body: dict,
    *,
    rules_authority: dict | None = None,
) -> None:
    """Pin a dataset to an approved, frozen Rules source version."""
    reasons = body.get("nonblocking_deferred_reasons", [])
    if (
        not isinstance(reasons, list)
        or any(not isinstance(r, str) or not r for r in reasons)
        or len(set(reasons)) != len(reasons)
    ):
        raise ValueError("nonblocking_deferred_reasons requires distinct reason names")
    adapter = body.get("adapter", {})
    if {"fields", "matching", "field_shape"} & set(adapter):
        # The reading is the contract's one statement of a record's fields and
        # matching values; a contract without one is refused when it maps a record.
        raise ValueError("adapter.fields, adapter.matching and adapter.field_shape are no contract keys; "
                         "the contract's reading states them")
    if adapter.get("classification") and ("kind" in adapter or "kind_field" in adapter):
        # One writer of the kind: the contract states it when every record is
        # that kind, or names the rule that decides it, never both (ADR 0015).
        raise ValueError(
            "A Dataset Contract states a kind or names a classification rule, not both"
        )
    from .evidence import KINDS

    probable = adapter.get("probable_kind_values", {})
    if not isinstance(probable, dict) or any(v not in KINDS for v in probable.values()):
        raise ValueError("probable_kind_values must map source values to kinds")
    from .adapters import FORMATS

    _check_cross_references(adapter, _issued_namespaces(conn, code))
    _check_details(adapter)
    formats = [
        adapter.get("record_key_format"),
        *adapter.get("identifier_formats", {}).values(),
        *adapter.get("cross_reference_formats", {}).values(),
    ]
    if any(f is not None and f not in FORMATS for f in formats):
        raise ValueError("Unknown format in Dataset Contract")
    if "quality" in body:
        from .quality import QualityError, check_quality, exception_reasons

        try:
            check_quality(body["quality"])
        except QualityError as exc:
            raise ValueError(str(exc)) from exc
        # A data quality exception sets its record aside and never stops the
        # run (operator, 2026-09-28), so its reason must be non-blocking.
        missing = exception_reasons(body["quality"]) - set(reasons)
        if missing:
            raise ValueError(f"List the quality exceptions as nonblocking_deferred_reasons: {sorted(missing)}")
    if rules_authority is None:
        raise Conflict("Dataset requires approved frozen Rules source authority")
    missing = sorted(set(CONTRACT_PARTS) - set(body))
    if missing:
        raise ValueError(f"A Dataset Contract names {', '.join(missing)}")
    from edgar_warehouse.rules import registry
    from edgar_warehouse.rules.acquisition_authority import registration_authority

    evidence = registration_authority(rules_authority, code, body)
    authority_version = evidence["version_id"]
    # Pin the authority after the comparison below, not before: a registry
    # version bump is not a mapping change, and must not mint a reading that
    # would fork every later assertion id for a mapping nobody corrected.
    pinned = {**body, "registry_evidence": evidence}
    current = registry.reading(conn, code)
    if current is not None:
        stored = current["body"]
        if stored == pinned and current["registry_version"] == authority_version:
            return
        if _mapping_of(stored) == _mapping_of(pinned):
            raise Conflict(
                "Dataset mapping is unchanged; a registry version bump is not a new reading"
            )
        protected_change(stored, pinned)
        registry.add_reading(conn, code, current["mapping_version"] + 1, pinned, str(UUID(authority_version)))
        return
    registry.add_reading(conn, code, 1, pinned, str(UUID(authority_version)))


# What every Dataset Contract states.
CONTRACT_PARTS = ("provider", "family", "schema_version", "record_key", "publication_key", "effective_time", "semantics")


def _mapping_of(body: dict) -> dict:
    """A contract without the registry authority pinned onto it."""
    return {k: v for k, v in body.items() if k != "registry_evidence"}


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


def current_reading(conn: Connection, code: str) -> tuple[int, dict] | None:
    """The reading a source is read under now, with the body that defines it.

    One accessor, so that a caller cannot take the contract body without the
    reading number that produced it. Reading them apart is how an adapter ends
    up stamping version 1 onto a record it read under a corrected mapping.
    `conn` is a Rules Database connection (`edgar_warehouse.rules.registry`).
    """
    from edgar_warehouse.rules import registry

    found = registry.reading(conn, code)
    return (found["mapping_version"], found["body"]) if found is not None else None


def reading_at(conn: Connection, code: str, mapping_version: int) -> tuple[int, dict]:
    """One named reading of a source, whatever the current one is.

    A run pins the readings it started under, so resuming it resolves those
    rather than whatever has been registered since. Without this, registering
    a corrected mapping mid-run changes the reconstructed run scope and the
    run can never be resumed (Codex review of PR #695, P1).
    """
    from edgar_warehouse.rules import registry

    found = registry.reading(conn, code, mapping_version)
    if found is None:
        raise Conflict(
            f"Run pins reading {mapping_version} of {code}, which is not registered"
        )
    return found["mapping_version"], found["body"]


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
