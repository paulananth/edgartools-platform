"""A process opens the Change Journal once: each new engine is a new database session, and a persons bundle opened
fifteen on a hosted store."""
from edgar_warehouse.mdm import changed_files


def test_the_journal_is_opened_once_for_a_database(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_URL", f"sqlite:///{tmp_path}/one.db")
    first = changed_files.journal()
    assert changed_files.journal() is first


def test_another_database_is_another_journal(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_URL", f"sqlite:///{tmp_path}/one.db")
    first = changed_files.journal()
    monkeypatch.setenv("DB_URL", f"sqlite:///{tmp_path}/two.db")
    assert changed_files.journal() is not first
