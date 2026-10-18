"""Generate engine-specific storage capabilities from one operation sequence.

Only storage syntax varies. Payloads are opaque bytes, and no routine
interprets a domain, matching rule, field winner or relationship policy.
"""

from __future__ import annotations


class SQL:
    def __init__(self, dialect, tables, *, protocol=1):
        self.dialect = dialect
        self.name = dialect.name
        self.tables = tables
        self.names = {
            key: dialect.identifier_preparer.format_table(t)
            for key, t in tables.items()
        }
        self.schema = next(iter(tables.values())).schema
        self.protocol = protocol

    def v(self, name):
        return ("@v_" if self.name == "mssql" else "v_") + name

    @property
    def wire(self):
        return "@p_wire" if self.name == "mssql" else "p_wire"

    def field(self, name, source=None):
        source = source or self.wire
        if self.name == "postgresql":
            return f"({source}::jsonb->>'{name}')"
        if self.name == "mysql":
            return f"JSON_UNQUOTE(JSON_EXTRACT({source},'$.{name}'))"
        # OPENJSON preserves long scalars; JSON_VALUE has a scalar size limit.
        return f"(SELECT [value] FROM OPENJSON({source}) WHERE [key]='{name}')"

    def integer(self, expression):
        return f"CAST({expression} AS {'SIGNED' if self.name == 'mysql' else 'BIGINT'})"

    def decode(self, expression):
        if self.name == "postgresql":
            return f"decode({expression},'hex')"
        if self.name == "mysql":
            return f"UNHEX({expression})"
        return f"CONVERT(VARBINARY(MAX),{expression},2)"

    def encode(self, expression):
        if self.name == "postgresql":
            return f"encode({expression},'hex')"
        if self.name == "mysql":
            return f"LOWER(HEX({expression}))"
        return f"LOWER(CONVERT(VARCHAR(MAX),{expression},2))"

    def hash(self, expression):
        if self.name == "postgresql":
            return f"encode(sha256({expression}),'hex')"
        if self.name == "mysql":
            return f"LOWER(SHA2({expression},256))"
        return f"LOWER(CONVERT(VARCHAR(64),HASHBYTES('SHA2_256',{expression}),2))"

    def ascii_bytes(self, expression):
        if self.name == "postgresql":
            return f"convert_to({expression},'UTF8')"
        return f"CAST({expression} AS {'BINARY' if self.name == 'mysql' else 'VARBINARY(MAX)'})"

    @property
    def now(self):
        if self.name == "postgresql":
            return "CAST(extract(epoch FROM clock_timestamp()) * 1000000 AS BIGINT)"
        if self.name == "mysql":
            return "TIMESTAMPDIFF(MICROSECOND,'1970-01-01',UTC_TIMESTAMP(6))"
        return (
            "DATEDIFF_BIG(MICROSECOND,CONVERT(DATETIME2,'1970-01-01'),SYSUTCDATETIME())"
        )

    def assign(self, name, expression):
        return (
            f"{self.v(name)} := {expression};"
            if self.name == "postgresql"
            else f"SET {self.v(name)} = {expression};"
        )

    def if_(self, condition, body):
        if self.name == "mssql":
            return f"IF {condition} BEGIN\n{body}\nEND;"
        return f"IF {condition} THEN\n{body}\nEND IF;"

    def guard(self, condition, code):
        # Conditions are refusal conditions; messages never include row values.
        if self.name == "postgresql":
            fail = f"RAISE EXCEPTION '{code}' USING ERRCODE='P0001';"
        elif self.name == "mysql":
            fail = f"SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='{code}';"
        else:
            fail = f"THROW 50001,'{code}',1;"
        return self.if_(condition, fail)

    def number_guard(self, name, source=None, *, positive=False):
        value = self.field(name, source)
        if self.name == "postgresql":
            bad = f"{value} IS NULL OR {value} !~ '^[0-9]+$'"
        elif self.name == "mysql":
            bad = f"{value} IS NULL OR NOT ({value} REGEXP '^[0-9]+$')"
        else:
            bad = f"{value} IS NULL OR {value}='' OR {value} LIKE '%[^0-9]%'"
        result = self.guard(bad, "invalid_counter")
        if positive:
            result += "\n" + self.guard(
                f"{self.integer(value)} <= 0", "invalid_counter"
            )
        return result

    def lock(self):
        gate = self.names["gate"]
        var = self.v("generation")
        if self.name == "mssql":
            query = f"SELECT {var}=g.generation FROM {gate} g WITH (UPDLOCK,HOLDLOCK,ROWLOCK) WHERE g.id=1;"
        else:
            query = (
                f"SELECT g.generation INTO {var} FROM {gate} g WHERE g.id=1 FOR UPDATE;"
            )
        return query + "\n" + self.guard(f"{var} IS NULL", "missing_storage_gate")

    def finish(self, columns):
        selection = "SELECT " + ",".join(
            f"{expression} AS {self.dialect.identifier_preparer.quote(name)}"
            for name, expression in columns
        )
        if self.name == "postgresql":
            return "RETURN QUERY " + selection + "; RETURN;"
        if self.name == "mysql":
            return "COMMIT; " + selection + "; LEAVE capability;"
        return "COMMIT TRANSACTION; " + selection + "; RETURN;"

    def rows(self, path, *, expected=False, consumer=False, payloads=False):
        """One set-based input relation; all keys and bodies are decoded bytes."""
        source = self.v("intent")
        names = ("consumer",) if consumer else ("type", "id", "body")
        if consumer and payloads:
            names += ("payload",)
        if self.name == "postgresql":
            scalar = lambda n: f"(j.value->>'{n}')"
            origin = f"jsonb_array_elements({source}::jsonb->'{path}') AS j(value)"
        elif self.name == "mysql":
            specs = [f"{n}_hex LONGTEXT PATH '$.{n}' ERROR ON ERROR" for n in names]
            if expected:
                specs.append(
                    "expected_text VARCHAR(32) PATH '$.expected_version' ERROR ON ERROR"
                )
            origin = (
                f"JSON_TABLE({source},'$.{path}[*]' COLUMNS ({','.join(specs)})) AS j"
            )
            scalar = lambda n: (
                "j.expected_text" if n == "expected_version" else f"j.{n}_hex"
            )
        else:
            specs = [f"{n}_hex VARCHAR(MAX) '$.{n}'" for n in names]
            if expected:
                specs.append("expected_text VARCHAR(32) '$.expected_version'")
            origin = f"OPENJSON({source},'$.{path}') WITH ({','.join(specs)}) AS j"
            scalar = lambda n: (
                "j.expected_text" if n == "expected_version" else f"j.{n}_hex"
            )
        parts = []
        for name in names:
            decoded = self.decode(scalar(name))
            parts.extend(
                [f"{decoded} AS {name}_bytes", f"{self.hash(decoded)} AS {name}_key"]
            )
        if expected:
            parts.extend(
                [
                    f"{self.integer(scalar('expected_version'))} AS expected_version",
                    f"{scalar('expected_version')} AS expected_text",
                ]
            )
        return f"(SELECT {','.join(parts)} FROM {origin})"

    def update_from(self, table, assignments, source, condition):
        name = self.names[table]
        if self.name == "mysql":
            values = ",".join(f"c.{key}={value}" for key, value in assignments.items())
            return f"UPDATE {name} c JOIN {source} ON {condition} SET {values};"
        values = ",".join(f"{key}={value}" for key, value in assignments.items())
        if self.name == "mssql":
            return f"UPDATE c SET {values} FROM {name} c JOIN {source} ON {condition};"
        return f"UPDATE {name} AS c SET {values} FROM {source} WHERE {condition};"

    def update_row(self, table, assignments, condition):
        name = self.names[table]
        values = ",".join(
            f"{'o.' if self.name == 'mysql' else ''}{key}={value}"
            for key, value in assignments.items()
        )
        if self.name == "mssql":
            return f"UPDATE o SET {values} FROM {name} o WHERE {condition};"
        return f"UPDATE {name} AS o SET {values} WHERE {condition};"

    def wrap(self, prefix, operation, body, variables, returns):
        quote = self.dialect.identifier_preparer.quote
        name = f"{quote(self.schema)}.{quote(prefix + '_' + operation)}"
        body = (
            self.guard(
                f"NOT EXISTS(SELECT 1 FROM {self.names['migration']} m WHERE m.version={self.protocol} AND m.complete=1)",
                "storage_not_initialized",
            )
            + "\n"
            + body
        )
        types = {
            "text": "VARCHAR(MAX)"
            if self.name == "mssql"
            else "LONGTEXT"
            if self.name == "mysql"
            else "text",
            "key": "VARCHAR(64)",
            "int": "BIGINT",
            "bytes": "VARBINARY(MAX)"
            if self.name == "mssql"
            else "LONGBLOB"
            if self.name == "mysql"
            else "bytea",
        }
        if self.name == "postgresql":
            declarations = "\n".join(
                f"{self.v(n)} {types[t]};" for n, t in variables.items()
            )
            outputs = ",".join(f"{n} {types[t]}" for n, t in returns.items())
            return (
                name,
                f"""CREATE OR REPLACE FUNCTION {name}(p_wire text) RETURNS TABLE({outputs})
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $capability$
DECLARE {declarations}
BEGIN
{body}
END $capability$;""",
            )
        declarations = "\n".join(
            f"DECLARE {self.v(n)} {types[t]};" for n, t in variables.items()
        )
        if self.name == "mysql":
            return (
                name,
                f"""CREATE PROCEDURE {name}(IN p_wire LONGTEXT) SQL SECURITY DEFINER
capability: BEGIN
{declarations}
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
BEGIN
DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;
START TRANSACTION;
{body}
END;
END""",
            )
        return (
            name,
            f"""CREATE OR ALTER PROCEDURE {name} @p_wire VARCHAR(MAX) WITH EXECUTE AS OWNER AS
BEGIN
SET NOCOUNT ON; SET XACT_ABORT ON;
{declarations}
IF @@TRANCOUNT<>0 BEGIN THROW 50001,'ambient_transaction_refused',1; END;
BEGIN TRY
BEGIN TRANSACTION;
{body}
END TRY
BEGIN CATCH
IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
THROW;
END CATCH
END""",
        )


