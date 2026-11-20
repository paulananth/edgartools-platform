"""The hosted reset puts back each database's owner and grants exactly as read from its access list."""
import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "reset_hosted_databases", Path(__file__).parents[2] / "infra" / "scripts" / "reset-hosted-databases.py")
reset = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reset)


def test_an_access_list_becomes_the_grants_other_than_the_owners_own():
    acl = ["=T/admin", "admin=CTc/admin", "app_runtime=c/admin", "app_reader=c/admin"]
    assert reset.grants(acl, "admin") == [("PUBLIC", "TEMPORARY"), ("app_runtime", "CONNECT"), ("app_reader", "CONNECT")]


def test_a_database_with_no_access_list_has_no_grants():
    assert reset.grants(None, "admin") == []
    assert reset.grants([], "admin") == []


def test_every_database_the_platform_holds_is_named():
    assert reset.DATABASES == ("data", "control")


def test_a_sign_off_keeps_the_words_the_time_and_what_was_dropped_in_a_private_file(tmp_path):
    log = tmp_path / "reinit-approvals.log"
    reset.sign_off(log, "yes drop them", {"mdm": "165 MB"})
    reset.sign_off(log, "again", {"mdm": "8 kB"})
    lines = [reset.json.loads(line) for line in log.read_text().splitlines()]
    assert [(l["words"], l["dropped"]) for l in lines] == [("yes drop them", {"mdm": "165 MB"}), ("again", {"mdm": "8 kB"})]
    assert lines[0]["at"].endswith(" ET") and log.stat().st_mode & 0o777 == 0o600


def test_the_approvals_log_is_in_the_stores_folder(monkeypatch, tmp_path):
    monkeypatch.setenv("STORES_FOLDER", str(tmp_path))
    assert reset.approvals_log() == tmp_path / "reinit-approvals.log"


def test_a_drop_without_words_is_refused_before_any_connection(monkeypatch, capsys):
    monkeypatch.setattr(reset.sys, "argv", ["reset", "--words", " "])
    monkeypatch.setenv("DB_URL", "postgresql://invented@h/postgres")
    monkeypatch.setattr(reset.sa, "create_engine", lambda *a, **k: (_ for _ in ()).throw(AssertionError("connected")))
    assert reset.main() == 2
    assert "exact approval" in capsys.readouterr().err


def test_a_reset_deletes_the_run_files_of_the_stores_it_drops_and_keeps_the_extracts(tmp_path):
    """No store refers to them once Bookkeeping is dropped: kept, they only fill the disk (185 GB once)."""
    root = tmp_path / "manifests"
    (root / "load" / "invented.source" / "mastering" / "2026-01-01T000000Z" / "bundle-001").mkdir(parents=True)
    (root / "load" / "invented.source" / "mastering" / "2026-01-01T000000Z" / "bundle-001" / "documents.json").write_text("[]")
    (root / "extracts" / "abc").mkdir(parents=True)
    stores = tmp_path / "stores"
    stores.mkdir()
    (stores / "worker.env").write_text(f"export DB_URL='postgresql://invented/db'\nexport BOOKKEEPING_MANIFEST_ROOT='file://{root}'\n")
    assert reset.clear_run_files(stores) == root / "load"
    assert not (root / "load").exists() and (root / "extracts" / "abc").is_dir()
    assert reset.clear_run_files(stores) is None  # nothing left: a second reset deletes nothing


def test_a_stores_folder_that_names_no_run_files_folder_deletes_nothing(tmp_path):
    (tmp_path / "worker.env").write_text("export DB_URL='postgresql://invented/db'\n")
    assert reset.clear_run_files(tmp_path) is None
