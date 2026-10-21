"""Save Rust-prepared run checks against authoritative destination observations.

The routine locks one run, rechecks its counters, rejects forged completion and
stores the prepared state. It computes neither the next state nor the summary.
Runtime logins receive EXECUTE only; direct control writes remain forbidden.
"""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.control_contract import Blocked
from .storage import tables


class StaleObservation(Blocked):
    """The run changed after its completion observations were read."""


def execute_ddl(conn, statement):
    """Send compiled DDL verbatim; JSON colons and literal percent signs are SQL."""
    with conn.connection.driver_connection.cursor() as cursor:
        cursor.execute(statement)


def statements(engine):
    """One enforcement sequence with selected-engine storage syntax."""
    import edgar_control
    contract = json.loads(edgar_control.completion_storage_contract())
    dialect = engine.dialect.name
    names = {name: engine.dialect.identifier_preparer.format_table(table)
             for name, table in tables(dialect).items()}
    sql = _StorageSQL(dialect)
    v, field = sql.variable, sql.field
    declarations = {"run_id": "uuid", "raw_run": "text", "state": "text", "checks": "text", "summary": "text", "compacted": "int"}
    counters = ("expected", "actual", "verified", "pending", "unsealed")
    declarations.update({name: "int" for name in (*counters, *("observed_" + name for name in counters))})
    declarations.update({"raw_" + name: "text" for name in counters})
    body = []
    for name in counters:
        raw = "raw_" + name
        body += [sql.assign(raw, field(name)),
                 sql.guard(sql.bad_number(v(raw)), "invalid_control_counter"),
                 sql.assign(name, sql.integer(v(raw)))]
    body += [sql.assign("raw_run", field("run_id")),
             sql.guard(sql.bad_uuid(v("raw_run")), "invalid_control_run"),
             sql.assign("run_id", sql.uuid(v("raw_run"))),
             sql.assign("state", field("state")),
             sql.assign("checks", sql.decode(field("checks"))),
             sql.assign("summary", sql.decode(field("summary")))]
    body += [sql.guard(f"{v('state')} IS NULL OR NOT ({sql.equal(v('state'), sql.literal('complete'))} "
                       f"OR {sql.equal(v('state'), sql.literal('waiting'))})", "invalid_control_state"),
             sql.guard(f"{v('checks')} IS NULL OR NOT ({sql.one_of(v('checks'), contract['checks'])})", "invalid_control_checks")]
    run = names["pipeline_run"]
    body.append(sql.read([("observed_expected", "p.expected_count"),
                          ("compacted", "CASE WHEN p.compacted_at IS NULL THEN 0 ELSE 1 END")],
                         f"{run} p", f"p.run_id={v('run_id')}", lock=True))
    body += [sql.guard(f"{v('observed_expected')} IS NULL", "unknown_control_run"),
             sql.guard(f"{v('compacted')}<>0", "compacted_control_run")]
    work = names["work_item"]
    body.append(sql.read([("observed_actual", sql.count),
        ("observed_verified", f"COALESCE(SUM(CASE WHEN w.state='verified' THEN {sql.integer('1')} ELSE {sql.integer('0')} END),0)")],
        f"{work} w", f"w.run_id={v('run_id')}"))
    body.append(sql.read([("observed_unsealed", sql.count)], f"{work} w",
                         f"w.run_id={v('run_id')} AND w.generated_count IS NULL AND {sql.has_expansion('w.unit')}"))
    body.append(sql.read([("observed_pending", sql.count)], f"{names['journal_outbox']} j",
                         f"j.run_id={v('run_id')} AND j.delivered_at IS NULL"))
    body.append(sql.guard(" OR ".join(f"{v(name)}<>{v('observed_' + name)}" for name in counters),
                          "control_observations_changed"))
    # These finite proof representations and the summary layout come from
    # Rust's versioned contract. Destination validation is byte-exact, so a
    # forged duplicate key cannot be interpreted differently by JSON parsers.
    failed_completion = (f"{v('actual')}<>{v('expected')} OR {v('verified')}<>{v('actual')} "
        f"OR {v('pending')}<>0 OR {v('unsealed')}<>0 OR NOT ({sql.one_of(v('checks'), contract['passing'])})")
    body.append(sql.guard(f"{sql.equal(v('state'), sql.literal('complete'))} AND ({failed_completion})",
                          "unverified_control_completion"))
    body.append(sql.guard(f"{sql.equal(v('state'), sql.literal('waiting'))} AND NOT ({failed_completion})",
                          "invalid_control_state"))
    pieces = []
    for part in contract["summary"]:
        if part["counter"] not in counters:
            raise Blocked("Unsupported control summary contract")
        pieces.extend([sql.literal(part["prefix"]), sql.text_value(v(part["counter"]))])
    pieces.append(sql.literal(contract["suffix"]))
    body.append(sql.guard(f"{v('summary')} IS NULL OR NOT ({sql.equal(v('summary'), sql.concat(pieces))})",
                          "invalid_control_summary"))
    same = (f"p.state={v('state')} AND {sql.same_json('p.checks', v('checks'))} "
            f"AND {sql.same_json('p.summary', v('summary'))}")
    assignments = f"checks={sql.document(v('checks'))},summary={sql.document(v('summary'))},state={v('state')}," \
        f"completed_at=CASE WHEN {sql.equal(v('state'), sql.literal('complete'))} " \
        f"THEN COALESCE(p.completed_at,{sql.now}) ELSE NULL END"
    body.append(sql.update(run, assignments, f"p.run_id={v('run_id')} AND NOT ({same})"))
    return sql.wrap("\n".join(body), declarations)


