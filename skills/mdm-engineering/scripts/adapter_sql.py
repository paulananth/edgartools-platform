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

    def rows(self, path, *, expected=False, consumer=False, payloads=False, producer=False):
        """One set-based input relation; all keys and bodies are decoded bytes."""
        source = self.v("intent")
        names = ("consumer",) if consumer else ("type", "id", "body")
        if consumer and payloads:
            names += ("payload",)
        if producer:
            names += ("prefix", "suffix")
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


def authority_checks(d):
    """Destination-local monotonic fences, outside immutable business intent."""
    names = ("resource", "run", "attempt")
    if d.name == "postgresql":
        present = f"{d.wire}::jsonb ? 'authority'"
        kind = f"jsonb_typeof({d.wire}::jsonb->'authority')"
        origin = f"jsonb_array_elements(COALESCE({d.wire}::jsonb->'authority','[]'::jsonb)) j(value)"
        scalar = lambda name: f"(j.value->>'{name}')"
        array_kind = "array"
    else:
        present = f"JSON_CONTAINS_PATH({d.wire},'one','$.authority')=1"
        kind = f"JSON_TYPE(JSON_EXTRACT({d.wire},'$.authority'))"
        specs = [f"{name}_hex LONGTEXT PATH '$.{name}' ERROR ON ERROR" for name in names]
        specs += [f"{name}_text VARCHAR(32) PATH '$.{name}' ERROR ON ERROR" for name in ("token","expires")]
        origin = f"JSON_TABLE({d.wire},'$.authority[*]' COLUMNS ({','.join(specs)})) j"
        scalar = lambda name: f"j.{name}_text" if name in {"token","expires"} else f"j.{name}_hex"
        array_kind = "ARRAY"
    columns = []
    for name in names:
        decoded = d.decode(scalar(name))
        columns.append(f"{decoded} AS {name}_bytes")
        if name == "resource":
            hashed = d.hash(decoded)
            if d.name == "mysql":
                hashed = f"CAST({hashed} AS CHAR(64) CHARACTER SET ascii) COLLATE ascii_bin"
            columns.append(f"{hashed} AS resource_key")
    for name in ("token","expires"):
        columns += [f"{scalar(name)} AS {name}_text", f"{d.integer(scalar(name))} AS {name}"]
    proofs = f"(SELECT {','.join(columns)} FROM {origin})"
    invalid = []
    for name in ("token","expires"):
        value = f"i.{name}_text"
        pattern = f"{value} !~ '^[1-9][0-9]*$'" if d.name == "postgresql" else f"NOT({value} REGEXP '^[1-9][0-9]*$')"
        invalid.append(f"{value} IS NULL OR {pattern} OR LENGTH({value})>19 OR (LENGTH({value})=19 AND {value}>'9223372036854775807')")
    invalid += [f"i.{name}_bytes IS NULL OR OCTET_LENGTH(i.{name}_bytes)=0" for name in names]
    table = d.names["authority"]
    match = "c.resource_key=i.resource_key"
    assignments = {name:f"i.{name}" for name in ("token","run_bytes","attempt_bytes","expires")}
    if d.name == "postgresql":
        existing = f"(SELECT a.resource_key,a.resource_bytes,a.token,a.run_bytes,a.attempt_bytes,a.expires FROM {table} a WHERE a.resource_key=i.resource_key OFFSET 0)"
        joined = f"{proofs} i CROSS JOIN LATERAL {existing} c"
        update_source = f"{proofs} i CROSS JOIN LATERAL (SELECT a.ctid AS tid FROM {table} a WHERE a.resource_key=i.resource_key OFFSET 0) held"
        update = d.update_from("authority", assignments, update_source, "c.ctid=held.tid")
        absent = f"NOT EXISTS(SELECT 1 FROM {existing} c)"
        valid = f"SELECT 1 FROM {existing} c WHERE c.resource_bytes=i.resource_bytes AND c.token=i.token AND c.run_bytes=i.run_bytes AND c.attempt_bytes=i.attempt_bytes AND c.expires=i.expires AND c.expires>{d.now}"
    else:
        joined = f"{proofs} i STRAIGHT_JOIN {table} c FORCE INDEX (PRIMARY) ON {match}"
        update = f"UPDATE {joined} SET " + ",".join(f"c.{name}={value}" for name,value in assignments.items()) + ";"
        absent = f"NOT EXISTS(SELECT 1 FROM {table} c FORCE INDEX (PRIMARY) WHERE {match})"
        valid = f"SELECT 1 FROM {table} c FORCE INDEX (PRIMARY) WHERE {match} AND c.resource_bytes=i.resource_bytes AND c.token=i.token AND c.run_bytes=i.run_bytes AND c.attempt_bytes=i.attempt_bytes AND c.expires=i.expires AND c.expires>{d.now}"
    start = [
        f"SELECT CASE WHEN version={d.protocol} THEN complete ELSE 0 END INTO {d.v('authority_ready')} FROM {d.names['migration']} ORDER BY version DESC LIMIT 1 FOR SHARE;",
        d.guard(f"{d.v('authority_ready')} IS NULL OR {d.v('authority_ready')}<>1", "storage_not_initialized"),
        d.guard(f"({present}) AND ({kind} IS NULL OR {kind}<>'{array_kind}')", "invalid_destination_authority"),
        d.guard(f"({present}) AND NOT EXISTS(SELECT 1 FROM {proofs} i)", "invalid_destination_authority"),
        d.guard(f"EXISTS(SELECT 1 FROM {proofs} i WHERE {' OR '.join(invalid)})", "invalid_destination_authority"),
        d.guard(f"EXISTS(SELECT i.resource_key FROM {proofs} i GROUP BY i.resource_key HAVING COUNT(*)>1)", "invalid_destination_authority"),
        d.guard(f"EXISTS(SELECT 1 FROM {proofs} i WHERE i.expires<={d.now})", "expired_destination_authority"),
        d.guard(f"EXISTS(SELECT 1 FROM {joined} WHERE c.resource_bytes<>i.resource_bytes OR c.token>i.token OR (c.token=i.token AND (c.run_bytes<>i.run_bytes OR c.attempt_bytes<>i.attempt_bytes)))", "stale_destination_authority"),
        update,
        f"INSERT INTO {table}(resource_key,resource_bytes,token,run_bytes,attempt_bytes,expires) SELECT i.resource_key,i.resource_bytes,i.token,i.run_bytes,i.attempt_bytes,i.expires FROM {proofs} i WHERE {absent};",
    ]
    finish = d.guard(f"EXISTS(SELECT 1 FROM {proofs} i WHERE NOT EXISTS({valid}))", "destination_authority_expired_before_save")
    return start, finish


