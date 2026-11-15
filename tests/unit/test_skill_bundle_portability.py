"""A skill tree must work after installation without the repository's infra."""

import shutil
from pathlib import Path

from edgar_warehouse import bundle, cli


def test_skill_commands_and_links_resolve_without_checkout(tmp_path):
    source = Path(__file__).resolve().parents[2] / "skills"
    installed = tmp_path / "installed" / "skills"
    shutil.copytree(source, installed)

    assert bundle.unresolved(cli.build_parser(), installed) == []