def resume_statements(engine):
    """Resume one uncompacted run using the same locked storage boundary."""
    sql = _StorageSQL(engine.dialect.name)
    v = sql.variable
    run = engine.dialect.identifier_preparer.format_table(tables(engine.dialect.name)["pipeline_run"])
    declarations = {"raw_run": "text", "run_id": "uuid", "state": "text", "expected_state": "text",
                    "checks": "text", "observed_state": "text", "observed_checks": "text",
                    "observed_completed": "text", "expected_checks": "text", "expected_completion": "text", "compacted": "int"}
    body = [sql.assign("raw_run", sql.field("run_id")),
            sql.guard(sql.bad_uuid(v("raw_run")), "invalid_control_run"),
            sql.assign("run_id", sql.uuid(v("raw_run"))),
            sql.assign("state", sql.field("state")),
            sql.assign("expected_state", sql.field("expected_state")),
            sql.assign("expected_checks", sql.decode(sql.field("expected_checks"))),
            sql.assign("expected_completion", sql.field("expected_completion")),
            sql.assign("checks", sql.decode(sql.field("checks"))),
            sql.guard(f"{v('state')} IS NULL OR NOT ({sql.equal(v('state'), sql.literal('running'))}) "
                      f"OR {v('checks')} IS NULL OR NOT ({sql.equal(v('checks'), sql.literal('{}'))}) "
                      f"OR {v('expected_checks')} IS NULL OR {v('expected_completion')} IS NULL "
                      f"OR {v('expected_state')} IS NULL OR NOT ({sql.one_of(v('expected_state'), ['running', 'waiting', 'blocked', 'complete'])})",
                      "invalid_control_resume"),
            sql.read([("observed_state", "p.state"),
                      ("observed_checks", sql.text_value("p.checks")),
                      ("observed_completed", sql.stamp_token("p.completed_at")),
                      ("compacted", "CASE WHEN p.compacted_at IS NULL THEN 0 ELSE 1 END")],
                     f"{run} p", f"p.run_id={v('run_id')}", lock=True),
            sql.guard(f"{v('observed_state')} IS NULL", "unknown_control_run"),
            sql.guard(f"{v('compacted')}<>0", "compacted_control_run"),
            sql.guard(f"NOT ({sql.equal(v('observed_state'), v('expected_state'))} AND "
                      f"{sql.equal(v('observed_checks'), v('expected_checks'))} AND "
                      f"{sql.equal(v('observed_completed'), v('expected_completion'))}) AND NOT ("
                      f"{sql.equal(v('observed_state'), v('state'))} AND "
                      f"{sql.equal(v('observed_checks'), v('checks'))} AND {v('observed_completed')}='')",
                      "control_observations_changed")]
    same = f"p.state={v('state')} AND {sql.same_json('p.checks', v('checks'))} AND p.completed_at IS NULL"
    body.append(sql.update(run, f"state={v('state')},checks={sql.document(v('checks'))},completed_at=NULL",
                           f"p.run_id={v('run_id')} AND NOT ({same})"))
    return sql.wrap("\n".join(body), declarations, name="resume_run_prepared")


def record_run_resume(engine, wire):
    return _record(engine, wire, "resume_run_prepared")


def record_run_checks(engine, wire):
    return _record(engine, wire, "record_run_checks")


