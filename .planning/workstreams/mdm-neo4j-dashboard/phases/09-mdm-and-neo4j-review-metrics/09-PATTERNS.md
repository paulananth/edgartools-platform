# Phase 09: MDM And Neo4j Review Metrics - Pattern Map

**Mapped:** 2026-05-20
**Files analyzed:** 7
**Analogs found:** 7 / 7

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `edgar_warehouse/mdm/dashboard_readonly.py` | service | request-response, CRUD-read, transform | `edgar_warehouse/mdm/dashboard_readonly.py` + `edgar_warehouse/mdm/cli.py::_relationship_counts_by_type` | exact |
| `edgar_warehouse/mdm/graph_readonly.py` | service | request-response, CRUD-read, transform | `edgar_warehouse/mdm/graph_readonly.py` + `edgar_warehouse/mdm/cli.py::_handle_verify_graph` | exact |
| `examples/mdm_graph_dashboard/streamlit_app.py` | component | request-response, cached-read, transform | `examples/mdm_graph_dashboard/streamlit_app.py` | exact |
| `tests/mdm/test_dashboard_readonly.py` | test | request-response, CRUD-read, static-safety | `tests/mdm/test_dashboard_readonly.py` | exact |
| `tests/mdm/test_graph_readonly.py` | test | request-response, CRUD-read, static-safety | `tests/mdm/test_graph_readonly.py` | exact |
| `tests/architecture/test_dashboard_foundation_boundaries.py` | test | static-analysis, boundary-guard | `tests/architecture/test_dashboard_foundation_boundaries.py` | exact |
| `examples/mdm_graph_dashboard/README.md` | documentation | operator-guidance | `examples/mdm_graph_dashboard/README.md` | exact |

## Pattern Assignments

### `edgar_warehouse/mdm/dashboard_readonly.py` (service, request-response / CRUD-read)

**Analog:** `edgar_warehouse/mdm/dashboard_readonly.py`

**Imports pattern** (lines 4-17):
```python
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from edgar_warehouse.mdm.database import (
    MdmCompany,
    MdmEntity,
    MdmEntityTypeDefinition,
    get_engine,
    get_session,
)
```

Copy this style for Phase 9 helper imports: standard library first, SQLAlchemy primitives next, MDM model imports last. Add `case`, `MdmAdviser`, `MdmPerson`, `MdmSecurity`, `MdmFund`, `MdmRelationshipType`, and `MdmRelationshipInstance` here rather than importing CLI handlers.

**Structured result pattern** (lines 27-58):
```python
@dataclass(frozen=True)
class MdmDashboardStatus:
    connected: bool
    message: str
    env_var: str = MDM_DATABASE_ENV_VAR
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "message": self.message,
            "env_var": self.env_var,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class MdmSmokeResult:
    available: bool
    message: str
    limit: int
    rows: list[dict[str, Any]] = field(default_factory=list)
    error_env_var: str | None = None
```

Define Phase 9 metric rows, warning rows, samples, and aggregate result as frozen dataclasses with `as_dict()`. Keep Streamlit consumption plain dict/list output.

**Session ownership and safe failure pattern** (lines 61-85):
```python
def check_mdm_status(
    *,
    engine: Engine | None = None,
    session: Session | None = None,
) -> MdmDashboardStatus:
    owned_session: Session | None = None
    try:
        active_session = session
        if active_session is None:
            active_engine = engine or get_engine()
            owned_session = get_session(active_engine)
            active_session = owned_session

        entity_type_count = active_session.scalar(
            select(func.count(MdmEntityTypeDefinition.entity_type))
        )
        return MdmDashboardStatus(
            connected=True,
            message="MDM database connected.",
            details={"entity_types": int(entity_type_count or 0)},
        )
    except Exception:
        return _unavailable_status()
    finally:
        _close_owned_session(owned_session)
```

Copy this for `get_dashboard_metrics(...)`: accept injected `Session` for tests, create/close only owned sessions, catch exceptions into fixed status payloads, and never render raw exception text or DSNs.

