"""Typed reference-data storage; business decisions belong to the RDM caller.

Unbounded keys stay verbatim. MySQL indexes hashes of length-delimited JSON
tuples and every lookup also compares the original fields using a binary,
non-padding collation. Hash collisions therefore refuse writes, never alias
two reference values. PostgreSQL retains its existing indexed text keys.
"""
from functools import lru_cache
from contextlib import contextmanager

from sqlalchemy import (Column, Computed, Date, Index, Integer,
                        MetaData, String, Table, Text, and_, cast, func, literal, text)
from sqlalchemy.dialects.mysql import LONGTEXT

from edgar_warehouse.control_contract import Blocked
from edgar_warehouse.database_types import ExactJSON, UTCDateTime


KEYS = {
    "code_set": ("code_set",),
    "code_set_version": ("code_set", "version"),
    "code": ("code_set", "version", "code"),
    "code_label": ("code_set", "version", "code", "language", "label"),
    "level": ("code_set", "version", "depth"),
    "code_path": ("code_set", "version", "code"),
    "crosswalk_row": ("from_set", "from_version", "from_code", "to_set", "to_version", "to_code"),
    "code_set_usage": ("code_set", "version", "store", "object", "field"),
    "code_set_hint": ("code_set", "version", "kind", "ordinal"),
}


def tuple_hash(*values):
    """The same expression for stored keys and bound lookup keys."""
    from sqlalchemy import LargeBinary

    return func.sha2(cast(func.json_array(*values), LargeBinary), 256)


@lru_cache
def tables(dialect: str) -> dict[str, Table]:
    if dialect not in {"postgresql", "mysql"}:
        raise Blocked("Reference storage currently supports PostgreSQL and MySQL")
    metadata = MetaData(schema="rdm" if dialect == "postgresql" else None)
    words = Text().with_variant(LONGTEXT(charset="utf8mb4", collation="utf8mb4_0900_bin"), "mysql")
    body = ExactJSON()
    moment = UTCDateTime()
    created = text("(UTC_TIMESTAMP(6))") if dialect == "mysql" else func.clock_timestamp()

    def text_column(name, *, nullable=False):
        return Column(name, words, nullable=nullable)

    def table(name, *columns):
        found = Table(name, metadata, *columns, mysql_engine="InnoDB",
                      mysql_charset="utf8mb4", mysql_collate="utf8mb4_0900_bin")
        if dialect == "mysql":
            q = lambda field: "`" + field + "`"
            def expression(fields):
                return "sha2(cast(json_array(" + ",".join(q(f) for f in fields) + ") as binary),256)"
            # MySQL forbids generated primary keys. The owner-installed BEFORE
            # INSERT trigger computes this key; runtime cannot supply it.
            found.append_column(Column("_row_key", String(64, collation="ascii_bin"),
                                       primary_key=True, server_default=""))
            fields = ("from_set", "from_version") if name == "crosswalk_row" else ("code_set", "version")
            if name != "code_set":
                found.append_column(Column("_version_key", String(64, collation="ascii_bin"),
                                           Computed(expression(fields), persisted=True)))
                Index(name + "_version_lookup", found.c._version_key)
            if name == "code_set_version":
                found.append_column(Column("_set_key", String(64, collation="ascii_bin"),
                                           Computed(expression(("code_set",)), persisted=True)))
                Index("version_set_lookup", found.c._set_key)
                found.append_column(Column("_current_key", String(64, collation="ascii_bin"),
                    Computed("case when status='published' and valid_to is null then "
                             + expression(("code_set",)) + " else null end", persisted=True)))
                Index("one_current_published", found.c._current_key, unique=True)
            if name == "code_label":
                found.append_column(Column("_preferred_key", String(64, collation="ascii_bin"),
                    Computed("case when kind='preferred' then "
                             + expression(("code_set", "version", "code", "language"))
                             + " else null end", persisted=True)))
                Index("one_preferred_label", found.c._preferred_key, unique=True)
            if name in {"code", "code_label"}:
                # Keep exact labels and their keys binary. The search index has
                # its own case-insensitive, accent-sensitive representation,
                # maintained by the destination trigger.
                found.append_column(Column("_search_text", LONGTEXT(charset="utf8mb4", collation="utf8mb4_0900_as_ci"),
                                           nullable=False, server_default=text("('')")))
                found.append_column(Column("_search_tokens", LONGTEXT(charset="ascii", collation="ascii_bin"),
                                           nullable=False, server_default=text("('')")))
                Index(name + "_search_tokens_words", found.c._search_tokens, mysql_prefix="FULLTEXT")
        return found

    result = {}
    result["code_set"] = table("code_set", *(text_column(n) for n in
        ("code_set", "name", "definition", "authority", "steward")),
        Column("created_at", moment, nullable=False, server_default=created))
    result["code_set_version"] = table("code_set_version",
        *(text_column(n) for n in ("code_set", "version", "created_by")),
        Column("status", words, nullable=False, server_default=text("('draft')")),
        *(text_column(n, nullable=True) for n in ("supersedes", "approved_by", "approved_words", "sha256")),
        Column("evidence", body, nullable=False),
        Column("created_at", moment, nullable=False, server_default=created),
        *(Column(n, moment) for n in ("valid_from", "valid_to", "approved_at", "published_at")))
    result["code"] = table("code", *(text_column(n) for n in
        ("code_set", "version", "code", "label", "definition", "status")),
        text_column("parent_code", nullable=True), text_column("invalid_reason", nullable=True),
        Column("valid_from", Date), Column("valid_to", Date))
    result["code_label"] = table("code_label", *(text_column(n) for n in
        ("code_set", "version", "code", "language", "label", "kind", "source")))
    result["level"] = table("level", *(text_column(n) for n in
        ("code_set", "version", "name", "definition")), Column("depth", Integer, nullable=False))
    result["code_path"] = table("code_path", *(text_column(n) for n in
        ("code_set", "version", "code", "path", "label_path")),
        text_column("level", nullable=True), Column("depth", Integer, nullable=False))
    result["crosswalk_row"] = table("crosswalk_row", *(text_column(n) for n in
        ("from_set", "from_version", "from_code", "to_set", "to_version", "to_code", "match_type")),
        Column("evidence", body, nullable=False))
    result["code_set_usage"] = table("code_set_usage", *(text_column(n) for n in
        ("code_set", "version", "store", "object", "field", "match", "note")))
    result["code_set_hint"] = table("code_set_hint", *(text_column(n) for n in
        ("code_set", "version", "kind", "text")), Column("ordinal", Integer, nullable=False))
    return result


