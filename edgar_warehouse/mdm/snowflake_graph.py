"""Snowflake SQL generation for hosted Neo4j graph analytics tables."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Any, Callable

from edgar_warehouse.mdm.export import SnowflakeConnectionSettings


DEFAULT_TARGET_SCHEMA = "NEO4J_GRAPH_MIGRATION"
DEFAULT_MDM_SCHEMA = "MDM"
DEFAULT_NATIVE_APP_NAME = "Neo4j_Graph_Analytics"
DEFAULT_NATIVE_APP_DATABASE_ROLE = "NEO4J_GRAPH_ANALYTICS_MIGRATION_ROLE"
DEFAULT_NATIVE_APP_COMPUTE_POOL = "CPU_X64_XS"
DEFAULT_NATIVE_APP_USER_ROLE = "EDGARTOOLS_GRAPH_APP_USER"
DEFAULT_NATIVE_APP_ADMIN_ROLE = "EDGARTOOLS_GRAPH_APP_ADMIN"
ALLOWED_ENTITY_TYPES = ("adviser", "audit_firm", "company", "fund", "person", "security")
ALLOWED_RELATIONSHIP_TYPES = (
    "AUDITED_BY",           # Company → AuditFirm  (10-K XBRL dei_AuditorFirmId)
    "COMPANY_HOLDS",
    "EMPLOYED_BY",          # Person → Company     (DEF 14A proxy)
    "HAS_PARENT_COMPANY",
    "HOLDS",
    "INSTITUTIONAL_HOLDS",  # Adviser → Security   (13F holdings)
    "IS_ENTITY_OF",
    "IS_INSIDER",
    "IS_PERSON_OF",
    "ISSUED_BY",
    "MANAGES_FUND",
)
NODE_TABLES = (
    "MDM_GRAPH_NODES",
    "GRAPH_NODE_ADVISER",
    "GRAPH_NODE_AUDITFIRM",
    "GRAPH_NODE_COMPANY",
    "GRAPH_NODE_FUND",
    "GRAPH_NODE_PERSON",
    "GRAPH_NODE_SECURITY",
)
EDGE_TABLES = (
    "MDM_GRAPH_EDGES",
    "GRAPH_EDGE_AUDITED_BY",
    "GRAPH_EDGE_COMPANY_HOLDS",
    "GRAPH_EDGE_EMPLOYED_BY",
    "GRAPH_EDGE_HAS_PARENT_COMPANY",
    "GRAPH_EDGE_HOLDS",
    "GRAPH_EDGE_INSTITUTIONAL_HOLDS",
    "GRAPH_EDGE_IS_ENTITY_OF",
    "GRAPH_EDGE_IS_INSIDER",
    "GRAPH_EDGE_IS_PERSON_OF",
    "GRAPH_EDGE_ISSUED_BY",
    "GRAPH_EDGE_MANAGES_FUND",
)


@dataclass(frozen=True)
class SnowflakeGraphMigrationConfig:
    env: str
    output_dir: Path
    target_database: str | None = None
    target_schema: str = DEFAULT_TARGET_SCHEMA
    mdm_database: str | None = None
    mdm_schema: str = DEFAULT_MDM_SCHEMA
    silver_path: Path | None = None

    def resolved_target_database(self) -> str:
        return self.target_database or f"EDGARTOOLS_{self.env.upper()}"

    def resolved_mdm_database(self) -> str:
        return self.mdm_database or self.resolved_target_database()


class SnowflakeGraphValidationError(ValueError):
    """Raised when graph sync filters fail closed before Snowflake execution."""


@dataclass(frozen=True)
class SnowflakeGraphSyncConfig:
    target_database: str | None = None
    target_schema: str = DEFAULT_TARGET_SCHEMA
    mdm_database: str | None = None
    mdm_schema: str = DEFAULT_MDM_SCHEMA
    entity_types: tuple[str, ...] = ()
    relationship_types: tuple[str, ...] = ()
    limit: int | None = None
    limit_per_type: int | None = None

    def resolved_target_database(self, default_database: str | None = None) -> str:
        database = self.target_database or default_database
        if not database:
            raise SnowflakeGraphValidationError(
                "target_database is required when Snowflake connection settings do not provide a database"
            )
        return database

    def resolved_mdm_database(self, default_database: str | None = None) -> str:
        return self.mdm_database or self.resolved_target_database(default_database)


@dataclass(frozen=True)
class SnowflakeGraphSyncResult:
    node_count: int
    edge_count: int
    target_database: str
    target_schema: str
    node_tables: tuple[str, ...]
    edge_tables: tuple[str, ...]
    applied_filters: dict[str, Any]


@dataclass(frozen=True)
class SnowflakeGraphVerificationConfig:
    target_database: str | None = None
    target_schema: str = DEFAULT_TARGET_SCHEMA
    mdm_database: str | None = None
    mdm_schema: str = DEFAULT_MDM_SCHEMA
    sample_limit: int = 20
    verify_native_app: bool = True
    native_app_name: str = DEFAULT_NATIVE_APP_NAME
    native_app_database_role: str = DEFAULT_NATIVE_APP_DATABASE_ROLE
    native_app_compute_pool: str = DEFAULT_NATIVE_APP_COMPUTE_POOL
    native_app_user_role: str = DEFAULT_NATIVE_APP_USER_ROLE
    native_app_admin_role: str = DEFAULT_NATIVE_APP_ADMIN_ROLE

    def resolved_target_database(self, default_database: str | None = None) -> str:
        database = self.target_database or default_database
        if not database:
            raise SnowflakeGraphValidationError(
                "target_database is required when Snowflake connection settings do not provide a database"
            )
        return database

    def resolved_mdm_database(self, default_database: str | None = None) -> str:
        return self.mdm_database or self.resolved_target_database(default_database)


@dataclass(frozen=True)
class SnowflakeGraphVerificationResult:
    passed: bool
    payload: dict[str, Any]


class SnowflakeGraphSyncExecutor:
    """Materialize Snowflake graph tables through a connector-style connection."""

    def __init__(self, connection: Any, *, default_database: str | None = None) -> None:
        self.connection = connection
        self.default_database = default_database

    @classmethod
    def from_env(cls) -> "SnowflakeGraphSyncExecutor":
        settings = SnowflakeConnectionSettings.from_env()
        return cls(settings.connect(), default_database=settings.database)

    def sync(self, config: SnowflakeGraphSyncConfig) -> SnowflakeGraphSyncResult:
        target_database = config.resolved_target_database(self.default_database)
        mdm_database = config.resolved_mdm_database(self.default_database)
        entity_types = _normalize_entity_types(config.entity_types)
        relationship_types = _normalize_relationship_types(config.relationship_types)
        limit = _validate_limit(config.limit, "limit")
        limit_per_type = _validate_limit(config.limit_per_type, "limit_per_type")
        context = _graph_context(
            target_database=target_database,
            target_schema=config.target_schema,
            mdm_database=mdm_database,
            mdm_schema=config.mdm_schema,
            entity_types=entity_types,
            relationship_types=relationship_types,
            limit=limit,
            limit_per_type=limit_per_type,
        )
        cursor = self.connection.cursor()
        try:
            _execute_sql_script(cursor, render_graph_tables(context))
            node_count = _fetch_scalar(
                cursor,
                f"SELECT COUNT(*) FROM {_fq(context, 'MDM_GRAPH_NODES')}",
            )
            edge_count = _fetch_scalar(
                cursor,
                f"SELECT COUNT(*) FROM {_fq(context, 'MDM_GRAPH_EDGES')}",
            )
        finally:
            cursor.close()

        return SnowflakeGraphSyncResult(
            node_count=node_count,
            edge_count=edge_count,
            target_database=target_database,
            target_schema=config.target_schema,
            node_tables=NODE_TABLES,
            edge_tables=EDGE_TABLES,
            applied_filters={
                "entity_types": entity_types,
                "relationship_types": relationship_types,
                "limit": limit,
                "limit_per_type": limit_per_type,
            },
        )


class SnowflakeGraphVerifier:
    """Verify Snowflake graph tables against active MDM source rows."""

    def __init__(self, connection: Any, *, default_database: str | None = None) -> None:
        self.connection = connection
        self.default_database = default_database

    @classmethod
    def from_env(cls) -> "SnowflakeGraphVerifier":
        settings = SnowflakeConnectionSettings.from_env()
        return cls(settings.connect(), default_database=settings.database)

    def verify(self, config: SnowflakeGraphVerificationConfig) -> SnowflakeGraphVerificationResult:
        sample_limit = _validate_limit(config.sample_limit, "sample_limit") or 20
        context = {
            "target_database": _ident(config.resolved_target_database(self.default_database)),
            "target_schema": _ident(config.target_schema),
            "mdm_database": _ident(config.resolved_mdm_database(self.default_database)),
            "mdm_schema": _ident(config.mdm_schema),
            "sample_limit": sample_limit,
        }
        cursor = self.connection.cursor()
        try:
            node_rows = _fetch_rows(
                cursor,
                _render_verify_node_counts(context),
                (
                    "ENTITY_TYPE",
                    "MDM_ACTIVE_COUNT",
                    "SNOWFLAKE_GRAPH_NODE_COUNT",
                    "MDM_MINUS_GRAPH",
                    "GRAPH_MINUS_MDM",
                ),
            )
            relationship_rows = _fetch_rows(
                cursor,
                _render_verify_relationship_counts(context),
                (
                    "RELATIONSHIP_TYPE",
                    "MDM_ACTIVE_COUNT",
                    "SNOWFLAKE_GRAPH_EDGE_COUNT",
                    "MDM_MINUS_GRAPH",
                    "GRAPH_MINUS_MDM",
                ),
            )
            diagnostics = {
                "missing_graph_nodes": _format_sample_rows(
                    _fetch_rows(cursor, _render_missing_nodes(context), ("ENTITY_TYPE", "NODEID")),
                    ("ENTITY_TYPE", "NODEID"),
                ),
                "extra_graph_nodes": _format_sample_rows(
                    _fetch_rows(cursor, _render_extra_nodes(context), ("ENTITY_TYPE", "NODEID")),
                    ("ENTITY_TYPE", "NODEID"),
                ),
                "missing_graph_edges": _format_sample_rows(
                    _fetch_rows(cursor, _render_missing_edges(context), ("RELATIONSHIP_TYPE", "EDGEID")),
                    ("RELATIONSHIP_TYPE", "EDGEID"),
                ),
                "extra_graph_edges": _format_sample_rows(
                    _fetch_rows(cursor, _render_extra_edges(context), ("RELATIONSHIP_TYPE", "EDGEID")),
                    ("RELATIONSHIP_TYPE", "EDGEID"),
                ),
                "missing_graph_edge_endpoints": _format_sample_rows(
                    _fetch_rows(
                        cursor,
                        _render_missing_edge_endpoints(context),
                        (
                            "RELATIONSHIP_TYPE",
                            "EDGEID",
                            "SOURCENODEID",
                            "TARGETNODEID",
                            "MISSING_SOURCE_NODE",
                            "MISSING_TARGET_NODE",
                        ),
                    ),
                    (
                        "RELATIONSHIP_TYPE",
                        "EDGEID",
                        "SOURCENODEID",
                        "TARGETNODEID",
                        "MISSING_SOURCE_NODE",
                        "MISSING_TARGET_NODE",
                    ),
                ),
            }
            native_app = _verify_native_app(cursor, context, config)
        finally:
            cursor.close()

        node_parity = _node_parity_payload(node_rows)
        relationship_parity = _relationship_parity_payload(relationship_rows)
        diagnostics_clean = all(not rows for rows in diagnostics.values())
        native_app_ok = (
            not native_app["required"]
            or native_app["status"] == "ok"
        )
        passed = (
            node_parity["status"] == "ok"
            and relationship_parity["status"] == "ok"
            and diagnostics_clean
            and native_app_ok
        )
        payload = {
            "status": "ok" if passed else "failed",
            "snowflake_graph_nodes": node_parity["total_snowflake_graph"],
            "snowflake_graph_edges": relationship_parity["total_snowflake_graph"],
            "target": {
                "database": context["target_database"],
                "schema": context["target_schema"],
            },
            "node_parity": node_parity,
            "relationship_parity": relationship_parity,
            "diagnostics": diagnostics,
            "native_app": native_app,
        }
        return SnowflakeGraphVerificationResult(passed=passed, payload=payload)


def _verify_native_app(
    cursor: Any,
    context: dict[str, Any],
    config: SnowflakeGraphVerificationConfig,
) -> dict[str, Any]:
    if not config.verify_native_app:
        return {
            "status": "skipped",
            "required": False,
            "phase3_acceptance": False,
            "remediation": "Run without --skip-native-app for live Phase 3 acceptance.",
            "checks": [],
        }

    app_name = _ident(config.native_app_name)
    database_role = _ident(config.native_app_database_role)
    compute_pool = _ident(config.native_app_compute_pool)
    user_role = _ident(config.native_app_user_role)
    admin_role = _ident(config.native_app_admin_role)
    grant_script = "infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql"
    checks: list[dict[str, Any]] = []

    checks.append(
        _native_rows_check(
            cursor,
            name="app_installation",
            sql=_render_native_app_installation(config.native_app_name),
            ok=lambda rows: bool(rows),
            remediation=(
                f"Install and activate the Snowflake Native App as {config.native_app_name}."
            ),
        )
    )
    checks.append(
        _native_rows_check(
            cursor,
            name="app_user_role_grant",
            sql=_render_native_app_role_grant(app_name, "app_user"),
            ok=lambda rows: _rows_contain_all(rows, (user_role,)),
            remediation=(
                f"Run {grant_script} or grant APPLICATION ROLE {app_name}.app_user "
                f"TO ROLE {user_role}."
            ),
        )
    )
    checks.append(
        _native_rows_check(
            cursor,
            name="app_admin_role_grant",
            sql=_render_native_app_role_grant(app_name, "app_admin"),
            ok=lambda rows: _rows_contain_all(rows, (admin_role,)),
            remediation=(
                f"Run {grant_script} or grant APPLICATION ROLE {app_name}.app_admin "
                f"TO ROLE {admin_role}."
            ),
        )
    )
    checks.append(
        _native_rows_check(
            cursor,
            name="database_role_to_application",
            sql=_render_native_app_database_role_to_application(app_name),
            ok=lambda rows: _rows_contain_all(rows, (database_role,)),
            remediation=(
                f"Run {grant_script} to grant DATABASE ROLE {database_role} "
                f"TO APPLICATION {app_name}."
            ),
        )
    )
    checks.append(
        _native_rows_check(
            cursor,
            name="database_role_privileges",
            sql=_render_native_app_database_role_privileges(context, database_role),
            ok=lambda rows: _database_role_privileges_ok(rows, context),
            remediation=(
                f"Run {grant_script} to grant USAGE, SELECT, and scoped CREATE TABLE "
                f"on {context['target_database']}.{context['target_schema']}."
            ),
        )
    )
    checks.append(
        _native_rows_check(
            cursor,
            name="compute_pool",
            sql=_render_native_app_compute_pools(app_name),
            ok=lambda rows: _rows_contain_all(rows, (compute_pool,)),
            remediation=(
                f"Activate {app_name} and confirm compute pool selector {compute_pool} "
                "is available from GRAPH.SHOW_AVAILABLE_COMPUTE_POOLS()."
            ),
        )
    )

    sample_check, sample_node_id = _native_sample_node_check(cursor, context)
    checks.append(sample_check)
    if all(check["status"] == "ok" for check in checks):
        checks.extend(
            [
                _native_execute_check(
                    cursor,
                    name="graph_info",
                    sql=_render_native_app_graph_info(context, app_name, compute_pool),
                    remediation=(
                        f"Run {grant_script} and confirm {app_name}.GRAPH.GRAPH_INFO "
                        "can read the graph schema."
                    ),
                ),
                _native_execute_check(
                    cursor,
                    name="bfs",
                    sql=_render_native_app_bfs(context, app_name, compute_pool, sample_node_id),
                    remediation=(
                        f"Run {grant_script}; then retry BFS with compute pool {compute_pool} "
                        "against the hosted MDM graph."
                    ),
                ),
                _native_execute_check(
                    cursor,
                    name="wcc",
                    sql=_render_native_app_wcc(context, app_name, compute_pool),
                    remediation=(
                        f"Run {grant_script}; then retry WCC with compute pool {compute_pool} "
                        "against the hosted MDM graph."
                    ),
                ),
            ]
        )

    status = "ok" if all(check["status"] == "ok" for check in checks) else "failed"
    return {
        "status": status,
        "required": True,
        "phase3_acceptance": status == "ok",
        "app_name": app_name,
        "database_role": database_role,
        "compute_pool": compute_pool,
        "checks": checks,
    }


def _native_rows_check(
    cursor: Any,
    *,
    name: str,
    sql: str,
    ok: Callable[[list[Any]], bool],
    remediation: str,
) -> dict[str, Any]:
    try:
        rows = _fetch_raw_rows(cursor, sql)
    except Exception as exc:  # pragma: no cover - exercised by live connector failures
        return _native_failed_check(name, remediation, exc)
    if ok(rows):
        return {"name": name, "status": "ok", "row_count": len(rows)}
    return {
        "name": name,
        "status": "failed",
        "row_count": len(rows),
        "remediation": remediation,
    }


def _native_execute_check(
    cursor: Any,
    *,
    name: str,
    sql: str,
    remediation: str,
) -> dict[str, Any]:
    try:
        rows = _fetch_raw_rows(cursor, sql)
    except Exception as exc:  # pragma: no cover - exercised by live connector failures
        return _native_failed_check(name, remediation, exc)
    return {"name": name, "status": "ok", "row_count": len(rows)}


def _native_sample_node_check(
    cursor: Any,
    context: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    remediation = (
        f"Materialize graph rows in {context['target_database']}.{context['target_schema']} "
        "with `edgar-warehouse mdm sync-graph` before running Native App smoke checks."
    )
    try:
        rows = _fetch_rows(
            cursor,
            _render_native_app_sample_node(context),
            ("NODEID",),
        )
    except Exception as exc:  # pragma: no cover - exercised by live connector failures
        return _native_failed_check("graph_schema_sample", remediation, exc), ""
    sample_node_id = str(rows[0]["NODEID"]) if rows and rows[0]["NODEID"] else ""
    if sample_node_id:
        return {
            "name": "graph_schema_sample",
            "status": "ok",
            "row_count": len(rows),
            "sample_nodeid": sample_node_id,
        }, sample_node_id
    return {
        "name": "graph_schema_sample",
        "status": "failed",
        "row_count": len(rows),
        "remediation": remediation,
    }, ""


def _native_failed_check(name: str, remediation: str, exc: Exception) -> dict[str, Any]:
    return {
        "name": name,
        "status": "failed",
        "remediation": remediation,
        "error": f"{exc.__class__.__name__}: {exc}",
    }


def _fetch_raw_rows(cursor: Any, sql: str) -> list[Any]:
    result = cursor.execute(sql)
    fetch_source = result if hasattr(result, "fetchall") else cursor
    return list(fetch_source.fetchall())


def _rows_contain_all(rows: list[Any], values: tuple[str, ...]) -> bool:
    required = tuple(str(value).upper() for value in values)
    return any(all(value in _row_text(row) for value in required) for row in rows)


def _database_role_privileges_ok(rows: list[Any], context: dict[str, Any]) -> bool:
    required_grants = (
        ("USAGE", "DATABASE", context["target_database"]),
        ("USAGE", "SCHEMA", context["target_schema"]),
        ("SELECT", "TABLE"),
        ("SELECT", "VIEW"),
        ("CREATE TABLE", "SCHEMA", context["target_schema"]),
    )
    return all(
        any(all(value in _row_text(row) for value in grant) for row in rows)
        for grant in required_grants
    )


def _row_text(row: Any) -> str:
    if isinstance(row, dict):
        values = row.values()
    elif isinstance(row, (list, tuple)):
        values = row
    else:
        values = (row,)
    return " ".join(str(value).upper() for value in values if value is not None)


def _execute_sql_script(cursor: Any, sql: str) -> None:
    for statement in _split_sql_statements(sql):
        cursor.execute(statement)


def _split_sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False
    index = 0

    while index < len(sql):
        char = sql[index]
        current.append(char)
        if char == "'":
            if in_single_quote and index + 1 < len(sql) and sql[index + 1] == "'":
                current.append(sql[index + 1])
                index += 2
                continue
            in_single_quote = not in_single_quote
        elif char == ";" and not in_single_quote:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        index += 1

    trailing = "".join(current).strip()
    if trailing:
        statements.append(trailing)
    return statements


def generate_snowflake_graph_migration(config: SnowflakeGraphMigrationConfig) -> dict[str, Path]:
    """Write SQL files that build graph-ready tables inside Snowflake.

    Neo4j Graph Analytics is treated as Snowflake-hosted. The generated SQL
    reads Snowflake MDM mirror tables directly; it does not require Aura,
    Bolt, `NEO4J_*` credentials, or JSONL exports from an external graph.
    """
    context = _graph_context(
        target_database=config.resolved_target_database(),
        target_schema=config.target_schema,
        mdm_database=config.resolved_mdm_database(),
        mdm_schema=config.mdm_schema,
        silver_path=config.silver_path,
    )

    files = {
        "00_graph_tables.sql": render_graph_tables(context),
        "01_validation.sql": render_validation(context),
        "02_hosted_neo4j_e2e.sql": render_hosted_neo4j_e2e(context),
        "README.md": render_readme(context),
    }
    config.output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for name, content in files.items():
        path = config.output_dir / name
        path.write_text(content.rstrip() + "\n", encoding="utf-8")
        written[name] = path
    return written


def run_snowflake_graph_sql(files: dict[str, Path], *, snow_connection: str) -> list[str]:
    """Execute generated SQL files with Snowflake CLI in deterministic order."""
    executed: list[str] = []
    for name in sorted(files):
        if not name.endswith(".sql"):
            continue
        path = files[name]
        subprocess.run(
            ["snow", "sql", "-c", snow_connection, "-f", str(path)],
            check=True,
        )
        executed.append(name)
    return executed


def run_hosted_neo4j_e2e(files: dict[str, Path], *, snow_connection: str) -> list[str]:
    """Execute only the read-only hosted Neo4j Graph Analytics e2e SQL."""
    path = files["02_hosted_neo4j_e2e.sql"]
    subprocess.run(
        ["snow", "sql", "-c", snow_connection, "-f", str(path)],
        check=True,
    )
    return ["02_hosted_neo4j_e2e.sql"]


def render_graph_tables(context: dict[str, Any]) -> str:
    return f"""-- Build graph-ready node and edge tables for Snowflake-hosted Neo4j Graph Analytics.
