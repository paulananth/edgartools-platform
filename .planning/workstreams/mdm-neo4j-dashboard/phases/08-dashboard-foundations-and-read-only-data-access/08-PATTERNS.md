# Phase 08: Dashboard Foundations And Read-Only Data Access - Pattern Map

**Mapped:** 2026-05-17
**Files analyzed:** 7
**Analogs found:** 7 / 7

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `examples/mdm_graph_dashboard/streamlit_app.py` | component | request-response | `examples/dashboard/edgar_universe_dashboard.py` | exact |
| `examples/mdm_graph_dashboard/README.md` | config/docs | request-response | `examples/dashboard/README.md` + `pyproject.toml` | role-match |
| `edgar_warehouse/mdm/dashboard_readonly.py` | service | CRUD (read-only SELECT) | `edgar_warehouse/mdm/database.py` + `edgar_warehouse/mdm/cli.py` | role-match |
| `edgar_warehouse/mdm/graph_readonly.py` | service | request-response (read-only Cypher) | `edgar_warehouse/mdm/graph.py` + `edgar_warehouse/mdm/cli.py` | role-match |
| `tests/mdm/test_dashboard_readonly.py` | test | CRUD (read-only SELECT) | `tests/mdm/conftest.py` | exact |
| `tests/mdm/test_graph_readonly.py` | test | request-response (fake Neo4j read) | `tests/mdm/test_graph.py` | exact |
| `tests/architecture/test_dashboard_foundation_boundaries.py` | test | static analysis | `tests/architecture/test_boundaries.py` | exact |

## Pattern Assignments

### `examples/mdm_graph_dashboard/streamlit_app.py` (component, request-response)

**Analog:** `examples/dashboard/edgar_universe_dashboard.py`

**Imports pattern** (lines 13-25):
```python
from __future__ import annotations

import csv
import io
import os
import pathlib
import tomllib
from typing import Any

import pandas as pd
import plotly.express as px
import snowflake.connector
import streamlit as st
```

For Phase 8, keep only the imports needed for Streamlit and local helper calls. Do not import Snowflake, Plotly, dbt, Terraform, or graph sync code.

**Cache/resource pattern** (lines 455-526):
```python
@st.cache_resource
def get_conn() -> snowflake.connector.SnowflakeConnection:
    cfg = _read_config()
    if cfg is None:
        raise RuntimeError(
            "No Snowflake connection found. Create ~/.snowflake/config.toml with a "
            "[connections.<name>] block and set default_connection_name. See "
            "examples/dashboard/README.md for the expected stanza."
        )
    ...

@st.cache_data(ttl=3600, show_spinner=False)
def q(sql: str, params: tuple | None = None) -> pd.DataFrame:
    """Run SQL, auto-reconnecting once if the cached session token has expired."""
    ...

def q_optional(sql: str, params: tuple | None = None) -> pd.DataFrame | None:
    """Like ``q`` but returns None when the target object is missing/unauthorized."""
```

Copy the cache shape, but set `ttl=60` per UI-SPEC and cache calls to `dashboard_readonly.py` / `graph_readonly.py`, not raw SQL/Cypher inside Streamlit.

**Status summary pattern** (lines 529-536):
```python
def _cfg_summary() -> str:
    cfg = _read_config()
    if cfg is None:
        return "not configured"
    db = cfg.get("database", DEFAULT_DATABASE)
    schema = cfg.get("schema", DEFAULT_SCHEMA)
    wh = cfg.get("warehouse", "—")
    return f"{cfg['name']} · {db}.{schema} · warehouse={wh}"
```

For Phase 8, expose labels such as `MDM connected`, `MDM unavailable`, `Neo4j connected`, `Neo4j not configured`, or `Neo4j failed`. Never show DSN, URI, username, password, secret JSON, or hostnames.

**State handling pattern** (lines 603-625):
```python
def render_overview() -> None:
    st.header("📊 Overview")

    # Probe tables individually so missing/unauthorized ones show "—" without
    # hiding the rest of the section.
    try:
        counts = {name: _table_count(name) for name in (
            "COMPANY", "FILING_ACTIVITY", "OWNERSHIP_ACTIVITY", "PRIVATE_FUNDS", "TICKER_REFERENCE",
        )}
    except Exception as exc:
        st.error(f"Unable to query {qualified('COMPANY')}: {exc}")
        st.info("Check your ~/.snowflake/config.toml and the role's grants on EDGARTOOLS_GOLD.")
        return

    missing = [name for name, count in counts.items() if count is None]
    if missing:
        st.warning(
            "Missing or unauthorized tables — showing partial data: "
            + ", ".join(missing)
        )
```