def capabilities(dialect, tables, prefix, *, protocol=1):
    d = SQL(dialect, tables, protocol=protocol)
    n, v = d.names, d.v
    routines = {}

    def save(operation, lines, variables, returns):
        routines[operation] = d.wrap(
            prefix, operation, "\n".join(lines), variables, returns
        )

    lease_vars = {
        "generation": "int",
        "intent": "text",
        "scope": "bytes",
        "scope_key": "key",
        "owner_key": "key",
        "fence": "int",
        "expires": "int",
    }
    lines = [
        d.lock(),
        d.assign("scope", d.decode(d.field("scope"))),
        d.assign("scope_key", d.hash(v("scope"))),
        d.assign("owner_key", d.hash(d.decode(d.field("owner")))),
        d.guard(f"{v('scope')} IS NULL OR {v('owner_key')} IS NULL", "invalid_scope"),
        d.number_guard("seconds", positive=True),
        d.guard(f"{d.integer(d.field('seconds'))}>3600", "invalid_lease_duration"),
        d.guard(
            f"EXISTS(SELECT 1 FROM {n['lease']} l WHERE l.scope_key={v('scope_key')} AND l.scope_bytes<>{v('scope')})",
            "scope_digest_collision",
        ),
        d.guard(
            f"EXISTS(SELECT 1 FROM {n['lease']} l WHERE l.scope_key={v('scope_key')} AND l.owner_key<>{v('owner_key')} AND l.expires>{d.now})",
            "scope_already_leased",
        ),
        d.assign(
            "fence",
            f"COALESCE((SELECT l.fence FROM {n['lease']} l WHERE l.scope_key={v('scope_key')}),0)+1",
        ),
        d.assign("expires", f"{d.now}+{d.integer(d.field('seconds'))}*1000000"),
        f"UPDATE {n['lease']} SET owner_key={v('owner_key')},fence={v('fence')},expires={v('expires')} WHERE scope_key={v('scope_key')};",
        f"INSERT INTO {n['lease']}(scope_key,scope_bytes,owner_key,fence,expires) SELECT {v('scope_key')},{v('scope')},{v('owner_key')},{v('fence')},{v('expires')} WHERE NOT EXISTS(SELECT 1 FROM {n['lease']} l WHERE l.scope_key={v('scope_key')});",
        d.finish(
            [
                ("fence", v("fence")),
                ("expires", v("expires")),
                ("generation", v("generation")),
            ]
        ),
    ]
    save(
        "claim",
        lines,
        lease_vars,
        {"fence": "int", "expires": "int", "generation": "int"},
    )

    variables = {
        "generation": "int",
        "intent": "text",
        "scope_key": "key",
        "run_key": "key",
        "batch_key": "key",
        "owner_key": "key",
        "request_hash": "key",
        "pins": "bytes",
        "payload": "bytes",
        "changed": "int",
        "scope": "bytes",
        "run": "bytes",
        "batch": "bytes",
        "checkpoint": "int",
    }
    f = lambda name: d.field(name, v("intent"))
    incoming = d.rows("objects", expected=True)
    evidence = d.rows("evidence")
    consumers = d.rows("consumers", consumer=True, payloads=protocol >= 2)
    publication_payload = v("payload")
    consumer_refusal = f"NOT EXISTS(SELECT 1 FROM {consumers} i) OR EXISTS(SELECT i.consumer_key FROM {consumers} i GROUP BY i.consumer_key HAVING COUNT(*)>1)"
    if protocol >= 2:
        publication_payload = f"CASE WHEN {f('version')}='2' THEN i.payload_bytes ELSE {v('payload')} END"
        consumer_refusal += f" OR ({f('version')}='2' AND EXISTS(SELECT 1 FROM {consumers} i WHERE i.payload_bytes IS NULL))"
    matching = "c.type_key=i.type_key AND c.id_key=i.id_key"
    lease_check = (
        f"NOT EXISTS(SELECT 1 FROM {n['lease']} l WHERE l.scope_key={v('scope_key')} "
        f"AND l.owner_key={v('owner_key')} AND l.fence={d.integer(d.field('fence'))} AND l.expires>{d.now})"
    )
    lines = [
        d.assign("intent", d.field("intent")),
        d.guard(
            f"{f('version')} IS NULL OR " + (f"{f('version')} NOT IN ('1','2')" if protocol >= 2 else f"{f('version')}<>'1'"),
            "unsupported_request_version",
        ),
        d.number_guard("fence", positive=True),
        d.number_guard("expected_generation"),
        d.number_guard("expected_checkpoint", v("intent")),
        d.number_guard("checkpoint", v("intent"), positive=True),
        d.lock(),
    ]
    for name in ("scope", "run", "batch", "pins", "payload"):
        lines.append(d.assign(name, d.decode(f(name))))
    for name in ("scope", "run", "batch"):
        lines.extend(
            [
                d.guard(f"{v(name)} IS NULL", "missing_request_identity"),
                d.assign(name + "_key", d.hash(v(name))),
            ]
        )
    lines.extend(
        [
            d.assign("request_hash", d.hash(d.ascii_bytes(v("intent")))),
            d.assign("owner_key", d.hash(d.decode(d.field("owner")))),
            d.guard(lease_check, "stale_scope_lease"),
            d.guard(
                f"{v('pins')} IS NULL OR {v('payload')} IS NULL OR {d.decode(f('assessment'))} IS NULL",
                "missing_prepared_evidence",
            ),
        ]
    )
    prior = f"{n['batch']} b WHERE b.batch_key={v('batch_key')}"
    lines.append(
        d.if_(
            f"EXISTS(SELECT 1 FROM {prior})",
            "\n".join(
                [
                    d.guard(
                        f"NOT EXISTS(SELECT 1 FROM {prior} AND b.request_hash={v('request_hash')} AND b.batch_bytes={v('batch')})",
                        "batch_content_collision",
                    ),
                    d.finish(
                        [
                            ("generation", f"(SELECT b.generation FROM {prior})"),
                            ("duplicate", d.integer("1")),
                            ("changed", d.integer(f"(SELECT b.changed FROM {prior})")),
                            ("checkpoint", f"(SELECT b.position FROM {prior})"),
                        ]
                    ),
                ]
            ),
        )
    )
    lines.extend(
        [
            d.guard(
                f"{v('generation')}<>{d.integer(d.field('expected_generation'))}",
                "stale_generation",
            ),
            d.assign(
                "checkpoint",
                f"COALESCE((SELECT c.position FROM {n['checkpoint']} c WHERE c.scope_key={v('scope_key')}),0)",
            ),
            d.guard(
                f"{v('checkpoint')}<>{d.integer(f('expected_checkpoint'))} OR {d.integer(f('checkpoint'))}<={v('checkpoint')}",
                "stale_checkpoint",
            ),
            d.guard(
                f"EXISTS(SELECT 1 FROM {n['run']} r WHERE r.run_key={v('run_key')} AND (r.run_bytes<>{v('run')} OR r.pins<>{v('pins')}))",
                "frozen_pins_changed",
            ),
            d.guard(
                consumer_refusal,
                "invalid_consumers",
            ),
        ]
    )
    if d.name == "postgresql":
        invalid_expected = "i.expected_text IS NULL OR i.expected_text !~ '^[0-9]+$'"
    elif d.name == "mysql":
        invalid_expected = (
            "i.expected_text IS NULL OR NOT(i.expected_text REGEXP '^[0-9]+$')"
        )
    else:
        invalid_expected = "i.expected_text IS NULL OR i.expected_text='' OR i.expected_text LIKE '%[^0-9]%'"
    lines.extend(
        [
            d.guard(
                f"EXISTS(SELECT 1 FROM {incoming} i WHERE {invalid_expected})",
                "invalid_object_version",
            ),
            d.guard(
                f"EXISTS(SELECT i.type_key,i.id_key FROM {incoming} i GROUP BY i.type_key,i.id_key HAVING COUNT(*)>1)",
                "duplicate_object_key",
            ),
            d.guard(
                f"EXISTS(SELECT i.type_key,i.id_key FROM {evidence} i GROUP BY i.type_key,i.id_key HAVING COUNT(*)>1)",
                "duplicate_evidence_key",
            ),
            d.guard(
                f"EXISTS(SELECT 1 FROM {incoming} i LEFT JOIN {n['current']} c ON {matching} WHERE COALESCE(c.version,0)<>i.expected_version OR i.body_bytes IS NULL OR i.type_bytes IS NULL OR i.id_bytes IS NULL)",
                "stale_object_version",
            ),
            d.guard(
                f"EXISTS(SELECT 1 FROM {incoming} i JOIN {n['current']} c ON {matching} WHERE c.type_bytes<>i.type_bytes OR c.id_bytes<>i.id_bytes)",
                "object_digest_collision",
            ),
            d.guard(
                f"EXISTS(SELECT 1 FROM {evidence} i JOIN {n['evidence']} c ON {matching} WHERE c.body<>i.body_bytes OR c.type_bytes<>i.type_bytes OR c.id_bytes<>i.id_bytes)",
                "immutable_evidence_collision",
            ),
            d.assign(
                "changed",
                f"CASE WHEN EXISTS(SELECT 1 FROM {incoming} i LEFT JOIN {n['current']} c ON {matching} WHERE c.body_hash IS NULL OR c.body_hash<>i.body_key OR c.body<>i.body_bytes) OR EXISTS(SELECT 1 FROM {evidence} i WHERE NOT EXISTS(SELECT 1 FROM {n['evidence']} c WHERE {matching})) THEN 1 ELSE 0 END",
            ),
            d.assign("generation", f"{v('generation')}+1"),
            f"INSERT INTO {n['run']}(run_key,run_bytes,pins) SELECT {v('run_key')},{v('run')},{v('pins')} WHERE NOT EXISTS(SELECT 1 FROM {n['run']} r WHERE r.run_key={v('run_key')});",
            f"INSERT INTO {n['batch']}(batch_key,batch_bytes,request_hash,run_key,scope_key,lease_owner,lease_fence,generation,position,intent,assessment,changed) VALUES({v('batch_key')},{v('batch')},{v('request_hash')},{v('run_key')},{v('scope_key')},{v('owner_key')},{d.integer(d.field('fence'))},{v('generation')},{d.integer(f('checkpoint'))},{d.ascii_bytes(v('intent'))},{d.decode(f('assessment'))},{v('changed')});",
            f"INSERT INTO {n['history']}(type_key,id_key,generation,type_bytes,id_bytes,body,body_hash,batch_key,version) SELECT i.type_key,i.id_key,{v('generation')},i.type_bytes,i.id_bytes,i.body_bytes,i.body_key,{v('batch_key')},COALESCE(c.version,0)+1 FROM {incoming} i LEFT JOIN {n['current']} c ON {matching} WHERE c.body_hash IS NULL OR c.body_hash<>i.body_key OR c.body<>i.body_bytes;",
            d.update_from(
                "current",
                {
                    key: f"h.{key}"
                    for key in (
                        "body",
                        "body_hash",
                        "batch_key",
                        "version",
                        "generation",
                    )
                },
                f"{n['history']} h",
                f"c.type_key=h.type_key AND c.id_key=h.id_key AND h.generation={v('generation')}",
            ),
            f"INSERT INTO {n['current']}(type_key,id_key,type_bytes,id_bytes,body,body_hash,batch_key,version,generation) SELECT h.type_key,h.id_key,h.type_bytes,h.id_bytes,h.body,h.body_hash,h.batch_key,h.version,h.generation FROM {n['history']} h WHERE h.generation={v('generation')} AND NOT EXISTS(SELECT 1 FROM {n['current']} c WHERE c.type_key=h.type_key AND c.id_key=h.id_key);",
            f"INSERT INTO {n['evidence']}(type_key,id_key,type_bytes,id_bytes,body,body_hash,batch_key) SELECT i.type_key,i.id_key,i.type_bytes,i.id_bytes,i.body_bytes,i.body_key,{v('batch_key')} FROM {evidence} i WHERE NOT EXISTS(SELECT 1 FROM {n['evidence']} c WHERE {matching});",
            f"UPDATE {n['checkpoint']} SET position={d.integer(f('checkpoint'))} WHERE scope_key={v('scope_key')};",
            f"INSERT INTO {n['checkpoint']}(scope_key,position) SELECT {v('scope_key')},{d.integer(f('checkpoint'))} WHERE NOT EXISTS(SELECT 1 FROM {n['checkpoint']} c WHERE c.scope_key={v('scope_key')});",
            f"UPDATE {n['gate']} SET generation={v('generation')} WHERE id=1;",
            f"INSERT INTO {n['outbox']}(batch_key,consumer_key,consumer_bytes,payload,payload_hash,fence,verified) SELECT {v('batch_key')},i.consumer_key,i.consumer_bytes,{publication_payload},{d.hash(publication_payload)},0,0 FROM {consumers} i WHERE {v('changed')}=1;",
            d.guard(lease_check, "scope_lease_expired_before_save"),
            d.finish(
                [
                    ("generation", v("generation")),
                    ("duplicate", d.integer("0")),
                    ("changed", d.integer(v("changed"))),
                    ("checkpoint", d.integer(f("checkpoint"))),
                ]
            ),
        ]
    )
    save(
        "apply",
        lines,
        variables,
        {
            "generation": "int",
            "duplicate": "int",
            "changed": "int",
            "checkpoint": "int",
        },
    )

    variables = {
        "generation": "int",
        "batch_key": "key",
        "consumer_key": "key",
        "owner_key": "key",
        "fence": "int",
        "expires": "int",
    }
    target = f"{n['outbox']} o WHERE o.batch_key={v('batch_key')} AND o.consumer_key={v('consumer_key')}"
    initialize = [
        d.lock(),
        d.assign("batch_key", d.hash(d.decode(d.field("batch")))),
        d.assign("consumer_key", d.hash(d.decode(d.field("consumer")))),
        d.assign("owner_key", d.hash(d.decode(d.field("owner")))),
        d.guard(f"NOT EXISTS(SELECT 1 FROM {target})", "unknown_publication"),
    ]
    outputs = [
        ("fence", f"(SELECT o.fence FROM {target})"),
        ("expires", f"(SELECT o.expires FROM {target})"),
        ("verified", d.integer(f"(SELECT o.verified FROM {target})")),
        ("payload_hex", f"(SELECT {d.encode('o.payload')} FROM {target})"),
        (
            "payload_hash",
            f"CAST((SELECT o.payload_hash FROM {target}) AS {'text' if d.name == 'postgresql' else 'CHAR(64)' if d.name == 'mysql' else 'VARCHAR(MAX)'})",
        ),
    ]
    lines = initialize + [
        d.number_guard("seconds", positive=True),
        d.guard(f"{d.integer(d.field('seconds'))}>3600", "invalid_lease_duration"),
        d.if_(f"EXISTS(SELECT 1 FROM {target} AND o.verified=1)", d.finish(outputs)),
        d.guard(
            f"EXISTS(SELECT 1 FROM {target} AND o.owner_key<>{v('owner_key')} AND o.expires>{d.now})",
            "publication_already_leased",
        ),
        d.update_row(
            "outbox",
            {
                "owner_key": v("owner_key"),
                "fence": "o.fence+1",
                "expires": f"{d.now}+{d.integer(d.field('seconds'))}*1000000",
            },
            f"o.batch_key={v('batch_key')} AND o.consumer_key={v('consumer_key')}",
        ),
        d.finish(outputs),
    ]
    save(
        "claim_outbox",
        lines,
        variables,
        {
            "fence": "int",
            "expires": "int",
            "verified": "int",
            "payload_hex": "text",
            "payload_hash": "text",
        },
    )
    lines = initialize + [
        d.number_guard("fence", positive=True),
        d.guard(
            f"NOT EXISTS(SELECT 1 FROM {target} AND o.owner_key={v('owner_key')} AND o.fence={d.integer(d.field('fence'))} AND o.payload_hash={d.field('receipt')})",
            "stale_or_invalid_publication_receipt",
        ),
        d.if_(
            f"EXISTS(SELECT 1 FROM {target} AND o.verified=1)",
            d.finish([("verified", d.integer("1"))]),
        ),
        d.guard(
            f"EXISTS(SELECT 1 FROM {target} AND o.verified=0 AND o.expires<={d.now})",
            "publication_lease_expired",
        ),
        f"UPDATE {n['outbox']} SET verified=1 WHERE batch_key={v('batch_key')} AND consumer_key={v('consumer_key')};",
        d.finish([("verified", d.integer("1"))]),
    ]
    save("ack_outbox", lines, variables, {"verified": "int"})
    return routines