-- Neo4j is not external in this flow. Source data comes from Snowflake MDM mirror tables.

CREATE SCHEMA IF NOT EXISTS {context["target_database"]}.{context["target_schema"]};

CREATE OR REPLACE TABLE {_fq(context, "MDM_GRAPH_NODES")} AS
SELECT
  E.ENTITY_ID::STRING AS NODEID,
  ETD.NEO4J_LABEL::STRING AS LABEL,
  E.ENTITY_TYPE::STRING AS ENTITY_TYPE,
  'mdm' AS SOURCE_SYSTEM,
  COALESCE(
    C.VALID_FROM,
    A.VALID_FROM,
    P.VALID_FROM,
    S.VALID_FROM,
    F.VALID_FROM,
    E.UPDATED_AT
  ) AS SOURCE_UPDATED_AT,
  E.CREATED_AT AS CREATED_AT,
  E.UPDATED_AT AS UPDATED_AT,
  OBJECT_CONSTRUCT_KEEP_NULL(
    'entity_id', E.ENTITY_ID,
    'entity_type', E.ENTITY_TYPE,
    'label', ETD.NEO4J_LABEL,
    'cik', COALESCE(C.CIK, A.CIK),
    'owner_cik', P.OWNER_CIK,
    'crd_number', A.CRD_NUMBER,
    'canonical_name', COALESCE(C.CANONICAL_NAME, A.CANONICAL_NAME, P.CANONICAL_NAME, F.CANONICAL_NAME),
    'canonical_title', S.CANONICAL_TITLE,
    'ticker', COALESCE(C.TICKER, C.PRIMARY_TICKER),
    'primary_ticker', C.PRIMARY_TICKER,
    'primary_exchange', C.PRIMARY_EXCHANGE,
    'issuer_entity_id', S.ISSUER_ENTITY_ID,
    'adviser_entity_id', F.ADVISER_ENTITY_ID,
    'parent_company_entity_id', C.PARENT_COMPANY_ENTITY_ID,
    'security_type', S.SECURITY_TYPE,
    'fund_type', F.FUND_TYPE,
    'primary_role', P.PRIMARY_ROLE
  ) AS PROPERTIES
