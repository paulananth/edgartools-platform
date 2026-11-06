"""Every package reaches a wheel, or is named here with its reason. Reads files only."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NOT_SHIPPED = {"infrastructure", "serving"}  # An empty package, and dashboard helpers no bundle command reads.


def bundled() -> set:
    names = set()
    for project in (ROOT / "packages").glob("*/pyproject.toml"):
        wheel = tomllib.loads(project.read_text())["tool"]["hatch"]["build"]["targets"]["wheel"]
        for source in wheel.get("force-include", {}):
            parts = Path(source).parts
            if "edgar_warehouse" in parts[:-1]:
                names.add(parts[parts.index("edgar_warehouse") + 1])
    return names


def test_every_package_is_in_a_bundle_wheel():
    packages = {path.parent.name for path in (ROOT / "edgar_warehouse").glob("*/__init__.py")}
    assert packages - bundled() - NOT_SHIPPED == set()
