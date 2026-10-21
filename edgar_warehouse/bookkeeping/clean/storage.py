"""Typed control reads compiled for the selected database.

This module transports stored observations; it makes no workflow decisions.
Write authorization, leases and atomic transitions belong to the destination.
"""
from __future__ import annotations

from contextlib import contextmanager, nullcontext
from functools import lru_cache
import json

from sqlalchemy import (JSON, BigInteger, Boolean, Column, DateTime, LargeBinary,
                        MetaData, String, Table, UnicodeText, Uuid, and_, case, cast, column, func, literal, literal_column, select)
from sqlalchemy.dialects.mysql import BINARY, DATETIME, LONGTEXT
from sqlalchemy.dialects.mssql import DATETIMEOFFSET, VARBINARY
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator


class ExactJSON(TypeDecorator):
    """MySQL's native JSON type rounds large numbers; preserve prepared text."""
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(LONGTEXT(charset="utf8mb4", collation="utf8mb4_0900_bin"))

    def process_bind_param(self, value, dialect):
        from edgar_warehouse.control_contract import canonical
        return canonical(value)

    def process_result_value(self, value, dialect):
        return json.loads(value) if value is not None else None


@lru_cache(maxsize=3)
def tables(kind: str) -> dict[str, Table]:
    if kind not in {"postgresql", "mysql", "mssql"}:
        raise ValueError("Unsupported control storage engine")
    metadata = MetaData(schema=None if kind == "mysql" else "bookkeeping")
    document = JSON().with_variant(JSONB(), "postgresql").with_variant(ExactJSON(), "mysql")

    def table(name, columns):
        return Table("bookkeeping_" + name if kind == "mysql" else name, metadata,
                     *(Column(key, type_) for key, type_ in columns))

    uuid = Uuid(as_uuid=False)
    timestamp = DateTime(timezone=True).with_variant(DATETIME(fsp=6), "mysql").with_variant(DATETIMEOFFSET(), "mssql")
    return {
        "pipeline_run": table("pipeline_run", [
            ("run_id", uuid), ("submission", document), ("submission_hash", String(64)),
            ("expected_count", BigInteger), ("state", String(16)), ("checks", document),
            ("summary", document), ("pinned", Boolean), ("created_at", timestamp),
            ("completed_at", timestamp), ("compacted_at", timestamp), ("runtimes", document),
            ("document_hash", LargeBinary(32).with_variant(BINARY(32), "mysql"))]),
        "work_item": table("work_item", [
            ("run_id", uuid), ("step", UnicodeText), ("unit_key", UnicodeText), ("ordinal", BigInteger),
            ("resources", document), ("unit", document), ("state", String(16)),
            ("attempt", uuid), ("attempts", BigInteger), ("authority_until", timestamp),
            ("receipt", document), ("checks", document), ("error", UnicodeText),
            ("generated_count", BigInteger), ("candidate", document), ("reporter", UnicodeText),
            ("verifier", UnicodeText)]),
        "lease": table("lease", [
            ("resource", UnicodeText), ("token", BigInteger), ("run_id", uuid), ("attempt", uuid),
            ("expires_at", timestamp), ("heartbeat_at", timestamp)]),
        "checkpoint": table("checkpoint", [
            ("run_id", uuid), ("scope", UnicodeText), ("ordinal", BigInteger), ("cursor", document),
            ("receipt", document), ("resource", UnicodeText), ("revision", BigInteger)]),
        "journal_outbox": table("journal_outbox", [
            ("event_id", uuid), ("run_id", uuid), ("step", UnicodeText), ("unit_key", UnicodeText),
            ("payload", document), ("attempts", BigInteger), ("error", UnicodeText),
            ("created_at", timestamp), ("delivered_at", timestamp), ("event_type", UnicodeText)]),
    }


def rows(conn, statement):
    return [dict(row) for row in conn.execute(statement).mappings()]


def count(engine):
    return func.count_big(literal_column("*"), type_=BigInteger()) if engine.dialect.name == "mssql" else func.count()


def json_text(engine, document, key):
    """Retrieve a text field without SQL Server JSON_VALUE's 4,000-character limit."""
    if engine.dialect.name == "mssql":
        fields = func.openjson(document).table_valued(
            column("key", UnicodeText()), column("value", UnicodeText()))
        return select(fields.c.value).where(fields.c.key == key).scalar_subquery()
    return document[key].as_string()


def text_equal(engine, field, value):
    """Original keys remain exact even under a database's default collation."""
    if engine.dialect.name == "mysql":
        return and_(field == value, cast(field, BINARY()) == value.encode("utf-8"))
    if engine.dialect.name == "mssql":
        return and_(field == value, cast(field, VARBINARY(None)) == value.encode("utf-16-le"))
    return field == value