FROM {_mdm_fq(context, "MDM_ENTITY")} E
JOIN {_mdm_fq(context, "MDM_ENTITY_TYPE_DEFINITION")} ETD
  ON ETD.ENTITY_TYPE = E.ENTITY_TYPE
 AND ETD.IS_ACTIVE = TRUE
LEFT JOIN {_mdm_fq(context, "MDM_COMPANY")} C
  ON C.ENTITY_ID = E.ENTITY_ID
 AND E.ENTITY_TYPE = 'company'
LEFT JOIN {_mdm_fq(context, "MDM_ADVISER")} A
  ON A.ENTITY_ID = E.ENTITY_ID
 AND E.ENTITY_TYPE = 'adviser'
LEFT JOIN {_mdm_fq(context, "MDM_PERSON")} P
  ON P.ENTITY_ID = E.ENTITY_ID
 AND E.ENTITY_TYPE = 'person'
LEFT JOIN {_mdm_fq(context, "MDM_SECURITY")} S
  ON S.ENTITY_ID = E.ENTITY_ID
 AND E.ENTITY_TYPE = 'security'
LEFT JOIN {_mdm_fq(context, "MDM_FUND")} F
  ON F.ENTITY_ID = E.ENTITY_ID
 AND E.ENTITY_TYPE = 'fund'
