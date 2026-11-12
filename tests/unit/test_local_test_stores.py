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


def test_a_gone_owner_checkout_is_adopted(tmp_path):
    gone = tmp_path / "gone"
    gone.mkdir()
    first = local.LocalStores(tmp_path, gone)
    with first.locked("same"):
        first.identity("same", create=True)
    gone.rmdir()
    second_root = tmp_path / "second"
    second_root.mkdir()
    adopted = local.LocalStores(tmp_path, second_root).identity("same")
    assert adopted["owner"] == str(second_root.resolve())


def test_another_worktree_cannot_adopt_an_environment(tmp_path):
    (tmp_path / "first").mkdir()
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


def test_new_environments_default_to_five_and_an_unlisted_selection_keeps_silver(tmp_path):
    stores = local.LocalStores(tmp_path, tmp_path)
    identity = stores.identity("one", create=True)
    assert set(stores.stores("one")) == {"mdm", "rdm", "rules", "bookkeeping", "change_journal"}
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


def test_the_store_name_comes_from_the_argument_then_the_configuration_then_one_default():
    assert local.server_name("mine", {local.SERVER_ENV: "configured"}) == "mine"
    assert local.server_name(None, {local.SERVER_ENV: "configured"}) == "configured"
    assert local.server_name(None, {}) == local.DEFAULT_SERVER == "local-test-server"
    assert local.server_name(None, {local.SERVER_ENV: ""}) == "local-test-server"


def test_no_other_store_name_is_built_into_the_script():
    names = [line for line in PATH.read_text().splitlines()
             if "company-on" in line or "source-by-source" in line]
    assert names == []


def test_a_new_server_starts_with_the_load_settings(tmp_path, monkeypatch):
    stores = local.LocalStores(tmp_path, tmp_path)
    calls = []
    monkeypatch.setattr(stores, "resource", lambda *a: None)
    monkeypatch.setattr(stores, "docker", lambda *a: calls.append(a))
    monkeypatch.setattr(stores, "engine", lambda *a: (_ for _ in ()).throw(RuntimeError("stop after docker run")))
    monkeypatch.setattr(local.time, "monotonic", iter([0, 99]).__next__)
    with pytest.raises(RuntimeError):
        stores.start("settings")
    run = next(call for call in calls if call[0] == "run")
    assert run[-len(local.SERVER_SETTINGS):] == local.SERVER_SETTINGS
    assert "work_mem=256MB" in run


def _git(folder, *args):
    import subprocess
    return subprocess.run(["git", "-C", str(folder), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def test_a_checkout_behind_origin_main_says_by_how_many_commits(tmp_path):
    _git(tmp_path, "init", "-q")
    for name in ("one", "two", "three"):
        (tmp_path / name).write_text(name)
        _git(tmp_path, "add", name)
        _git(tmp_path, "commit", "-q", "-m", name)
    newest = _git(tmp_path, "rev-parse", "HEAD")
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", newest)
    assert local.commits_behind(tmp_path) == 0

    _git(tmp_path, "reset", "-q", "--hard", "HEAD~2")
    assert local.commits_behind(tmp_path) == 2


def test_a_folder_git_cannot_describe_has_no_commit_count(tmp_path):
    assert local.commits_behind(tmp_path) is None


def test_a_failure_shows_its_text_only_when_the_text_is_this_scripts_own_or_the_engines_refusal():
    class Blocked(ValueError):
        pass

    assert local.error_text(ValueError("Environment is stopped")) == "Environment is stopped"
    assert local.error_text(RuntimeError("did not become ready")) == "did not become ready"
    assert local.error_text(Blocked("Migration 7 is newer than this code")) == "Blocked: Migration 7 is newer than this code"
    assert local.error_text(KeyError("password=invented")) == "KeyError"


def test_bookkeeping_owner_uses_the_runtime_url_key(tmp_path, monkeypatch):
    stores = local.LocalStores(tmp_path, tmp_path)
    stores.identity("one", create=True)

    class Address:
        def render_as_string(self, hide_password=False):
            return "postgresql://invented@127.0.0.1/invented"

    monkeypatch.setattr(stores, "url", lambda *a, **k: Address())
    stores.connections("one")
    worker = (stores.folder("one") / "worker.env").read_text()
    connection = (stores.folder("one") / "connection.env").read_text()

    def exported(text):
        return [line.split("=", 1)[0][7:] for line in text.splitlines() if line.startswith("export ")]

    assert "BOOKKEEPING_DATABASE_URL" in exported(worker)
    assert "BOOKKEEPING_DATABASE_URL" in exported(connection)
    assert "BOOKKEEPING_MIGRATION_DATABASE_URL" not in exported(worker)
    assert "BOOKKEEPING_MIGRATION_DATABASE_URL" not in exported(connection)
    assert "BOOKKEEPING_MIGRATION_DATABASE_URL" in worker
    assert "BOOKKEEPING_MIGRATION_DATABASE_URL" in connection
    assert "BOOKKEEPING_ADMIN_DATABASE_URL" not in exported(worker)
    assert "BOOKKEEPING_ADMIN_DATABASE_URL" not in exported(connection)
    assert "BOOKKEEPING_ADMIN_DATABASE_URL" in worker
    assert "BOOKKEEPING_ADMIN_DATABASE_URL" in connection
    assert "BOOKKEEPING_MANIFEST_ROOT" in exported(worker)
    assert "BOOKKEEPING_MANIFEST_ROOT" in exported(connection)


def test_bookkeeping_cli_does_not_name_a_migration_url():
    text = (PATH.parents[2] / "edgar_warehouse/bookkeeping/clean/cli.py").read_text()
    assert "BOOKKEEPING_MIGRATION_DATABASE_URL" not in text
    assert "get_engine()" in text


def test_provision_script_uses_the_bookkeeping_url_key():
    text = (PATH.parents[1] / "scripts/provision-clean-bookkeeping.py").read_text()
    assert "BOOKKEEPING_ADMIN_DATABASE_URL" not in text
    assert 'os.environ["BOOKKEEPING_DATABASE_URL"]' in text
    assert 'set(database="postgres")' in text
    shell = (PATH.parents[1] / "scripts/provision-local-postgres-stores.sh").read_text()
    assert "BOOKKEEPING_ADMIN_DATABASE_URL" not in shell
    skills = PATH.parents[2] / "skills"
    named = [str(path.relative_to(skills)) for path in skills.rglob("*.md")
             if "BOOKKEEPING_ADMIN_DATABASE_URL" in path.read_text()]
    assert named == []