def scope(conn, table: Table, **values):
    """An indexed scope plus exact original-key comparisons."""
    terms = [table.c[name] == value for name, value in values.items()]
    if conn.dialect.name == "mysql":
        name = getattr(table, "original", table).name
        key = KEYS[name]
        version = ("from_set", "from_version") if name == "crosswalk_row" else ("code_set", "version")
        def bound(value):
            return value if hasattr(value, "__clause_element__") else literal(value)
        if set(key) <= values.keys():
            terms.insert(0, table.c._row_key == tuple_hash(*(bound(values[n]) for n in key)))
        elif set(version) <= values.keys() and "_version_key" in table.c:
            terms.insert(0, table.c._version_key == tuple_hash(*(bound(values[n]) for n in version)))
        elif name == "code_set_version" and "code_set" in values:
            terms.insert(0, table.c._set_key == tuple_hash(bound(values["code_set"])))
    return and_(*terms)


def public_columns(table):
    return [column for column in table.c if not column.name.startswith("_")]


@contextmanager
def transaction(engine, *, write=True):
    """Reads share one observation; an incomplete MySQL installation is unusable."""
    with engine.connect() as conn:
        # The parent lock may wait for an earlier publication. A write must
        # observe its commit after acquiring that lock, not the readiness
        # query's earlier MySQL snapshot. Version/content row locks provide
        # stability while the caller prepares the publication.
        conn = conn.execution_options(isolation_level="READ COMMITTED" if write else "REPEATABLE READ")
        with conn.begin():
            if conn.dialect.name == "mysql":
                if conn.scalar(text("SELECT complete FROM rdm_readiness")) != 1:
                    raise Blocked("Reference migration incomplete")
            yield conn


def lock_code_set(conn, code_set: str):
    """Serialize publication and content writes on their durable parent row."""
    from sqlalchemy import text

    statement = ("SELECT pg_advisory_xact_lock(hashtext('rdm.publish:' || :s))" if conn.dialect.name == "postgresql"
                 else "CALL lock_code_set(:s)")
    conn.execute(text(statement), {"s": code_set}).close()


def clock(conn):
    """Database wall time, normalized to UTC by the connection setup."""
    from sqlalchemy import select, type_coerce

    value = func.clock_timestamp() if conn.dialect.name == "postgresql" else func.utc_timestamp(6)
    return conn.scalar(select(type_coerce(value, UTCDateTime())))


def code_context(conn, code_set, version, code):
    """One published reference code, without a dependency on another store."""
    from sqlalchemy import select

    base = tables(conn.dialect.name)["code"]
    metadata = MetaData()
    view = Table("code_context", metadata, *(Column(n, Text) for n in
        ("code_set", "version", "code", "label", "definition", "path", "label_path", "level", "parent_code", "invalid_reason", "code_status")),
        Column("depth", Integer), Column("synonyms", ExactJSON()), Column("crosswalk", ExactJSON()),
        Column("code_valid_from", Date), Column("code_valid_to", Date),
        schema=base.schema)
    if conn.dialect.name == "mysql":
        view.append_column(Column("_row_key", String(64)))
    query = select(*(c for c in view.c if not c.name.startswith("_"))).where(
        view.c.code_set == code_set, view.c.code == code, view.c.version == version)
    if conn.dialect.name == "mysql":
        query = query.where(view.c._row_key == tuple_hash(literal(code_set), literal(version), literal(code)))
    row = conn.execute(query).mappings().first()
    if row is None:
        return None
    result = dict(row)
    # Keep language ordering, which the view's flat synonym list cannot carry.
    labels = Table("code_label", MetaData(), *(Column(n, Text) for n in
        ("code_set", "version", "code", "language", "label", "kind")), schema=base.schema)
    predicate = and_(labels.c.code_set == code_set, labels.c.version == version,
                     labels.c.code == code, labels.c.kind == "synonym")
    if conn.dialect.name == "mysql":
        labels.append_column(Column("_code_key", String(64)))
        predicate = and_(labels.c._code_key == tuple_hash(literal(code_set), literal(version), literal(code)), predicate)
    ordered = [dict(row) for row in conn.execute(select(labels.c.language, labels.c.label).where(predicate)).mappings()]
    import edgar_control
    import json
    result.update(json.loads(edgar_control.prepare_reference_context(json.dumps(
        {"labels": ordered, "crosswalk": result["crosswalk"]}, ensure_ascii=False, allow_nan=False))))
    return result