WHERE E.IS_QUARANTINED = FALSE{context["entity_type_filter"]}
{context["entity_per_type_limit"]}{context["entity_limit"]};

CREATE OR REPLACE TABLE {_fq(context, "MDM_GRAPH_EDGES")} AS
SELECT
  RI.INSTANCE_ID::STRING AS EDGEID,
  RT.REL_TYPE_NAME::STRING AS RELATIONSHIP_TYPE,
  RI.SOURCE_ENTITY_ID::STRING AS SOURCENODEID,
  RI.TARGET_ENTITY_ID::STRING AS TARGETNODEID,
  RT.SOURCE_NODE_TYPE::STRING AS SOURCE_ENTITY_TYPE,
  RT.TARGET_NODE_TYPE::STRING AS TARGET_ENTITY_TYPE,
  RI.SOURCE_SYSTEM::STRING AS SOURCE_SYSTEM,
  RI.SOURCE_ACCESSION::STRING AS SOURCE_ACCESSION,
  RI.EFFECTIVE_FROM AS EFFECTIVE_FROM,
  RI.EFFECTIVE_TO AS EFFECTIVE_TO,
  RT.MERGE_STRATEGY::STRING AS MERGE_STRATEGY,
  CASE
    WHEN RI.GRAPH_SYNCED_AT IS NULL THEN 'PENDING'
    ELSE 'SYNCED'
  END AS GRAPH_SYNC_STATUS,
  RI.GRAPH_SYNCED_AT AS GRAPH_SYNCED_AT,
  RI.CREATED_AT AS CREATED_AT,
  RI.UPDATED_AT AS UPDATED_AT,
  OBJECT_CONSTRUCT_KEEP_NULL(
    'instance_id', RI.INSTANCE_ID,
    'source_system', RI.SOURCE_SYSTEM,
    'source_accession', RI.SOURCE_ACCESSION,
    'effective_from', RI.EFFECTIVE_FROM,
    'effective_to', RI.EFFECTIVE_TO,
    'properties', TRY_PARSE_JSON(RI.PROPERTIES),
    'merge_strategy', RT.MERGE_STRATEGY,
    'source_node_type', RT.SOURCE_NODE_TYPE,
    'target_node_type', RT.TARGET_NODE_TYPE,
    'graph_sync_status', CASE
      WHEN RI.GRAPH_SYNCED_AT IS NULL THEN 'PENDING'
      ELSE 'SYNCED'
    END
  ) AS PROPERTIES
FROM {_mdm_fq(context, "MDM_RELATIONSHIP_INSTANCE")} RI
JOIN {_mdm_fq(context, "MDM_RELATIONSHIP_TYPE")} RT
  ON RT.REL_TYPE_ID = RI.REL_TYPE_ID