**Bounded read query pattern** (lines 88-130):
```python
def run_mdm_smoke_query(
    *,
    engine: Engine | None = None,
    session: Session | None = None,
    limit: int = 5,
) -> MdmSmokeResult:
    row_limit = _bounded_limit(limit)
    owned_session: Session | None = None
    try:
        active_session = session
        if active_session is None:
            active_engine = engine or get_engine()
            owned_session = get_session(active_engine)
            active_session = owned_session

        stmt = (
            select(
                MdmEntity.entity_type,
                MdmCompany.cik,
                MdmCompany.canonical_name,
            )
            .join(MdmCompany, MdmCompany.entity_id == MdmEntity.entity_id)
            .order_by(MdmCompany.cik)
            .limit(row_limit)
        )
        rows = [
            {
                "entity_type": entity_type,
                "cik": int(cik),
                "canonical_name": canonical_name,
            }
            for entity_type, cik, canonical_name in active_session.execute(stmt)
        ]
```

Reuse this shape for pending sync and diagnostic samples: clamp limits before query construction, select only operator-readable fields, order deterministically, and return dictionaries.

**Limit and close pattern** (lines 133-165):
```python
def _bounded_limit(limit: int) -> int:
    try:
        requested = int(limit)
    except (TypeError, ValueError):
        requested = 5
    return max(0, min(requested, 5))


def _close_owned_session(session: Session | None) -> None:
    if session is None:
        return
    try:
        session.rollback()
    finally:
        session.close()
```

Add separate helpers for per-type and global sample limits, but keep the same "rollback then close owned session" cleanup.

**Domain model references** (lines 167-204, 247-295):
```python
class MdmCompany(Base):
    __tablename__ = "mdm_company"
    ...
    cik: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)

class MdmAdviser(Base):
    __tablename__ = "mdm_adviser"
    ...
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)

class MdmSecurity(Base):
    __tablename__ = "mdm_security"
    ...
    canonical_title: Mapped[str] = mapped_column(Text, nullable=False)

class MdmFund(Base):
    __tablename__ = "mdm_fund"
    ...
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
```

Entity counts should count `MdmCompany`, `MdmAdviser`, `MdmPerson`, `MdmSecurity`, and `MdmFund`. For sample display names, use `canonical_name` where present and `canonical_title` for securities.

**Relationship count query pattern** (lines 740-770):
```python
pending_expr = case(
    (
        (MdmRelationshipInstance.instance_id.isnot(None))
        & (MdmRelationshipInstance.graph_synced_at.is_(None)),
        1,
    ),
    else_=0,
)
rows = session.execute(
    select(
        MdmRelationshipType.rel_type_name,
        func.count(MdmRelationshipInstance.instance_id),
        func.coalesce(func.sum(pending_expr), 0),
    )
    .outerjoin(
        MdmRelationshipInstance,
        (MdmRelationshipInstance.rel_type_id == MdmRelationshipType.rel_type_id)
        & (MdmRelationshipInstance.is_active == True),
    )
    .where(MdmRelationshipType.is_active == True)
    .group_by(MdmRelationshipType.rel_type_name)
    .order_by(MdmRelationshipType.rel_type_name)
)
```

Copy this query shape into `dashboard_readonly.py`, not the CLI function. The driving table must be `MdmRelationshipType` so active types with zero rows still render.

**Pending sample ordering pattern** (lines 463-511):
```python
stmt = (
    select(MdmRelationshipInstance)
    .where(
        MdmRelationshipInstance.graph_synced_at.is_(None),
        MdmRelationshipInstance.is_active == True,
        MdmRelationshipInstance.rel_type_id == rel_type_id,
    )
    .order_by(MdmRelationshipInstance.created_at, MdmRelationshipInstance.instance_id)
    .limit(limit_per_type)
)
for row in self.session.scalars(stmt):
    selected.append(row)
    if limit is not None and len(selected) >= limit:
        return selected
```

Use this as query guidance only. Do not import `GraphSyncEngine`; implement a read-only equivalent in `dashboard_readonly.py`.

---

### `edgar_warehouse/mdm/graph_readonly.py` (service, request-response / CRUD-read)

**Analog:** `edgar_warehouse/mdm/graph_readonly.py`

