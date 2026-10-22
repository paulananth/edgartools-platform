"""Journal storage only: indexed reads and a restricted atomic insertion interface."""
from __future__ import annotations

import edgar_control
import json
from datetime import UTC

from sqlalchemy import BigInteger, Column, DateTime, LargeBinary, MetaData, Table, Text, and_, bindparam, func, literal_column, select, text
from sqlalchemy.exc import DBAPIError


def event_table(engine):
    name = engine.dialect.name
    if name not in {"postgresql", "mysql", "mssql"}:
        raise ValueError("Journal storage has not been qualified for this database engine")
    return Table("journal_event" if name == "mysql" else "event", MetaData(),
        Column("id", BigInteger), Column("producer", Text), Column("event_key", Text),
        Column("key_hash", LargeBinary(32)), Column("run_id", Text), Column("source", Text), Column("feed", Text),
        Column("event_type", Text), Column("occurred_at", Text), Column("recorded_at", DateTime(timezone=True)),
        Column("canonical_body", Text), Column("canonical_hash", Text),
        schema=None if name == "mysql" else "journal")


def readable_table(engine):
    event = event_table(engine)
    return Table("journal_records" if engine.dialect.name == "mysql" else "event_records", MetaData(),
        *(Column(c.name, c.type) for c in event.c), schema=event.schema)


def assert_ready(conn):
    from edgar_warehouse.control_contract import Blocked
    name=conn.dialect.name
    if name=="postgresql": return
    view="journal_readiness" if name=="mysql" else "journal.readiness"
    if conn.scalar(text(f"SELECT complete FROM {view}"))!=1:
        raise Blocked("Journal migration incomplete")


def transport_row(row):
    value = dict(row)
    for key in ("producer", "event_key", "canonical_body", "canonical_hash"):
        if isinstance(value.get(key), bytes):
            value[key] = value[key].decode("utf-8")
    stamp = value["recorded_at"]
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    value["recorded_at"] = stamp.isoformat()
    result={key: value[key] for key in ("id", "canonical_body", "canonical_hash", "recorded_at")}
    if "recorded_at_epoch" in value:
        result["recorded_at_epoch"]=str(value["recorded_at_epoch"])
    return result


def record_event(engine, body, content_hash):
    name = engine.dialect.name
    statement = {"postgresql": "SELECT journal.record_event(:b,:h)",
        "mysql": "CALL journal_record_event(:b,:h)",
        "mssql": "EXEC journal.record_event @body=:b,@content_hash=:h"}[name]
    with engine.begin() as conn:
        assert_ready(conn)
        conn.execute(text(statement), {"b": body, "h": content_hash})


def key_condition(engine, table, producer, event_key):
    if engine.dialect.name == "mysql":
        return and_(table.c.producer == producer.encode(), table.c.key_hash == bytes.fromhex(edgar_control.hash_text(event_key)), table.c.event_key == event_key.encode())
    if engine.dialect.name == "mssql":
        from sqlalchemy import cast
        from sqlalchemy.dialects.mssql import VARBINARY
        return and_(table.c.producer == producer, table.c.key_hash == bytes.fromhex(edgar_control.hash_text(event_key)),
            cast(table.c.event_key, VARBINARY(None)) == event_key.encode("utf-16-le"))
    return and_(table.c.producer == producer, table.c.key_hash == bytes.fromhex(edgar_control.hash_text(event_key)), table.c.event_key == event_key)


def read_events_statement(engine, table):
    # MySQL exposes TIMESTAMP columns in the session's timezone. Retrieve its
    # exact decimal UTC epoch so native receipt construction never guesses it.
    return (select(table,func.unix_timestamp(table.c.recorded_at).label("recorded_at_epoch"))
            if engine.dialect.name=="mysql" else select(table))


def get_event(engine, producer, event_key):
    table = readable_table(engine)
    with engine.connect() as conn:
        assert_ready(conn)
        query=read_events_statement(engine,table).where(key_condition(engine,table,producer,event_key))
        if engine.dialect.name=="mssql":query=query.with_hint(table,"WITH (FORCESEEK)","mssql")
        row = conn.execute(query).mappings().first()
    return transport_row(row) if row else None


def list_events(engine, *, source=None, feed=None, run_id=None, limit=100, after=0):
    table = readable_table(engine)
    query = read_events_statement(engine,table).where(table.c.id > after)
    for column, value in ((table.c.source, source), (table.c.feed, feed), (table.c.run_id, run_id)):
        if value is not None:
            query = query.where(column == value)
    with engine.connect() as conn:
        assert_ready(conn)
        return [transport_row(row) for row in conn.execute(query.order_by(table.c.id).limit(limit)).mappings()]


def find_keys_statement(engine, producer, group):
    table = readable_table(engine)
    if engine.dialect.name == "postgresql":
        condition = and_(table.c.producer == producer, table.c.key_hash.in_([bytes.fromhex(edgar_control.hash_text(key)) for key in group]))
    else:
        condition = and_(table.c.producer == (producer.encode() if engine.dialect.name == "mysql" else producer),
            table.c.key_hash.in_([bytes.fromhex(edgar_control.hash_text(key)) for key in group]))
    query=select(table.c.event_key).where(condition)
    return query.with_hint(table,"WITH (FORCESEEK)","mssql") if engine.dialect.name=="mssql" else query


def found_events(engine, producer, keys):
    found = set()
    unique = list(dict.fromkeys(keys))
    # Bound driver parameters on every engine; each group uses the producer/key index.
    for start in range(0,len(unique),400):
        query = find_keys_statement(engine, producer, unique[start:start+400])
        with engine.connect() as conn:
            assert_ready(conn)
            values = conn.execute(query).scalars()
            found.update(key.decode() if isinstance(key,bytes) else key for key in values)
    # The full original key is verified even in the theoretical case of a hash collision.
    return found.intersection(keys)


def event_status(engine, *, source=None, feed=None):
    table = readable_table(engine)
    count = func.count_big(literal_column("*"), type_=BigInteger()) if engine.dialect.name == "mssql" else func.count()
    query=select(count.label("events"),func.max(table.c.id).label("last_id"))
    for column,value in ((table.c.source,source),(table.c.feed,feed)):
        if value is not None: query=query.where(column==value)
    with engine.connect() as conn:
        assert_ready(conn)
        counts=conn.execute(query).mappings().one()
    return {"database":engine.url.database,"events":counts["events"],"last_id":counts["last_id"],"source":source,"feed":feed}