WHERE RI.IS_ACTIVE = TRUE
  AND RT.IS_ACTIVE = TRUE{context["relationship_type_filter"]}
{context["relationship_per_type_limit"]}{context["relationship_limit"]};

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_NODES")} AS
SELECT NODEID, LABEL, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_NODES")};

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGES")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")};

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_NODE_COMPANY")} AS
SELECT NODEID, LABEL, ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_UPDATED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_NODES")}
WHERE ENTITY_TYPE = 'company';

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_NODE_PERSON")} AS
SELECT NODEID, LABEL, ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_UPDATED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_NODES")}
WHERE ENTITY_TYPE = 'person';

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_NODE_SECURITY")} AS
SELECT NODEID, LABEL, ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_UPDATED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_NODES")}
WHERE ENTITY_TYPE = 'security';

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_NODE_ADVISER")} AS
SELECT NODEID, LABEL, ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_UPDATED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_NODES")}
WHERE ENTITY_TYPE = 'adviser';

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_NODE_FUND")} AS
SELECT NODEID, LABEL, ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_UPDATED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_NODES")}
WHERE ENTITY_TYPE = 'fund';

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_IS_INSIDER")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'IS_INSIDER';

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_HOLDS")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'HOLDS';

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_COMPANY_HOLDS")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'COMPANY_HOLDS';

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_ISSUED_BY")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'ISSUED_BY';

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_IS_ENTITY_OF")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'IS_ENTITY_OF';

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_HAS_PARENT_COMPANY")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'HAS_PARENT_COMPANY';

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_MANAGES_FUND")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'MANAGES_FUND';

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_IS_PERSON_OF")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'IS_PERSON_OF';

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_EMPLOYED_BY")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'EMPLOYED_BY';

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_AUDITED_BY")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'AUDITED_BY';

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_INSTITUTIONAL_HOLDS")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'INSTITUTIONAL_HOLDS';

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_NODE_COUNTS")} AS
SELECT LABEL, COUNT(*) AS NODE_COUNT
FROM {_fq(context, "MDM_GRAPH_NODES")}
GROUP BY LABEL;

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_COUNTS")} AS
SELECT RELATIONSHIP_TYPE, COUNT(*) AS EDGE_COUNT
FROM {_fq(context, "MDM_GRAPH_EDGES")}
GROUP BY RELATIONSHIP_TYPE;
"""


def render_validation(context: dict[str, Any]) -> str:
    return f"""-- Validation for Snowflake-hosted Neo4j Graph Analytics tables.

SELECT 'snowflake_graph_nodes' AS METRIC, COUNT(*) AS VALUE
FROM {_fq(context, "MDM_GRAPH_NODES")}
UNION ALL
SELECT 'snowflake_graph_edges' AS METRIC, COUNT(*) AS VALUE
FROM {_fq(context, "MDM_GRAPH_EDGES")}
UNION ALL
SELECT 'active_mdm_entities' AS METRIC, COUNT(*) AS VALUE
FROM {_mdm_fq(context, "MDM_ENTITY")} E
JOIN {_mdm_fq(context, "MDM_ENTITY_TYPE_DEFINITION")} ETD
  ON ETD.ENTITY_TYPE = E.ENTITY_TYPE
 AND ETD.IS_ACTIVE = TRUE
WHERE E.IS_QUARANTINED = FALSE
UNION ALL
SELECT 'mdm_relationship_instances_active' AS METRIC, COUNT(*) AS VALUE
FROM {_mdm_fq(context, "MDM_RELATIONSHIP_INSTANCE")}
WHERE IS_ACTIVE = TRUE;

SELECT LABEL, NODE_COUNT
FROM {_fq(context, "GRAPH_NODE_COUNTS")}
ORDER BY LABEL;

SELECT RELATIONSHIP_TYPE, EDGE_COUNT
FROM {_fq(context, "GRAPH_EDGE_COUNTS")}
ORDER BY RELATIONSHIP_TYPE;

SELECT
  'active_mdm_relationship_parity' AS CHECK_NAME,
  RT.REL_TYPE_NAME AS RELATIONSHIP_TYPE,
  COUNT(RI.INSTANCE_ID) AS MDM_ACTIVE_COUNT,
  COALESCE(G.EDGE_COUNT, 0) AS SNOWFLAKE_GRAPH_EDGE_COUNT,
  COUNT(RI.INSTANCE_ID) - COALESCE(G.EDGE_COUNT, 0) AS MDM_MINUS_GRAPH
FROM {_mdm_fq(context, "MDM_RELATIONSHIP_TYPE")} RT
LEFT JOIN {_mdm_fq(context, "MDM_RELATIONSHIP_INSTANCE")} RI
  ON RI.REL_TYPE_ID = RT.REL_TYPE_ID
 AND RI.IS_ACTIVE = TRUE
LEFT JOIN {_fq(context, "GRAPH_EDGE_COUNTS")} G
  ON G.RELATIONSHIP_TYPE = RT.REL_TYPE_NAME
WHERE RT.IS_ACTIVE = TRUE
GROUP BY RT.REL_TYPE_NAME, G.EDGE_COUNT
ORDER BY RT.REL_TYPE_NAME;

SELECT
  'missing_graph_edge_endpoints' AS CHECK_NAME,
  E.RELATIONSHIP_TYPE,
  E.SOURCENODEID,
  E.TARGETNODEID,
  E.EDGEID,
  IFF(S.NODEID IS NULL, TRUE, FALSE) AS MISSING_SOURCE_NODE,
  IFF(T.NODEID IS NULL, TRUE, FALSE) AS MISSING_TARGET_NODE
FROM {_fq(context, "MDM_GRAPH_EDGES")} E
LEFT JOIN {_fq(context, "MDM_GRAPH_NODES")} S
  ON S.NODEID = E.SOURCENODEID
LEFT JOIN {_fq(context, "MDM_GRAPH_NODES")} T
  ON T.NODEID = E.TARGETNODEID
WHERE S.NODEID IS NULL OR T.NODEID IS NULL
LIMIT 100;
"""


def render_hosted_neo4j_e2e(context: dict[str, Any]) -> str:
    return f"""-- Read-only e2e validation for Neo4j Graph Analytics hosted in Snowflake.
-- This checks existing Snowflake graph tables and Neo4j Graph Analytics result tables.

SELECT 'GRAPH_NODE_COMPANY' AS TABLE_NAME, COUNT(*) AS ROW_COUNT
FROM {_fq(context, "GRAPH_NODE_COMPANY")}
UNION ALL
SELECT 'GRAPH_NODE_PERSON', COUNT(*)
FROM {_fq(context, "GRAPH_NODE_PERSON")}
UNION ALL
SELECT 'GRAPH_NODE_SECURITY', COUNT(*)
FROM {_fq(context, "GRAPH_NODE_SECURITY")}
UNION ALL
SELECT 'GRAPH_EDGE_HOLDS', COUNT(*)
FROM {_fq(context, "GRAPH_EDGE_HOLDS")}
UNION ALL
SELECT 'GRAPH_EDGE_ISSUED_BY', COUNT(*)
FROM {_fq(context, "GRAPH_EDGE_ISSUED_BY")}
UNION ALL
SELECT 'GRAPH_EDGE_IS_INSIDER', COUNT(*)
FROM {_fq(context, "GRAPH_EDGE_IS_INSIDER")}
UNION ALL
SELECT 'GRAPH_NODE_COMPANY_PAGERANK', COUNT(*)
FROM {_fq(context, "GRAPH_NODE_COMPANY_PAGERANK")}
UNION ALL
SELECT 'GRAPH_NODE_COMPANY_COMMUNITY', COUNT(*)
FROM {_fq(context, "GRAPH_NODE_COMPANY_COMMUNITY")}
UNION ALL
SELECT 'GRAPH_SHORTEST_PATH_RESULTS', COUNT(*)
FROM {_fq(context, "GRAPH_SHORTEST_PATH_RESULTS")};
"""


def render_readme(context: dict[str, Any]) -> str:
    return f"""# Snowflake-Hosted Neo4j Graph Analytics