**Imports and safe copy constants** (lines 4-20):
```python
import json
import os
from dataclasses import dataclass, field
from typing import Any, Mapping

from edgar_warehouse.mdm.graph import Neo4jGraphClient


NEO4J_ENV_VARS = ["NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD"]
NEO4J_NOT_CONFIGURED_MESSAGE = (
    "Neo4j is not configured. MDM relationship tables are still available."
)
NEO4J_QUERY_FAILED_MESSAGE = (
    "Neo4j query failed. Check `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, "
    "and network access."
)
```

Keep error copy fixed and secret-safe. Add Phase 9 unavailable/partial metric result messages here instead of exposing exception strings.

**Client loading pattern** (lines 41-76):
```python
def load_neo4j_review_client(
    environ: Mapping[str, str] | None = None,
) -> tuple[Neo4jReviewStatus, Neo4jGraphClient | None]:
    env = environ if environ is not None else os.environ
    uri = env.get("NEO4J_URI")
    user = env.get("NEO4J_USER") or env.get("NEO4J_USERNAME")
    password = env.get("NEO4J_PASSWORD")
    database = env.get("NEO4J_DATABASE")

    if not (uri and user and password):
        secret_payload = _load_secret_payload(env.get("NEO4J_SECRET_JSON"))
        uri = uri or _string_or_none(secret_payload.get("uri"))
        user = user or _string_or_none(
            secret_payload.get("user") or secret_payload.get("username")
        )
        password = password or _string_or_none(secret_payload.get("password"))
        database = database or _string_or_none(secret_payload.get("database"))

    if not (uri and user and password):
        return _not_configured_status(), None
```

Reuse this loader. New graph metric functions should accept injected fake clients and only create/close clients they own.

**Read-only query pattern** (lines 99-117):
```python
def run_neo4j_smoke_query(*, client: Any | None) -> Neo4jReviewStatus:
    if client is None:
        return _not_configured_status()

    try:
        with client.session() as session:
            record = session.run(NEO4J_SMOKE_QUERY).single()
        ok = bool(record and record["ok"] == 1)
    except Exception:
        return _query_failed_status()

    if not ok:
        return _query_failed_status()
    return Neo4jReviewStatus(
        state="connected",
        connected=True,
        message="Neo4j connected.",
        details={"ok": True},
    )
```

Graph count helpers should use the same `with client.session()` pattern, catch all driver failures into unavailable metrics, and return MDM-compatible partial state.

**Registry load pattern** (lines 45-87):
```python
@dataclass
class GraphRegistry:
    labels_by_entity_type: dict[str, str] = field(default_factory=dict)
    rel_type_by_id: dict[str, dict] = field(default_factory=dict)
    rel_type_by_name: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def load(cls, session: Session) -> "GraphRegistry":
        reg = cls()
        for et in session.scalars(
            select(MdmEntityTypeDefinition).where(
                MdmEntityTypeDefinition.is_active == True
            )
        ):
            reg.labels_by_entity_type[et.entity_type] = et.neo4j_label
        ...
        return reg

    def label(self, entity_type: str) -> str:
        try:
            return self.labels_by_entity_type[entity_type]
        except KeyError as e:
            raise KeyError(f"Unknown entity_type '{entity_type}' in graph registry") from e
```

Load labels and relationship types from the SQL registry before composing dynamic Cypher. Do not hard-code graph labels in the Streamlit app.

**Neo4j count reference pattern** (lines 682-709):
```python
registry = GraphRegistry.load(session)
relationship_types = sorted(registry.rel_type_by_name)
with client.session() as s:
    payload = {"neo4j_nodes_total": s.run("MATCH (n) RETURN count(n) AS n").single()["n"]}
    for rel_type in relationship_types:
        _validate_cypher_relationship_type(rel_type)
        payload[f"neo4j_{rel_type}_edges"] = s.run(
            f"MATCH ()-[r:{rel_type}]->() RETURN count(r) AS n"
        ).single()["n"]
```

Copy the query intent, not the CLI handler. Phase 9 should return structured graph metric rows instead of printing JSON or importing `GraphSyncEngine`.

**Dynamic identifier validation pattern** (lines 773-775):
```python
def _validate_cypher_relationship_type(rel_type: str) -> None:
    if not rel_type.replace("_", "").isalnum() or not rel_type[0].isalpha():
        raise ValueError(f"Unsafe Neo4j relationship type: {rel_type}")