def proposal_event(d, event, *, proposal=None, batch="NULL"):
    """Append an opaque observer's event once, under the destination gate."""
    key = proposal or d.v("proposal_key")
    observer = d.v("run")
    observer_key = d.hash(observer)
    table = d.names["proposal_event"]
    return (f"INSERT INTO {table}(proposal_key,observer_key,event,observer_bytes,batch_key,occurred) "
            f"SELECT {key},{observer_key},{event},{observer},{batch},{d.now} "
            f"WHERE NOT EXISTS(SELECT 1 FROM {table} e WHERE e.proposal_key={key} "
            f"AND e.observer_key={observer_key} AND e.event={event});")


def record_proposal_lines(d, body, outcome):
    """Record bytes and a prepared intent without changing business generation."""
    v, n = d.v, d.names
    ready = f"{v('proposal_outcome')}='ready'"
    return [
        d.assign("proposal_body", body),
        d.assign("proposal_outcome", outcome),
        d.guard(f"{v('proposal_body')} IS NULL OR octet_length({v('proposal_body')})=0 OR "
                f"{v('proposal_outcome')} IS NULL OR {v('proposal_outcome')} NOT IN ('ready','rejected') "
                f"OR {v('batch')} IS NULL OR {v('run')} IS NULL OR octet_length({v('run')})=0", "invalid_proposal"),
        d.guard(f"{ready} AND ({d.field('version',v('intent'))} IS NULL OR "
                f"{d.field('version',v('intent'))}<>'5' OR "
                f"{d.decode(d.field('batch',v('intent')))} IS NULL OR "
                f"{d.decode(d.field('batch',v('intent')))}<>{v('batch')})", "invalid_proposal_intent"),
        d.if_(ready, d.assign("pins", d.decode(d.field("pins", v("intent")))) + "\n" + approved_command_pins(d)),
        d.assign("proposal_key", d.hash(v("proposal_body"))),
        d.assign("proposal_intent", f"CASE WHEN {ready} THEN {d.ascii_bytes(v('intent'))} ELSE NULL END"),
        d.assign("proposal_hash", d.hash(v("proposal_intent"))),
        d.guard(f"EXISTS(SELECT 1 FROM {n['proposal']} p WHERE p.proposal_key={v('proposal_key')} "
                f"AND (p.body<>{v('proposal_body')} OR p.batch_key<>{v('batch_key')} "
                f"OR COALESCE(p.intent_hash,'')<>COALESCE({v('proposal_hash')},'') "
                f"OR (p.intent IS NULL AND {v('proposal_intent')} IS NOT NULL) "
                f"OR (p.intent IS NOT NULL AND {v('proposal_intent')} IS NULL) "
                f"OR p.intent<>{v('proposal_intent')} "
                f"OR p.outcome<>{v('proposal_outcome')}))", "proposal_content_collision"),
        f"INSERT INTO {n['proposal']}(proposal_key,batch_key,body,intent,intent_hash,observed_generation,outcome,state) "
        f"SELECT {v('proposal_key')},{v('batch_key')},{v('proposal_body')},{v('proposal_intent')},"
        f"{v('proposal_hash')},{v('generation')},{v('proposal_outcome')},{v('proposal_outcome')} "
        f"WHERE NOT EXISTS(SELECT 1 FROM {n['proposal']} p WHERE p.proposal_key={v('proposal_key')});",
        proposal_event(d, v("proposal_outcome")),
        proposal_event(d, "'observed'"),
    ]


def proposal_variables():
    return {"proposal_key": "key", "proposal_body": "bytes", "proposal_outcome": "key",
            "proposal_intent": "bytes", "proposal_hash": "key"}