def migration_guards(dialect, tables, prefix):
    """Fence already-entered legacy RPCs at their authoritative writes.

    Every mutating RPC holds the gate and writes either the generation gate,
    a lease or an outbox row. Current locking reads also fence a call whose
    repeatable-read snapshot predates the migration barrier.
    """
    d = SQL(dialect, tables)
    quote = dialect.identifier_preparer.quote
    definitions = []
    for table in ("gate", "lease", "outbox"):
        name = prefix + "_" + table + "_migration_guard"
        qualified = f"{quote(d.schema)}.{quote(name)}"
        if dialect.name == "postgresql":
            function = qualified + "_check"
            body = (f"DECLARE ready integer; BEGIN SELECT complete INTO ready FROM {d.names['migration']} "
                    "ORDER BY version DESC LIMIT 1 FOR SHARE; "
                    "IF ready IS DISTINCT FROM 1 THEN RAISE EXCEPTION 'storage_not_initialized' USING ERRCODE='P0001'; "
                    "END IF; RETURN NEW; END")
            sql = f"CREATE FUNCTION {function}() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $guard${body}$guard$;"
            ddl = f"CREATE TRIGGER {quote(name)} BEFORE INSERT OR UPDATE ON {d.names[table]} FOR EACH ROW EXECUTE FUNCTION {function}();"
            definitions.append((name, sql, ddl, table, body))
        elif dialect.name == "mysql":
            body = (f"BEGIN DECLARE ready BIGINT; SELECT complete INTO ready FROM {d.names['migration']} "
                    "ORDER BY version DESC LIMIT 1 FOR SHARE; "
                    "IF ready IS NULL OR ready<>1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='storage_not_initialized'; END IF; END")
            for event in ("INSERT", "UPDATE"):
                trigger = name + "_" + event.lower()
                ddl = f"CREATE TRIGGER {quote(d.schema)}.{quote(trigger)} BEFORE {event} ON {d.names[table]} FOR EACH ROW {body}"
                definitions.append((trigger, None, ddl, table, body))
        else:
            body = (f"BEGIN SET NOCOUNT ON; DECLARE @ready BIGINT; SELECT TOP(1) @ready=complete FROM {d.names['migration']} WITH (UPDLOCK,HOLDLOCK) "
                    "ORDER BY version DESC; IF @ready IS NULL OR @ready<>1 THROW 50001,'storage_not_initialized',1; END;")
            ddl = f"CREATE TRIGGER {qualified} ON {d.names[table]} WITH EXECUTE AS OWNER AFTER INSERT,UPDATE AS {body}"
            definitions.append((name, None, ddl, table, body))
    return definitions