```

Add an equivalent validator for labels and relationship types in `graph_readonly.py`. Use only registry-backed identifiers.

---

### `examples/mdm_graph_dashboard/streamlit_app.py` (component, cached request-response)

**Analog:** `examples/mdm_graph_dashboard/streamlit_app.py`

**Imports and navigation pattern** (lines 3-16):
```python
from typing import Any

import streamlit as st

from edgar_warehouse.mdm import dashboard_readonly, graph_readonly


SECTIONS = [
    "Overview",
    "Entities",
    "Relationships",
    "Graph Coverage",
    "Neighborhood",
]
```

Keep the existing navigation labels. Phase 9 should populate `Overview`, `Entities`, `Relationships`, and `Graph Coverage`; leave `Neighborhood` as the Phase 8 placeholder.

**Cache and refresh pattern** (lines 27-54):
```python
@st.cache_data(ttl=60, show_spinner=False)
def _read_mdm_status() -> dict[str, Any]:
    return dashboard_readonly.check_mdm_status().as_dict()


@st.cache_data(ttl=60, show_spinner=False)
def _read_neo4j_status() -> dict[str, Any]:
    return graph_readonly.check_neo4j_status().as_dict()


def _clear_dashboard_cache() -> None:
    st.cache_data.clear()
```

Create cached `_read_*_metrics()` wrappers that call helper dataclasses' `as_dict()`. Section refresh can clear specific cached functions if clean; otherwise this global pattern is accepted by the UI spec.

**Status and table rendering pattern** (lines 57-77):
```python
def _render_status(label: str, status: dict[str, Any], *, required: bool) -> None:
    if status.get("connected"):
        st.success(f"{label}: {status['message']}")
        return
    if required:
        st.error(status["message"])
    else:
        st.warning(status["message"])


def _render_mdm_smoke(smoke: dict[str, Any]) -> None:
    ...
    st.dataframe(rows, use_container_width=True, hide_index=True)
```

Copy the severity mapping approach for grouped warnings. Render all metric tables with `st.dataframe(..., use_container_width=True, hide_index=True)`.

**Overview layout pattern** (lines 87-115):
```python
def render_overview() -> None:
    st.title("EdgarTools MDM Graph")
    st.caption("Read-only connectivity checks for local MDM and optional Neo4j review.")

    mdm_status = _read_mdm_status()
    neo4j_status = _read_neo4j_status()

    status_left, status_right = st.columns(2)
    with status_left:
        st.subheader("MDM status")
        _render_status("MDM", mdm_status, required=True)
    with status_right:
        st.subheader("Neo4j status")
        _render_status("Neo4j", neo4j_status, required=False)

    if not mdm_status.get("connected"):
        return
```

Use this "MDM required, Neo4j optional" branch structure. Phase 9 overview should show coverage snapshot first, grouped warnings second, timestamps third, and only then low-priority diagnostics if kept.

**App shell pattern** (lines 122-135):
```python
def main() -> None:
    st.set_page_config(page_title="EdgarTools MDM Graph", layout="wide")
    st.sidebar.title("EdgarTools MDM")
    st.sidebar.caption("Read-only MDM and Neo4j status")
    section_name = st.sidebar.radio("Section", SECTIONS)
    st.sidebar.divider()
    if st.sidebar.button("Refresh data", use_container_width=True):
        _clear_dashboard_cache()
        st.rerun()

    if section_name == "Overview":
        render_overview()
    else:
        render_placeholder(section_name)
```

Keep page config, sidebar title/caption, and native Streamlit controls. Change button copy to `Refresh metrics` per UI-SPEC.

---

### `tests/mdm/test_dashboard_readonly.py` (test, read-only helper coverage)

**Analog:** `tests/mdm/test_dashboard_readonly.py`

**Fixture seeding pattern** (lines 16-21):
```python
def _seed_company(session, cik: int = 320193, name: str = "Apple Inc.") -> None:
    entity = MdmEntity(entity_type="company", resolution_method="test", confidence=1.0)
    session.add(entity)
    session.flush()
    session.add(MdmCompany(entity_id=entity.entity_id, cik=cik, canonical_name=name))
    session.commit()