Use the same `st.error` / `st.warning` / `st.info` control flow, but replace raw exception display with secret-safe fixed copy from UI-SPEC.

**App shell pattern** (lines 1331-1355):
```python
SECTIONS: dict[str, Any] = {
    "📊 Overview": render_overview,
    "🗺️ World & US Map": render_world_map,
    "🏭 Industry & Entity": render_industry,
    "📈 Filing Activity": render_filings,
    "💼 Ownership & Funds": render_ownership,
    "🔎 Company Lookup": render_lookup,
}

def main() -> None:
    st.set_page_config(
        page_title="EdgarTools Universe",
        page_icon="🌐",
        layout="wide",
    )
    st.sidebar.title("EdgarTools Universe")
    st.sidebar.caption("Streamlit over EDGARTOOLS_GOLD")
    section_name = st.sidebar.radio("Section", list(SECTIONS.keys()))
    st.sidebar.divider()
    if st.sidebar.button("🔄 Refresh data", use_container_width=True):
        q.clear()
        st.rerun()
    st.sidebar.caption(f"Connection · {_cfg_summary()}")
    SECTIONS[section_name]()
```

Copy the shell, but use exact Phase 8 labels: `page_title="EdgarTools MDM Graph"`, `layout="wide"`, sidebar title `EdgarTools MDM`, caption `Read-only MDM and Neo4j status`, nav entries `Overview`, `Entities`, `Relationships`, `Graph Coverage`, `Neighborhood`, and the only action `Refresh data`.

---

### `examples/mdm_graph_dashboard/README.md` (config/docs, request-response)

**Analogs:** `examples/dashboard/README.md`, `pyproject.toml`

**README structure pattern** (lines 1-8, 19-24, 48-55):
````markdown
# EdgarTools Universe Dashboard

A six-section Streamlit explorer over the Snowflake gold layer built by
[`infra/snowflake/dbt/edgartools_gold`](../../infra/snowflake/dbt/edgartools_gold/).

## Prerequisites

- Python 3.11+
- A Snowflake role with `SELECT` ...

## Run

```bash
streamlit run examples/dashboard/edgar_universe_dashboard.py
```
````

Copy the short README shape: title, purpose, prerequisites, setup/run, caveats, related references. Do not copy the Snowflake/dbt content.

**Dependency/run pattern source** (`pyproject.toml` lines 41-66):
```toml
dashboard = [
    "streamlit>=1.32",
    "plotly>=5.20",
    "pandas>=2.1",
    "snowflake-connector-python>=3.7",
]
mdm-runtime = [
    "sqlalchemy>=2.0.0",
    "psycopg2-binary>=2.9.9",
    "neo4j>=5.20.0",
    "jellyfish>=1.0.0",
    "pydantic>=2.7.0",
    "boto3>=1.34.0",
]
```

README should document uv-based launch:
```bash
uv run --extra dashboard --extra mdm-runtime streamlit run examples/mdm_graph_dashboard/streamlit_app.py
```

Do not copy the old README `python -m venv` / `pip install` setup from lines 40-46 because AGENTS.md requires `uv` for repo workflows.

---

### `edgar_warehouse/mdm/dashboard_readonly.py` (service, CRUD read-only SELECT)

**Analogs:** `edgar_warehouse/mdm/database.py`, `edgar_warehouse/mdm/cli.py`

**Imports/session pattern** (`database.py` lines 8-35, 73-86):
```python
from sqlalchemy import (
    BigInteger,
    Boolean,
    ...
    create_engine,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

def get_engine(url: str | None = None) -> Engine:
    url = url or os.environ["MDM_DATABASE_URL"]
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("mssql"):
        kwargs["fast_executemany"] = True
    engine = create_engine(url, **kwargs)
    from edgar_warehouse.mdm.observability import install_mdm_sql_logging

    install_mdm_sql_logging(engine)
    return engine

def get_session(engine: Engine) -> Session:
    return Session(engine)
```

Use `get_engine()` / `get_session()` or accept injected `Session`/`Engine` for tests. Helpers should create bounded read sessions and close them; they must not call `commit()`.