def has_json_key(engine, document, key):
    if engine.dialect.name == "postgresql":
        return document.op("?")(literal(key, UnicodeText()))
    if engine.dialect.name == "mysql":
        return func.json_contains_path(document, "one", "$." + key) == 1
    fields = func.openjson(document).table_valued(column("key", UnicodeText()))
    return select(1).select_from(fields).where(fields.c.key == key).exists()


@contextmanager
def consistent_read(engine):
    """Keep related observations in one snapshot or serializable read set."""
    isolation = "SERIALIZABLE" if engine.dialect.name == "mssql" else "REPEATABLE READ"
    with engine.connect().execution_options(isolation_level=isolation) as conn:
        with conn.begin():
            yield conn


def frozen(engine, run_id):
    with consistent_read(engine) as conn:
        return run(engine, run_id, connection=conn), work(engine, run_id, connection=conn)


def run(engine, run_id, *, connection=None):
    table = tables(engine.dialect.name)["pipeline_run"]
    with (nullcontext(connection) if connection is not None else engine.connect()) as conn:
        return rows(conn, select(*(column for column in table.c if column.name != "document_hash")
                                 ).where(table.c.run_id == run_id))


def work(engine, run_id, *, step=None, key=None, states=None, ordered=False, limit=None, connection=None):
    table = tables(engine.dialect.name)["work_item"]
    statement = select(table).where(table.c.run_id == run_id)
    for column, value in ((table.c.step, step), (table.c.unit_key, key)):
        if value is not None:
            statement = statement.where(text_equal(engine, column, value))
    if states is not None:
        statement = statement.where(table.c.state.in_(states))
    if ordered:
        statement = statement.order_by(table.c.step, table.c.ordinal)
    if limit is not None:
        statement = statement.limit(limit)
    with (nullcontext(connection) if connection is not None else engine.connect()) as conn:
        return rows(conn, statement)


def available_keys(engine, run_id, step, limit):
    named = tables(engine.dialect.name)
    work, lease = named["work_item"], named["lease"]
    clock = {"postgresql": func.clock_timestamp, "mysql": lambda: func.utc_timestamp(6),
             "mssql": func.sysutcdatetime}[engine.dialect.name]()
    live = select(1).where(and_(lease.c.run_id == work.c.run_id,
                               lease.c.attempt == work.c.attempt, lease.c.expires_at > clock)).exists()
    statement = select(work.c.unit_key).where(
        work.c.run_id == run_id, work.c.step == step,
        work.c.state.not_in(["verified", "reported"]), ~live).order_by(work.c.ordinal).limit(limit)
    with engine.connect() as conn:
        return list(conn.scalars(statement))


def reported(engine, run_id, steps, limit):
    table = tables(engine.dialect.name)["work_item"]
    statement = select(table.c.step, table.c.unit_key, table.c.attempt, table.c.candidate).where(
        table.c.run_id == run_id, table.c.step.in_(steps), table.c.state == "reported"
    ).order_by(table.c.step, table.c.ordinal).limit(limit)
    with engine.connect() as conn:
        return rows(conn, statement)


def checkpoint(engine, resource):
    table = tables(engine.dialect.name)["checkpoint"]
    statement = select(table).where(text_equal(engine, table.c.resource, resource))
    if engine.dialect.name == "mssql":
        statement = statement.with_hint(table, "WITH (FORCESEEK)", "mssql")
    with engine.connect() as conn:
        return rows(conn, statement)


def status(engine, run_id, limit):
    named = tables(engine.dialect.name)
    work, checkpoints, leases, outbox = (named[key] for key in
                                        ("work_item", "checkpoint", "lease", "journal_outbox"))
    with engine.connect() as conn:
        counts = rows(conn, select(work.c.state, count(engine).label("count")).where(
            work.c.run_id == run_id).group_by(work.c.state))
        items = rows(conn, select(*(work.c[key] for key in
            ("step", "unit_key", "ordinal", "state", "attempt", "attempts", "receipt", "checks", "error"))
        ).where(work.c.run_id == run_id).order_by(work.c.step, work.c.ordinal).limit(limit))
        progress = rows(conn, select(checkpoints).where(checkpoints.c.run_id == run_id))
        authority = rows(conn, select(leases).where(leases.c.run_id == run_id).order_by(
            leases.c.resource).limit(limit))
        pending = conn.scalar(select(count(engine)).select_from(outbox).where(
            outbox.c.run_id == run_id, outbox.c.delivered_at.is_(None)))
        deliveries = rows(conn, select(*(outbox.c[key] for key in
            ("event_id", "step", "unit_key", "attempts", "error", "delivered_at"))
        ).where(outbox.c.run_id == run_id).order_by(
            case((outbox.c.delivered_at.is_(None), 0), else_=1),
            outbox.c.delivered_at, outbox.c.created_at).limit(limit))
    return {"items": items, "counts": {row["state"]: row["count"] for row in counts},
            "checkpoints": progress, "leases": authority, "pending_deliveries": pending,
            "deliveries": deliveries}