This generated runbook builds graph-ready node and edge tables inside Snowflake.
Neo4j is not an external Aura or Bolt runtime in this flow; all graph analytics
data is hosted in Snowflake and sourced from the Snowflake MDM mirror tables.

Run order:

1. `snow sql -c <connection> -f 00_graph_tables.sql`
2. `snow sql -c <connection> -f 01_validation.sql`
3. `snow sql -c <connection> -f 02_hosted_neo4j_e2e.sql`

Target schema: `{context["target_database"]}.{context["target_schema"]}`
MDM source schema: `{context["mdm_database"]}.{context["mdm_schema"]}`
Silver source: `{context["silver_path"] or "environment-backed"}`

The generated tables use Neo4j Graph Analytics friendly columns:

- `MDM_GRAPH_NODES(NODEID, LABEL, ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_UPDATED_AT, CREATED_AT, UPDATED_AT, PROPERTIES)`
- `MDM_GRAPH_EDGES(EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_SYSTEM, SOURCE_ACCESSION, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, PROPERTIES)`
- `GRAPH_NODE_*` views expose one Native App-compatible node table per label.
- `GRAPH_EDGE_*` views expose one Native App-compatible relationship table per type.

`MDM_GRAPH_NODES` and `MDM_GRAPH_EDGES` are the canonical contract tables.
`GRAPH_NODES` and `GRAPH_EDGES` remain compatibility views over the canonical
tables for older validation queries.

Neo4j Graph Analytics procedures such as `NEO4J_GRAPH_ANALYTICS.GRAPH.PAGE_RANK`,
`NEO4J_GRAPH_ANALYTICS.GRAPH.LOUVAIN`, and
`NEO4J_GRAPH_ANALYTICS.GRAPH.GRAPH_INFO` consume these generated graph tables.
This SQL generation step does not invoke those procedures. Algorithm output
tables should land in governed `{context["target_database"]}.{context["target_schema"]}`
tables with operator cleanup ownership.

For an already materialized Snowflake-hosted graph, run only
`02_hosted_neo4j_e2e.sql`. It validates existing graph node/edge tables and
Neo4j Graph Analytics result tables without mutating Snowflake.
"""


def _graph_context(
    *,
    target_database: str,
    target_schema: str,
    mdm_database: str,
    mdm_schema: str,
    silver_path: Path | None = None,
    entity_types: tuple[str, ...] = (),
    relationship_types: tuple[str, ...] = (),
    limit: int | None = None,
    limit_per_type: int | None = None,
) -> dict[str, Any]:
    return {
        "target_database": _ident(target_database),
        "target_schema": _ident(target_schema),
        "mdm_database": _ident(mdm_database),
        "mdm_schema": _ident(mdm_schema),
        "silver_path": silver_path,
        "entity_type_filter": _in_filter("E.ENTITY_TYPE", entity_types),
        "relationship_type_filter": _in_filter("RT.REL_TYPE_NAME", relationship_types),
        "entity_per_type_limit": _qualify_limit("E.ENTITY_TYPE", "E.ENTITY_ID", limit_per_type),
        "relationship_per_type_limit": _qualify_limit(
            "RT.REL_TYPE_NAME",
            "RI.INSTANCE_ID",
            limit_per_type,
        ),
        "entity_limit": _limit_clause(limit),
        "relationship_limit": _limit_clause(limit),
    }


def _normalize_entity_types(values: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(sorted({str(value).lower() for value in values}))
    invalid = [value for value in normalized if value not in ALLOWED_ENTITY_TYPES]
    if invalid:
        raise SnowflakeGraphValidationError(
            "Invalid entity type filter(s): "
            + ", ".join(invalid)
            + ". Allowed values: "
            + ", ".join(ALLOWED_ENTITY_TYPES)
        )
    return normalized


def _normalize_relationship_types(values: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(sorted({str(value).upper() for value in values}))
    invalid = [value for value in normalized if value not in ALLOWED_RELATIONSHIP_TYPES]
    if invalid:
        raise SnowflakeGraphValidationError(
            "Invalid relationship type filter(s): "
            + ", ".join(invalid)
            + ". Allowed values: "
            + ", ".join(ALLOWED_RELATIONSHIP_TYPES)
        )
    return normalized


def _validate_limit(value: int | None, name: str) -> int | None:
    if value is None:
        return None
    if value < 1:
        raise SnowflakeGraphValidationError(f"{name} must be a positive integer")
    return int(value)


def _in_filter(column: str, values: tuple[str, ...]) -> str:
    if not values:
        return ""
    quoted = ", ".join(_sql_literal(value) for value in values)
    return f"\n  AND {column} IN ({quoted})"


def _qualify_limit(partition_column: str, order_column: str, limit: int | None) -> str:
    if limit is None:
        return ""
    return (
        "QUALIFY ROW_NUMBER() OVER "
        f"(PARTITION BY {partition_column} ORDER BY {order_column}) <= {limit}\n"
    )


def _limit_clause(limit: int | None) -> str:
    if limit is None:
        return ""
    return f"LIMIT {limit}"


def _fetch_rows(cursor: Any, sql: str, columns: tuple[str, ...]) -> list[dict[str, Any]]:
    result = cursor.execute(sql)
    fetch_source = result if hasattr(result, "fetchall") else cursor
    rows = fetch_source.fetchall()
    return [_normalize_result_row(row, columns) for row in rows]


def _normalize_result_row(row: Any, columns: tuple[str, ...]) -> dict[str, Any]:
    if isinstance(row, dict):
        return {column: _dict_value(row, column) for column in columns}
    return {column: row[index] if index < len(row) else None for index, column in enumerate(columns)}


def _dict_value(row: dict[str, Any], column: str) -> Any:
    if column in row:
        return row[column]
    lowered = column.lower()
    if lowered in row:
        return row[lowered]
    return None


def _node_parity_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_type = [
        {
            "entity_type": str(row["ENTITY_TYPE"]),
            "mdm_active_count": _as_int(row["MDM_ACTIVE_COUNT"]),
            "snowflake_graph_node_count": _as_int(row["SNOWFLAKE_GRAPH_NODE_COUNT"]),
            "mdm_minus_graph": _as_int(row["MDM_MINUS_GRAPH"]),
            "graph_minus_mdm": _as_int(row["GRAPH_MINUS_MDM"]),
        }
        for row in rows
    ]
    failed = any(
        row["mdm_minus_graph"] != 0 or row["graph_minus_mdm"] != 0
        for row in by_type
    )
    return {
        "status": "failed" if failed else "ok",
        "total_mdm_active": sum(row["mdm_active_count"] for row in by_type),
        "total_snowflake_graph": sum(row["snowflake_graph_node_count"] for row in by_type),
        "by_entity_type": by_type,
    }


def _relationship_parity_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_type = [
        {
            "relationship_type": str(row["RELATIONSHIP_TYPE"]),
            "mdm_active_count": _as_int(row["MDM_ACTIVE_COUNT"]),
            "snowflake_graph_edge_count": _as_int(row["SNOWFLAKE_GRAPH_EDGE_COUNT"]),
            "mdm_minus_graph": _as_int(row["MDM_MINUS_GRAPH"]),
            "graph_minus_mdm": _as_int(row["GRAPH_MINUS_MDM"]),
        }
        for row in rows
    ]
    failed = any(
        row["mdm_minus_graph"] != 0 or row["graph_minus_mdm"] != 0
        for row in by_type
    )
    return {
        "status": "failed" if failed else "ok",
        "total_mdm_active": sum(row["mdm_active_count"] for row in by_type),
        "total_snowflake_graph": sum(row["snowflake_graph_edge_count"] for row in by_type),
        "by_relationship_type": by_type,
    }


def _format_sample_rows(rows: list[dict[str, Any]], columns: tuple[str, ...]) -> list[dict[str, Any]]:
    return [
        {column.lower(): row[column] for column in columns}
        for row in rows
    ]


def _as_int(value: Any) -> int:
    return int(value or 0)


def _render_verify_node_counts(context: dict[str, Any]) -> str:
    return f"""-- verify_graph:node_counts