def search_candidates(conn, code_set, version, words):
    """Dialect-specific index probes; one native reducer chooses the answer."""
    from sqlalchemy import select, literal, union_all

    models = tables(conn.dialect.name)
    code, path, labels = (models[name] for name in ("code", "code_path", "code_label"))
    join_path = scope(conn, path, code_set=code.c.code_set, version=code.c.version, code=code.c.code)
    join_label = scope(conn, code, code_set=labels.c.code_set, version=labels.c.version, code=labels.c.code)

    def ranked(table):
        if conn.dialect.name == "postgresql":
            vector = func.to_tsvector(literal("simple"), table.c.label)
            query = func.websearch_to_tsquery(literal("simple"), words)
            return func.ts_rank_cd(vector, query), vector.op("@@")(query)
        from sqlalchemy.dialects.mysql import match
        import edgar_control

        query = edgar_control.compile_reference_query(words)
        if not query:
            # A negative-only query is the complement within this one indexed
            # version, never an unrestricted read of the store.
            return literal(0.0), literal(True)
        score = match(table.c._search_tokens, against=query).in_boolean_mode()
        return score, score > 0

    rank, matches = ranked(code)
    direct = select(code.c.code, code.c.label, path.c.label_path,
        literal("label").label("matched_by"), literal(0.0).label("rank"), code.c.label.label("search_text")).select_from(code.join(path, join_path)).where(
            scope(conn, code, code_set=code_set, version=version), matches)
    rank, matches = ranked(labels)
    synonyms = select(code.c.code, code.c.label, path.c.label_path,
        literal("synonym").label("matched_by"), literal(0.0).label("rank"), labels.c.label.label("search_text")).select_from(
            labels.join(code, join_label).join(path, join_path)).where(
                scope(conn, labels, code_set=code_set, version=version), labels.c.kind == "synonym", matches)
    import edgar_control
    found = [dict(row) for row in conn.execute(union_all(direct, synonyms)).mappings()
             if conn.dialect.name == "postgresql" or edgar_control.reference_query_matches(words, row["search_text"])]
    if found:
        return found
    pattern = "%" + words.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    def contains(table):
        column = table.c._search_text if conn.dialect.name == "mysql" else table.c.label
        return column.like(pattern, escape="\\") if conn.dialect.name == "mysql" else column.ilike(pattern, escape="\\")
    direct = select(code.c.code, code.c.label, path.c.label_path, literal("label contains").label("matched_by"),
        literal(0.0).label("rank"), code.c.label.label("search_text")).select_from(code.join(path, join_path)).where(
            scope(conn, code, code_set=code_set, version=version), contains(code))
    synonyms = select(code.c.code, code.c.label, path.c.label_path, literal("synonym contains").label("matched_by"),
        literal(0.0).label("rank"), labels.c.label.label("search_text")).select_from(labels.join(code, join_label).join(path, join_path)).where(
            scope(conn, labels, code_set=code_set, version=version), labels.c.kind == "synonym", contains(labels))
    return [dict(row) for row in conn.execute(union_all(direct, synonyms)).mappings()]


def refresh_search_tokens(conn, **version):
    """Refresh derived search tokens before approval, or during owner upgrade.

    Content remains the canonical authority. Draft edits through SQL cannot
    leave a stale index when that version is approved. The caller holds its
    version lock; an owner upgrade has revoked runtime writes first.
    """
    import edgar_control
    from sqlalchemy import bindparam, select

    for name in ("code", "code_label"):
        table = tables("mysql")[name]
        query = select(table.c._row_key, table.c.label)
        if version:
            query = query.where(scope(conn, table, **version))
        query = query.order_by(table.c._row_key).limit(1000)
        statement = table.update().where(table.c._row_key == bindparam("held_key")).values(
            _search_tokens=bindparam("tokens"))
        after = None
        while True:
            page = query if after is None else query.where(table.c._row_key > after)
            rows = conn.execute(page).mappings().all()
            if not rows:
                break
            conn.execute(statement, [{"held_key": row["_row_key"],
                "tokens": edgar_control.encode_reference_search(row["label"])} for row in rows])
            after = rows[-1]["_row_key"]