**Model/table pattern** (`database.py` lines 167-184, 544-580, 679-730):
```python
class MdmCompany(Base):
    __tablename__ = "mdm_company"
    entity_id: Mapped[str] = mapped_column(GUID(), ForeignKey("mdm_entity.entity_id"), primary_key=True)
    cik: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    tracking_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

class MdmRelationshipType(Base):
    __tablename__ = "mdm_relationship_type"
    rel_type_name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    source_node_type: Mapped[str] = mapped_column(Text, ForeignKey("mdm_entity_type_definition.entity_type"), nullable=False)
    target_node_type: Mapped[str] = mapped_column(Text, ForeignKey("mdm_entity_type_definition.entity_type"), nullable=False)

class MdmRelationshipInstance(Base):
    __tablename__ = "mdm_relationship_instance"
    source_entity_id: Mapped[str] = mapped_column(GUID(), ForeignKey("mdm_entity.entity_id"), nullable=False)
    target_entity_id: Mapped[str] = mapped_column(GUID(), ForeignKey("mdm_entity.entity_id"), nullable=False)
    graph_synced_at: Mapped[Optional[object]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
```

Use SQLAlchemy `select()` against these models for smoke/status helpers. Phase 8 should keep output minimal, e.g. connection check and tiny `limit 5` sample/metadata rows.

**Existing count reference, not direct dashboard API** (`cli.py` lines 579-588, 756-786):
```python
def _handle_counts(args) -> int:
    from edgar_warehouse.mdm.database import get_engine
    from edgar_warehouse.mdm.migrations.runtime import count_tables

    engine = get_engine()
    payload = dict(count_tables(engine))
    with Session(engine) as session:
        payload["relationships_by_type"] = _relationship_counts_by_type(session)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0

def _relationship_counts_by_type(session: Session) -> dict[str, dict[str, int]]:
    from sqlalchemy import case, func, select
    from edgar_warehouse.mdm.database import MdmRelationshipInstance, MdmRelationshipType
    ...
    return {
        name: {"active": int(active or 0), "pending_graph_sync": int(pending or 0)}
        for name, active, pending in rows
    }
```

Copy the structured return style from `_relationship_counts_by_type`, not the CLI handler shape. Do not print JSON from helper functions.

---

### `edgar_warehouse/mdm/graph_readonly.py` (service, read-only Cypher request-response)

**Analogs:** `edgar_warehouse/mdm/graph.py`, `edgar_warehouse/mdm/cli.py`

**Client/session pattern** (`graph.py` lines 123-184):
```python
@dataclass
class Neo4jGraphClient:
    uri: str
    user: str
    password: str = field(repr=False)
    database: str | None = None
    _driver: Any = field(default=None, init=False, repr=False)

    def connect(self) -> None:
        ...
        self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    @contextmanager
    def session(self):
        if self._driver is None:
            self.connect()
        kwargs = {"database": self.database} if self.database else {}
        with self._driver.session(**kwargs) as s:
            yield _LoggedNeo4jSession(s, uri=self.uri)
```

Reuse `Neo4jGraphClient`; do not import or instantiate `GraphSyncEngine`.

**Logged query pattern** (`graph.py` lines 191-227):
```python
def run(self, query: str, parameters: dict | None = None, **kwargs: Any):
    started_at = time.monotonic()
    query_hash = _query_hash(query)
    emit_mdm_event(
        "neo4j_query_started",
        host=_uri_host(self._uri),
        operation=_query_operation(query),
        parameter_keys=_parameter_keys(parameters, kwargs),
        query=_summarize_query(query),
        query_hash=query_hash,
        scheme=urlparse(self._uri).scheme,
    )
    ...
    return result
```

Helper functions can call `client.session().run(...)`; logging happens inside the client wrapper.

**Config loading pattern** (`cli.py` lines 228-247):
```python
def _neo4j_client():
    from edgar_warehouse.mdm.graph import Neo4jGraphClient

    uri = os.environ.get("NEO4J_URI")
    user = os.environ.get("NEO4J_USER") or os.environ.get("NEO4J_USERNAME")
    password = os.environ.get("NEO4J_PASSWORD")
    database = os.environ.get("NEO4J_DATABASE")
    if not (uri and user and password) and os.environ.get("NEO4J_SECRET_JSON"):
        payload = json.loads(os.environ["NEO4J_SECRET_JSON"])
        uri = uri or payload.get("uri")
        user = user or payload.get("user") or payload.get("username")
        password = password or payload.get("password")
        database = database or payload.get("database")
    if not (uri and user and password):
        return None
    if uri and uri.startswith("neo4j://"):
        uri = "bolt://" + uri[len("neo4j://"):]
    return Neo4jGraphClient(uri=uri, user=user, password=password, database=database)
```