def approved_pin_check(d, expression=None, *, allow_empty=False):
    """Every opaque pin must exist and remain owner-approved at admission."""
    expression = expression or d.v("pins")
    raw = (f"convert_from({expression},'UTF8')" if d.name == "postgresql"
           else f"CONVERT({expression} USING utf8mb4)")
    if d.name == "postgresql":
        rows = f"jsonb_each({raw}::jsonb) AS p(name,value)"
        name = "p.name"
        value = "(p.value#>>'{}')"
        kind = "jsonb_typeof(p.value)"
        text_kind = "string"
        bad_object = f"jsonb_typeof({raw}::jsonb)<>'object'" + ("" if allow_empty else f" OR {raw}::jsonb='{{}}'::jsonb")
    else:
        rows = f"JSON_TABLE(JSON_KEYS({raw}),'$[*]' COLUMNS (pin_name LONGTEXT PATH '$')) AS p"
        name = "p.pin_name"
        selected = f"JSON_EXTRACT({raw},CONCAT('$.',JSON_QUOTE(p.pin_name)))"
        value = f"JSON_UNQUOTE({selected})"
        kind = f"JSON_TYPE({selected})"
        text_kind = "STRING"
        bad_object = f"JSON_TYPE({raw})<>'OBJECT'" + ("" if allow_empty else f" OR JSON_LENGTH({raw})=0")
    name_bytes, value_bytes = d.ascii_bytes(name), d.ascii_bytes(value)
    return d.guard(
        f"{expression} IS NULL OR {bad_object} OR EXISTS(SELECT 1 FROM {rows} LEFT JOIN {d.names['pin']} approved "
        f"ON approved.name_key={d.hash(name_bytes)} AND approved.value_key={d.hash(value_bytes)} "
        f"WHERE {kind}<>'{text_kind}' OR approved.active IS NULL OR approved.active<>1 "
        f"OR approved.name_bytes<>{name_bytes} OR approved.value_bytes<>{value_bytes})",
        "unregistered_frozen_pins")


def approved_command_pins(d):
    # Root-run pins stay frozen across batches. Command references additionally
    # approve that batch's immutable inputs without changing the root contract.
    return approved_pin_check(d) + "\n" + approved_pin_check(
        d, d.decode(d.field("required_pins", d.v("intent"))), allow_empty=True
    )