def completion_observations(engine, run_id):
    """One statement observes the counters needed for a prepared completion."""
    named = tables(engine.dialect.name)
    run, work, outbox = (named[key] for key in ("pipeline_run", "work_item", "journal_outbox"))

    def work_count(*conditions):
        return select(count(engine)).select_from(work).where(
            work.c.run_id == run.c.run_id, *conditions).correlate(run).scalar_subquery()

    pending = select(count(engine)).select_from(outbox).where(
        outbox.c.run_id == run.c.run_id, outbox.c.delivered_at.is_(None)).correlate(run).scalar_subquery()
    statement = select(run.c.expected_count.label("expected"), work_count().label("actual"),
        work_count(work.c.state == "verified").label("verified"), pending.label("pending_deliveries"),
        work_count(work.c.generated_count.is_(None),
                   has_json_key(engine, work.c.unit["cursor"], "generated_step")).label("unsealed_expansions")
    ).where(run.c.run_id == run_id)
    with engine.connect() as conn:
        found = conn.execute(statement).mappings().first()
    if found is None:
        from edgar_warehouse.control_contract import Blocked
        raise Blocked("Unknown control run")
    return dict(found)


def resume_observations(engine, run_id):
    """Read exact storage tokens for the fields resumption may overwrite."""
    from .run_storage import _StorageSQL
    syntax = _StorageSQL(engine.dialect.name)
    run = tables(engine.dialect.name)["pipeline_run"].alias("p")
    statement = select(run.c.run_id, run.c.state, case((run.c.compacted_at.is_not(None), True), else_=False).label("compacted"),
        literal_column(syntax.text_value("p.checks"), UnicodeText()).label("checks_token"),
        literal_column(syntax.stamp_token("p.completed_at"), UnicodeText()).label("completion_token")
    ).select_from(run).where(run.c.run_id == run_id)
    with engine.connect() as conn:
        found = conn.execute(statement).mappings().first()
    if found is None:
        from edgar_warehouse.control_contract import Blocked
        raise Blocked("Unknown control run")
    return dict(found)


def pending_events(engine, run_id, limit):
    table = tables(engine.dialect.name)["journal_outbox"]
    statement = select(table).where(table.c.run_id == run_id, table.c.delivered_at.is_(None)
                                   ).order_by(table.c.created_at, table.c.event_id).limit(limit)
    with engine.connect() as conn:
        return rows(conn, statement)


def runs(engine, limit, *, state=None):
    table = tables(engine.dialect.name)["pipeline_run"]
    statement = select(*(table.c[key] for key in
        ("run_id", "state", "created_at", "completed_at", "expected_count", "summary")),
        *(json_text(engine, table.c.submission, key).label(key) for key in ("kind", "name", "target")))
    if state is not None:
        statement = statement.where(table.c.state == state)
    statement = statement.order_by(table.c.created_at.desc(), table.c.run_id).limit(limit)
    with engine.connect() as conn:
        return rows(conn, statement)


def capture_runs_statement(engine, *, kind, source, target):
    import edgar_control
    table = tables(engine.dialect.name)["pipeline_run"]
    statement = select(table.c.run_id, table.c.state, table.c.created_at,
                       table.c.compacted_at, json_text(engine, table.c.submission, "capture").label("capture")).where(
        table.c.document_hash == bytes.fromhex(edgar_control.hash_text(f"{kind}:{source}:{target}")),
        json_text(engine, table.c.submission, "kind") == kind,
        json_text(engine, table.c.submission, "name") == source,
        json_text(engine, table.c.submission, "target") == target)
    if engine.dialect.name == "mssql":
        statement = statement.with_hint(table, "WITH (FORCESEEK)", "mssql")
    return statement


def capture_runs(engine, *, kind, source, target, connection=None):
    """Read one indexed document's run metadata; no work rows cross this boundary."""
    with (nullcontext(connection) if connection is not None else engine.connect()) as conn:
        return rows(conn, capture_runs_statement(engine, kind=kind, source=source, target=target))


def verified_units(engine, run_ids, step, *, connection=None):
    named = tables(engine.dialect.name)
    run, work = named["pipeline_run"], named["work_item"]
    result = []
    # Grouped indexed reads respect every selected driver's parameter limit.
    with (nullcontext(connection) if connection is not None else engine.connect()) as conn:
        for start in range(0, len(run_ids), 400):
            statement = select(work.c.run_id.label("run"), work.c.step,
                work.c.unit_key.label("key"), json_text(engine, work.c.receipt, "sha256").label("sha256"),
                run.c.completed_at).select_from(work.join(run, work.c.run_id == run.c.run_id)).where(
                    work.c.run_id.in_(run_ids[start:start + 400]),
                    work.c.step == step, work.c.state == "verified")
            if engine.dialect.name == "mssql":
                statement = statement.with_hint(work, "WITH (FORCESEEK)", "mssql").with_hint(
                    run, "WITH (FORCESEEK)", "mssql")
            result.extend(rows(conn, statement))
    return result