WITH expected AS (
  SELECT E.ENTITY_TYPE, COUNT(*) AS MDM_ACTIVE_COUNT
  FROM {_mdm_fq(context, "MDM_ENTITY")} E
  JOIN {_mdm_fq(context, "MDM_ENTITY_TYPE_DEFINITION")} ETD
    ON ETD.ENTITY_TYPE = E.ENTITY_TYPE
   AND ETD.IS_ACTIVE = TRUE
  WHERE E.IS_QUARANTINED = FALSE
  GROUP BY E.ENTITY_TYPE
),
actual AS (
  SELECT ENTITY_TYPE, COUNT(*) AS SNOWFLAKE_GRAPH_NODE_COUNT
  FROM {_fq(context, "MDM_GRAPH_NODES")}
  GROUP BY ENTITY_TYPE
)
SELECT
  COALESCE(expected.ENTITY_TYPE, actual.ENTITY_TYPE) AS ENTITY_TYPE,
  COALESCE(expected.MDM_ACTIVE_COUNT, 0) AS MDM_ACTIVE_COUNT,
  COALESCE(actual.SNOWFLAKE_GRAPH_NODE_COUNT, 0) AS SNOWFLAKE_GRAPH_NODE_COUNT,
  COALESCE(expected.MDM_ACTIVE_COUNT, 0) - COALESCE(actual.SNOWFLAKE_GRAPH_NODE_COUNT, 0) AS MDM_MINUS_GRAPH,
  COALESCE(actual.SNOWFLAKE_GRAPH_NODE_COUNT, 0) - COALESCE(expected.MDM_ACTIVE_COUNT, 0) AS GRAPH_MINUS_MDM
FROM expected
FULL OUTER JOIN actual
  ON actual.ENTITY_TYPE = expected.ENTITY_TYPE
ORDER BY ENTITY_TYPE
"""


def _render_verify_relationship_counts(context: dict[str, Any]) -> str:
    return f"""-- verify_graph:relationship_counts
WITH expected AS (
  SELECT RT.REL_TYPE_NAME AS RELATIONSHIP_TYPE, COUNT(RI.INSTANCE_ID) AS MDM_ACTIVE_COUNT
  FROM {_mdm_fq(context, "MDM_RELATIONSHIP_TYPE")} RT
  LEFT JOIN {_mdm_fq(context, "MDM_RELATIONSHIP_INSTANCE")} RI
    ON RI.REL_TYPE_ID = RT.REL_TYPE_ID
   AND RI.IS_ACTIVE = TRUE
  WHERE RT.IS_ACTIVE = TRUE
  GROUP BY RT.REL_TYPE_NAME
),
actual AS (
  SELECT RELATIONSHIP_TYPE, COUNT(*) AS SNOWFLAKE_GRAPH_EDGE_COUNT
  FROM {_fq(context, "MDM_GRAPH_EDGES")}
  GROUP BY RELATIONSHIP_TYPE
)
SELECT
  COALESCE(expected.RELATIONSHIP_TYPE, actual.RELATIONSHIP_TYPE) AS RELATIONSHIP_TYPE,
  COALESCE(expected.MDM_ACTIVE_COUNT, 0) AS MDM_ACTIVE_COUNT,
  COALESCE(actual.SNOWFLAKE_GRAPH_EDGE_COUNT, 0) AS SNOWFLAKE_GRAPH_EDGE_COUNT,
  COALESCE(expected.MDM_ACTIVE_COUNT, 0) - COALESCE(actual.SNOWFLAKE_GRAPH_EDGE_COUNT, 0) AS MDM_MINUS_GRAPH,
  COALESCE(actual.SNOWFLAKE_GRAPH_EDGE_COUNT, 0) - COALESCE(expected.MDM_ACTIVE_COUNT, 0) AS GRAPH_MINUS_MDM
FROM expected
FULL OUTER JOIN actual
  ON actual.RELATIONSHIP_TYPE = expected.RELATIONSHIP_TYPE
ORDER BY RELATIONSHIP_TYPE
"""


def _render_missing_nodes(context: dict[str, Any]) -> str:
    return f"""-- verify_graph:missing_nodes
SELECT E.ENTITY_TYPE, E.ENTITY_ID::STRING AS NODEID
FROM {_mdm_fq(context, "MDM_ENTITY")} E
JOIN {_mdm_fq(context, "MDM_ENTITY_TYPE_DEFINITION")} ETD
  ON ETD.ENTITY_TYPE = E.ENTITY_TYPE
 AND ETD.IS_ACTIVE = TRUE
LEFT JOIN {_fq(context, "MDM_GRAPH_NODES")} G
  ON G.NODEID = E.ENTITY_ID::STRING
WHERE E.IS_QUARANTINED = FALSE
  AND G.NODEID IS NULL
ORDER BY E.ENTITY_TYPE, E.ENTITY_ID
LIMIT {context["sample_limit"]}
"""


def _render_extra_nodes(context: dict[str, Any]) -> str:
    return f"""-- verify_graph:extra_nodes
SELECT G.ENTITY_TYPE, G.NODEID
FROM {_fq(context, "MDM_GRAPH_NODES")} G
LEFT JOIN {_mdm_fq(context, "MDM_ENTITY")} E
  ON E.ENTITY_ID::STRING = G.NODEID
LEFT JOIN {_mdm_fq(context, "MDM_ENTITY_TYPE_DEFINITION")} ETD
  ON ETD.ENTITY_TYPE = E.ENTITY_TYPE
 AND ETD.IS_ACTIVE = TRUE
WHERE E.ENTITY_ID IS NULL
   OR E.IS_QUARANTINED = TRUE
   OR ETD.ENTITY_TYPE IS NULL
ORDER BY G.ENTITY_TYPE, G.NODEID
LIMIT {context["sample_limit"]}
"""


def _render_missing_edges(context: dict[str, Any]) -> str:
    return f"""-- verify_graph:missing_edges