```

Add small local seed helpers for adviser/person/security/fund and relationship instances in this test file unless the shared fixture must change.

**Structured result test pattern** (lines 24-37):
```python
def test_check_mdm_status_returns_structured_connected_status(db_session):
    from edgar_warehouse.mdm.dashboard_readonly import (
        MdmDashboardStatus,
        check_mdm_status,
    )

    status = check_mdm_status(session=db_session)

    assert isinstance(status, MdmDashboardStatus)
    assert status.connected is True
    assert status.message == "MDM database connected."
    assert status.env_var == "MDM_DATABASE_URL"
    assert status.details["entity_types"] >= 4
```

Mirror this for `MdmDashboardMetrics` and row dataclasses. Assert exact counts, statuses, and dict payload shape.

**Read-only guard pattern** (lines 56-66):
```python
def test_helpers_never_commit(db_session, monkeypatch):
    from edgar_warehouse.mdm import dashboard_readonly

    def fail_commit():
        raise AssertionError("dashboard read-only helpers must not commit")

    monkeypatch.setattr(db_session, "commit", fail_commit)

    dashboard_readonly.check_mdm_status(session=db_session)
    dashboard_readonly.run_mdm_smoke_query(session=db_session, limit=5)
```

Extend this test to call new Phase 9 metric and sample helpers.

**Secret-safe failure pattern** (lines 85-107):
```python
def test_failed_mdm_connection_does_not_leak_dsn_or_raw_exception(monkeypatch):
    from edgar_warehouse.mdm.dashboard_readonly import check_mdm_status

    secret_dsn = "postgresql://dashboard_user:super-secret@example.internal/mdm"

    def fail_engine():
        raise RuntimeError(f"could not connect to {secret_dsn}")

    monkeypatch.setenv("MDM_DATABASE_URL", secret_dsn)
    monkeypatch.setattr("edgar_warehouse.mdm.dashboard_readonly.get_engine", fail_engine)

    status = check_mdm_status()
    payload = status.as_dict()
    rendered = repr(payload)

    assert "super-secret" not in rendered
    assert "dashboard_user" not in rendered
    assert "example.internal" not in rendered
    assert "could not connect" not in rendered
```

New metric failure tests should assert the same masking for aggregate payloads and warning rows.

**Static mutation guard pattern** (lines 123-149):
```python
def test_dashboard_readonly_module_avoids_mutation_surfaces():
    module_text = Path("edgar_warehouse/mdm/dashboard_readonly.py").read_text()

    blocked_tokens = [
        "MDMPipeline",
        "migrations.runtime",
        "ResolverContext",
        "GraphSyncEngine",
        "sync_pending",
        "sync_entities",
        "_handle_sync_graph",
        "commit(",
        ".commit",
    ]
    for token in blocked_tokens:
        assert token not in module_text
```

Keep this close to new helper names. Add tokens if Phase 9 introduces new risk surfaces.

**Shared fixture pattern** (lines 90-117):
```python
@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    ...
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

For Phase 9, seed missing `person` entity type and additional relationship types locally in tests if needed; avoid changing unrelated fixture assumptions unless tests require it.

---

### `tests/mdm/test_graph_readonly.py` (test, Neo4j helper coverage)

**Analog:** `tests/mdm/test_graph_readonly.py`

**Fake client/session pattern** (lines 18-57):
```python
class _FakeResult:
    def __init__(self, record: dict | None = None) -> None:
        self._record = record or {"ok": 1}

    def single(self):
        return self._record


class _FakeGraphSession:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, dict]] = []

    def run(self, query: str, **kwargs):
        self.calls.append((query, kwargs))
        if self.fail:
            raise RuntimeError("failed against neo4j://neo4j:secret@example.internal")
        return _FakeResult()
```

Extend this fake to return counts by query and capture all dynamic Cypher. Assert Phase 9 graph metric queries are read-only.

