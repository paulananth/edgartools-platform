"""A fresh hosted instance takes its logins from the stores folder's duty files, so no password changes; every file moves to the
new instance and the owner file takes the administrator's new password. Every name, address and password here is invented."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "skills/data-platform/scripts"))

from provision_hosted_store import (DATABASES, DUTIES, Refused, ddl_free, duty_file, ensure_files, logins, main, provision,
                                    read_url, read_urls, rewrite)

OLD = "old.invalid"


def _folder(tmp_path, loader="l-invented", governance="g-invented", reader=None):
    files = {"owner.env": f"postgresql://admin:a-old@{OLD}:5432",
             "worker.env": f"postgresql://edgar_loader:{loader}@{OLD}:5432",
             "governance.env": f"postgresql://governance:{governance}@{OLD}:5432"}
    if reader:
        files["reader.env"] = f"postgresql://ops_reader:{reader}@{OLD}:5432"
    for name, url in files.items():
        (tmp_path / name).write_text(duty_file(url))
    return tmp_path


def test_each_duty_file_names_its_login_with_the_password_it_holds(tmp_path):
    held = logins(_folder(tmp_path, reader="r-invented"), "admin")
    assert held["edgar_loader"] == ("l-invented", set(DATABASES))
    assert held["governance"] == ("g-invented", {"data", "control"})
    assert held["ops_reader"] == ("r-invented", set(DATABASES))
    assert "admin" not in held


def test_a_file_that_names_another_login_than_its_duty_is_refused(tmp_path):
    folder = _folder(tmp_path)
    (folder / "worker.env").write_text(duty_file(f"postgresql://mdm_runtime:x@{OLD}:5432"))
    with pytest.raises(Refused, match="worker.env names mdm_runtime, and the worker duty is edgar_loader"):
        logins(folder, "admin")


def test_a_missing_file_is_a_missing_duty_not_an_error(tmp_path):
    folder = _folder(tmp_path)
    (folder / "governance.env").unlink()
    assert set(logins(folder, "admin")) == {"edgar_loader"}


def test_every_file_moves_to_the_new_instance_and_only_the_administrator_takes_a_new_password(tmp_path):
    folder = _folder(tmp_path, reader="r-invented")
    assert rewrite(folder, "new.invalid", 5432, "admin", "a-new") == 8  # two URLs a file
    assert read_urls(folder, "owner.env") == {"DATA_URL": "postgresql://admin:a-new@new.invalid:5432/data",
                                               "CONTROL_URL": "postgresql://admin:a-new@new.invalid:5432/control"}
    assert read_url(folder, "worker.env") == "postgresql://edgar_loader:l-invented@new.invalid:5432/data"
    assert OLD not in "".join((folder / name).read_text() for name in ("owner.env", "worker.env", "governance.env", "reader.env"))
    assert (folder / "worker.env").stat().st_mode & 0o777 == 0o600
    assert (folder / "worker.env").read_text().startswith("unset DATA_URL CONTROL_URL\n")


def test_missing_duty_files_are_made_private_with_a_new_password_and_none_is_replaced(tmp_path):
    (tmp_path / "worker.env").write_text(duty_file("postgresql://edgar_loader:keep-invented@h:5432"))
    made = ensure_files(tmp_path, "new.invalid", 5432, {"user": "admin", "password": "a-new"})
    assert made == ["owner.env", "governance.env", "reader.env"]
    assert read_url(tmp_path, "worker.env").endswith("keep-invented@h:5432/data")  # an existing file is left as it is
    reader = read_url(tmp_path, "reader.env")
    assert reader.startswith("postgresql://ops_reader:") and reader.endswith("@new.invalid:5432/data") and "a-new" not in reader
    assert (tmp_path / "reader.env").stat().st_mode & 0o777 == 0o600
    assert ensure_files(tmp_path, "new.invalid", 5432, {"user": "admin", "password": "a-new"}) == []


class _Server:
    """An instance with no roles and no databases; `owner` makes every database exist, owned by that role."""

    def __init__(self, owner=None, logins=()):
        self.owner, self.logins, self.last, self.statements = owner, set(logins), "", []

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement, *args):
        self.last = str(statement)
        self.statements.append(self.last)
        self.args = args

    def fetchone(self):
        if self.owner and "pg_database" in self.last:
            return (self.owner,)
        if "rolcanlogin" in self.last and self.args and self.args[0][0] in self.logins:
            return (True,)
        return None


HELD = {"edgar_loader": ("l-invented", set(DATABASES)), "governance": ("g-invented", set(DATABASES)),
        "ops_reader": ("r-invented", set(DATABASES))}


def test_the_logins_groups_and_memberships_of_each_duty_are_made():
    steps = provision(_Server(), HELD, "admin", confirm=False)
    assert {"create login edgar_loader", "create login governance", "create login ops_reader"} <= set(steps)
    assert "put edgar_loader in silver_runtime" in steps and "put governance in mdm_governance" in steps
    assert "put governance in rules_governance" in steps and "put rules_governance in rules_agent" in steps
    assert "give ops_reader pg_monitor: sessions, locks and statistics, no table" in steps
    assert "data: connect and temporary tables for edgar_loader, governance" in steps
    assert "control: connect and temporary tables for edgar_loader, governance" in steps
    assert "control: connect for ops_reader" in steps
    assert DATABASES == ("data", "control")


def test_a_governance_role_of_an_earlier_layout_stops_being_a_login_and_stays_a_group():
    server = _Server(logins={"mdm_governance"})
    steps = provision(server, HELD, "admin", confirm=True)
    assert "mdm_governance stops being a login and stays a group" in steps
    assert any("NOLOGIN" in s and "ALTER ROLE" in s for s in server.statements)


def test_a_database_another_role_owns_is_never_adopted():
    with pytest.raises(Refused, match="data exists, owned by someone_else"):
        provision(_Server(owner="someone_else"), HELD, "admin", confirm=False)


def test_a_login_connects_and_uses_temporary_tables_on_its_databases_and_public_gets_nothing():
    server = _Server(owner="admin")
    provision(server, HELD, "admin", confirm=True)
    assert any("REVOKE ALL ON DATABASE" in s for s in server.statements)
    grants = [s for s in server.statements if "GRANT CONNECT, TEMPORARY" in s]
    assert any("edgar_loader" in s for s in grants) and not any("ops_reader" in s for s in grants)


def test_a_url_the_parser_refuses_prints_its_class_never_its_password(tmp_path, monkeypatch, capsys):
    stores = _folder(tmp_path)
    (stores / "worker.env").write_text("export DATA_URL='postgresql://edgar_loader:p-invented＃x@old.invalid:5432/data'\n"
                                       "export CONTROL_URL='postgresql://edgar_loader:p-invented＃x@old.invalid:5432/control'\n")
    (tmp_path / "services").write_text("[invented]\nhost=new.invalid\nport=5432\nuser=admin\n")
    (tmp_path / "pgpass").write_text("new.invalid:5432:*:admin:a-new\n")
    monkeypatch.setenv("PGSERVICEFILE", str(tmp_path / "services"))
    monkeypatch.setenv("PGPASSFILE", str(tmp_path / "pgpass"))
    assert main(["--service", "invented", "--stores", str(stores)]) == 1
    printed = capsys.readouterr()
    assert printed.err.strip() == "failed: ValueError" and "p-invented" not in printed.out + printed.err


def test_a_login_holding_a_schema_create_or_an_object_is_refused():
    class Database:
        def __init__(self, creates, owned, privileged=0):
            self.rows = [creates, owned, privileged]

        def cursor(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, *args):
            pass

        def fetchone(self):
            return (self.rows.pop(0),)

    assert ddl_free(Database("", 0), "edgar_loader", "silver") is None
    with pytest.raises(Refused, match="edgar_loader can create in silver: public"):
        ddl_free(Database("public", 0), "edgar_loader", "silver")
    with pytest.raises(Refused, match="edgar_loader owns 3 objects in silver"):
        ddl_free(Database("", 3), "edgar_loader", "silver")
    with pytest.raises(Refused, match="edgar_loader is a superuser, or can create databases or roles"):
        ddl_free(Database("", 0, 1), "edgar_loader", "silver")


@pytest.mark.parametrize("text, refusal", [
    ("export DATA_URL='postgresql://edgar_loader:x@h:5432/data'\n", "must hold DATA_URL and CONTROL_URL"),
    (duty_file("postgresql://edgar_loader:x@h:5432").replace("/control", "/data"), "CONTROL_URL must name the control database"),
    (duty_file("postgresql://edgar_loader:x@h:5432").replace("edgar_loader:x@h:5432/control", "edgar_loader:y@h:5432/control"),
     "two logins"),
])
def test_a_duty_file_holds_one_login_as_two_urls_one_a_database(tmp_path, text, refusal):
    (tmp_path / "worker.env").write_text(text)
    with pytest.raises(Refused, match=refusal):
        read_url(tmp_path, "worker.env")
