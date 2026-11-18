"""A fresh hosted instance takes its logins from the stores folder's own URLs, so no password changes; every URL moves
to the new instance and the administrator's takes its new password.
Every name, address and password here is invented."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "skills/data-platform/scripts"))

from provision_hosted_store import logins, read_urls, rewrite  # noqa: E402

OLD = "old.invalid"


def _folder(tmp_path, worker_password="w-invented"):
    files = {
        "connection.env": [f"export MDM_MIGRATION_DATABASE_URL='postgresql://admin:a-old@{OLD}:5432/mdm'",
                           f"export MDM_DATABASE_URL='postgresql://mdm_runtime:m-invented@{OLD}:5432/mdm'",
                           "export MDM_APPLICATION_ROLE=mdm_runtime"],
        "worker.env": [f"export MDM_DATABASE_URL='postgresql://mdm_runtime:m-invented@{OLD}:5432/mdm'",
                       f"export BOOKKEEPING_DATABASE_URL='postgresql://bookkeeping_runtime:{worker_password}@{OLD}:5432/bookkeeping'",
                       "export BOOKKEEPING_MANIFEST_ROOT=file:///invented/manifests"],
        "governance.env": [f"export MDM_REGISTRATION_DATABASE_URL='postgresql://mdm_governance:g-invented@{OLD}:5432/mdm'",
                           f"export BOOKKEEPING_DATABASE_URL='postgresql://bookkeeping_runtime:w-invented@{OLD}:5432/bookkeeping'"],
    }
    for name, lines in files.items():
        (tmp_path / name).write_text("unset MDM_MIGRATION_DATABASE_URL\n" + "\n".join(lines) + "\n")
    return tmp_path


def test_each_login_keeps_the_password_and_databases_its_urls_hold(tmp_path):
    held = logins(read_urls(_folder(tmp_path)), "admin")
    assert held == {"mdm_runtime": ("m-invented", {"mdm"}), "bookkeeping_runtime": ("w-invented", {"bookkeeping"}),
                    "mdm_governance": ("g-invented", {"mdm"})}


def test_two_urls_giving_one_login_two_passwords_are_refused(tmp_path):
    with pytest.raises(ValueError, match="bookkeeping_runtime another password"):
        logins(read_urls(_folder(tmp_path, worker_password="other")), "admin")


def test_every_url_moves_to_the_new_instance_and_only_the_administrator_takes_a_new_password(tmp_path):
    folder = _folder(tmp_path)
    assert rewrite(folder, "new.invalid", 5432, "admin", "a-new") == 6
    urls = read_urls(folder)
    assert urls["connection.env"]["MDM_MIGRATION_DATABASE_URL"] == "postgresql://admin:a-new@new.invalid:5432/mdm"
    assert urls["worker.env"]["MDM_DATABASE_URL"] == "postgresql://mdm_runtime:m-invented@new.invalid:5432/mdm"
    text = (folder / "worker.env").read_text()
    assert OLD not in text and "BOOKKEEPING_MANIFEST_ROOT=file:///invented/manifests" in text
    assert (folder / "connection.env").read_text().startswith("unset MDM_MIGRATION_DATABASE_URL\n")
    assert (folder / "worker.env").stat().st_mode & 0o777 == 0o600


class _EmptyServer:
    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, *args):
        pass

    def fetchone(self):
        return None


def test_a_group_that_is_also_a_login_is_made_once_as_the_login():
    from provision_hosted_store import provision

    held = {"rules_agent": ("r-invented", {"rules"}), "rules_governance": ("g-invented", {"rules"}),
            "bookkeeping_runtime": ("w-invented", {"bookkeeping"})}
    steps = provision(_EmptyServer(), held, "admin", confirm=False)
    assert "create login rules_agent" in steps and "create group rules_agent" not in steps
    assert "create group bookkeeping_control" in steps and "put rules_governance in rules_agent" in steps