SELECT RT.REL_TYPE_NAME AS RELATIONSHIP_TYPE, RI.INSTANCE_ID::STRING AS EDGEID
FROM {_mdm_fq(context, "MDM_RELATIONSHIP_INSTANCE")} RI
JOIN {_mdm_fq(context, "MDM_RELATIONSHIP_TYPE")} RT
  ON RT.REL_TYPE_ID = RI.REL_TYPE_ID
 AND RT.IS_ACTIVE = TRUE
LEFT JOIN {_fq(context, "MDM_GRAPH_EDGES")} G
  ON G.EDGEID = RI.INSTANCE_ID::STRING
WHERE RI.IS_ACTIVE = TRUE
  AND G.EDGEID IS NULL
ORDER BY RT.REL_TYPE_NAME, RI.INSTANCE_ID
LIMIT {context["sample_limit"]}
"""


def _render_extra_edges(context: dict[str, Any]) -> str:
    return f"""-- verify_graph:extra_edges
SELECT G.RELATIONSHIP_TYPE, G.EDGEID
FROM {_fq(context, "MDM_GRAPH_EDGES")} G
LEFT JOIN {_mdm_fq(context, "MDM_RELATIONSHIP_INSTANCE")} RI
  ON RI.INSTANCE_ID::STRING = G.EDGEID
LEFT JOIN {_mdm_fq(context, "MDM_RELATIONSHIP_TYPE")} RT
  ON RT.REL_TYPE_ID = RI.REL_TYPE_ID
 AND RT.IS_ACTIVE = TRUE
WHERE RI.INSTANCE_ID IS NULL
   OR RI.IS_ACTIVE = FALSE
   OR RT.REL_TYPE_ID IS NULL
ORDER BY G.RELATIONSHIP_TYPE, G.EDGEID
LIMIT {context["sample_limit"]}
"""


def _render_missing_edge_endpoints(context: dict[str, Any]) -> str:
    return f"""-- verify_graph:missing_edge_endpoints
SELECT
  E.RELATIONSHIP_TYPE,
  E.EDGEID,
  E.SOURCENODEID,
  E.TARGETNODEID,
  IFF(S.NODEID IS NULL, TRUE, FALSE) AS MISSING_SOURCE_NODE,
  IFF(T.NODEID IS NULL, TRUE, FALSE) AS MISSING_TARGET_NODE
FROM {_fq(context, "MDM_GRAPH_EDGES")} E
LEFT JOIN {_fq(context, "MDM_GRAPH_NODES")} S
  ON S.NODEID = E.SOURCENODEID
LEFT JOIN {_fq(context, "MDM_GRAPH_NODES")} T
  ON T.NODEID = E.TARGETNODEID
WHERE S.NODEID IS NULL OR T.NODEID IS NULL
ORDER BY E.RELATIONSHIP_TYPE, E.EDGEID
LIMIT {context["sample_limit"]}
"""


def _render_native_app_installation(app_name: str) -> str:
    return f"""-- verify_graph:native_app_installation
SHOW APPLICATIONS LIKE {_sql_literal(app_name)}
"""


def _render_native_app_role_grant(app_name: str, app_role: str) -> str:
    return f"""-- verify_graph:native_app_{app_role}_role
SHOW GRANTS OF APPLICATION ROLE {app_name}.{app_role}
"""


def _render_native_app_database_role_to_application(app_name: str) -> str:
    return f"""-- verify_graph:native_app_application_database_role
SHOW GRANTS TO APPLICATION {app_name}
"""


def _render_native_app_database_role_privileges(
    context: dict[str, Any],
    database_role: str,
) -> str:
    return f"""-- verify_graph:native_app_database_role_privileges
SHOW GRANTS TO DATABASE ROLE {context["target_database"]}.{database_role}
"""


def _render_native_app_compute_pools(app_name: str) -> str:
    return f"""-- verify_graph:native_app_compute_pools
CALL {app_name}.GRAPH.SHOW_AVAILABLE_COMPUTE_POOLS()
"""


def _render_native_app_sample_node(context: dict[str, Any]) -> str:
    return f"""-- verify_graph:native_app_sample_node
SELECT NODEID
FROM {_fq(context, "MDM_GRAPH_NODES")}
WHERE NODEID IS NOT NULL
ORDER BY NODEID
LIMIT 1
"""


def _render_native_app_graph_info(
    context: dict[str, Any],
    app_name: str,
    compute_pool: str,
) -> str:
    graph_name = f"{context['target_database']}.{context['target_schema']}"
    return f"""-- verify_graph:native_app_graph_info
SELECT *
FROM TABLE(
  {app_name}.GRAPH.GRAPH_INFO(
    {_sql_literal(graph_name)},
    {{
      'project_name': 'edgartools_mdm_verify_graph_info',
      'compute_pool': {_sql_literal(compute_pool)},
      'node_tables': ['MDM_GRAPH_NODES'],
      'relationship_tables': ['MDM_GRAPH_EDGES']
    }}
  )
)
"""


def _render_native_app_bfs(
    context: dict[str, Any],
    app_name: str,
    compute_pool: str,
    sample_node_id: str,
) -> str:
    graph_name = f"{context['target_database']}.{context['target_schema']}"
    return f"""-- verify_graph:native_app_bfs
SELECT *
FROM TABLE(
  {app_name}.GRAPH.BFS(
    {_sql_literal(graph_name)},
    {{
      'project_name': 'edgartools_mdm_verify_bfs',
      'compute_pool': {_sql_literal(compute_pool)},
      'node_tables': ['MDM_GRAPH_NODES'],
      'relationship_tables': ['MDM_GRAPH_EDGES'],
      'source_node_id': {_sql_literal(sample_node_id)},
      'max_depth': 2,
      'write_options': {{'output_prefix': 'MDM_GRAPH_VERIFY_BFS_SMOKE'}}
    }}
  )
)
"""


def _render_native_app_wcc(
    context: dict[str, Any],
    app_name: str,
    compute_pool: str,
) -> str:
    graph_name = f"{context['target_database']}.{context['target_schema']}"
    return f"""-- verify_graph:native_app_wcc
SELECT *
FROM TABLE(
  {app_name}.GRAPH.WCC(
    {_sql_literal(graph_name)},
    {{
      'project_name': 'edgartools_mdm_verify_wcc',
      'compute_pool': {_sql_literal(compute_pool)},
      'node_tables': ['MDM_GRAPH_NODES'],
      'relationship_tables': ['MDM_GRAPH_EDGES'],
      'write_options': {{'output_prefix': 'MDM_GRAPH_VERIFY_WCC_SMOKE'}}
    }}
  )
)
"""


def _fetch_scalar(cursor: Any, sql: str) -> int:
    cursor.execute(sql)
    row = cursor.fetchone()
    return int(row[0] if row else 0)


def _fq(context: dict[str, Any], name: str) -> str:
    return f"{context['target_database']}.{context['target_schema']}.{_ident(name)}"


def _mdm_fq(context: dict[str, Any], name: str) -> str:
    return f"{context['mdm_database']}.{context['mdm_schema']}.{_ident(name)}"


def _ident(value: str) -> str:
    cleaned = str(value).upper()
    if not cleaned.replace("_", "").isalnum() or not cleaned[0].isalpha():
        raise ValueError(f"Unsafe Snowflake identifier: {value!r}")
    return cleaned


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
