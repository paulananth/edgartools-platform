from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "verify-neo4j-phase7-capabilities.sh"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_requires_exact_dev_connection(tmp_path: Path) -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=ROOT,
        env={**os.environ, "SNOW_CONNECTION": "wrong"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "SNOW_CONNECTION must be exactly snowconn" in result.stderr


def test_capability_matrix_and_safe_temporary_switch(tmp_path: Path) -> None:
    snow = tmp_path / "snow"
    uv = tmp_path / "uv"
    _write_executable(
        snow,
        """#!/usr/bin/env bash
query="$*"
case "$query" in
  *SHOW*APPLICATIONS*) echo Neo4j_Graph_Analytics ;;
  *SHOW_AVAILABLE_COMPUTE_POOLS*) echo CPU_X64_XS ;;
  *NODEID*LIMIT*) echo '[{"NODEID": "node-1"}]' ;;
  *GRAPH.GRAPH_INFO*|*GRAPH.BFS*) echo '[{"JOB_STATUS":"SUCCESS"}]' ;;
  *PHASE7_test_run_EDGE_A*) echo 'GEN_A DATE GEN_B DATE ACTIVE' ;;
  *GRANT*OWNERSHIP*) echo 'does not exist' ;;
  *) echo OK ;;
esac
""",
    )
    _write_executable(
        uv,
        """#!/usr/bin/env bash
echo '{"failure_domains":[],"failure_summary":{"parity":"ok","readiness":"ok","capability":"ok"},"status":"ok"}'
""",
    )
    env = {
        **os.environ,
        "SNOW_CONNECTION": "snowconn",
        "SNOW_BIN": str(snow),
        "UV_BIN": str(uv),
        "PHASE7_PREFLIGHT_SKIP_OWNERSHIP_CHECK": "true",
        "PHASE7_PREFLIGHT_RESULTS_DIR": str(tmp_path),
        "PHASE7_PREFLIGHT_RUN_ID": "test-run",
    }
    result = subprocess.run(
        ["bash", str(SCRIPT)], cwd=ROOT, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    expected = {
        "ownership_check",
        "app_installation",
        "compute_pool",
        "contract_views",
        "semantic_contract_parity",
        "graph_info",
        "bfs",
        "list_graphs",
        "typed_dates_generation_and_registry",
        "cleanup",
        "aggregate",
    }
    rows = (tmp_path / "neo4j-phase7-preflight-test-run.tsv").read_text().splitlines()
    assert expected == {row.split("\t", 1)[0] for row in rows}
    assert any(row.startswith("aggregate\tGO\t") for row in rows)
    script_text = SCRIPT.read_text()
    assert "CREATE TEMPORARY TABLE" in script_text
    assert "CREATE OR REPLACE TEMPORARY VIEW" in script_text
    assert "GRAPH_REGISTRY" in script_text
    assert "'project':" in script_text
    assert "'targetNodesTable':" in script_text
    assert "DROP TABLE EDGARTOOLS_DEV" not in script_text


def test_supported_required_failure_produces_no_go_but_list_graphs_does_not(tmp_path: Path) -> None:
    snow = tmp_path / "snow"
    uv = tmp_path / "uv"
    _write_executable(
        snow,
        """#!/usr/bin/env bash
query="$*"
if [[ "$query" == *EXPERIMENTAL.LIST_GRAPHS* ]]; then exit 7; fi
if [[ "$query" == *GRAPH.GRAPH_INFO* ]]; then echo 'JOB_STATUS ERROR validation failed'; exit 0; fi
if [[ "$query" == *SHOW*APPLICATIONS* ]]; then echo Neo4j_Graph_Analytics; exit 0; fi
if [[ "$query" == *SHOW_AVAILABLE_COMPUTE_POOLS* ]]; then echo CPU_X64_XS; exit 0; fi
if [[ "$query" == *NODEID*LIMIT* ]]; then echo '[{"NODEID": "node-1"}]'; exit 0; fi
if [[ "$query" == *GRAPH.BFS* ]]; then echo '[{"JOB_STATUS":"SUCCESS"}]'; exit 0; fi
if [[ "$query" == *PHASE7_failure_run_EDGE_A* ]]; then echo 'GEN_A DATE GEN_B DATE ACTIVE'; exit 0; fi
if [[ "$query" == *GRANT*OWNERSHIP* ]]; then echo 'does not exist'; exit 0; fi
echo OK
""",
    )
    _write_executable(
        uv,
        """#!/usr/bin/env bash
echo '{"failure_domains":[],"failure_summary":{"parity":"ok","readiness":"ok","capability":"ok"},"status":"ok"}'
""",
    )
    env = {
        **os.environ,
        "SNOW_CONNECTION": "snowconn",
        "SNOW_BIN": str(snow),
        "UV_BIN": str(uv),
        "PHASE7_PREFLIGHT_SKIP_OWNERSHIP_CHECK": "true",
        "PHASE7_PREFLIGHT_RESULTS_DIR": str(tmp_path),
        "PHASE7_PREFLIGHT_RUN_ID": "failure-run",
    }
    result = subprocess.run(
        ["bash", str(SCRIPT)], cwd=ROOT, env=env, capture_output=True, text=True
    )
    assert result.returncode == 1
    rows = (tmp_path / "neo4j-phase7-preflight-failure-run.tsv").read_text()
    assert "graph_info\tFAIL\tcommand=" in rows
    assert "Native App job reported ERROR" not in rows
    assert "list_graphs\tEXTERNAL_BLOCKER\t" in rows
    assert "aggregate\tNO_GO\t" in rows


def test_list_graphs_failure_is_non_blocking(tmp_path: Path) -> None:
    snow = tmp_path / "snow"
    uv = tmp_path / "uv"
    _write_executable(
        snow,
        """#!/usr/bin/env bash
query="$*"
if [[ "$query" == *EXPERIMENTAL.LIST_GRAPHS* ]]; then exit 7; fi
if [[ "$query" == *SHOW*APPLICATIONS* ]]; then echo Neo4j_Graph_Analytics; exit 0; fi
if [[ "$query" == *SHOW_AVAILABLE_COMPUTE_POOLS* ]]; then echo CPU_X64_XS; exit 0; fi
if [[ "$query" == *NODEID*LIMIT* ]]; then echo '[{"NODEID": "node-1"}]'; exit 0; fi
if [[ "$query" == *GRAPH.GRAPH_INFO* || "$query" == *GRAPH.BFS* ]]; then echo '[{"JOB_STATUS":"SUCCESS"}]'; exit 0; fi
if [[ "$query" == *PHASE7_list_only_EDGE_A* ]]; then echo 'GEN_A DATE GEN_B DATE ACTIVE'; exit 0; fi
if [[ "$query" == *GRANT*OWNERSHIP* ]]; then echo 'does not exist'; exit 0; fi
echo OK
""",
    )
    _write_executable(uv, "#!/usr/bin/env bash\necho '{\"failure_domains\":[],\"failure_summary\":{\"parity\":\"ok\",\"readiness\":\"ok\",\"capability\":\"ok\"},\"status\":\"ok\"}'\n")
    env = {
        **os.environ,
        "SNOW_CONNECTION": "snowconn",
        "SNOW_BIN": str(snow),
        "UV_BIN": str(uv),
        "PHASE7_PREFLIGHT_SKIP_OWNERSHIP_CHECK": "true",
        "PHASE7_PREFLIGHT_RESULTS_DIR": str(tmp_path),
        "PHASE7_PREFLIGHT_RUN_ID": "list-only",
    }
    result = subprocess.run(["bash", str(SCRIPT)], cwd=ROOT, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    rows = (tmp_path / "neo4j-phase7-preflight-list-only.tsv").read_text()
    assert "list_graphs\tEXTERNAL_BLOCKER\t" in rows
    assert "aggregate\tGO\t" in rows
