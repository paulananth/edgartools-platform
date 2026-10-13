"""The images carry `rules/`: production loads its MDM rules from there."""

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


def test_every_path_an_image_copies_exists():
    # Both images copied `edgar/` long after #766 deleted it, so neither could
    # build (Codex's go-live review, 2026-10-12); CI builds no image to notice.
    for dockerfile in sorted(ROOT.glob("Dockerfile*")):
        for line in dockerfile.read_text().splitlines():
            words = line.split()
            if not words or words[0] != "COPY" or any(w.startswith("--from") for w in words):
                continue
            for source in [w for w in words[1:-1] if not w.startswith("--")]:
                assert (ROOT / source).exists(), f"{dockerfile.name} copies {source}, which does not exist"
