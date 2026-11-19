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
    assert reset.DATABASES == ("mdm", "rdm", "rules", "bookkeeping", "change_journal", "silver")


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
