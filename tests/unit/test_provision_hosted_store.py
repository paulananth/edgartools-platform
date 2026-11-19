"""A fresh hosted instance takes its logins from the stores folder's own URLs, so no password changes; every URL moves
to the new instance and the administrator's takes its new password.
Every name, address and password here is invented."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "skills/data-platform/scripts"))

from provision_hosted_store import Refused, ensure_reader, logins, main, provision, read_urls, retire, rewrite

OLD = "old.invalid"


OTHERS = [f"export {name.upper()}_DATABASE_URL='postgresql://{name}_runtime:{name[0]}-invented@{OLD}:5432/{name}'"
          for name in ("rdm", "rules", "change_journal", "silver")]


def _folder(tmp_path, worker_password="w-invented", others=OTHERS):
    files = {
        "owner.env": [f"export DB_URL='postgresql://admin:a-old@{OLD}:5432'"],
        "worker.env": [f"export MDM_DATABASE_URL='postgresql://mdm_runtime:m-invented@{OLD}:5432/mdm'",
                       f"export BOOKKEEPING_DATABASE_URL='postgresql://bookkeeping_runtime:{worker_password}@{OLD}:5432/bookkeeping'",
                       "export BOOKKEEPING_MANIFEST_ROOT=file:///invented/manifests", *others],
        "governance.env": [f"export MDM_REGISTRATION_DATABASE_URL='postgresql://mdm_governance:g-invented@{OLD}:5432/mdm'",
                           f"export BOOKKEEPING_DATABASE_URL='postgresql://bookkeeping_runtime:w-invented@{OLD}:5432/bookkeeping'"],
    }
    for name, lines in files.items():
        (tmp_path / name).write_text("unset DB_URL\n" + "\n".join(lines) + "\n")
    return tmp_path


def test_each_login_keeps_the_password_and_databases_its_urls_hold(tmp_path):
    held = logins(read_urls(_folder(tmp_path)), "admin")
    assert held["mdm_runtime"] == ("m-invented", {"mdm"})
    assert held["bookkeeping_runtime"] == ("w-invented", {"bookkeeping"})
    assert held["mdm_governance"] == ("g-invented", {"mdm"})
    assert held["change_journal_runtime"] == ("c-invented", {"change_journal"})
    assert "admin" not in held and len(held) == 7


def test_a_store_no_login_connects_to_is_refused(tmp_path):
    with pytest.raises(Refused, match="names a login for silver"):
        logins(read_urls(_folder(tmp_path, others=OTHERS[:3])), "admin")


def test_two_urls_giving_one_login_two_passwords_are_refused(tmp_path):
    with pytest.raises(ValueError, match="bookkeeping_runtime another password"):
        logins(read_urls(_folder(tmp_path, worker_password="other")), "admin")


def test_every_url_moves_to_the_new_instance_and_only_the_administrator_takes_a_new_password(tmp_path):
    folder = _folder(tmp_path)
    assert rewrite(folder, "new.invalid", 5432, "admin", "a-new") == 9  # reader.env absent: skipped
    urls = read_urls(folder)
    assert urls["owner.env"]["DB_URL"] == "postgresql://admin:a-new@new.invalid:5432"
    assert urls["worker.env"]["MDM_DATABASE_URL"] == "postgresql://mdm_runtime:m-invented@new.invalid:5432/mdm"
    text = (folder / "worker.env").read_text()
    assert OLD not in text and "BOOKKEEPING_MANIFEST_ROOT=file:///invented/manifests" in text
    assert (folder / "owner.env").read_text().startswith("unset DB_URL\n")
    assert (folder / "worker.env").stat().st_mode & 0o777 == 0o600


class _EmptyServer:
    """An instance with no roles and no databases; `owner` makes every database exist, owned by that role."""

    def __init__(self, owner=None):
        self.owner, self.last, self.statements = owner, "", []

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement, *args):
        self.last = str(statement)
        self.statements.append(self.last)

    def fetchone(self):
        return (self.owner,) if self.owner and "pg_database" in self.last else None


HELD = {"rules_agent": ("r-invented", {"rules"}), "rules_governance": ("g-invented", {"rules"}),
        "bookkeeping_runtime": ("w-invented", {"bookkeeping"})}


def test_a_group_that_is_also_a_login_is_made_once_as_the_login():
    steps = provision(_EmptyServer(), HELD, "admin", confirm=False)
    assert "create login rules_agent" in steps and "create group rules_agent" not in steps
    assert "create group bookkeeping_control" in steps and "put rules_governance in rules_agent" in steps


def test_a_group_member_no_url_names_is_refused_before_anything_is_made():
    held = {name: value for name, value in HELD.items() if name != "rules_governance"}
    with pytest.raises(Refused, match="no URL names rules_governance"):
        provision(_EmptyServer(), held, "admin", confirm=False)


def test_a_database_another_role_owns_is_never_adopted():
    with pytest.raises(Refused, match="mdm exists, owned by someone_else"):
        provision(_EmptyServer(owner="someone_else"), HELD, "admin", confirm=False)
    assert "mdm: connect and temporary tables for " in " ".join(provision(_EmptyServer(owner="admin"), HELD, "admin", confirm=False))


def test_a_url_the_parser_refuses_prints_its_class_never_its_password(tmp_path, monkeypatch, capsys):
    stores = _folder(tmp_path)
    worker = stores / "worker.env"
    worker.write_text(worker.read_text() + f"export SILVER_DATABASE_URL='postgresql://silver_runtime:p-invented\uff03x@{OLD}/silver'\n")
    (tmp_path / "services").write_text("[invented]\nhost=new.invalid\nport=5432\nuser=admin\n")
    (tmp_path / "pgpass").write_text("new.invalid:5432:*:admin:a-new\n")
    monkeypatch.setenv("PGSERVICEFILE", str(tmp_path / "services"))
    monkeypatch.setenv("PGPASSFILE", str(tmp_path / "pgpass"))
    assert main(["--service", "invented", "--stores", str(stores)]) == 1
    printed = capsys.readouterr()
    assert printed.err.strip() == "failed: ValueError" and "p-invented" not in printed.out + printed.err


def test_a_login_may_connect_and_use_temporary_tables_on_its_database():
    """Revoking PUBLIC takes the default right to temporary tables too; the silver writer stages each load in one."""
    server = _EmptyServer(owner="admin")
    held = {**HELD, "silver_runtime": ("s-invented", {"silver"})}
    provision(server, held, "admin", confirm=True)
    grants = [statement for statement in server.statements if "GRANT CONNECT, TEMPORARY" in statement]
    assert any("silver_runtime" in statement for statement in grants)
    assert len(grants) == 4  # rules_agent, rules_governance, bookkeeping_runtime, silver_runtime


def test_the_diagnostic_login_reads_sessions_and_locks_and_connects_to_no_store():
    server = _EmptyServer(owner="admin")
    held = {**HELD, "ops_reader": ("o-invented", {"postgres"})}
    steps = provision(server, held, "admin", confirm=True)
    assert any(statement for statement in server.statements if "GRANT pg_monitor TO" in statement)
    assert "give ops_reader pg_monitor: sessions, locks and statistics, no table" in steps
    connects = [statement for statement in server.statements if "GRANT CONNECT, TEMPORARY" in statement]
    assert not any("ops_reader" in statement for statement in connects)  # no temporary tables, so no writing
    only_connect = [statement for statement in server.statements if "GRANT CONNECT ON DATABASE" in statement]
    assert sum("ops_reader" in statement for statement in only_connect) == 6  # it reads catalogs and statistics, no table


def test_reader_env_is_made_once_private_with_a_new_password_and_moves_with_the_other_urls(tmp_path):
    folder = _folder(tmp_path)
    assert read_urls(folder)["reader.env"] == {}  # absent is allowed
    assert ensure_reader(folder, "old.invalid", 5432) is True
    first = (folder / "reader.env").read_text()
    assert (folder / "reader.env").stat().st_mode & 0o777 == 0o600
    assert ensure_reader(folder, "other.invalid", 5432) is False and (folder / "reader.env").read_text() == first
    held = logins(read_urls(folder), "admin")
    assert held["ops_reader"][1] == {"postgres"}
    rewrite(folder, "new.invalid", 5432, "admin", "a-new")
    assert "new.invalid" in (folder / "reader.env").read_text() and "old.invalid" not in (folder / "reader.env").read_text()


RUNTIME = ("mdm_runtime", "rdm_runtime", "rules_agent", "bookkeeping_runtime", "change_journal_runtime", "silver_runtime")


def test_one_loader_login_is_a_member_of_every_runtime_role_and_holds_nothing_of_its_own():
    server = _EmptyServer(owner="admin")
    held = {"edgar_loader": ("l-invented", {"mdm", "rdm", "rules", "bookkeeping", "change_journal", "silver"}),
            "rules_governance": ("g-invented", {"rules"})}
    steps = provision(server, held, "admin", confirm=True)
    for role in RUNTIME:
        assert f"create group {role}" in steps and f"put edgar_loader in {role}" in steps
    grants = " ".join(server.statements)
    connects = [statement for statement in server.statements if "GRANT CONNECT, TEMPORARY" in statement]
    assert sum("edgar_loader" in statement for statement in connects) == 6  # one login reaches all six databases
    assert "ADMIN" not in grants and "CREATEDB" in grants  # NOCREATEDB NOCREATEROLE NOSUPERUSER on the login


def test_a_login_holding_a_schema_create_or_an_object_is_refused():
    from provision_hosted_store import ddl_free

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


def test_every_runtime_url_in_every_stores_file_becomes_the_loader_login_and_the_old_files_are_kept(tmp_path):
    from provision_hosted_store import use_loader

    folder = _folder(tmp_path)
    (folder / "worker.env").write_text("\n".join([
        f"export MDM_DATABASE_URL='postgresql://mdm_runtime:m-invented@{OLD}:5432/mdm'",
        f"export SILVER_DATABASE_URL='postgresql://silver_runtime:s-invented@{OLD}:5432/silver'",
        "export BOOKKEEPING_MANIFEST_ROOT=file:///invented/manifests", ""]))
    assert use_loader(folder) == 3  # worker.env 2 and governance.env's runtime URL; owner.env names no runtime login
    found = read_urls(folder)
    users = {name: {url.split("//")[1].split(":")[0] for url in urls.values()} for name, urls in found.items()}
    assert users["worker.env"] == {"edgar_loader"}
    assert users["owner.env"] == {"admin"}  # the administrator's URL stays and is no runtime URL
    assert users["governance.env"] == {"mdm_governance", "edgar_loader"}  # so does the governance login
    passwords = {url.split("//")[1].split(":")[1].split("@")[0] for urls in found.values() for url in urls.values()
                 if url.split("//")[1].startswith("edgar_loader")}
    assert len(passwords) == 1 and "m-invented" not in passwords  # one login, one password, in every file
    assert found["worker.env"]["SILVER_DATABASE_URL"].endswith("/silver") and "BOOKKEEPING_MANIFEST_ROOT" in (folder / "worker.env").read_text()
    for name in ("worker.env", "governance.env"):
        assert (folder / f"{name}.before-loader").stat().st_mode & 0o777 == 0o600
    assert "m-invented" in (folder / "worker.env.before-loader").read_text()
    assert use_loader(folder) == 0  # already the loader everywhere: nothing changes, the kept files stay


def test_a_file_moved_later_takes_the_password_the_loader_urls_already_hold(tmp_path):
    from provision_hosted_store import use_loader

    folder = _folder(tmp_path)
    (folder / "worker.env").write_text(f"export MDM_DATABASE_URL='postgresql://edgar_loader:held-invented@{OLD}:5432/mdm'\n")
    assert use_loader(folder) == 1  # governance.env, not worker.env
    found = read_urls(folder)
    assert {url.split("//")[1].split(":")[1].split("@")[0] for name in ("governance.env",)
            for url in found[name].values() if url.split("//")[1].startswith("edgar_loader")} == {"held-invented"}


class _Roles(_EmptyServer):
    """An instance whose runtime roles may log in (`login`) and have sessions (`sessions`, by role)."""

    def __init__(self, login=True, sessions=None):
        super().__init__()
        self.login, self.sessions, self.asked = login, sessions or {}, None

    def execute(self, statement, *args):
        super().execute(statement, *args)
        self.asked = args[0][0] if args else None

    def fetchone(self):
        if "rolcanlogin" in self.last:
            return (self.login,) if self.login is not None else None
        if "pg_stat_activity" in self.last:
            return (self.sessions.get(self.asked, 0),)
        return None


def test_the_six_runtime_logins_become_groups_and_the_loader_is_never_touched():
    server = _Roles()
    assert retire(server, confirm=False) == [f"would retire {role}: NOLOGIN" for role in RUNTIME]
    assert not [statement for statement in server.statements if "ALTER ROLE" in statement]  # a listing changes nothing, even briefly
    server = _Roles()
    steps = retire(server, confirm=True)
    assert steps == [f"retire {role}: NOLOGIN" for role in RUNTIME]
    altered = [statement for statement in server.statements if "ALTER ROLE" in statement]
    assert altered == [f'ALTER ROLE "{role}" NOLOGIN' for role in RUNTIME]  # each runtime role, and no other
    assert "edgar_loader" not in " ".join(altered)


def test_a_session_logged_in_as_a_runtime_role_refuses_the_run_and_leaves_every_role_a_login():
    server = _Roles(sessions={"rdm_runtime": 2})
    with pytest.raises(Refused, match="rdm_runtime still has open sessions"):
        retire(server, confirm=True)
    altered = [statement for statement in server.statements if "ALTER ROLE" in statement]
    assert altered == [f'ALTER ROLE "{role}" NOLOGIN' for role in RUNTIME] + [f'ALTER ROLE "{role}" LOGIN' for role in RUNTIME]
    # made NOLOGIN first and the sessions counted after, so a login made in between cannot slip through; then put back
    with pytest.raises(Refused, match="still has open sessions"):
        retire(_Roles(sessions={"mdm_runtime": 1}), confirm=False)  # a listing says it would be refused, and changes nothing


def test_a_url_that_still_names_a_runtime_role_refuses_before_anything_changes():
    server = _Roles()
    with pytest.raises(Refused, match="still names bookkeeping_runtime, mdm_runtime: run --loader first"):
        retire(server, confirm=True, named={"mdm_runtime", "bookkeeping_runtime", "edgar_loader", "rules_governance"})
    assert not server.statements  # not even a read


def test_a_role_that_cannot_log_in_or_is_absent_is_left_alone():
    for login in (False, None):
        server = _Roles(login=login)
        steps = retire(server, confirm=True)
        assert all("cannot log in already" in step for step in steps) and len(steps) == len(RUNTIME)
        assert not [statement for statement in server.statements if "ALTER ROLE" in statement]


def test_provisioning_runs_again_after_the_retirement_once_no_url_names_a_runtime_login(tmp_path):
    from provision_hosted_store import use_loader

    folder = _folder(tmp_path)
    use_loader(folder)  # governance.env no longer names mdm_runtime or bookkeeping_runtime
    held = logins(read_urls(folder), "admin")
    assert not set(held) & set(RUNTIME)
    held["rules_governance"] = ("g-invented", {"rules"})  # the fixture folder names no Rules governance login
    provision(_EmptyServer(), held, "admin", confirm=False)  # the existing NOLOGIN groups are not asked to be logins