**Env convention test pattern** (lines 76-110):
```python
def test_load_neo4j_review_client_uses_existing_env_conventions(monkeypatch):
    from edgar_warehouse.mdm import graph_readonly

    created = {}

    class CapturingClient:
        def __init__(self, *, uri, user, password, database=None):
            created.update(
                {"uri": uri, "user": user, "password": password, "database": database}
            )

    monkeypatch.setattr(graph_readonly, "Neo4jGraphClient", CapturingClient)
    env = {
        "NEO4J_URI": "neo4j://example.internal:7687",
        "NEO4J_USERNAME": "neo4j-user",
        "NEO4J_PASSWORD": "super-secret",
        "NEO4J_DATABASE": "review",
    }
```

Do not add a new Neo4j secret or environment model for metrics. Reuse this behavior.

**Read-only Cypher assertion pattern** (lines 144-157):
```python
def test_run_neo4j_smoke_query_uses_static_read_only_cypher():
    from edgar_warehouse.mdm.graph_readonly import run_neo4j_smoke_query

    client = _FakeGraphClient()

    status = run_neo4j_smoke_query(client=client)

    assert status.state == "connected"
    assert status.connected is True
    assert status.details["ok"] is True
    assert client.graph_session.calls == [("RETURN 1 AS ok", {})]
    query = client.graph_session.calls[0][0]
    assert query == "RETURN 1 AS ok"
    assert not (set(query.upper().split()) & WRITE_TOKENS)
```

Add equivalent tests for `MATCH (n:Label) RETURN count(n)` and `MATCH ()-[r:TYPE]->() RETURN count(r)` generated from registry-backed identifiers.

**Secret-safe failure pattern** (lines 181-196):
```python
def test_query_failure_returns_secret_safe_status():
    from edgar_warehouse.mdm.graph_readonly import run_neo4j_smoke_query

    status = run_neo4j_smoke_query(client=_FakeGraphClient(fail=True))
    payload = status.as_dict()
    rendered = repr(payload)

    assert status.state == "query_failed"
    assert status.connected is False
    assert status.message == NEO4J_QUERY_FAILED_COPY
    assert "NEO4J_URI" in rendered
    assert "NEO4J_USER" in rendered
    assert "NEO4J_PASSWORD" in rendered
    assert "secret" not in rendered
    assert "example.internal" not in rendered
    assert "failed against" not in rendered
```

Graph metric failures should mark Neo4j unavailable while preserving MDM metrics, and must not leak URI/user/password/host values.

**Static graph guard pattern** (lines 210-228):
```python
def test_graph_readonly_module_avoids_sync_and_write_surfaces():
    module_text = Path("edgar_warehouse/mdm/graph_readonly.py").read_text()

    blocked_tokens = [
        "GraphSyncEngine",
        "relationship_merge_cypher",
        "node_merge_cypher",
        "sync_entities",
        "sync_pending",
        "backfill_relationship_instances",
        "MERGE ",
        "CREATE ",
        "DELETE ",
        "SET ",
        "REMOVE ",
        "CALL ",
    ]
    for token in blocked_tokens:
        assert token not in module_text
```

Keep this test green by implementing count/sample queries with `MATCH` and `RETURN` only.

---

### `tests/architecture/test_dashboard_foundation_boundaries.py` (test, static-analysis boundary guard)

**Analog:** `tests/architecture/test_dashboard_foundation_boundaries.py`

**Target list pattern** (lines 8-18):
```python
REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE8_TARGETS = [
    REPO_ROOT / "examples" / "mdm_graph_dashboard" / "streamlit_app.py",
    REPO_ROOT / "examples" / "mdm_graph_dashboard" / "README.md",
    REPO_ROOT / "edgar_warehouse" / "mdm" / "dashboard_readonly.py",
    REPO_ROOT / "edgar_warehouse" / "mdm" / "graph_readonly.py",
]
DASHBOARD_TEXT_TARGETS = [
    REPO_ROOT / "examples" / "mdm_graph_dashboard" / "streamlit_app.py",
    REPO_ROOT / "examples" / "mdm_graph_dashboard" / "README.md",
]
```

Rename or extend targets for Phase 9, but keep the same files in scope. Add any new README/static targets only if the implementation adds them.

