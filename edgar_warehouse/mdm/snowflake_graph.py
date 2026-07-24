"""Snowflake SQL generation for hosted Neo4j graph analytics tables."""
from __future__ import annotations

from dataclasses import dataclass
import json
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
# D-01 / EDGE-01..04: the 4 relationship types already populated this milestone.
# The remaining 7 ALLOWED_RELATIONSHIP_TYPES (AUDITED_BY, EMPLOYED_BY,
# HAS_PARENT_COMPANY, INSTITUTIONAL_HOLDS, IS_ENTITY_OF, IS_PERSON_OF,
# MANAGES_FUND) are intentionally excluded from named parity checks until
# Phases 6-7 populate them -- named-checking a legitimately-zero type this
# milestone does not yet cover would false-fail verify-graph (T-05-05).
#
# Phase 6 (fix-pipelines) investigated 5 of these 7 (EDGE-05 IS_ENTITY_OF,
# EDGE-06 IS_PERSON_OF, EDGE-09 EMPLOYED_BY, EDGE-10 AUDITED_BY, EDGE-11
# INSTITUTIONAL_HOLDS) and confirmed NONE reached graph-populated status --
# see 06-PHASE-CLOSURE-LEDGER.md for the evidenced disposition of each (two
# source-coverage exclusions, one structural-API exclusion, two confirmed
# bugs with an identified but deferred fix). None is added here: per D-05,
# a type must not enter this tuple before its own mdm sync-graph has
# produced rows -- adding any of the 5 now would false-fail verify-graph
# for a type this environment has never actually populated. HAS_PARENT_COMPANY
# and MANAGES_FUND remain out of Phase 6's scope entirely.
POPULATED_RELATIONSHIP_TYPES = ("COMPANY_HOLDS", "HOLDS", "ISSUED_BY", "IS_INSIDER")
NODE_TABLES = (
    "MDM_GRAPH_NODES",
    "GRAPH_APP_NODES",
    "GRAPH_NODE_ADVISER",
    "GRAPH_NODE_AUDITFIRM",
    "GRAPH_NODE_COMPANY",
    "GRAPH_NODE_FUND",
    "GRAPH_NODE_PERSON",
    "GRAPH_NODE_SECURITY",
)
EDGE_TABLES = (
    "MDM_GRAPH_EDGES",
    "GRAPH_APP_EDGES",
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
# 07-05 (RSYNC-01/02/05): the platform-owned generation registry and single
# guarded activation pointer. GRAPH_GENERATION is the authoritative graph
# discovery/lifecycle surface; GRAPH_ACTIVE_POINTER is the one row every
# stable GRAPH_APP_*/GRAPH_NODE_*/GRAPH_EDGE_* view joins against, so node and
# edge rows can never resolve to two different generations.
GENERATION_TABLES = ("GRAPH_GENERATION", "GRAPH_ACTIVE_POINTER")
GENERATION_STATUSES = ("building", "verified", "activated", "retired", "failed")
# Statuses a generation must have been in to be a legal rollback/retention target
# -- it passed verification and went live at some point (never 'building'/'failed').
RETAINABLE_GENERATION_STATUSES = ("activated", "retired")
DEFAULT_RETENTION_MIN_GENERATIONS = 3
DEFAULT_RETENTION_DAYS = 30


@dataclass(frozen=True)
class SnowflakeGraphMigrationConfig:
    env: str
    output_dir: Path
    target_database: str | None = None
    target_schema: str = DEFAULT_TARGET_SCHEMA
    mdm_database: str | None = None
    mdm_schema: str = DEFAULT_MDM_SCHEMA
    silver_path: Path | None = None
    # 07-05: this static/manual bootstrap script needs a real generation_id to
    # publish into (staged rows are additive, never a blanket replace). A
    # fixed, documented sentinel is fine here -- an operator running this
    # by hand activates it explicitly afterward (see README's activation step).
    generation_id: str = "bootstrap"

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
    # 07-05: the generation this sync publishes into. Required -- staged rows
    # are tagged GENERATION_ID and never blanket-replaced, so a sync without a
    # generation_id would have no way to scope its own DELETE+INSERT rebuild
    # (see render_graph_tables' additive publish, RSYNC-01/RSYNC-02). Should be
    # the same generation_id MDM's own mdm_graph_generation assigned (07-04),
    # so the Snowflake pointer and MDM serving reads agree on one generation.
    generation_id: str = ""
    rule_version: str = "v1"
    schema_version: str = "v1"

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
    # Optional rel_type_name -> status ("populated"|"valid_zero"|"excluded") map
    # from edgar_warehouse.mdm.coverage.compute_relationship_coverage_manifest.
    # When supplied, named relationship checks evaluate exhaustively over every
    # type in this map instead of only POPULATED_RELATIONSHIP_TYPES (07-02,
    # RCOV-01/02). When None, behavior is unchanged from before 07-02.
    relationship_coverage: dict[str, str] | None = None
    # 07-05: verify a specific candidate generation before it is activated.
    # None (default) verifies the currently-active generation, preserving
    # pre-07-05 verify-graph behavior for callers that don't yet participate
    # in the generation lifecycle.
    generation_id: str | None = None

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


class SnowflakeGraphActivationError(ValueError):
    """Raised when activation/rollback is attempted against a generation that
    is not in a legal state for that operation. Raising here happens strictly
    BEFORE any pointer-mutating SQL runs, so a rejected activation/rollback
    leaves the previous active pointer completely untouched (RSYNC-02)."""


@dataclass(frozen=True)
class SnowflakeGraphActivationResult:
    generation_id: str
    previous_generation_id: str | None


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
        if not config.generation_id:
            raise SnowflakeGraphValidationError(
                "generation_id is required -- staged rows are tagged per-generation "
                "and never blanket-replaced (07-05 additive publish)"
            )
        context = _graph_context(
            target_database=target_database,
            target_schema=config.target_schema,
            mdm_database=mdm_database,
            mdm_schema=config.mdm_schema,
            entity_types=entity_types,
            relationship_types=relationship_types,
            limit=limit,
            limit_per_type=limit_per_type,
            generation_id=config.generation_id,
            rule_version=config.rule_version,
            schema_version=config.schema_version,
        )
        cursor = self.connection.cursor()
        try:
            _execute_sql_script(cursor, render_graph_tables(context))
            node_count = _fetch_scalar(
                cursor,
                f"SELECT COUNT(*) FROM {_fq(context, 'MDM_GRAPH_NODES')} "
                f"WHERE GENERATION_ID = {context['generation_id_literal']}",
            )
            edge_count = _fetch_scalar(
                cursor,
                f"SELECT COUNT(*) FROM {_fq(context, 'MDM_GRAPH_EDGES')} "
                f"WHERE GENERATION_ID = {context['generation_id_literal']}",
            )
            cursor.execute(
                f"UPDATE {_fq(context, 'GRAPH_GENERATION')} "
                f"SET NODE_COUNT = {node_count}, EDGE_COUNT = {edge_count} "
                f"WHERE GENERATION_ID = {context['generation_id_literal']}"
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
                "generation_id": config.generation_id,
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
        generation_id = config.generation_id
        cursor = self.connection.cursor()
        try:
            node_rows = _fetch_rows(
                cursor,
                _render_verify_node_counts(context, generation_id),
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
                _render_verify_relationship_counts(context, generation_id),
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
                    _fetch_rows(cursor, _render_missing_nodes(context, generation_id), ("ENTITY_TYPE", "NODEID")),
                    ("ENTITY_TYPE", "NODEID"),
                ),
                "extra_graph_nodes": _format_sample_rows(
                    _fetch_rows(cursor, _render_extra_nodes(context, generation_id), ("ENTITY_TYPE", "NODEID")),
                    ("ENTITY_TYPE", "NODEID"),
                ),
                "missing_graph_edges": _format_sample_rows(
                    _fetch_rows(cursor, _render_missing_edges(context, generation_id), ("RELATIONSHIP_TYPE", "EDGEID")),
                    ("RELATIONSHIP_TYPE", "EDGEID"),
                ),
                "extra_graph_edges": _format_sample_rows(
                    _fetch_rows(cursor, _render_extra_edges(context, generation_id), ("RELATIONSHIP_TYPE", "EDGEID")),
                    ("RELATIONSHIP_TYPE", "EDGEID"),
                ),
                "missing_graph_edge_endpoints": _format_sample_rows(
                    _fetch_rows(
                        cursor,
                        _render_missing_edge_endpoints(context, generation_id),
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
            # 07-05 Task 2: identity/property-exact parity, not count-only --
            # a matching count with a different edge identity or property
            # must fail verification (RSYNC-02 acceptance criterion).
            exact_node_rows = _fetch_rows(
                cursor,
                _render_exact_node_parity(context, generation_id),
                ("MDM_CONTENT_HASH", "GRAPH_CONTENT_HASH", "MDM_ROW_COUNT", "GRAPH_ROW_COUNT", "IDENTITY_PROPERTY_MATCH"),
            )
            exact_relationship_rows = _fetch_rows(
                cursor,
                _render_exact_relationship_parity(context, generation_id),
                ("MDM_CONTENT_HASH", "GRAPH_CONTENT_HASH", "MDM_ROW_COUNT", "GRAPH_ROW_COUNT", "IDENTITY_PROPERTY_MATCH"),
            )
            canonical_remap_leaks = _format_sample_rows(
                _fetch_rows(
                    cursor,
                    _render_canonical_remap_leaks(context, generation_id),
                    ("EDGEID", "RELATIONSHIP_TYPE", "SOURCENODEID", "TARGETNODEID"),
                ),
                ("EDGEID", "RELATIONSHIP_TYPE", "SOURCENODEID", "TARGETNODEID"),
            )
            native_app = _verify_native_app(cursor, context, config)
        finally:
            cursor.close()

        node_parity = _node_parity_payload(node_rows)
        relationship_parity = _relationship_parity_payload(relationship_rows)
        diagnostics_clean = all(not rows for rows in diagnostics.values())
        exact_node_match = bool(exact_node_rows) and bool(exact_node_rows[0].get("IDENTITY_PROPERTY_MATCH"))
        exact_relationship_match = bool(exact_relationship_rows) and bool(
            exact_relationship_rows[0].get("IDENTITY_PROPERTY_MATCH")
        )
        exact_parity_ok = exact_node_match and exact_relationship_match and not canonical_remap_leaks
        native_app_ok = (
            not native_app["required"]
            or native_app["status"] == "ok"
        )
        # NODE-01..06 / EDGE-01..04 (D-01): named per-type checks over the parity
        # data already computed above -- no new SQL. A type missing entirely from
        # the parity rows is a hard failure here even when it contributed no row to
        # the aggregate node_parity/relationship_parity status (silent-omission gap).
        node_named_checks = _named_node_parity_checks(node_parity)
        relationship_named_checks = _named_relationship_parity_checks(
            relationship_parity, config.relationship_coverage
        )
        named_checks_ok = all(
            check["status"] == "ok" for check in node_named_checks
        ) and all(check["status"] == "ok" for check in relationship_named_checks)
        passed = (
            node_parity["status"] == "ok"
            and relationship_parity["status"] == "ok"
            and diagnostics_clean
            and native_app_ok
            and named_checks_ok
            and exact_parity_ok
        )
        parity_ok = (
            node_parity["status"] == "ok"
            and relationship_parity["status"] == "ok"
            and diagnostics_clean
            and named_checks_ok
            and exact_parity_ok
        )
        native_domains = native_app.get("domains", {})
        failure_domains: list[str] = []
        if not parity_ok:
            failure_domains.append("parity")
        for domain in ("readiness", "capability"):
            if native_domains.get(domain, {}).get("status") == "failed":
                failure_domains.append(domain)
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
            "named_checks": {
                "node_parity": node_named_checks,
                "relationship_parity": relationship_named_checks,
            },
            "exact_parity": {
                "status": "ok" if exact_parity_ok else "failed",
                "node_identity_property_match": exact_node_match,
                "relationship_identity_property_match": exact_relationship_match,
                "canonical_remap_leaks": canonical_remap_leaks,
            },
            "diagnostics": diagnostics,
            "native_app": native_app,
            "failure_domains": failure_domains,
            "failure_summary": {
                "parity": "ok" if parity_ok else "failed",
                "readiness": native_domains.get("readiness", {}).get("status", "skipped"),
                "capability": native_domains.get("capability", {}).get("status", "skipped"),
            },
        }
        # RSYNC-02: verifying an explicit candidate generation (not the
        # default "verify the active one") is what promotes it from
        # 'building' to 'verified' -- the only status activate_graph_
        # generation() accepts -- or demotes it to 'failed' with the reasons
        # recorded, mirroring 07-04's fan_in_generation on the MDM side.
        if generation_id:
            status_cursor = self.connection.cursor()
            try:
                if passed:
                    status_cursor.execute(
                        f"UPDATE {_fq(context, 'GRAPH_GENERATION')} "
                        f"SET STATUS = 'verified', VERIFIED_AT = CURRENT_TIMESTAMP() "
                        f"WHERE GENERATION_ID = {_sql_literal(generation_id)} AND STATUS = 'building'"
                    )
                else:
                    status_cursor.execute(
                        f"UPDATE {_fq(context, 'GRAPH_GENERATION')} "
                        f"SET STATUS = 'failed', FAILURE_REASONS = PARSE_JSON({_sql_literal(json.dumps(failure_domains))}) "
                        f"WHERE GENERATION_ID = {_sql_literal(generation_id)} AND STATUS = 'building'"
                    )
            finally:
                status_cursor.close()
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
            "domains": {
                "readiness": {"status": "skipped", "failed_checks": []},
                "capability": {"status": "skipped", "failed_checks": []},
            },
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
                f"Activate {app_name}: CALL {app_name}.INTERNAL.CREATE_COMPUTE_POOLS() and "
                f"CALL {app_name}.INTERNAL.GRANT_CALLBACK(['CREATE COMPUTE POOL','CREATE WAREHOUSE']) "
                "(SQL-only installs never fire the grant callback, so the app's pools and "
                "warehouse are missing until these run); then confirm compute pool selector "
                f"{compute_pool} is available from GRAPH.SHOW_AVAILABLE_COMPUTE_POOLS()."
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
                    f"Retry {app_name}.GRAPH.GRAPH_INFO with the current project/compute API "
                    "against GRAPH_APP_NODES/GRAPH_APP_EDGES."
                ),
            ),
            _native_execute_check(
                cursor,
                name="bfs",
                sql=_render_native_app_bfs(context, app_name, compute_pool, sample_node_id),
                remediation=(
                    f"Retry {app_name}.GRAPH.BFS with sourceNodeTable/sourceNode and clean "
                    "the governed MDM_GRAPH_VERIFY_BFS_SMOKE output table."
                ),
            ),
            _native_execute_check(
                cursor,
                name="wcc",
                sql=_render_native_app_wcc(context, app_name, compute_pool),
                remediation=(
                    f"Run {grant_script}; then retry WCC with compute pool {compute_pool} "
                    "against the hosted MDM graph (projects the GRAPH_APP_NODES/"
                    "GRAPH_APP_EDGES ID-only views created by `mdm sync-graph`)."
                ),
            ),
            _native_execute_check(
                cursor,
                name="list_graphs",
                sql=_render_native_app_list_graphs(app_name),
                remediation=(
                    "The installed EXPERIMENTAL.LIST_GRAPHS procedure is an optional diagnostic. "
                    "If it fails inside the Marketplace app, capture the app version and exact "
                    "error as an external blocker."
                ),
                blocking=False,
            ),
            ]
        )

    domains = _native_domain_payload(checks)
    status = "ok" if all(
        check["status"] == "ok" or not check.get("blocking", True)
        for check in checks
    ) else "failed"
    return {
        "status": status,
        "required": True,
        "phase3_acceptance": status == "ok",
        "app_name": app_name,
        "database_role": database_role,
        "compute_pool": compute_pool,
        "checks": checks,
        "domains": domains,
    }


