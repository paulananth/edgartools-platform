"""The images carry `rules/`: production loads its Clean MDM rules from there."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_both_images_copy_the_rules_folder():
    for dockerfile in ("Dockerfile", "Dockerfile.mdm-neo4j"):
        assert "COPY rules /app/rules\n" in (ROOT / dockerfile).read_text(), dockerfile


def test_the_build_context_keeps_the_rules_folder():
    ignored = {
        line.strip().rstrip("/")
        for line in (ROOT / ".dockerignore").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert not ignored & {"rules", "rules/*", "rules/**"}


def test_the_rules_package_finds_the_folder_the_image_copies():
    from edgar_warehouse.rules import files

    assert files.ROOT == ROOT / "rules"
    assert (files.ROOT / "merge" / "policy.yaml").is_file()