**Forbidden import guard pattern** (lines 29-52):
```python
def test_phase8_targets_do_not_import_mutation_surfaces(self) -> None:
    forbidden = [
        "MDMPipeline",
        "GraphSyncEngine",
        "migrations.runtime",
        "edgar_warehouse.mdm.resolvers",
        "edgar_warehouse.mdm.stewardship",
        "relationship_merge_cypher",
        "node_merge_cypher",
        "backfill_relationship_instances",
        "_handle_run",
        "_handle_migrate",
        "_handle_sync_graph",
        "_handle_derive_relationships",
        "_handle_load_relationships",
    ]
```

Keep helper files from importing sync, migration, resolver, stewardship, and CLI mutation surfaces.

**No write Cypher pattern** (lines 54-64):
```python
def test_graph_readonly_contains_no_write_cypher_tokens(self) -> None:
    target = REPO_ROOT / "edgar_warehouse" / "mdm" / "graph_readonly.py"
    if not target.exists():
        self.skipTest("graph_readonly.py not created yet")
    text = _read(target)
    offenders = [
        token
        for token in ("MERGE", "CREATE", "DELETE", "SET", "REMOVE", "CALL")
        if re.search(rf"\b{token}\b", text)
    ]
    self.assertEqual(offenders, [])
```

This should cover new graph metric helpers too.

**No mutation controls pattern** (lines 66-84):
```python
def test_dashboard_text_contains_no_mutation_controls(self) -> None:
    forbidden_labels = [
        "sync graph",
        "derive relationships",
        "load relationships",
        "migrate",
        "seed universe",
        "merge",
        "quarantine",
        "accept",
        "reject",
    ]
```

Add Phase 9 forbidden labels from UI-SPEC if rendered copy changes: repair, run sync, load, edit, mutate, or credential display.

**Streamlit helper boundary pattern** (lines 105-113):
```python
def test_streamlit_shell_uses_readonly_helpers_only(self) -> None:
    target = REPO_ROOT / "examples" / "mdm_graph_dashboard" / "streamlit_app.py"
    if not target.exists():
        self.skipTest("streamlit_app.py not created yet")
    text = _read(target)
    self.assertIn("dashboard_readonly", text)
    self.assertIn("graph_readonly", text)
    self.assertNotIn("SELECT ", text.upper())
    self.assertNotIn("RETURN 1 AS ok", text)
```

Extend this to forbid `MATCH ` and raw Cypher in Streamlit if graph metrics move into helpers as expected.

---

### `examples/mdm_graph_dashboard/README.md` (documentation, operator guidance)

**Analog:** `examples/mdm_graph_dashboard/README.md`

**Scope and launch pattern** (lines 1-18):
```text
# EdgarTools MDM Graph Dashboard

Local Streamlit shell for checking MDM SQL connectivity and optional Neo4j
connectivity before the richer review metrics arrive in later phases.

## Prerequisites

- Python environment managed with `uv`.
- `MDM_DATABASE_URL` for an existing local or dev MDM database.
- Optional Neo4j variables when graph connectivity should be checked:
  `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`.
- Optional graph settings: `NEO4J_DATABASE` or `NEO4J_SECRET_JSON`.

## Run

uv run --extra dashboard --extra mdm-runtime streamlit run examples/mdm_graph_dashboard/streamlit_app.py
```

If README is updated, keep this local `uv` launch pattern. Do not add deployment, Terraform, Step Functions, Snowflake, or secret-management instructions.

**Read-only and secret-safe pattern** (lines 24-33):
```text
## Scope

This Phase 8 dashboard is read-only. It uses helper modules under
`edgar_warehouse.mdm` for bounded status and smoke checks, and it does not
offer data-changing controls.

Status messages name environment variables but do not render raw database URLs,
usernames, passwords, hostnames, secret JSON payloads, or driver exception text.
```

Update "Phase 8" to "Phase 9" only if README is touched, and describe metrics without implying the dashboard can sync, repair, migrate, or mutate.

## Shared Patterns

### Read-Only Helper Boundary

**Source:** `edgar_warehouse/mdm/dashboard_readonly.py`, `edgar_warehouse/mdm/graph_readonly.py`, `tests/architecture/test_dashboard_foundation_boundaries.py`
**Apply to:** helper modules, Streamlit app, README, tests