def commit_guards(dialect, tables, prefix):
    """Deferred destination checks for a direct SQL caller's PostgreSQL commit."""
    if dialect.name != "postgresql":
        return []
    d = SQL(dialect, tables)
    quote = dialect.identifier_preparer.quote
    definitions = []
    for table, condition in (
        (
            "batch",
            f"NOT EXISTS(SELECT 1 FROM {d.names['lease']} l WHERE l.scope_key=NEW.scope_key AND l.owner_key=NEW.lease_owner AND l.fence=NEW.lease_fence AND l.expires>{d.now})",
        ),
        (
            "outbox",
            f"NEW.owner_key IS NOT NULL AND (NEW.expires<={d.now} OR NOT EXISTS(SELECT 1 FROM {d.names['outbox']} o WHERE o.batch_key=NEW.batch_key AND o.consumer_key=NEW.consumer_key AND o.owner_key=NEW.owner_key AND o.fence=NEW.fence))",
        ),
    ):
        function = f"{quote(d.schema)}.{quote(prefix + '_' + table + '_commit_check')}"
        trigger = prefix + "_" + table + "_commit_guard"
        body = f"BEGIN IF {condition} THEN RAISE EXCEPTION 'lease_invalid_at_commit' USING ERRCODE='P0001'; END IF; RETURN NEW; END"
        sql = f"CREATE OR REPLACE FUNCTION {function}() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $guard${body}$guard$;"
        events = "INSERT" if table == "batch" else "INSERT OR UPDATE"
        ddl = f"CREATE CONSTRAINT TRIGGER {quote(trigger)} AFTER {events} ON {d.names[table]} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION {function}();"
        definitions.append((function, sql, ddl, table, trigger, body))
    return definitions
