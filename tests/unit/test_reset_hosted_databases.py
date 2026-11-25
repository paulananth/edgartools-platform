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


def test_a_reset_names_only_the_data_and_control_databases():
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
    monkeypatch.setenv("DATA_URL", "postgresql://invented@h/postgres")
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
    (stores / "worker.env").write_text(f"export DATA_URL='postgresql://invented/db'\nexport BOOKKEEPING_MANIFEST_ROOT='file://{root}'\n")
    assert reset.clear_run_files(stores) == root / "load"
    assert not (root / "load").exists() and (root / "extracts" / "abc").is_dir()
    assert reset.clear_run_files(stores) is None  # nothing left: a second reset deletes nothing


def test_a_stores_folder_that_names_no_run_files_folder_deletes_nothing(tmp_path):
    (tmp_path / "worker.env").write_text("export DATA_URL='postgresql://invented/db'\n")
    assert reset.clear_run_files(tmp_path) is None


def test_reset_journey_reports_and_force_drops_only_idle_extension_workers(monkeypatch, tmp_path, capsys):
    class Result:
        def __init__(self, row=None, rows=()):
            self.row = row
            self.rows = list(rows)

        def first(self):
            return self.row

        def all(self):
            return self.rows

    class Connection:
        def __init__(self, sessions):
            self.sessions = sessions
            self.statements = []

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, statement, params=None):
            sql = str(statement)
            if "FROM pg_database" in sql:
                database = params["n"]
                size = "25 GB" if database == "data" else "469 MB"
                return Result(row=("admin", ["app_runtime=c/admin"], size))
            if "FROM pg_stat_activity" in sql:
                return Result(rows=self.sessions)
            raise AssertionError(f"unexpected query: {sql}")

        def exec_driver_sql(self, statement):
            self.statements.append(statement)

    class Engine:
        def __init__(self, sessions):
            self.connection = Connection(sessions)
            self.dialect = type("Dialect", (), {
                "identifier_preparer": type("Preparer", (), {"quote": staticmethod(lambda name: f'"{name}"')})()
            })()
            self.disposed = False

        def connect(self):
            return self.connection

        def dispose(self):
            self.disposed = True

    idle_extension_workers = [
        ("data", "pg base extension worker", None, None),
        ("data", "pg base extension worker", None, None),
    ]
    active_client = ("control", "client backend", "idle in transaction", object())
    sessions = idle_extension_workers.copy()
    engines = []

    def engine_factory(*_args, **_kwargs):
        engine = Engine(sessions.copy())
        engines.append(engine)
        return engine

    import types
    import sys

    monkeypatch.setitem(sys.modules, "edgar_warehouse.database_connections", types.SimpleNamespace(
        instance_url=lambda: "postgresql://not-a-real-address"
    ))
    monkeypatch.setattr(reset.sa, "create_engine", engine_factory)
    monkeypatch.setenv("STORES_FOLDER", str(tmp_path))
    monkeypatch.setattr(reset.sys, "argv", ["reset-hosted-databases.py"])

    # The dry run identifies the idle server workers but does not disconnect or mutate anything.
    assert reset.main() == 0
    dry_run = capsys.readouterr().out
    assert "data: 2 idle extension worker session(s)" in dry_run
    assert "Nothing dropped." in dry_run
    assert engines[-1].connection.statements == []
    assert not (tmp_path / "reinit-approvals.log").exists()

    # The approved reset records those workers and relies on the database drop's FORCE behavior.
    monkeypatch.setattr(reset.sys, "argv", ["reset-hosted-databases.py", "--words", "operator reset words"])
    assert reset.main() == 0
    reset_sql = engines[-1].connection.statements
    assert 'DROP DATABASE IF EXISTS "data" WITH (FORCE)' in reset_sql
    assert 'CREATE DATABASE "data" OWNER "admin"' in reset_sql
    assert 'GRANT CONNECT ON DATABASE "data" TO "app_runtime"' in reset_sql
    assert 'DROP DATABASE IF EXISTS "control" WITH (FORCE)' in reset_sql
    approvals = [reset.json.loads(line) for line in (tmp_path / "reinit-approvals.log").read_text().splitlines()]
    assert approvals[-1]["sessions_to_disconnect"] == {"data": 2}

    before = len(approvals)
    blockers = [
        active_client,
        ("control", "pg base extension worker", None, object()),
        ("control", "pg base extension worker", "active", None),
    ]
    for blocker in blockers:
        sessions[:] = idle_extension_workers + [blocker]
        assert reset.main() == 3
        assert engines[-1].connection.statements == []
        assert len((tmp_path / "reinit-approvals.log").read_text().splitlines()) == before
    assert engines[-1].disposed