```python
self.assertIn("dashboard_readonly", text)
self.assertIn("graph_readonly", text)
self.assertNotIn("SELECT ", text.upper())
self.assertNotIn("RETURN 1 AS ok", text)
```

All SQL and Cypher construction belongs in helper modules. Streamlit renders helper payloads only.

### Secret-Safe Errors

**Source:** `edgar_warehouse/mdm/dashboard_readonly.py` lines 20-24 and `edgar_warehouse/mdm/graph_readonly.py` lines 12-19
**Apply to:** MDM failure results, Neo4j failure results, warning rows, Streamlit copy

```python
MDM_UNAVAILABLE_MESSAGE = (
    "MDM database unavailable. Check `MDM_DATABASE_URL`, confirm the database "
    "is reachable, and restart the dashboard."
)
NEO4J_QUERY_FAILED_MESSAGE = (
    "Neo4j query failed. Check `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, "
    "and network access."
)
```

Tests must assert raw DSNs, usernames, passwords, hosts, secret JSON payloads, and driver exception text do not appear in result payloads.

### Registry-Driven Graph Counts

**Source:** `edgar_warehouse/mdm/graph.py` lines 45-87 and `edgar_warehouse/mdm/cli.py` lines 682-709
**Apply to:** graph node counts, edge counts, coverage rows, sample Cypher

```python
registry = GraphRegistry.load(session)
relationship_types = sorted(registry.rel_type_by_name)
for rel_type in relationship_types:
    _validate_cypher_relationship_type(rel_type)
    payload[f"neo4j_{rel_type}_edges"] = s.run(
        f"MATCH ()-[r:{rel_type}]->() RETURN count(r) AS n"
    ).single()["n"]
```

Planner should preserve the registry-driven approach but implement it in `graph_readonly.py`, with no CLI handler calls and no `GraphSyncEngine` import.

### Relationship Counts Include Zero Rows

**Source:** `edgar_warehouse/mdm/cli.py` lines 740-770
**Apply to:** MDM relationship metrics and relationship coverage table

```python
.outerjoin(
    MdmRelationshipInstance,
    (MdmRelationshipInstance.rel_type_id == MdmRelationshipType.rel_type_id)
    & (MdmRelationshipInstance.is_active == True),
)
.where(MdmRelationshipType.is_active == True)
```

The relationship registry must drive the table so active registered types with zero active relationships still appear.

### Bounded Samples

**Source:** `edgar_warehouse/mdm/dashboard_readonly.py` lines 133-138 and `edgar_warehouse/mdm/graph.py` lines 492-511
**Apply to:** pending sync samples, missing-edge samples, extra graph data samples

```python
return max(0, min(requested, 5))
...
for row in self.session.scalars(stmt):
    selected.append(row)
    if limit is not None and len(selected) >= limit:
        return selected
```

Caps belong inside helper functions before display. UI copy must state samples are bounded and not exhaustive.

### Streamlit Native Rendering

**Source:** `examples/mdm_graph_dashboard/streamlit_app.py` lines 87-135
**Apply to:** Overview, Entities, Relationships, Graph Coverage, Neighborhood

```python
st.set_page_config(page_title="EdgarTools MDM Graph", layout="wide")
st.sidebar.title("EdgarTools MDM")
st.sidebar.caption("Read-only MDM and Neo4j status")
section_name = st.sidebar.radio("Section", SECTIONS)
```

Use Streamlit native primitives only. Keep the wide layout and existing sidebar destinations. Replace placeholders with metric views.

## No Analog Found

None. Every expected Phase 9 target extends an existing Phase 8 file or a direct helper/test analog.

## Metadata

**Analog search scope:** `edgar_warehouse/mdm`, `examples/mdm_graph_dashboard`, `tests/mdm`, `tests/architecture`
**Files scanned:** 9 primary files plus phase artifacts
**Pattern extraction date:** 2026-05-20
**Workstream:** `.planning/active-workstream` = `mdm-neo4j-dashboard`
**Existing unrelated dirty files observed:** `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/STATE.md`