Copy env compatibility and `neo4j://` normalization. Return a structured `not_configured` state instead of failing startup.

**Read-only smoke query pattern** (`cli.py` lines 591-608):
```python
payload = {"sql": check_connectivity(get_engine())}
if args.neo4j:
    client = _neo4j_client()
    if client is None:
        payload["neo4j"] = {"connected": False, "error": "NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD not configured"}
    else:
        try:
            with client.session() as session:
                record = session.run("RETURN 1 AS ok").single()
            payload["neo4j"] = {"connected": bool(record and record["ok"] == 1)}
        finally:
            client.close()
```

Use static `RETURN 1 AS ok` for Phase 8. Do not add label or relationship interpolation in this phase.

**Dynamic relationship validation reference** (`cli.py` lines 789-791):
```python
def _validate_cypher_relationship_type(rel_type: str) -> None:
    if not rel_type.replace("_", "").isalnum() or not rel_type[0].isalpha():
        raise ValueError(f"Unsafe Neo4j relationship type: {rel_type}")
```

If any future read helper interpolates relationship types, validate with this pattern first. Prefer no interpolation in Phase 8.

---

### `tests/mdm/test_dashboard_readonly.py` (test, CRUD read-only SELECT)

**Analog:** `tests/mdm/conftest.py`

**SQLite fixture pattern** (lines 90-117):
```python
@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """In-memory SQLite session with MDM schema + minimal graph seed data."""
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        _seed_entity_type(session, "company",  "Company",  "mdm_company")
        _seed_entity_type(session, "adviser",  "Adviser",  "mdm_adviser")
        _seed_entity_type(session, "fund",     "Fund",     "mdm_fund")
        _seed_entity_type(session, "security", "Security", "mdm_security")
        _seed_rel_type(session, "MANAGES_FUND", "adviser",  "fund")
        _seed_rel_type(session, "ISSUED_BY",    "security", "company")
        session.commit()
        yield session
```

Use this fixture directly. Add tests that seed tiny MDM rows, call helper functions, and assert helpers return structured objects/dicts.

**Safety assertions to add:**
- Monkeypatch or fake `Session.commit` to raise, then prove read-only helpers do not call it.
- Assert helper functions do not import `MDMPipeline`, migrations, stewardship, resolver write modules, or graph sync.
- Assert missing `MDM_DATABASE_URL` / failed connection surfaces a fixed safe message with env var names only.

---

### `tests/mdm/test_graph_readonly.py` (test, fake Neo4j read request-response)

**Analog:** `tests/mdm/test_graph.py`

**Fake graph client pattern** (lines 145-168):
```python
class _FakeGraphSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def run(self, query: str, **kwargs):
        self.calls.append((query, kwargs))
        return None

class _FakeGraphClient:
    def __init__(self) -> None:
        self.graph_session = _FakeGraphSession()

    def session(self):
        client = self

        class _Context:
            def __enter__(self):
                return client.graph_session

            def __exit__(self, exc_type, exc, tb):
                return None

        return _Context()
```

Copy this fake-client shape, but make `run()` return a fake result with `.single()` for `RETURN 1 AS ok`.

**Env/config test pattern** (lines 572-608):
```python
with patch.dict(os.environ, {
    "NEO4J_URI":      uri,
    "NEO4J_USER":     "neo4j",
    "NEO4J_PASSWORD": "secret",
}):
    return _neo4j_client()
...
with patch.dict(os.environ, {}, clear=True):
    assert _neo4j_client() is None
```

Use `patch.dict(os.environ, ..., clear=True)` for credential-free config tests. Assert no raw env values appear in returned error/status messages.

**Read-only query safety assertions:**
```python
WRITE_TOKENS = ("MERGE", "CREATE", "DELETE", "SET", "REMOVE", "CALL")
assert all(token not in captured_query.upper().split() for token in WRITE_TOKENS)
assert captured_query == "RETURN 1 AS ok"
```

Do not copy live Neo4j fixtures for Phase 8; tests should use fake clients only.

---

### `tests/architecture/test_dashboard_foundation_boundaries.py` (test, static analysis)

**Analog:** `tests/architecture/test_boundaries.py`

**Repository scanning pattern** (lines 1-13):
```python
from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "edgar_warehouse"

def _python_sources() -> list[Path]:
    return sorted(PACKAGE_ROOT.rglob("*.py"))
```

For this phase, scan only the new dashboard/helper targets plus relevant example path, not every workstream directory.