def capabilities(dialect, tables, prefix, *, protocol=1):
    d = SQL(dialect, tables, protocol=protocol)
    n, v = d.names, d.v
    routines = {}

    def save(operation, lines, variables, returns):
        if protocol >= 6 and operation in {"record_proposal","supersede_proposal"}:
            start, finish = authority_checks(d)
            variables = {**variables,"authority_ready":"int"}
            lines = [lines[0],*start,*lines[1:-1],finish+"\n"+lines[-1]]
        body = "\n".join(lines)
        if protocol >= 6:
            # Version 6 retains version-5 bytes/producer semantics. Older
            # committed requests remain replayable; fresh effects require 6.
            version = d.field("version", d.v("intent"))
            for first in (1, 2, 3, 4):
                old = "(" + ",".join("'" + str(n) + "'" for n in range(first, 6)) + ")"
                body = body.replace(old, old[:-1] + ",'6')")
            body = body.replace(version + "='5'", version + " IN ('5','6')")
            body = body.replace(version + "<>'5'", version + " NOT IN ('5','6')")
        routines[operation] = d.wrap(prefix, operation, body, variables, returns)

    lease_vars = {
        "generation": "int",
        "intent": "text",
        "scope": "bytes",
        "scope_key": "key",
        "owner_key": "key",
        "fence": "int",
        "expires": "int",
    }
    scope_authority_start, scope_authority_finish = ([], "")
    if protocol >= 6:
        lease_vars["authority_ready"] = "int"
        scope_authority_start, scope_authority_finish = authority_checks(d)
    lines = [
        d.lock(),
        *scope_authority_start,
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
        *([scope_authority_finish] if protocol >= 6 else []),
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
    if protocol >= 4:
        variables["authority_ready"] = "int"
    if protocol >= 5:
        variables.update(proposal_variables())
    f = lambda name: d.field(name, v("intent"))
    incoming = d.rows("objects", expected=True)
    evidence = d.rows("evidence")
    consumers = d.rows("consumers", consumer=True, payloads=protocol >= 2, producer=protocol >= 5)
    publication_payload = v("payload")
    consumer_refusal = f"NOT EXISTS(SELECT 1 FROM {consumers} i) OR EXISTS(SELECT i.consumer_key FROM {consumers} i GROUP BY i.consumer_key HAVING COUNT(*)>1)"
    if protocol >= 2:
        publication_payload = f"CASE WHEN {f('version')}='2' THEN i.payload_bytes ELSE {v('payload')} END"
        consumer_refusal += f" OR ({f('version')}='2' AND EXISTS(SELECT 1 FROM {consumers} i WHERE i.payload_bytes IS NULL))"
    if protocol >= 3:
        publication_payload = f"CASE WHEN {f('version')} IN ('2','3') THEN i.payload_bytes ELSE {v('payload')} END"
        consumer_refusal = f"NOT EXISTS(SELECT 1 FROM {consumers} i) OR EXISTS(SELECT i.consumer_key FROM {consumers} i GROUP BY i.consumer_key HAVING COUNT(*)>1) OR ({f('version')} IN ('2','3') AND EXISTS(SELECT 1 FROM {consumers} i WHERE i.payload_bytes IS NULL))"
    if protocol >= 4:
        publication_payload = f"CASE WHEN {f('version')} IN ('2','3','4') THEN i.payload_bytes ELSE {v('payload')} END"
        consumer_refusal = f"NOT EXISTS(SELECT 1 FROM {consumers} i) OR EXISTS(SELECT i.consumer_key FROM {consumers} i GROUP BY i.consumer_key HAVING COUNT(*)>1) OR ({f('version')} IN ('2','3','4') AND EXISTS(SELECT 1 FROM {consumers} i WHERE i.payload_bytes IS NULL))"
    if protocol >= 5:
        publication_payload = f"CASE WHEN {f('version')} IN ('2','3','4','5') THEN i.payload_bytes ELSE {v('payload')} END"
        quoted_run = (f"to_json(convert_from({v('run')},'UTF8'))::text" if d.name == "postgresql"
                      else f"JSON_QUOTE(CONVERT({v('run')} USING utf8mb4))")
        joined = (f"i.prefix_bytes || {d.ascii_bytes(quoted_run)} || i.suffix_bytes" if d.name == "postgresql"
                  else f"CONCAT(i.prefix_bytes,{d.ascii_bytes(quoted_run)},i.suffix_bytes)")
        publication_payload = f"CASE WHEN {f('version')}='5' AND i.prefix_bytes IS NOT NULL THEN {joined} ELSE {publication_payload} END"
        consumer_refusal = f"NOT EXISTS(SELECT 1 FROM {consumers} i) OR EXISTS(SELECT i.consumer_key FROM {consumers} i GROUP BY i.consumer_key HAVING COUNT(*)>1) OR ({f('version')} IN ('2','3','4','5') AND EXISTS(SELECT 1 FROM {consumers} i WHERE i.payload_bytes IS NULL))"
        consumer_refusal += f" OR EXISTS(SELECT 1 FROM {consumers} i WHERE (i.prefix_bytes IS NULL AND i.suffix_bytes IS NOT NULL) OR (i.prefix_bytes IS NOT NULL AND i.suffix_bytes IS NULL))"
    matching = "c.type_key=i.type_key AND c.id_key=i.id_key"
    lease_check = (
        f"NOT EXISTS(SELECT 1 FROM {n['lease']} l WHERE l.scope_key={v('scope_key')} "
        f"AND l.owner_key={v('owner_key')} AND l.fence={d.integer(d.field('fence'))} AND l.expires>{d.now})"
    )
    lines = [
        d.assign("intent", d.field("intent")),
        d.guard(
            f"{f('version')} IS NULL OR " + (f"{f('version')} NOT IN ('1','2','3','4','5')" if protocol >= 5 else f"{f('version')} NOT IN ('1','2','3','4')" if protocol >= 4 else f"{f('version')} NOT IN ('1','2','3')" if protocol >= 3 else f"{f('version')} NOT IN ('1','2')" if protocol >= 2 else f"{f('version')}<>'1'"),
            "unsupported_request_version",
        ),
        d.number_guard("fence", positive=True),
        d.number_guard("expected_generation"),
        d.number_guard("expected_checkpoint", v("intent")),
        d.number_guard("checkpoint", v("intent"), positive=True),
        d.lock(),
    ]
    if protocol >= 4:
        flag_kind = (f"jsonb_typeof({v('intent')}::jsonb->'publish_inputs')" if d.name == "postgresql"
                     else f"JSON_TYPE(JSON_EXTRACT({v('intent')},'$.publish_inputs'))")
        boolean_kind = "boolean" if d.name == "postgresql" else "BOOLEAN"
        lines.append(d.guard(f"{f('version')}='4' AND (COALESCE({flag_kind},'')<>'{boolean_kind}' OR {f('publish_inputs')}<>'true')", "invalid_input_publication"))
        if protocol >= 5:
            lines.append(d.guard(f"{f('version')}='5' AND COALESCE({flag_kind},'')<>'{boolean_kind}'", "invalid_input_publication"))
    for name in ("scope", "run", "batch", "pins", "payload"):
        value = d.decode(f(name))
        if protocol >= 5 and name == "run":
            value = f"CASE WHEN {f('version')}='5' THEN {d.decode(d.field('observer'))} ELSE {value} END"
        lines.append(d.assign(name, value))
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
    authority_finish = ""
    if protocol >= 4:
        authority_start, authority_finish = authority_checks(d)
        lines.extend(authority_start)
    prior = f"{n['batch']} b WHERE b.batch_key={v('batch_key')}"
    apply_finishes = []

    def apply_finish(columns):
        apply_finishes.append(columns)
        return d.finish(columns)
    observe_duplicate = []
    if protocol >= 5:
        observe_duplicate = [d.if_(f"{f('version')}='5'", "\n".join([
            approved_command_pins(d),
            d.guard(f"EXISTS(SELECT 1 FROM {n['run']} r WHERE r.run_key={v('run_key')} AND (r.run_bytes<>{v('run')} OR r.pins<>{v('pins')}))", "frozen_pins_changed"),
            f"INSERT INTO {n['run']}(run_key,run_bytes,pins) SELECT {v('run_key')},{v('run')},{v('pins')} WHERE NOT EXISTS(SELECT 1 FROM {n['run']} r WHERE r.run_key={v('run_key')});",
            d.assign("proposal_key", f"(SELECT p.proposal_key FROM {n['proposal']} p WHERE p.batch_key={v('batch_key')} AND p.state='applied')"),
            d.guard(f"{v('proposal_key')} IS NULL", "proposal_required"),
            proposal_event(d, "'duplicate'", batch=v("batch_key")),
        ]))]
    lines.append(
        d.if_(
            f"EXISTS(SELECT 1 FROM {prior})",
            "\n".join(
                [
                    d.guard(
                        f"NOT EXISTS(SELECT 1 FROM {prior} AND b.request_hash={v('request_hash')} AND b.batch_bytes={v('batch')})",
                        "batch_content_collision",
                    ),
                    *([authority_finish] if protocol >= 4 else []),
                    *observe_duplicate,
                    apply_finish(
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
    if protocol >= 5:
        lines.extend([
            *([d.guard(f"{f('version')}<>'6'", "unsupported_request_version")] if protocol >= 6 else []),
            d.guard(f"{f('version')}<>'5'", "proposal_required"),
            approved_command_pins(d),
            d.guard(f"{d.field('proposal_key')} IS NOT NULL AND {d.field('proposal_body')} IS NOT NULL", "invalid_proposal"),
            d.if_(f"{d.field('proposal_body')} IS NOT NULL", "\n".join(
                record_proposal_lines(d, d.decode(d.field("proposal_body")), "'ready'"))),
            d.if_(f"{d.field('proposal_body')} IS NULL", d.assign("proposal_key", d.field("proposal_key"))),
            d.guard(f"{v('proposal_key')} IS NULL", "proposal_required"),
            d.guard(f"NOT EXISTS(SELECT 1 FROM {n['proposal']} p WHERE p.proposal_key={v('proposal_key')} AND p.batch_key={v('batch_key')} AND p.state='ready' AND p.outcome='ready')", "proposal_not_ready"),
            d.guard(f"NOT EXISTS(SELECT 1 FROM {n['proposal']} p WHERE p.proposal_key={v('proposal_key')} AND p.intent_hash={v('request_hash')} AND p.intent={d.ascii_bytes(v('intent'))})", "assessed_effects_changed"),
            d.guard(f"EXISTS(SELECT 1 FROM {n['proposal']} p WHERE p.proposal_key={v('proposal_key')} AND p.observed_generation<>{v('generation')})", "stale_generation"),
        ])
    if d.name == "postgresql":
        invalid_expected = "i.expected_text IS NULL OR i.expected_text !~ '^[0-9]+$'"
    elif d.name == "mysql":
        invalid_expected = (
            "i.expected_text IS NULL OR NOT(i.expected_text REGEXP '^[0-9]+$')"
        )
    else:
        invalid_expected = "i.expected_text IS NULL OR i.expected_text='' OR i.expected_text LIKE '%[^0-9]%'"
    index_guards, index_writes = [], []
    evidence_changed = f"EXISTS(SELECT 1 FROM {evidence} i WHERE NOT EXISTS(SELECT 1 FROM {n['evidence']} c WHERE {matching}))"
    if protocol >= 3:
        indexes = d.rows("indexes", expected=True)
        if protocol >= 4:
            evidence_changed = f"(({f('version')} NOT IN ('3','4') OR ({f('version')}='4' AND {f('publish_inputs')}='true')) AND {evidence_changed})"
            if protocol >= 5:
                evidence_changed = f"(({f('version')} NOT IN ('3','4','5') OR ({f('version')} IN ('4','5') AND {f('publish_inputs')}='true')) AND {evidence_changed})"
        else:
            evidence_changed = f"({f('version')}<>'3' AND {evidence_changed})"
        unsupported_indexes = f"{f('version')} NOT IN ('3','4')" if protocol >= 4 else f"{f('version')}<>'3'"
        if protocol >= 5:
            unsupported_indexes = f"{f('version')} NOT IN ('3','4','5')"
        index_guards = [
            d.guard(f"{unsupported_indexes} AND EXISTS(SELECT 1 FROM {indexes} i)", "unsupported_index_changes"),
            d.guard(f"EXISTS(SELECT 1 FROM {indexes} i WHERE {invalid_expected} OR i.type_bytes IS NULL OR i.id_bytes IS NULL)", "invalid_index_version"),
            d.guard(f"EXISTS(SELECT i.type_key,i.id_key FROM {indexes} i GROUP BY i.type_key,i.id_key HAVING COUNT(*)>1)", "duplicate_index_key"),
            d.guard(f"EXISTS(SELECT 1 FROM {indexes} i LEFT JOIN {n['lookup']} c ON {matching} WHERE COALESCE(c.version,0)<>i.expected_version)", "stale_index_version"),
            d.guard(f"EXISTS(SELECT 1 FROM {indexes} i JOIN {n['lookup']} c ON {matching} WHERE c.type_bytes<>i.type_bytes OR c.id_bytes<>i.id_bytes)", "index_digest_collision"),
        ]
        index_writes = [
            f"DELETE FROM {n['lookup']} WHERE EXISTS(SELECT 1 FROM {indexes} i WHERE i.body_bytes IS NULL AND {n['lookup']}.type_key=i.type_key AND {n['lookup']}.id_key=i.id_key);",
            d.update_from("lookup", {
                "body": "i.body_bytes", "body_hash": "i.body_key", "batch_key": v("batch_key"),
                "version": "c.version+1", "generation": v("generation"),
            }, f"{indexes} i", f"{matching} AND i.body_bytes IS NOT NULL AND (c.body_hash<>i.body_key OR c.body<>i.body_bytes)"),
            f"INSERT INTO {n['lookup']}(type_key,id_key,type_bytes,id_bytes,body,body_hash,batch_key,version,generation) SELECT i.type_key,i.id_key,i.type_bytes,i.id_bytes,i.body_bytes,i.body_key,{v('batch_key')},1,{v('generation')} FROM {indexes} i WHERE i.body_bytes IS NOT NULL AND NOT EXISTS(SELECT 1 FROM {n['lookup']} c WHERE {matching});",
        ]
    proposal_applied = []
    if protocol >= 5:
        proposal_applied = [
            proposal_event(d, "'applied'", batch=v("batch_key")),
            d.update_row("proposal", {"state": "'applied'"}, f"o.proposal_key={v('proposal_key')}"),
            # All alternative proposals of the same batch lose atomically.
            f"INSERT INTO {n['proposal_event']}(proposal_key,observer_key,event,observer_bytes,batch_key,occurred) "
            f"SELECT p.proposal_key,{v('run_key')},'superseded',{v('run')},{v('batch_key')},{d.now} FROM {n['proposal']} p "
            f"WHERE p.batch_key={v('batch_key')} AND p.state='ready' AND p.proposal_key<>{v('proposal_key')};",
            d.update_row("proposal", {"state": "'superseded'"}, f"o.batch_key={v('batch_key')} AND o.state='ready' AND o.proposal_key<>{v('proposal_key')}"),
        ]
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
            *index_guards,
            d.assign(
                "changed",
                f"CASE WHEN EXISTS(SELECT 1 FROM {incoming} i LEFT JOIN {n['current']} c ON {matching} WHERE c.body_hash IS NULL OR c.body_hash<>i.body_key OR c.body<>i.body_bytes) OR {evidence_changed} THEN 1 ELSE 0 END",
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
            *index_writes,
            f"UPDATE {n['checkpoint']} SET position={d.integer(f('checkpoint'))} WHERE scope_key={v('scope_key')};",
            f"INSERT INTO {n['checkpoint']}(scope_key,position) SELECT {v('scope_key')},{d.integer(f('checkpoint'))} WHERE NOT EXISTS(SELECT 1 FROM {n['checkpoint']} c WHERE c.scope_key={v('scope_key')});",
            f"UPDATE {n['gate']} SET generation={v('generation')} WHERE id=1;",
            f"INSERT INTO {n['outbox']}(batch_key,consumer_key,consumer_bytes,payload,payload_hash,fence,verified) SELECT {v('batch_key')},i.consumer_key,i.consumer_bytes,{publication_payload},{d.hash(publication_payload)},0,0 FROM {consumers} i WHERE {v('changed')}=1;",
            *proposal_applied,
            d.guard(lease_check, "scope_lease_expired_before_save"),
            *([authority_finish] if protocol >= 4 else []),
            apply_finish(
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
    if protocol >= 5:
        # Preview executes the same guarded writes, then always rolls them back.
        # It needs no lasting lease because no admission survives the call.
        preview = "\n".join(lines)
        for code in ("stale_scope_lease", "scope_lease_expired_before_save"):
            preview = preview.replace(d.guard(lease_check, code), "")
        for columns in apply_finishes:
            if d.name == "mysql":
                finish = d.finish(columns).replace("COMMIT;", "ROLLBACK;", 1)
            else:
                args = ",".join(f"'{name}',{value}" for name, value in columns)
                finish = d.assign("preview_result", f"json_build_object({args})::text")
                finish += "\nRAISE EXCEPTION 'preview_rollback' USING ERRCODE='P0P01';"
            preview = preview.replace(d.finish(columns), finish)
        preview_variables = dict(variables)
        if d.name == "postgresql":
            preview_variables["preview_result"] = "text"
            selection = ",".join(f"CAST({v('preview_result')}::jsonb->>'{name}' AS BIGINT)"
                                 for name in ("generation", "duplicate", "changed", "checkpoint"))
            preview = ("BEGIN\n" + preview + "\nEXCEPTION WHEN SQLSTATE 'P0P01' THEN\n"
                       f"IF {v('preview_result')} IS NULL THEN RAISE; END IF;\n"
                       f"RETURN QUERY SELECT {selection}; RETURN;\nEND;")
        save("preview", [preview], preview_variables,
             {"generation": "int", "duplicate": "int", "changed": "int", "checkpoint": "int"})
        variables = {"generation": "int", "intent": "text", "batch": "bytes", "pins": "bytes",
                     "batch_key": "key", "run": "bytes", **proposal_variables()}
        initialize = [d.lock(), d.assign("batch", d.decode(d.field("batch"))),
                      d.assign("batch_key", d.hash(v("batch"))),
                      d.assign("run", d.decode(d.field("observer"))),
                      d.assign("intent", d.field("intent"))]
        lines = initialize + [
            d.number_guard("expected_generation"),
            d.guard(f"{d.field('outcome')}='ready' AND {v('generation')}<>{d.integer(d.field('expected_generation'))}", "stale_generation"),
            *record_proposal_lines(d, d.decode(d.field("body")), d.field("outcome")),
            d.finish([("proposal_key", v("proposal_key"))]),
        ]
        save("record_proposal", lines, variables, {"proposal_key": "key"})
        lines = [d.lock(), d.assign("proposal_key", d.field("proposal_key")),
                 d.assign("run", d.decode(d.field("observer"))),
                 d.guard(f"{v('run')} IS NULL OR octet_length({v('run')})=0 OR NOT EXISTS(SELECT 1 FROM {n['proposal']} p WHERE p.proposal_key={v('proposal_key')})", "invalid_proposal"),
                 d.if_(f"EXISTS(SELECT 1 FROM {n['proposal']} p WHERE p.proposal_key={v('proposal_key')} AND p.state='ready')", "\n".join([
                     proposal_event(d, "'superseded'"),
                     d.update_row("proposal", {"state": "'superseded'"}, f"o.proposal_key={v('proposal_key')}"),
                 ])), d.finish([("generation", v("generation"))])]
        save("supersede_proposal", lines, variables, {"generation": "int"})

    variables = {
        "generation": "int",
        "batch_key": "key",
        "consumer_key": "key",
        "owner_key": "key",
        "fence": "int",
        "expires": "int",
    }
    target = f"{n['outbox']} o WHERE o.batch_key={v('batch_key')} AND o.consumer_key={v('consumer_key')}"
    authority_start, authority_finish = ([], "")
    if protocol >= 6:
        variables["authority_ready"] = "int"
        authority_start, authority_finish = authority_checks(d)
    initialize = [
        d.lock(),
        *authority_start,
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
    if protocol >= 6:
        variables["publication_context"] = "bytes"
    lines = initialize + [
        d.number_guard("seconds", positive=True),
        d.guard(f"{d.integer(d.field('seconds'))}>3600", "invalid_lease_duration"),
        d.if_(f"EXISTS(SELECT 1 FROM {target} AND o.verified=1)", (authority_finish + "\n" if protocol >= 6 else "") + d.finish(outputs)),
        *([d.guard(
            f"EXISTS(SELECT 1 FROM {n['outbox']} earlier JOIN {n['batch']} b ON b.batch_key=earlier.batch_key "
            f"WHERE earlier.consumer_key={v('consumer_key')} AND earlier.verified=0 "
            f"AND b.generation<(SELECT held.generation FROM {n['batch']} held WHERE held.batch_key={v('batch_key')}))",
            "earlier_publication_pending")] if protocol >= 6 else []),
        d.guard(
            f"EXISTS(SELECT 1 FROM {target} AND o.owner_key<>{v('owner_key')} AND o.expires>{d.now})",
            "publication_already_leased",
        ),
        *([d.assign("publication_context", d.decode(d.field("context"))),
           d.guard(f"{v('publication_context')} IS NULL OR OCTET_LENGTH({v('publication_context')})=0", "invalid_publication_context"),
           f"INSERT INTO {n.get('outbox_context')}(batch_key,consumer_key,body,body_hash) SELECT {v('batch_key')},{v('consumer_key')},{v('publication_context')},{d.hash(v('publication_context'))} WHERE NOT EXISTS(SELECT 1 FROM {n.get('outbox_context')} c WHERE c.batch_key={v('batch_key')} AND c.consumer_key={v('consumer_key')});"] if protocol >= 6 else []),
        d.update_row(
            "outbox",
            {
                "owner_key": v("owner_key"),
                "fence": "o.fence+1",
                "expires": f"{d.now}+{d.integer(d.field('seconds'))}*1000000",
            },
            f"o.batch_key={v('batch_key')} AND o.consumer_key={v('consumer_key')}",
        ),
        (authority_finish + "\n" if protocol >= 6 else "") + d.finish(outputs),
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
            (authority_finish + "\n" if protocol >= 6 else "") + d.finish([("verified", d.integer("1"))]),
        ),
        d.guard(
            f"EXISTS(SELECT 1 FROM {target} AND o.verified=0 AND o.expires<={d.now})",
            "publication_lease_expired",
        ),
        f"UPDATE {n['outbox']} SET verified=1 WHERE batch_key={v('batch_key')} AND consumer_key={v('consumer_key')};",
        (authority_finish + "\n" if protocol >= 6 else "") + d.finish([("verified", d.integer("1"))]),
    ]
    save("ack_outbox", lines, variables, {"verified": "int"})
    if protocol >= 6:
        save("release_outbox", initialize + [d.number_guard("fence", positive=True),
            d.guard(f"NOT EXISTS(SELECT 1 FROM {target} AND o.owner_key={v('owner_key')} AND o.fence={d.integer(d.field('fence'))} AND o.verified=0 AND o.expires>{d.now})", "stale_or_invalid_publication_receipt"),
            f"UPDATE {n['outbox']} SET owner_key=NULL,expires=NULL WHERE batch_key={v('batch_key')} AND consumer_key={v('consumer_key')};",
            authority_finish, d.finish([("released", d.integer("1"))])], variables, {"released":"int"})
    if protocol >= 6:
        table = n["metadata"]
        variables = {"generation": "int", "authority_ready": "int", "metadata_version": "int",
                     "type_key": "key", "id_key": "key", "body": "bytes"}
        start, finish = authority_checks(d)
        target = f"{table} o WHERE o.type_key={v('type_key')} AND o.id_key={v('id_key')}"
        lines = [d.lock(), *start,
            d.if_(f"{d.field('expected_generation')} IS NOT NULL", "\n".join([
                d.number_guard("expected_generation"),
                d.guard(f"{v('generation')}<>{d.integer(d.field('expected_generation'))}", "stale_generation")])),
            d.number_guard("expected_version"), d.number_guard("immutable"),
            d.guard(f"{d.field('immutable')} NOT IN ('0','1')", "invalid_metadata_mode"),
            d.assign("type_key", d.hash(d.decode(d.field("type")))),
            d.assign("id_key", d.hash(d.decode(d.field("id")))),
            d.assign("body", d.decode(d.field("body"))),
            d.guard(f"{v('body')} IS NULL OR {v('type_key')} IS NULL OR {v('id_key')} IS NULL", "invalid_metadata"),
            d.guard(f"EXISTS(SELECT 1 FROM {target} AND (o.type_bytes<>{d.decode(d.field('type'))} OR o.id_bytes<>{d.decode(d.field('id'))}))", "metadata_digest_collision"),
            d.guard(f"EXISTS(SELECT 1 FROM {target} AND o.immutable<>{d.integer(d.field('immutable'))})", "metadata_mode_changed"),
            d.assign("metadata_version", f"(SELECT o.version FROM {target})"),
            d.if_(f"EXISTS(SELECT 1 FROM {target} AND o.body={v('body')})",
                  finish + "\n" + d.finish([("stored_version", v("metadata_version"))])),
            d.guard(f"EXISTS(SELECT 1 FROM {target} AND o.immutable=1)", "immutable_metadata_changed"),
            d.guard(f"COALESCE({v('metadata_version')},0)<>{d.integer(d.field('expected_version'))}", "stale_metadata_version"),
            d.if_(f"{v('metadata_version')} IS NOT NULL", d.update_row("metadata",
                {"body":v("body"), "body_hash":d.hash(v("body")), "version":"o.version+1", "recorded_at":d.now},
                f"o.type_key={v('type_key')} AND o.id_key={v('id_key')}")),
            f"INSERT INTO {table}(type_key,id_key,type_bytes,id_bytes,body,body_hash,version,immutable,recorded_at) "
            f"SELECT {v('type_key')},{v('id_key')},{d.decode(d.field('type'))},{d.decode(d.field('id'))},{v('body')},{d.hash(v('body'))},1,{d.integer(d.field('immutable'))},{d.now} WHERE {v('metadata_version')} IS NULL;",
            finish, d.finish([("stored_version", f"COALESCE({v('metadata_version')},0)+1")])]
        save("retain_metadata", lines, variables, {"stored_version":"int"})
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
    for table in ("gate", "lease", "outbox") + (("pin", "proposal", "proposal_event") if "proposal" in tables else ()) + (("metadata", "outbox_context") if "metadata" in tables else ()):
        suffix = "_migration_guard" if table in {"gate", "lease", "outbox"} else "_guard"
        name = prefix + "_" + table + suffix
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
    conditions = [
        (
            "batch",
            f"NOT EXISTS(SELECT 1 FROM {d.names['lease']} l WHERE l.scope_key=NEW.scope_key AND l.owner_key=NEW.lease_owner AND l.fence=NEW.lease_fence AND l.expires>{d.now})",
        ),
        (
            "outbox",
            f"NEW.owner_key IS NOT NULL AND (NEW.expires<={d.now} OR NOT EXISTS(SELECT 1 FROM {d.names['outbox']} o WHERE o.batch_key=NEW.batch_key AND o.consumer_key=NEW.consumer_key AND o.owner_key=NEW.owner_key AND o.fence=NEW.fence))",
        ),
    ]
    if "authority" in tables:
        conditions.append(("authority", f"NEW.expires<={d.now}"))
    for table, condition in conditions:
        function = f"{quote(d.schema)}.{quote(prefix + '_' + table + '_commit_check')}"
        trigger = prefix + "_" + table + "_commit_guard"
        body = f"BEGIN IF {condition} THEN RAISE EXCEPTION 'lease_invalid_at_commit' USING ERRCODE='P0001'; END IF; RETURN NEW; END"
        sql = f"CREATE OR REPLACE FUNCTION {function}() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $guard${body}$guard$;"
        events = "INSERT" if table == "batch" else "INSERT OR UPDATE"
        ddl = f"CREATE CONSTRAINT TRIGGER {quote(trigger)} AFTER {events} ON {d.names[table]} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION {function}();"
        definitions.append((function, sql, ddl, table, trigger, body))
    return definitions
