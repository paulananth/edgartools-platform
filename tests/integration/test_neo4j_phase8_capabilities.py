from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "verify-neo4j-phase8-capabilities.sh"


def test_phase8_runner_is_dev_guarded_and_uses_current_api():
    text = SCRIPT.read_text()
    assert 'SNOW_CONNECTION:-}" != "snowconn"' in text
    assert ".GRAPH.GRAPH_INFO('${POOL}'" in text
    assert ".GRAPH.BFS('${POOL}'" in text
    assert "'sourceNodeTable'" in text
    assert "'targetNodesTable'" in text
    assert "'targetNodes':[]" in text
    assert "'maxDepth':2" in text
    assert ".EXPERIMENTAL.LIST_GRAPHS()" in text
    assert "EXTERNAL_BLOCKER" in text


def test_phase8_runner_has_owned_output_cleanup():
    text = SCRIPT.read_text()
    assert "PHASE8_BFS_${SAFE_ID}" in text
    assert "REVOKE CURRENT GRANTS" in text
    assert "DROP TABLE ${DATABASE}.${SCHEMA}.${OUTPUT_TABLE}" in text
    assert "trap cleanup EXIT" in text

