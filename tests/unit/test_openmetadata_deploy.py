"""The OpenMetadata deploy script refuses a compose file that maps the wrong port or mounts a checkout's path."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("openmetadata_deploy", ROOT / "skills/openmetadata-deploy/scripts/openmetadata.py")
om = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(om)


def document(port="8587", volumes=()):
    return {"services": {"openmetadata-server": {"ports": [{"published": port, "target": 8585}], "volumes": list(volumes)},
                         "postgresql": {"volumes": [{"type": "volume", "source": "db-data"}]}}}


def test_a_current_compose_document_has_no_problem():
    assert om.problems_in(document()) == []


def test_a_stale_port_is_named():
    (found,) = om.problems_in(document(port="8585"))
    assert "8585" in found and "stale" in found


def test_a_mounted_path_of_a_checkout_is_named():
    bind = {"type": "bind", "source": "/work/checkout/infra/openmetadata/seed.json"}
    (found,) = om.problems_in(document(volumes=[bind]))
    assert "openmetadata-server mounts a host path" in found


def test_a_server_with_no_published_port_is_a_problem():
    config = document()
    config["services"]["openmetadata-server"]["ports"] = []
    assert om.problems_in(config)


def test_the_repository_compose_file_mounts_no_path_and_publishes_the_port_by_default():
    text = (ROOT / "infra/openmetadata/docker-compose.yml").read_text()
    assert "OPENMETADATA_HOST_PORT:-8587" in text and "./" not in text.split("openmetadata-server:")[1].split("healthcheck")[0]