**Boundary assertion pattern** (lines 15-23, 79-90):
```python
class BoundaryTests(unittest.TestCase):
    def test_httpx_only_lives_in_sec_client(self) -> None:
        offenders = [
            path
            for path in _python_sources()
            if "import httpx" in path.read_text()
            and path != PACKAGE_ROOT / "infrastructure" / "sec_client.py"
        ]
        self.assertEqual(offenders, [])

    def test_snowflake_publishers_only_live_in_target_module(self) -> None:
        offenders = []
        for path in _python_sources():
            text = path.read_text()
            ...
        self.assertEqual(offenders, [])
```

Use this style for forbidden import/token/path guards.

**Forbidden Phase 8 dashboard boundaries:**
- Streamlit app and read-only helpers must not import `MDMPipeline`, `GraphSyncEngine`, `backfill_relationship_instances`, `migrate`, resolver modules, stewardship modules, or rollout/deployment modules.
- New dashboard path must not mention `infra/aws-*-application.json`, `infra/snowflake/dbt`, Terraform roots, Step Functions, generated deployment JSON, or runtime rollout scripts.
- New graph read-only helpers/tests must not contain write Cypher tokens: `MERGE`, `CREATE`, `DELETE`, `SET`, `REMOVE`, `CALL`.
- UI must not render mutation labels: `sync graph`, `derive relationships`, `load relationships`, `migrate`, `seed universe`, `merge`, `quarantine`, `accept`, `reject`.

## Shared Patterns

### Streamlit Dashboard Shell

**Source:** `examples/dashboard/edgar_universe_dashboard.py` lines 1331-1355  
**Apply to:** `examples/mdm_graph_dashboard/streamlit_app.py`

Use `st.set_page_config(..., layout="wide")`, sidebar title/caption, `st.sidebar.radio`, refresh button, cache clear, `st.rerun()`, and section dispatch. Replace emoji/icon labels with plain Phase 8 labels per UI-SPEC.

### MDM SQL Session Boundary

**Source:** `edgar_warehouse/mdm/database.py` lines 73-86  
**Apply to:** `edgar_warehouse/mdm/dashboard_readonly.py`, `tests/mdm/test_dashboard_readonly.py`

Use existing `get_engine()` and `get_session()` conventions. Helpers should either accept an injected session for tests or open/close a session around bounded SELECT-style queries. No helper in this phase should call `commit()`.

### Neo4j Optional Connection

**Source:** `edgar_warehouse/mdm/cli.py` lines 228-247 and `edgar_warehouse/mdm/graph.py` lines 123-184  
**Apply to:** `edgar_warehouse/mdm/graph_readonly.py`, `examples/mdm_graph_dashboard/streamlit_app.py`, `tests/mdm/test_graph_readonly.py`

Support `NEO4J_URI`, `NEO4J_USER`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`, and `NEO4J_SECRET_JSON`; normalize `neo4j://` to `bolt://`; return `not_configured` instead of blocking the dashboard when Neo4j is absent.

### Secret-Safe Error Handling

**Source:** `edgar_warehouse/mdm/cli.py` lines 208-220  
**Apply to:** all new helpers and Streamlit shell

```python
def _safe_arguments(args: argparse.Namespace) -> dict[str, object]:
    safe: dict[str, object] = {}
    blocked_fragments = ("password", "secret", "token", "key")
    for name, value in vars(args).items():
        if name == "handler" or any(fragment in name.lower() for fragment in blocked_fragments):
            continue
        ...
    return safe
```

Follow the same principle for dashboard diagnostics: show env var names and status categories, not raw values or raw exception strings that may include credentials.

### Static Boundary Tests

**Source:** `tests/architecture/test_boundaries.py` lines 7-23  
**Apply to:** `tests/architecture/test_dashboard_foundation_boundaries.py`

Use `Path.read_text()` and offender lists. Keep assertions direct: `self.assertEqual(offenders, [])`.

## No Analog Found

None. All planned files have close local analogs.

## Metadata

**Analog search scope:** `examples/dashboard`, `edgar_warehouse/mdm`, `tests/mdm`, `tests/architecture`, `pyproject.toml`  
**Files scanned:** 23 via `rg --files` plus targeted analog reads  
**Pattern extraction date:** 2026-05-17  
**Worktree:** `/Users/aneenaananth/gsd-workspaces/mdm-neo4j-dashboard/edgartools-platform`  
**Active workstream:** `mdm-neo4j-dashboard`