def _native_rows_check(
    cursor: Any,
    *,
    name: str,
    sql: str,
    ok: Callable[[list[Any]], bool],
    remediation: str,
    domain: str = "readiness",
) -> dict[str, Any]:
    try:
        rows = _fetch_raw_rows(cursor, sql)
    except Exception as exc:  # pragma: no cover - exercised by live connector failures
        return _native_failed_check(name, remediation, exc, domain=domain)
    if ok(rows):
        return {"name": name, "status": "ok", "row_count": len(rows), "domain": domain}
    return {
        "name": name,
        "status": "failed",
        "row_count": len(rows),
        "remediation": remediation,
        "domain": domain,
    }


def _native_execute_check(
    cursor: Any,
    *,
    name: str,
    sql: str,
    remediation: str,
    blocking: bool = True,
) -> dict[str, Any]:
    try:
        rows = _fetch_raw_rows(cursor, sql)
    except Exception as exc:  # pragma: no cover - exercised by live connector failures
        return _native_failed_check(name, remediation, exc, domain="capability", blocking=blocking)
    # The app's job procedures report failures as result rows (JOB_STATUS
    # 'ERROR' with detail in JOB_RESULT) while the SELECT itself succeeds,
    # so a successful fetch alone does not mean the job ran.
    for row in rows:
        if isinstance(row, dict):
            raw_values = row.values()
        elif isinstance(row, (list, tuple)):
            raw_values = row
        else:
            raw_values = [row]
        values = [str(v) for v in raw_values]
        if any(v == "ERROR" for v in values):
            detail = " | ".join(v[:200] for v in values if v and v != "ERROR")
            return _native_failed_check(
                name,
                remediation,
                RuntimeError(f"job reported ERROR: {detail}"),
                domain="capability",
                blocking=blocking,
            )
    return {
        "name": name,
        "status": "ok",
        "row_count": len(rows),
        "domain": "capability",
        "blocking": blocking,
    }


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
            "domain": "readiness",
        }, sample_node_id
    return {
        "name": "graph_schema_sample",
        "status": "failed",
        "row_count": len(rows),
        "remediation": remediation,
        "domain": "readiness",
    }, ""


