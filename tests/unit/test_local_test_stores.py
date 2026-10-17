"""Ownership and failed-copy checks for persistent local test stores."""
import importlib.util
import json
from pathlib import Path

import pytest


PATH = Path(__file__).resolve().parents[2] / "infra/scripts/local-test-stores.py"
spec = importlib.util.spec_from_file_location("local_test_stores", PATH)
local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local)


@pytest.mark.parametrize("name", ["../other", "Other", "-x", "", "a/b", "a" * 49])
def test_environment_names_cannot_escape_their_folder(tmp_path, name):
    with pytest.raises(ValueError):
        local.LocalStores(tmp_path, tmp_path).folder(name)


def test_another_worktree_cannot_adopt_an_environment(tmp_path):
    first = local.LocalStores(tmp_path, tmp_path / "first")
    with first.locked("same"):
        saved = first.identity("same", create=True)
    other = local.LocalStores(tmp_path, tmp_path / "second")
    with pytest.raises(ValueError, match="another worktree"):
        other.identity("same", create=True)
    assert first.identity("same") == saved
    assert (first.folder("same") / "identity.json").stat().st_mode & 0o777 == 0o600


def test_another_agents_resource_is_never_stopped(tmp_path, monkeypatch):
    stores = local.LocalStores(tmp_path, tmp_path)
    with stores.locked("one"):
        stores.identity("one", create=True)
    monkeypatch.setattr(stores, "resource", lambda *a: {"Config": {"Labels": {local.LABEL: "another"}}})
    monkeypatch.setattr(stores, "docker", lambda *a: pytest.fail("must not change Docker"))
    with pytest.raises(ValueError, match="ownership differs"):
        stores.stop("one")


def test_corrupt_backup_is_refused_before_creating_a_copy(tmp_path, monkeypatch):
    stores = local.LocalStores(tmp_path / "stores", tmp_path)
    snapshot = tmp_path / "backup"
    snapshot.mkdir()
    (snapshot / "manifest.json").write_text(json.dumps({"files": {d + ".dump": "wrong" for d in local.STORES}}))
    for name in local.STORES:
        (snapshot / (name + ".dump")).write_bytes(b"invented corrupt backup")
    monkeypatch.setattr(stores, "start", lambda *a, **k: pytest.fail("must not create a target"))
    with pytest.raises(ValueError, match="checksum"):
        stores.restore("new", snapshot)


def test_failed_restore_keeps_the_previous_baseline(tmp_path, monkeypatch):
    stores = local.LocalStores(tmp_path, tmp_path)
    (tmp_path / "baseline").write_text("previous snapshot\n")
    monkeypatch.setattr(stores, "backup", lambda name: tmp_path / "candidate")
    def fail(*args):
        raise ValueError("restore proof failed")
    monkeypatch.setattr(stores, "restore", fail)
    with pytest.raises(ValueError, match="restore proof"):
        stores.publish_baseline("one")
    assert (tmp_path / "baseline").read_text() == "previous snapshot\n"


def test_new_environments_default_to_five_and_legacy_backups_keep_silver(tmp_path):
    stores = local.LocalStores(tmp_path, tmp_path)
    identity = stores.identity("one", create=True)
    assert set(stores.stores("one")) == {"mdm", "rdm", "rules", "bookkeeping_clean", "change_journal_clean"}
    identity.pop("stores")
    local.private_write(stores.folder("one") / "identity.json", json.dumps(identity))
    assert "silver" in stores.stores("one")


@pytest.mark.parametrize("selection", [[], ["mdm"], list(local.STORES) + ["other"], list(local.STORES) + ["mdm"]])
def test_invalid_store_selection_is_refused(tmp_path, selection):
    stores = local.LocalStores(tmp_path, tmp_path)
    identity = stores.identity("one", create=True)
    local.private_write(stores.folder("one") / "identity.json", json.dumps({**identity, "stores": selection}))
    with pytest.raises(ValueError, match="selection is invalid"):
        stores.stores("one")