def _record(engine, wire, operation):
    dialect = engine.dialect.name
    query = {"postgresql": f"SELECT bookkeeping.{operation}(:w)",
             "mysql": f"CALL bookkeeping_{operation}(:w)",
             "mssql": f"EXEC bookkeeping.{operation} @p_wire=:w"}[dialect]
    try:
        if dialect == "postgresql":
            with engine.begin() as conn:
                conn.execute(text(query), {"w": wire})
        else:
            # The stored procedure owns its transaction on these engines.
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                conn.execute(text(query), {"w": wire})
    except DBAPIError as error:
        code = getattr(error.orig, "pgcode", None)
        number = error.orig.args[0] if getattr(error.orig, "args", ()) else None
        contention = (code in {"55P03", "40P01", "40001"} if dialect == "postgresql"
                      else number in {1205, 1213, 3572} if dialect == "mysql"
                      else number in {1205, 1222})
        if "control_observations_changed" in str(error.orig) or contention:
            raise StaleObservation("Control observations changed; refresh before transition") from None
        raise


class _StorageSQL:
    """Only SQL syntax varies; all engines use the enforcement sequence above."""
    def __init__(self, dialect):
        self.dialect = dialect
        self.count = "COUNT_BIG(*)" if dialect == "mssql" else "COUNT(*)"
        self.now = {"postgresql": "clock_timestamp()", "mysql": "UTC_TIMESTAMP(6)",
                    "mssql": "SYSUTCDATETIME()"}[dialect]

    def variable(self, name):
        return ("@v_" if self.dialect == "mssql" else "v_") + name

    def literal(self, value):
        return ("N" if self.dialect == "mssql" else "") + "'" + value.replace("'", "''") + "'"

    def field(self, key, *, source="p_wire"):
        if source == "p_wire" and self.dialect == "mssql":
            source = "@p_wire"
        if self.dialect == "postgresql":
            return f"({source}::jsonb->>{self.literal(key)})"
        if self.dialect == "mysql":
            return f"JSON_UNQUOTE(JSON_EXTRACT({source},'$.\"{key}\"'))"
        return f"(SELECT [value] FROM OPENJSON({source}) WHERE [key]={self.literal(key)})"

    def integer(self, value):
        return f"CAST({value} AS {'SIGNED' if self.dialect == 'mysql' else 'BIGINT'})"

    def bad_number(self, value):
        if self.dialect == "postgresql":
            return f"({value} IS NULL OR {value} !~ '^[0-9]+$')"
        if self.dialect == "mysql":
            return f"({value} IS NULL OR NOT ({value} REGEXP '^[0-9]+$'))"
        return f"({value} IS NULL OR {value}='' OR {value} COLLATE Latin1_General_100_BIN2 LIKE '%[^0-9]%')"

    def bad_uuid(self, value):
        if self.dialect == "postgresql":
            return f"{value} IS NULL"
        if self.dialect == "mysql":
            return f"{value} IS NULL OR CHAR_LENGTH({value})<>36 OR NOT IS_UUID({value})"
        return f"{value} IS NULL OR DATALENGTH({value})<>72 OR TRY_CONVERT(UNIQUEIDENTIFIER,{value}) IS NULL"

    def uuid(self, value):
        return f"REPLACE({value},'-','')" if self.dialect == "mysql" else f"CAST({value} AS {'uuid' if self.dialect == 'postgresql' else 'UNIQUEIDENTIFIER'})"

    def decode(self, value):
        if self.dialect == "postgresql":
            return f"convert_from(decode({value},'hex'),'UTF8')"
        if self.dialect == "mysql":
            return f"CONVERT(UNHEX({value}) USING utf8mb4)"
        return f"CONVERT(NVARCHAR(MAX),CONVERT(VARCHAR(MAX),CONVERT(VARBINARY(MAX),{value},2)) COLLATE Latin1_General_100_BIN2_UTF8)"

    def document(self, value):
        return f"CAST({value} AS jsonb)" if self.dialect == "postgresql" else value

    def text_value(self, value):
        kind = {"postgresql": "text", "mysql": "CHAR", "mssql": "NVARCHAR(MAX)"}[self.dialect]
        return f"CAST({value} AS {kind})"

    def stamp_token(self, value):
        """An opaque exact stored timestamp address, including sub-microsecond bits."""
        if self.dialect == "postgresql":
            token = f"encode(timestamptz_send({value}),'hex')"
        elif self.dialect == "mysql":
            token = f"DATE_FORMAT({value},'%Y-%m-%d %H:%i:%s.%f')"
        else:
            token = f"CONVERT(VARCHAR(64),CONVERT(VARBINARY(16),{value}),2)"
        return f"COALESCE({token},'')"

    def concat(self, values):
        return " || ".join(values) if self.dialect == "postgresql" else f"CONCAT({','.join(values)})"

    def one_of(self, value, allowed):
        return " OR ".join(f"({self.equal(value, self.literal(item))})" for item in allowed)

    def equal(self, left, right):
        if self.dialect == "mysql":
            return f"CAST({left} AS BINARY)=CAST({right} AS BINARY)"
        if self.dialect == "mssql":
            return f"CAST({left} AS VARBINARY(MAX))=CAST({right} AS VARBINARY(MAX))"
        return f"{left}={right}"

    def same_json(self, left, right):
        if self.dialect == "postgresql":
            return f"{left}={self.document(right)}"
        return self.equal(left, right)

    def has_expansion(self, value):
        if self.dialect == "postgresql":
            return f"({value}->'cursor' ? 'generated_step')"
        if self.dialect == "mysql":
            return f"JSON_CONTAINS_PATH({value},'one','$.cursor.generated_step')=1"
        return f"EXISTS(SELECT 1 FROM OPENJSON({value},'$.cursor') j WHERE j.[key]=N'generated_step')"

    def assign(self, name, value):
        return f"{self.variable(name)} := {value};" if self.dialect == "postgresql" else f"SET {self.variable(name)}={value};"

    def guard(self, condition, message):
        if self.dialect == "postgresql":
            return f"IF {condition} THEN RAISE EXCEPTION '{message}'; END IF;"
        if self.dialect == "mysql":
            return f"IF {condition} THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='{message}'; END IF;"
        return f"IF {condition} BEGIN; THROW 50001,'{message}',1; END;"

    def read(self, fields, origin, condition, *, lock=False):
        if self.dialect == "mssql":
            assignments = ','.join(f"{self.variable(name)}={value}" for name, value in fields)
            origin += " WITH (UPDLOCK,HOLDLOCK,ROWLOCK,NOWAIT)" if lock else ""
            return f"SELECT {assignments} FROM {origin} WHERE {condition};"
        values = ','.join(value for _, value in fields)
        variables = ','.join(self.variable(name) for name, _ in fields)
        return f"SELECT {values} INTO {variables} FROM {origin} WHERE {condition}" + (" FOR UPDATE NOWAIT" if lock else "") + ";"

    def update(self, table, assignments, condition):
        if self.dialect == "mssql":
            return f"UPDATE p SET {assignments} FROM {table} p WHERE {condition};"
        if self.dialect == "mysql":
            # MySQL accepts an alias on the destination; no column assignment
            # is ambiguous because values are distinct procedure variables.
            return f"UPDATE {table} p SET {assignments} WHERE {condition};"
        return f"UPDATE {table} AS p SET {assignments} WHERE {condition};"

    def wrap(self, body, variables, *, name="record_run_checks"):
        types = {"int": "BIGINT", "text": {"postgresql": "text", "mysql": "LONGTEXT CHARACTER SET utf8mb4", "mssql": "NVARCHAR(MAX)"}[self.dialect],
                 "uuid": {"postgresql": "uuid", "mysql": "CHAR(32)", "mssql": "UNIQUEIDENTIFIER"}[self.dialect]}
        if self.dialect == "postgresql":
            declarations = '\n'.join(f"{self.variable(name)} {types[kind]};" for name, kind in variables.items())
            return [f"""CREATE OR REPLACE FUNCTION bookkeeping.{name}(p_wire text) RETURNS void
                LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $control$
                DECLARE {declarations} BEGIN {body} END $control$;""",
                f"REVOKE ALL ON FUNCTION bookkeeping.{name}(text) FROM PUBLIC"]
        declarations = '\n'.join(f"DECLARE {self.variable(name)} {types[kind]};" for name, kind in variables.items())
        if self.dialect == "mysql":
            return [f"DROP PROCEDURE IF EXISTS bookkeeping_{name}", f"""CREATE PROCEDURE bookkeeping_{name}(IN p_wire LONGTEXT CHARACTER SET utf8mb4)
                SQL SECURITY DEFINER BEGIN {declarations}
                DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;
                SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
                START TRANSACTION; {body} COMMIT; END"""]
        return [f"""CREATE OR ALTER PROCEDURE bookkeeping.{name} @p_wire NVARCHAR(MAX)
            WITH EXECUTE AS OWNER AS BEGIN SET NOCOUNT ON; SET XACT_ABORT ON;
            {declarations} BEGIN TRY BEGIN TRANSACTION; {body} COMMIT TRANSACTION;
            END TRY BEGIN CATCH IF @@TRANCOUNT>0 ROLLBACK TRANSACTION; THROW; END CATCH END"""]