def _native_failed_check(
    name: str,
    remediation: str,
    exc: Exception,
    *,
    domain: str = "readiness",
    blocking: bool = True,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": "failed",
        "remediation": remediation,
        "error": f"{exc.__class__.__name__}: {exc}",
        "domain": domain,
        "blocking": blocking,
    }


def _native_domain_payload(checks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    payload: dict[str, dict[str, Any]] = {}
    for domain in ("readiness", "capability"):
        domain_checks = [check for check in checks if check.get("domain") == domain]
        failed = [
            check["name"]
            for check in domain_checks
            if check["status"] != "ok" and check.get("blocking", True)
        ]
        external = [
            check["name"]
            for check in domain_checks
            if check["status"] != "ok" and not check.get("blocking", True)
        ]
        payload[domain] = {
            "status": "failed" if failed else "ok",
            "failed_checks": failed,
            "external_blockers": external,
        }
    return payload


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
    """Split a SQL script on top-level semicolons.

    Must track `--` line comments, not just single-quoted strings: a
    semicolon used as ordinary prose punctuation inside a `--` comment
    (e.g. "-- never CREATE OR REPLACE);") is not a statement boundary, but
    a naive quote-only scanner treats it as one, producing a comment-only
    fragment that Snowflake rejects as "Empty SQL statement" (see PR #133's
    render_graph_tables header, which broke sync-graph this way).
    """
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False
    in_line_comment = False
    index = 0
    length = len(sql)

    while index < length:
        char = sql[index]

        if in_line_comment:
            current.append(char)
            if char == "\n":
                in_line_comment = False
            index += 1
            continue

        if not in_single_quote and char == "-" and index + 1 < length and sql[index + 1] == "-":
            current.append(char)
            current.append(sql[index + 1])
            in_line_comment = True
            index += 2
            continue

        current.append(char)
        if char == "'":
            if in_single_quote and index + 1 < length and sql[index + 1] == "'":
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


def render_activate_generation(context: dict[str, Any], generation_id: str) -> str:
    """Atomically flip the single active-generation pointer (RSYNC-02).

    BEGIN/COMMIT wraps the pointer MERGE and both GRAPH_GENERATION status
    UPDATEs so a crash mid-flip can never leave the pointer referencing a
    generation whose status wasn't also updated to 'activated'.
    """
    literal = _sql_literal(generation_id)
    return f"""-- Activate generation {generation_id} as the single guarded pointer target.
BEGIN;

MERGE INTO {_fq(context, "GRAPH_ACTIVE_POINTER")} AS T
USING (SELECT 'active' AS POINTER_ID, {literal} AS GENERATION_ID) AS S
ON T.POINTER_ID = S.POINTER_ID
WHEN MATCHED THEN UPDATE SET ACTIVE_GENERATION_ID = S.GENERATION_ID, ACTIVATED_AT = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT (POINTER_ID, ACTIVE_GENERATION_ID, ACTIVATED_AT)
VALUES (S.POINTER_ID, S.GENERATION_ID, CURRENT_TIMESTAMP());

UPDATE {_fq(context, "GRAPH_GENERATION")}
SET STATUS = 'retired', RETIRED_AT = CURRENT_TIMESTAMP()
WHERE STATUS = 'activated' AND GENERATION_ID != {literal};

UPDATE {_fq(context, "GRAPH_GENERATION")}
SET STATUS = 'activated', ACTIVATED_AT = CURRENT_TIMESTAMP()
WHERE GENERATION_ID = {literal};

COMMIT;
"""


def render_cleanup_candidates(
    context: dict[str, Any],
    *,
    min_generations: int = DEFAULT_RETENTION_MIN_GENERATIONS,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> str:
    """Retired generations eligible for deletion (RSYNC-05): retains at least
    the newest `min_generations` retired generations (which always includes
    the immediate predecessor of the current active one, since it retires
    most recently) and every generation created within `retention_days`.
    Never considers 'activated'/'building'/'verified'/'failed' rows -- only
    'retired' generations are ever cleanup candidates."""
    return f"""-- verify_graph:cleanup_candidates
WITH ranked AS (
  SELECT
    GENERATION_ID,
    RETIRED_AT,
    CREATED_AT,
    ROW_NUMBER() OVER (ORDER BY RETIRED_AT DESC NULLS LAST) AS RECENCY_RANK
  FROM {_fq(context, "GRAPH_GENERATION")}
  WHERE STATUS = 'retired'
)
SELECT GENERATION_ID
FROM ranked
WHERE RECENCY_RANK > {int(min_generations)}
  AND CREATED_AT < DATEADD('day', -{int(retention_days)}, CURRENT_TIMESTAMP())
"""


def _activation_context(target_database: str, target_schema: str) -> dict[str, Any]:
    return {"target_database": _ident(target_database), "target_schema": _ident(target_schema)}


def _generation_status(cursor: Any, context: dict[str, Any], generation_id: str) -> str | None:
    rows = _fetch_rows(
        cursor,
        f"SELECT STATUS FROM {_fq(context, 'GRAPH_GENERATION')} "
        f"WHERE GENERATION_ID = {_sql_literal(generation_id)}",
        ("STATUS",),
    )
    return rows[0]["STATUS"] if rows else None


def _active_generation_id(cursor: Any, context: dict[str, Any]) -> str | None:
    rows = _fetch_rows(
        cursor,
        f"SELECT ACTIVE_GENERATION_ID FROM {_fq(context, 'GRAPH_ACTIVE_POINTER')} WHERE POINTER_ID = 'active'",
        ("ACTIVE_GENERATION_ID",),
    )
    return rows[0]["ACTIVE_GENERATION_ID"] if rows else None


def _flip_active_pointer(
    connection: Any,
    *,
    target_database: str,
    target_schema: str,
    generation_id: str,
    required_statuses: tuple[str, ...],
    operation_name: str,
) -> SnowflakeGraphActivationResult:
    context = _activation_context(target_database, target_schema)
    cursor = connection.cursor()
    try:
        # Guarded strictly BEFORE any pointer-mutating SQL runs: a rejected
        # activation/rollback therefore leaves the previous active pointer
        # completely untouched (RSYNC-02).
        status = _generation_status(cursor, context, generation_id)
        if status is None:
            raise SnowflakeGraphActivationError(
                f"no generation {generation_id!r} found; refusing to {operation_name}"
            )
        if status not in required_statuses:
            raise SnowflakeGraphActivationError(
                f"generation {generation_id!r} has status {status!r}, not one of "
                f"{required_statuses!r}; refusing to {operation_name}"
            )
        previous_generation_id = _active_generation_id(cursor, context)
        _execute_sql_script(cursor, render_activate_generation(context, generation_id))
    finally:
        cursor.close()
    return SnowflakeGraphActivationResult(
        generation_id=generation_id, previous_generation_id=previous_generation_id
    )


def activate_graph_generation(
    connection: Any,
    *,
    target_database: str,
    target_schema: str = DEFAULT_TARGET_SCHEMA,
    generation_id: str,
) -> SnowflakeGraphActivationResult:
    """Activate a verified generation. Refuses (no SQL executed) unless the
    generation's status is exactly 'verified' -- activation must never
    promote a generation that hasn't passed fan-in + exact-parity
    verification."""
    return _flip_active_pointer(
        connection,
        target_database=target_database,
        target_schema=target_schema,
        generation_id=generation_id,
        required_statuses=("verified",),
        operation_name="activate",
    )


def rollback_graph_generation(
    connection: Any,
    *,
    target_database: str,
    target_schema: str = DEFAULT_TARGET_SCHEMA,
    generation_id: str,
) -> SnowflakeGraphActivationResult:
    """Roll back to a retained, previously verified+activated generation.
    Refuses (no SQL executed) unless the target's status is 'activated' or
    'retired' -- rollback can only select a generation that was itself
    legitimately verified and went live at some point, never a 'building'/
    'failed' one."""
    return _flip_active_pointer(
        connection,
        target_database=target_database,
        target_schema=target_schema,
        generation_id=generation_id,
        required_statuses=RETAINABLE_GENERATION_STATUSES,
        operation_name="roll back",
    )


def cleanup_retired_generations(
    connection: Any,
    *,
    target_database: str,
    target_schema: str = DEFAULT_TARGET_SCHEMA,
    min_generations: int = DEFAULT_RETENTION_MIN_GENERATIONS,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> list[str]:
    """Delete retired generations outside the retention window (RSYNC-05).

    Retains the newest `min_generations` retired generations (which always
    includes the immediate predecessor of the current active generation)
    plus every generation created within `retention_days`, regardless of
    count. Never touches 'building'/'verified'/'activated'/'failed' rows.
    """
    context = _activation_context(target_database, target_schema)
    cursor = connection.cursor()
    try:
        candidate_rows = _fetch_rows(
            cursor,
            render_cleanup_candidates(
                context, min_generations=min_generations, retention_days=retention_days
            ),
            ("GENERATION_ID",),
        )
        candidate_ids = [row["GENERATION_ID"] for row in candidate_rows if row.get("GENERATION_ID")]
        if candidate_ids:
            id_list = ", ".join(_sql_literal(gid) for gid in candidate_ids)
            cursor.execute(f"DELETE FROM {_fq(context, 'MDM_GRAPH_NODES')} WHERE GENERATION_ID IN ({id_list})")
            cursor.execute(f"DELETE FROM {_fq(context, 'MDM_GRAPH_EDGES')} WHERE GENERATION_ID IN ({id_list})")
            cursor.execute(f"DELETE FROM {_fq(context, 'GRAPH_GENERATION')} WHERE GENERATION_ID IN ({id_list})")
    finally:
        cursor.close()
    return candidate_ids


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
        generation_id=config.generation_id,
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


def _active_generation_filter(context: dict[str, Any]) -> str:
    """SQL expression resolving to the single currently-active generation_id.

    Only needs target_database/target_schema, so it works against any context
    dict -- including the minimal ones existing tests build by hand -- not
    just ones produced by _graph_context().
    """
    return f"""(SELECT ACTIVE_GENERATION_ID FROM {_fq(context, "GRAPH_ACTIVE_POINTER")} WHERE POINTER_ID = 'active')"""


def _generation_scope_filter(context: dict[str, Any], generation_id: str | None) -> str:
    """SQL expression scoping a query to one generation.

    None (default) resolves to the active generation (preserves pre-07-05
    verify_graph behavior); an explicit generation_id verifies a candidate
    generation that has not been activated yet (07-05 Task 2's pre-activation
    verification gate).
    """
    if generation_id:
        return _sql_literal(generation_id)
    return _active_generation_filter(context)


def render_graph_tables(context: dict[str, Any]) -> str:
    active_filter = _active_generation_filter(context)
    return f"""-- Build graph-ready node and edge tables for Snowflake-hosted Neo4j Graph Analytics.
-- Neo4j is not external in this flow. Source data comes from Snowflake MDM mirror tables.
--
-- 07-05 (RSYNC-01/RSYNC-02/RSYNC-05): publication is additive, not in-place
-- replace. MDM_GRAPH_NODES/MDM_GRAPH_EDGES accumulate one immutable,
-- GENERATION_ID-tagged copy of the graph per sync (never CREATE OR REPLACE);
-- GRAPH_GENERATION is the platform-owned discovery/lifecycle registry;
-- GRAPH_ACTIVE_POINTER is the single guarded pointer every stable
-- GRAPH_APP_*/GRAPH_NODE_*/GRAPH_EDGE_* view joins against, so node and edge
-- rows can never resolve to two different generations. Activation/rollback
-- (see activate_graph_generation/rollback_graph_generation) only ever flips
-- this one pointer row -- it never touches MDM_GRAPH_NODES/MDM_GRAPH_EDGES.

CREATE SCHEMA IF NOT EXISTS {context["target_database"]}.{context["target_schema"]};

CREATE TABLE IF NOT EXISTS {_fq(context, "GRAPH_GENERATION")} (
  GENERATION_ID STRING NOT NULL,
  STATUS STRING NOT NULL DEFAULT 'building',
  RULE_VERSION STRING,
  SCHEMA_VERSION STRING,
  NODE_COUNT NUMBER,
  EDGE_COUNT NUMBER,
  CREATED_AT TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
  VERIFIED_AT TIMESTAMP_TZ,
  ACTIVATED_AT TIMESTAMP_TZ,
  RETIRED_AT TIMESTAMP_TZ,
  FAILURE_REASONS VARIANT
);

CREATE TABLE IF NOT EXISTS {_fq(context, "GRAPH_ACTIVE_POINTER")} (
  POINTER_ID STRING NOT NULL,
  ACTIVE_GENERATION_ID STRING,
  ACTIVATED_AT TIMESTAMP_TZ
);

MERGE INTO {_fq(context, "GRAPH_GENERATION")} AS T
USING (SELECT {context["generation_id_literal"]} AS GENERATION_ID) AS S
ON T.GENERATION_ID = S.GENERATION_ID
WHEN NOT MATCHED THEN INSERT (GENERATION_ID, STATUS, RULE_VERSION, SCHEMA_VERSION)
VALUES (S.GENERATION_ID, 'building', {context["rule_version_literal"]}, {context["schema_version_literal"]});

CREATE TABLE IF NOT EXISTS {_fq(context, "MDM_GRAPH_NODES")} (
  NODEID STRING,
  LABEL STRING,
  ENTITY_TYPE STRING,
  SOURCE_SYSTEM STRING,
  SOURCE_UPDATED_AT TIMESTAMP_TZ,
  CREATED_AT TIMESTAMP_TZ,
  UPDATED_AT TIMESTAMP_TZ,
  PROPERTIES VARIANT,
  GENERATION_ID STRING
);

-- Scoped to this generation only -- other generations' rows are never
-- touched, so this DELETE+INSERT is a safe retry of the SAME generation_id,
-- not a blanket rebuild (07-04's content-addressed partitions mean a given
-- generation's underlying source data is fixed for the life of the build).
DELETE FROM {_fq(context, "MDM_GRAPH_NODES")} WHERE GENERATION_ID = {context["generation_id_literal"]};

INSERT INTO {_fq(context, "MDM_GRAPH_NODES")}
  (NODEID, LABEL, ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_UPDATED_AT, CREATED_AT, UPDATED_AT, PROPERTIES, GENERATION_ID)
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
  ) AS PROPERTIES,
  {context["generation_id_literal"]} AS GENERATION_ID
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

-- Bounded (5-hop) canonical-entity resolution for merged entities (RLINE-01):
-- MDM's merge_entities() tombstones the discarded entity and records
-- {{"merged_from": discard}} on the KEPT entity's mdm_change_log row, but never
-- rewrites mdm_relationship_instance.source_entity_id/target_entity_id -- so
-- edges still point at the discarded id. This view walks that lineage
-- forward so staged edges can carry both the ORIGINAL endpoint (as MDM
-- stored it) and the CANONICAL endpoint (after merge chains resolve).
CREATE OR REPLACE VIEW {_fq(context, "GRAPH_ENTITY_MERGE_LINEAGE")} AS
SELECT
  CHANGED_FIELDS:merged_from::STRING AS DISCARDED_ENTITY_ID,
  ENTITY_ID::STRING AS KEPT_ENTITY_ID
FROM {_mdm_fq(context, "MDM_CHANGE_LOG")}
WHERE CHANGED_FIELDS:merged_from IS NOT NULL;

CREATE TABLE IF NOT EXISTS {_fq(context, "MDM_GRAPH_EDGES")} (
  EDGEID STRING,
  RELATIONSHIP_TYPE STRING,
  SOURCENODEID STRING,
  TARGETNODEID STRING,
  SOURCE_ENTITY_TYPE STRING,
  TARGET_ENTITY_TYPE STRING,
  SOURCE_SYSTEM STRING,
  SOURCE_ACCESSION STRING,
  EFFECTIVE_FROM TIMESTAMP_TZ,
  EFFECTIVE_TO TIMESTAMP_TZ,
  RELATIONSHIP_ID STRING,
  VALID_FROM_DATE DATE,
  VALID_TO_DATE DATE,
  DATE_PROVENANCE STRING,
  RELATIONSHIP_KIND STRING,
  SOURCENODEID_ORIGINAL STRING,
  TARGETNODEID_ORIGINAL STRING,
  MERGE_STRATEGY STRING,
  GRAPH_SYNC_STATUS STRING,
  GRAPH_SYNCED_AT TIMESTAMP_TZ,
  CREATED_AT TIMESTAMP_TZ,
  UPDATED_AT TIMESTAMP_TZ,
  PROPERTIES VARIANT,
  GENERATION_ID STRING
);

DELETE FROM {_fq(context, "MDM_GRAPH_EDGES")} WHERE GENERATION_ID = {context["generation_id_literal"]};

INSERT INTO {_fq(context, "MDM_GRAPH_EDGES")}
  (EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE,
   SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO,
   RELATIONSHIP_ID, VALID_FROM_DATE, VALID_TO_DATE, DATE_PROVENANCE, RELATIONSHIP_KIND,
   SOURCENODEID_ORIGINAL, TARGETNODEID_ORIGINAL,
   MERGE_STRATEGY, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES, GENERATION_ID)
SELECT
  RI.INSTANCE_ID::STRING AS EDGEID,
  RT.REL_TYPE_NAME::STRING AS RELATIONSHIP_TYPE,
  COALESCE(SRC_ML2.KEPT_ENTITY_ID, SRC_ML1.KEPT_ENTITY_ID, RI.SOURCE_ENTITY_ID)::STRING AS SOURCENODEID,
  COALESCE(TGT_ML2.KEPT_ENTITY_ID, TGT_ML1.KEPT_ENTITY_ID, RI.TARGET_ENTITY_ID)::STRING AS TARGETNODEID,
  RT.SOURCE_NODE_TYPE::STRING AS SOURCE_ENTITY_TYPE,
  RT.TARGET_NODE_TYPE::STRING AS TARGET_ENTITY_TYPE,
  RI.SOURCE_SYSTEM::STRING AS SOURCE_SYSTEM,
  RI.SOURCE_ACCESSION::STRING AS SOURCE_ACCESSION,
  RI.EFFECTIVE_FROM AS EFFECTIVE_FROM,
  RI.EFFECTIVE_TO AS EFFECTIVE_TO,
  RI.RELATIONSHIP_ID::STRING AS RELATIONSHIP_ID,
  RI.VALID_FROM_DATE::DATE AS VALID_FROM_DATE,
  RI.VALID_TO_DATE::DATE AS VALID_TO_DATE,
  RI.DATE_PROVENANCE::STRING AS DATE_PROVENANCE,
  RI.RELATIONSHIP_KIND::STRING AS RELATIONSHIP_KIND,
  RI.SOURCE_ENTITY_ID::STRING AS SOURCENODEID_ORIGINAL,
  RI.TARGET_ENTITY_ID::STRING AS TARGETNODEID_ORIGINAL,
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
    'relationship_id', RI.RELATIONSHIP_ID,
    'source_system', RI.SOURCE_SYSTEM,
    'source_accession', RI.SOURCE_ACCESSION,
    'effective_from', RI.EFFECTIVE_FROM,
    'effective_to', RI.EFFECTIVE_TO,
    'valid_from_date', RI.VALID_FROM_DATE,
    'valid_to_date', RI.VALID_TO_DATE,
    'date_provenance', RI.DATE_PROVENANCE,
    'relationship_kind', RI.RELATIONSHIP_KIND,
    'source_entity_id_original', RI.SOURCE_ENTITY_ID,
    'target_entity_id_original', RI.TARGET_ENTITY_ID,
    'properties', TRY_PARSE_JSON(RI.PROPERTIES),
    'merge_strategy', RT.MERGE_STRATEGY,
    'source_node_type', RT.SOURCE_NODE_TYPE,
    'target_node_type', RT.TARGET_NODE_TYPE,
    'graph_sync_status', CASE
      WHEN RI.GRAPH_SYNCED_AT IS NULL THEN 'PENDING'
      ELSE 'SYNCED'
    END
  ) AS PROPERTIES,
  {context["generation_id_literal"]} AS GENERATION_ID
FROM {_mdm_fq(context, "MDM_RELATIONSHIP_INSTANCE")} RI
JOIN {_mdm_fq(context, "MDM_RELATIONSHIP_TYPE")} RT
  ON RT.REL_TYPE_ID = RI.REL_TYPE_ID
LEFT JOIN {_fq(context, "GRAPH_ENTITY_MERGE_LINEAGE")} SRC_ML1
  ON SRC_ML1.DISCARDED_ENTITY_ID = RI.SOURCE_ENTITY_ID
LEFT JOIN {_fq(context, "GRAPH_ENTITY_MERGE_LINEAGE")} SRC_ML2
  ON SRC_ML2.DISCARDED_ENTITY_ID = SRC_ML1.KEPT_ENTITY_ID
LEFT JOIN {_fq(context, "GRAPH_ENTITY_MERGE_LINEAGE")} TGT_ML1
  ON TGT_ML1.DISCARDED_ENTITY_ID = RI.TARGET_ENTITY_ID
LEFT JOIN {_fq(context, "GRAPH_ENTITY_MERGE_LINEAGE")} TGT_ML2
  ON TGT_ML2.DISCARDED_ENTITY_ID = TGT_ML1.KEPT_ENTITY_ID
WHERE RI.IS_ACTIVE = TRUE
  AND RT.IS_ACTIVE = TRUE{context["relationship_type_filter"]}
{context["relationship_per_type_limit"]}{context["relationship_limit"]};

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_APP_NODES")} AS
SELECT NODEID
FROM {_fq(context, "MDM_GRAPH_NODES")}
WHERE GENERATION_ID = {active_filter};

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_APP_EDGES")} AS
SELECT SOURCENODEID, TARGETNODEID
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE GENERATION_ID = {active_filter};

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_NODES")} AS
SELECT NODEID, LABEL, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_NODES")}
WHERE GENERATION_ID = {active_filter};

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGES")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE GENERATION_ID = {active_filter};

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_NODE_COMPANY")} AS
SELECT NODEID, LABEL, ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_UPDATED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_NODES")}
WHERE ENTITY_TYPE = 'company' AND GENERATION_ID = {active_filter};

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_NODE_PERSON")} AS
SELECT NODEID, LABEL, ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_UPDATED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_NODES")}
WHERE ENTITY_TYPE = 'person' AND GENERATION_ID = {active_filter};

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_NODE_SECURITY")} AS
SELECT NODEID, LABEL, ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_UPDATED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_NODES")}
WHERE ENTITY_TYPE = 'security' AND GENERATION_ID = {active_filter};

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_NODE_ADVISER")} AS
SELECT NODEID, LABEL, ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_UPDATED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_NODES")}
WHERE ENTITY_TYPE = 'adviser' AND GENERATION_ID = {active_filter};

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_NODE_FUND")} AS
SELECT NODEID, LABEL, ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_UPDATED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_NODES")}
WHERE ENTITY_TYPE = 'fund' AND GENERATION_ID = {active_filter};

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_NODE_AUDITFIRM")} AS
SELECT NODEID, LABEL, ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_UPDATED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_NODES")}
WHERE ENTITY_TYPE = 'audit_firm' AND GENERATION_ID = {active_filter};

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_IS_INSIDER")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, RELATIONSHIP_ID, VALID_FROM_DATE, VALID_TO_DATE, DATE_PROVENANCE, RELATIONSHIP_KIND, SOURCENODEID_ORIGINAL, TARGETNODEID_ORIGINAL, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'IS_INSIDER' AND GENERATION_ID = {active_filter};

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_HOLDS")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, RELATIONSHIP_ID, VALID_FROM_DATE, VALID_TO_DATE, DATE_PROVENANCE, RELATIONSHIP_KIND, SOURCENODEID_ORIGINAL, TARGETNODEID_ORIGINAL, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'HOLDS' AND GENERATION_ID = {active_filter};

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_COMPANY_HOLDS")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, RELATIONSHIP_ID, VALID_FROM_DATE, VALID_TO_DATE, DATE_PROVENANCE, RELATIONSHIP_KIND, SOURCENODEID_ORIGINAL, TARGETNODEID_ORIGINAL, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'COMPANY_HOLDS' AND GENERATION_ID = {active_filter};

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_ISSUED_BY")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, RELATIONSHIP_ID, VALID_FROM_DATE, VALID_TO_DATE, DATE_PROVENANCE, RELATIONSHIP_KIND, SOURCENODEID_ORIGINAL, TARGETNODEID_ORIGINAL, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'ISSUED_BY' AND GENERATION_ID = {active_filter};

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_IS_ENTITY_OF")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, RELATIONSHIP_ID, VALID_FROM_DATE, VALID_TO_DATE, DATE_PROVENANCE, RELATIONSHIP_KIND, SOURCENODEID_ORIGINAL, TARGETNODEID_ORIGINAL, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'IS_ENTITY_OF' AND GENERATION_ID = {active_filter};

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_HAS_PARENT_COMPANY")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, RELATIONSHIP_ID, VALID_FROM_DATE, VALID_TO_DATE, DATE_PROVENANCE, RELATIONSHIP_KIND, SOURCENODEID_ORIGINAL, TARGETNODEID_ORIGINAL, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'HAS_PARENT_COMPANY' AND GENERATION_ID = {active_filter};

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_MANAGES_FUND")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, RELATIONSHIP_ID, VALID_FROM_DATE, VALID_TO_DATE, DATE_PROVENANCE, RELATIONSHIP_KIND, SOURCENODEID_ORIGINAL, TARGETNODEID_ORIGINAL, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'MANAGES_FUND' AND GENERATION_ID = {active_filter};

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_IS_PERSON_OF")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, RELATIONSHIP_ID, VALID_FROM_DATE, VALID_TO_DATE, DATE_PROVENANCE, RELATIONSHIP_KIND, SOURCENODEID_ORIGINAL, TARGETNODEID_ORIGINAL, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'IS_PERSON_OF' AND GENERATION_ID = {active_filter};

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_EMPLOYED_BY")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, RELATIONSHIP_ID, VALID_FROM_DATE, VALID_TO_DATE, DATE_PROVENANCE, RELATIONSHIP_KIND, SOURCENODEID_ORIGINAL, TARGETNODEID_ORIGINAL, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'EMPLOYED_BY' AND GENERATION_ID = {active_filter};

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_AUDITED_BY")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, RELATIONSHIP_ID, VALID_FROM_DATE, VALID_TO_DATE, DATE_PROVENANCE, RELATIONSHIP_KIND, SOURCENODEID_ORIGINAL, TARGETNODEID_ORIGINAL, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'AUDITED_BY' AND GENERATION_ID = {active_filter};

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_INSTITUTIONAL_HOLDS")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, RELATIONSHIP_ID, VALID_FROM_DATE, VALID_TO_DATE, DATE_PROVENANCE, RELATIONSHIP_KIND, SOURCENODEID_ORIGINAL, TARGETNODEID_ORIGINAL, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'INSTITUTIONAL_HOLDS' AND GENERATION_ID = {active_filter};

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_NODE_COUNTS")} AS
SELECT LABEL, COUNT(*) AS NODE_COUNT
FROM {_fq(context, "MDM_GRAPH_NODES")}
WHERE GENERATION_ID = {active_filter}
GROUP BY LABEL;

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_COUNTS")} AS
SELECT RELATIONSHIP_TYPE, COUNT(*) AS EDGE_COUNT
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE GENERATION_ID = {active_filter}
GROUP BY RELATIONSHIP_TYPE;
"""


def render_validation(context: dict[str, Any]) -> str:
    active_filter = _active_generation_filter(context)
    return f"""-- Validation for Snowflake-hosted Neo4j Graph Analytics tables.
-- Scoped to the currently-active generation (07-05) -- MDM_GRAPH_NODES/EDGES
-- accumulate every generation ever synced, so an unscoped COUNT(*) here would
-- silently sum across generation history instead of reporting live graph size.

SELECT 'snowflake_graph_nodes' AS METRIC, COUNT(*) AS VALUE
FROM {_fq(context, "MDM_GRAPH_NODES")}
WHERE GENERATION_ID = {active_filter}
UNION ALL
SELECT 'snowflake_graph_edges' AS METRIC, COUNT(*) AS VALUE
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE GENERATION_ID = {active_filter}
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
  ON S.NODEID = E.SOURCENODEID AND S.GENERATION_ID = {active_filter}
LEFT JOIN {_fq(context, "MDM_GRAPH_NODES")} T
  ON T.NODEID = E.TARGETNODEID AND T.GENERATION_ID = {active_filter}
WHERE E.GENERATION_ID = {active_filter}
  AND (S.NODEID IS NULL OR T.NODEID IS NULL)
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
2. Activate the `{context["generation_id"] or "bootstrap"}` generation this script staged --
   `GRAPH_APP_*`/`GRAPH_NODE_*`/`GRAPH_EDGE_*` views resolve zero rows until a generation
   is active (see `activate_graph_generation` / `mdm graph-activate`).
3. `snow sql -c <connection> -f 01_validation.sql`
4. `snow sql -c <connection> -f 02_hosted_neo4j_e2e.sql`

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
    generation_id: str = "",
    rule_version: str = "v1",
    schema_version: str = "v1",
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
        "generation_id": generation_id,
        "generation_id_literal": _sql_literal(generation_id) if generation_id else "NULL",
        "rule_version_literal": _sql_literal(rule_version),
        "schema_version_literal": _sql_literal(schema_version),
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


def _named_node_parity_checks(node_parity: dict[str, Any]) -> list[dict[str, Any]]:
    """NODE-01..06 (D-01): one named parity check per expected node type.

    Reads only the already-computed node_parity["by_entity_type"] rows -- no new SQL.
    A type absent from the parity rows is a hard failure (present=False), closing the
    silent-omission gap where the FULL OUTER JOIN aggregate stays "ok" when a type
    contributes no row at all (e.g. a per-type GRAPH_NODE_* view that doesn't exist yet).
    """
    by_type = {row["entity_type"]: row for row in node_parity["by_entity_type"]}
    checks = []
    for entity_type in ALLOWED_ENTITY_TYPES:
        row = by_type.get(entity_type)
        present = row is not None
        mdm_active_count = row["mdm_active_count"] if present else 0
        snowflake_graph_node_count = row["snowflake_graph_node_count"] if present else 0
        at_parity = present and row["mdm_minus_graph"] == 0 and row["graph_minus_mdm"] == 0
        check = {
            "name": f"node_parity_{entity_type}",
            "entity_type": entity_type,
            "present": present,
            "mdm_active_count": mdm_active_count,
            "snowflake_graph_node_count": snowflake_graph_node_count,
            "status": "ok" if at_parity else "failed",
        }
        if not present:
            check["remediation"] = (
                f"No parity row for entity_type={entity_type!r}: confirm its "
                "GRAPH_NODE_* view exists (render_graph_tables()) and re-run "
                "mdm sync-graph."
            )
        checks.append(check)
    return checks


def _named_relationship_parity_checks(
    relationship_parity: dict[str, Any],
    relationship_coverage: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """EDGE-01..04 (D-01) / RCOV-01..02 (07-02): one named parity check per relationship type.

    Reads only the already-computed relationship_parity["by_relationship_type"] rows --
    no new SQL.

    ``relationship_coverage`` (rel_type_name -> status in
    {"populated","valid_zero","excluded"}), when supplied, replaces the old
    POPULATED_RELATIONSHIP_TYPES-only scoping with exhaustive evaluation over
    every type in the coverage manifest (edgar_warehouse.mdm.coverage):
    populated types must be at parity as before; valid_zero/excluded types
    must additionally have zero live MDM/graph rows -- a nonzero count for a
    type expected to be zero is now a hard failure (synthetic or unexpected
    edges), not silence.

    When omitted (the default), behavior is unchanged from before 07-02:
    only POPULATED_RELATIONSHIP_TYPES get a named check, and the other
    (not-yet-classified) types are skipped (T-05-05).
    """
    by_type = {
        row["relationship_type"]: row for row in relationship_parity["by_relationship_type"]
    }

    if relationship_coverage is None:
        scoped_types = {name: "populated" for name in POPULATED_RELATIONSHIP_TYPES}
    else:
        scoped_types = relationship_coverage

    checks = []
    for relationship_type, status in scoped_types.items():
        row = by_type.get(relationship_type)
        present = row is not None
        mdm_active_count = row["mdm_active_count"] if present else 0
        snowflake_graph_edge_count = row["snowflake_graph_edge_count"] if present else 0
        at_parity = present and row["mdm_minus_graph"] == 0 and row["graph_minus_mdm"] == 0
        is_zero_expected = status in ("valid_zero", "excluded")
        if is_zero_expected:
            ok = mdm_active_count == 0 and snowflake_graph_edge_count == 0
        else:
            ok = at_parity
        check = {
            "name": f"relationship_parity_{relationship_type.lower()}",
            "relationship_type": relationship_type,
            "coverage_status": status,
            "present": present,
            "mdm_active_count": mdm_active_count,
            "snowflake_graph_edge_count": snowflake_graph_edge_count,
            "status": "ok" if ok else "failed",
        }
        if not ok and is_zero_expected:
            check["remediation"] = (
                f"relationship_type={relationship_type!r} is classified {status!r} "
                f"(expected zero rows) but has mdm_active_count={mdm_active_count}, "
                f"snowflake_graph_edge_count={snowflake_graph_edge_count}: re-review its "
                "coverage exclusion/valid-zero record -- this may be a stale exclusion "
                "or synthetic/unexpected data."
            )
        elif not present:
            check["remediation"] = (
                f"No parity row for relationship_type={relationship_type!r}: confirm "
                "mdm load-relationships has populated this type and re-run mdm sync-graph."
            )
        checks.append(check)
    return checks


def _format_sample_rows(rows: list[dict[str, Any]], columns: tuple[str, ...]) -> list[dict[str, Any]]:
    return [
        {column.lower(): row[column] for column in columns}
        for row in rows
    ]


def _as_int(value: Any) -> int:
    return int(value or 0)


def _render_verify_node_counts(context: dict[str, Any], generation_id: str | None = None) -> str:
    scope = _generation_scope_filter(context, generation_id)
    return f"""-- verify_graph:node_counts
WITH expected AS (
  SELECT ETD.ENTITY_TYPE, COUNT(E.ENTITY_ID) AS MDM_ACTIVE_COUNT
  FROM {_mdm_fq(context, "MDM_ENTITY_TYPE_DEFINITION")} ETD
  LEFT JOIN {_mdm_fq(context, "MDM_ENTITY")} E
    ON E.ENTITY_TYPE = ETD.ENTITY_TYPE
   AND E.IS_QUARANTINED = FALSE
  WHERE ETD.IS_ACTIVE = TRUE
  GROUP BY ETD.ENTITY_TYPE
),
actual AS (
  SELECT ENTITY_TYPE, COUNT(*) AS SNOWFLAKE_GRAPH_NODE_COUNT
  FROM {_fq(context, "MDM_GRAPH_NODES")}
  WHERE GENERATION_ID = {scope}
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


def _render_verify_relationship_counts(context: dict[str, Any], generation_id: str | None = None) -> str:
    scope = _generation_scope_filter(context, generation_id)
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
  WHERE GENERATION_ID = {scope}
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


def _render_exact_node_parity(context: dict[str, Any], generation_id: str | None = None) -> str:
    """07-05 Task 2: identity + property exact parity (not count-only).

    HASH_AGG is order-independent, so a matching row COUNT with even one
    different NODEID/LABEL/ENTITY_TYPE flips the hash and fails this check --
    unlike the count-only checks above, which cannot detect that case.
    """
    scope = _generation_scope_filter(context, generation_id)
    return f"""-- verify_graph:exact_node_parity
WITH mdm_side AS (
  SELECT
    HASH_AGG(E.ENTITY_ID::STRING, E.ENTITY_TYPE::STRING, ETD.NEO4J_LABEL::STRING) AS CONTENT_HASH,
    COUNT(*) AS ROW_COUNT
  FROM {_mdm_fq(context, "MDM_ENTITY")} E
  JOIN {_mdm_fq(context, "MDM_ENTITY_TYPE_DEFINITION")} ETD
    ON ETD.ENTITY_TYPE = E.ENTITY_TYPE
   AND ETD.IS_ACTIVE = TRUE
  WHERE E.IS_QUARANTINED = FALSE
),
graph_side AS (
  SELECT
    HASH_AGG(NODEID::STRING, ENTITY_TYPE::STRING, LABEL::STRING) AS CONTENT_HASH,
    COUNT(*) AS ROW_COUNT
  FROM {_fq(context, "MDM_GRAPH_NODES")}
  WHERE GENERATION_ID = {scope}
)
SELECT
  mdm_side.CONTENT_HASH AS MDM_CONTENT_HASH,
  graph_side.CONTENT_HASH AS GRAPH_CONTENT_HASH,
  mdm_side.ROW_COUNT AS MDM_ROW_COUNT,
  graph_side.ROW_COUNT AS GRAPH_ROW_COUNT,
  IFF(mdm_side.CONTENT_HASH = graph_side.CONTENT_HASH, TRUE, FALSE) AS IDENTITY_PROPERTY_MATCH
FROM mdm_side, graph_side
"""


def _render_exact_relationship_parity(context: dict[str, Any], generation_id: str | None = None) -> str:
    """07-05 Task 2: identity + property + typed-temporal exact parity for
    edges. Compares against the ORIGINAL (pre-merge-remap) endpoints -- the
    canonical remap is an intentional transformation on top of raw MDM data,
    not something MDM itself has, so the faithful-mirror check must use the
    same endpoints MDM stores."""
    scope = _generation_scope_filter(context, generation_id)
    return f"""-- verify_graph:exact_relationship_parity
WITH mdm_side AS (
  SELECT
    HASH_AGG(
      RI.INSTANCE_ID::STRING, RI.RELATIONSHIP_ID::STRING,
      RI.SOURCE_ENTITY_ID::STRING, RI.TARGET_ENTITY_ID::STRING,
      RT.REL_TYPE_NAME::STRING,
      RI.VALID_FROM_DATE::STRING, RI.VALID_TO_DATE::STRING, RI.DATE_PROVENANCE::STRING
    ) AS CONTENT_HASH,
    COUNT(*) AS ROW_COUNT
  FROM {_mdm_fq(context, "MDM_RELATIONSHIP_INSTANCE")} RI
  JOIN {_mdm_fq(context, "MDM_RELATIONSHIP_TYPE")} RT
    ON RT.REL_TYPE_ID = RI.REL_TYPE_ID
   AND RT.IS_ACTIVE = TRUE
  WHERE RI.IS_ACTIVE = TRUE
),
graph_side AS (
  SELECT
    HASH_AGG(
      EDGEID::STRING, RELATIONSHIP_ID::STRING,
      SOURCENODEID_ORIGINAL::STRING, TARGETNODEID_ORIGINAL::STRING,
      RELATIONSHIP_TYPE::STRING,
      VALID_FROM_DATE::STRING, VALID_TO_DATE::STRING, DATE_PROVENANCE::STRING
    ) AS CONTENT_HASH,
    COUNT(*) AS ROW_COUNT
  FROM {_fq(context, "MDM_GRAPH_EDGES")}
  WHERE GENERATION_ID = {scope}
)
SELECT
  mdm_side.CONTENT_HASH AS MDM_CONTENT_HASH,
  graph_side.CONTENT_HASH AS GRAPH_CONTENT_HASH,
  mdm_side.ROW_COUNT AS MDM_ROW_COUNT,
  graph_side.ROW_COUNT AS GRAPH_ROW_COUNT,
  IFF(mdm_side.CONTENT_HASH = graph_side.CONTENT_HASH, TRUE, FALSE) AS IDENTITY_PROPERTY_MATCH
FROM mdm_side, graph_side
"""


def _render_canonical_remap_leaks(context: dict[str, Any], generation_id: str | None = None) -> str:
    """07-05 Task 2: a discarded (merged-away) entity_id must never appear as
    a staged edge's canonical endpoint -- proves the merge-lineage remap in
    render_graph_tables actually took effect, not just that the lineage view
    exists syntactically. Non-empty result = remap correctness failure."""
    scope = _generation_scope_filter(context, generation_id)
    return f"""-- verify_graph:canonical_remap_leaks
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID
FROM {_fq(context, "MDM_GRAPH_EDGES")} E
WHERE E.GENERATION_ID = {scope}
  AND (
    E.SOURCENODEID IN (SELECT DISCARDED_ENTITY_ID FROM {_fq(context, "GRAPH_ENTITY_MERGE_LINEAGE")})
    OR E.TARGETNODEID IN (SELECT DISCARDED_ENTITY_ID FROM {_fq(context, "GRAPH_ENTITY_MERGE_LINEAGE")})
  )
LIMIT {context.get("sample_limit", 20)}
"""


def _render_missing_nodes(context: dict[str, Any], generation_id: str | None = None) -> str:
    scope = _generation_scope_filter(context, generation_id)
    return f"""-- verify_graph:missing_nodes
SELECT E.ENTITY_TYPE, E.ENTITY_ID::STRING AS NODEID
FROM {_mdm_fq(context, "MDM_ENTITY")} E
JOIN {_mdm_fq(context, "MDM_ENTITY_TYPE_DEFINITION")} ETD
  ON ETD.ENTITY_TYPE = E.ENTITY_TYPE
 AND ETD.IS_ACTIVE = TRUE
LEFT JOIN {_fq(context, "MDM_GRAPH_NODES")} G
  ON G.NODEID = E.ENTITY_ID::STRING AND G.GENERATION_ID = {scope}
WHERE E.IS_QUARANTINED = FALSE
  AND G.NODEID IS NULL
ORDER BY E.ENTITY_TYPE, E.ENTITY_ID
LIMIT {context["sample_limit"]}
"""


def _render_extra_nodes(context: dict[str, Any], generation_id: str | None = None) -> str:
    scope = _generation_scope_filter(context, generation_id)
    return f"""-- verify_graph:extra_nodes
SELECT G.ENTITY_TYPE, G.NODEID
FROM {_fq(context, "MDM_GRAPH_NODES")} G
LEFT JOIN {_mdm_fq(context, "MDM_ENTITY")} E
  ON E.ENTITY_ID::STRING = G.NODEID
LEFT JOIN {_mdm_fq(context, "MDM_ENTITY_TYPE_DEFINITION")} ETD
  ON ETD.ENTITY_TYPE = E.ENTITY_TYPE
 AND ETD.IS_ACTIVE = TRUE
WHERE G.GENERATION_ID = {scope}
  AND (E.ENTITY_ID IS NULL
   OR E.IS_QUARANTINED = TRUE
   OR ETD.ENTITY_TYPE IS NULL)
ORDER BY G.ENTITY_TYPE, G.NODEID
LIMIT {context["sample_limit"]}
"""


def _render_missing_edges(context: dict[str, Any], generation_id: str | None = None) -> str:
    scope = _generation_scope_filter(context, generation_id)
    return f"""-- verify_graph:missing_edges
SELECT RT.REL_TYPE_NAME AS RELATIONSHIP_TYPE, RI.INSTANCE_ID::STRING AS EDGEID
FROM {_mdm_fq(context, "MDM_RELATIONSHIP_INSTANCE")} RI
JOIN {_mdm_fq(context, "MDM_RELATIONSHIP_TYPE")} RT
  ON RT.REL_TYPE_ID = RI.REL_TYPE_ID
 AND RT.IS_ACTIVE = TRUE
LEFT JOIN {_fq(context, "MDM_GRAPH_EDGES")} G
  ON G.EDGEID = RI.INSTANCE_ID::STRING AND G.GENERATION_ID = {scope}
WHERE RI.IS_ACTIVE = TRUE
  AND G.EDGEID IS NULL
ORDER BY RT.REL_TYPE_NAME, RI.INSTANCE_ID
LIMIT {context["sample_limit"]}
"""


def _render_extra_edges(context: dict[str, Any], generation_id: str | None = None) -> str:
    scope = _generation_scope_filter(context, generation_id)
    return f"""-- verify_graph:extra_edges
SELECT G.RELATIONSHIP_TYPE, G.EDGEID
FROM {_fq(context, "MDM_GRAPH_EDGES")} G
LEFT JOIN {_mdm_fq(context, "MDM_RELATIONSHIP_INSTANCE")} RI
  ON RI.INSTANCE_ID::STRING = G.EDGEID
LEFT JOIN {_mdm_fq(context, "MDM_RELATIONSHIP_TYPE")} RT
  ON RT.REL_TYPE_ID = RI.REL_TYPE_ID
 AND RT.IS_ACTIVE = TRUE
WHERE G.GENERATION_ID = {scope}
  AND (RI.INSTANCE_ID IS NULL
   OR RI.IS_ACTIVE = FALSE
   OR RT.REL_TYPE_ID IS NULL)
ORDER BY G.RELATIONSHIP_TYPE, G.EDGEID
LIMIT {context["sample_limit"]}
"""


def _render_missing_edge_endpoints(context: dict[str, Any], generation_id: str | None = None) -> str:
    scope = _generation_scope_filter(context, generation_id)
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
  ON S.NODEID = E.SOURCENODEID AND S.GENERATION_ID = {scope}
LEFT JOIN {_fq(context, "MDM_GRAPH_NODES")} T
  ON T.NODEID = E.TARGETNODEID AND T.GENERATION_ID = {scope}
WHERE E.GENERATION_ID = {scope}
  AND (S.NODEID IS NULL OR T.NODEID IS NULL)
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
FROM {_fq(context, "GRAPH_APP_NODES")}
WHERE NODEID IS NOT NULL
ORDER BY NODEID
LIMIT 1
"""


def _render_native_app_wcc(
    context: dict[str, Any],
    app_name: str,
    compute_pool: str,
) -> str:
    """WCC smoke via the app's current job API.

    The compute pool selector is the first *argument* (not config), the
    config is sectioned ({project, compute, write}) with camelCase keys and
    fully-qualified table names, and the projection must only see numeric/
    ID columns — hence the GRAPH_APP_NODES/GRAPH_APP_EDGES ID-only views
    (the app rejects VARCHAR property columns such as MDM_GRAPH_NODES.LABEL).
    consecutiveIds remaps the VARCHAR node ids for computation.
    """
    nodes = _fq(context, "GRAPH_APP_NODES")
    edges = _fq(context, "GRAPH_APP_EDGES")
    output = _fq(context, "MDM_GRAPH_VERIFY_WCC_SMOKE")
    return f"""-- verify_graph:native_app_wcc
CALL {app_name}.GRAPH.WCC(
  {_sql_literal(compute_pool)},
  {{
    'project': {{
      'nodeTables': [{_sql_literal(nodes)}],
      'relationshipTables': {{
        {_sql_literal(edges)}: {{
          'sourceTable': {_sql_literal(nodes)},
          'targetTable': {_sql_literal(nodes)},
          'orientation': 'NATURAL'
        }}
      }}
    }},
    'compute': {{ 'consecutiveIds': true }},
    'write': [{{
      'nodeLabel': 'GRAPH_APP_NODES',
      'outputTable': {_sql_literal(output)}
    }}]
  }}
)
"""


def _render_native_app_project(context: dict[str, Any]) -> str:
    nodes = _fq(context, "GRAPH_APP_NODES")
    edges = _fq(context, "GRAPH_APP_EDGES")
    return f"""'project': {{
      'nodeTables': [{_sql_literal(nodes)}],
      'relationshipTables': {{
        {_sql_literal(edges)}: {{
          'sourceTable': {_sql_literal(nodes)},
          'targetTable': {_sql_literal(nodes)},
          'orientation': 'NATURAL'
        }}
      }}
    }}"""


def _render_native_app_graph_info(
    context: dict[str, Any],
    app_name: str,
    compute_pool: str,
) -> str:
    return f"""-- verify_graph:native_app_graph_info
CALL {app_name}.GRAPH.GRAPH_INFO(
  {_sql_literal(compute_pool)},
  {{
    {_render_native_app_project(context)},
    'compute': {{}}
  }}
)
"""


def _render_native_app_bfs(
    context: dict[str, Any],
    app_name: str,
    compute_pool: str,
    sample_node_id: str,
) -> str:
    nodes = _fq(context, "GRAPH_APP_NODES")
    output = _fq(context, "MDM_GRAPH_VERIFY_BFS_SMOKE")
    return f"""-- verify_graph:native_app_bfs
CALL {app_name}.GRAPH.BFS(
  {_sql_literal(compute_pool)},
  {{
    {_render_native_app_project(context)},
    'compute': {{
      'sourceNodeTable': {_sql_literal(nodes)},
      'sourceNode': {_sql_literal(sample_node_id)},
      'targetNodesTable': {_sql_literal(nodes)},
      'targetNodes': [],
      'maxDepth': 2
    }},
    'write': [{{'outputTable': {_sql_literal(output)}}}]
  }}
)
"""


def _render_native_app_list_graphs(app_name: str) -> str:
    return f"""-- verify_graph:native_app_list_graphs
SELECT * FROM TABLE({app_name}.EXPERIMENTAL.LIST_GRAPHS())
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
